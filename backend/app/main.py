"""
FastAPI relay + orchestrator.

Design choices that matter for the demo:
- The relay (not a direct browser->Gemini socket) is deliberate for hackathon
  reliability. One extra ~50ms hop, but keys stay server-side and there is a
  SINGLE place to add fallbacks. Direct-socket is documented as 'future work'.
- Every job is cancellable. An 'interrupt' (barge-in) cancels the in-flight
  asyncio task and starts the new one — this is what makes interruption REAL
  rather than cosmetic.
- Optimistic UI: we emit a 'placeholder' the instant intent is parsed, before
  the model returns, so perceived latency is near-zero.
"""
from __future__ import annotations

import asyncio
import contextlib
import uuid
from typing import Dict, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from . import pipeline
from .config import settings
from .prompts import nb2_image_prompt as nb2_image_prompt_str
from .schemas import Intent

app = FastAPI(title="VoiceCanvas AI relay")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


@app.get("/healthz")
async def healthz():
    return {"ok": True, "mock_mode": settings.use_mocks,
            "models": {"image": settings.model_image, "video": settings.model_video}}


@app.get("/live-token")
async def live_token():
    """Gemini Live ephemeral token. The auth_tokens API is not yet stable in the
    public SDK — return mock so the frontend falls through to Deepgram (which is
    wired and working). Swap this out when the Live token API is confirmed."""
    return {"mode": "mock", "token": None, "model": settings.model_live}


@app.get("/stt-status")
async def stt_status():
    """Tells the frontend whether to use the Deepgram proxy for STT. The key
    itself never leaves the server — audio is relayed through /ws-stt below."""
    return {"provider": "deepgram" if settings.deepgram_api_key else None}


@app.websocket("/ws-stt")
async def ws_stt(browser: WebSocket):
    """Deepgram STT proxy. Browser streams 16kHz PCM here; we forward it to
    Deepgram over a server-side socket (key stays here, passed via subprotocol
    which is version-stable), and relay transcripts back. This works with a
    plain Deepgram API key — no token-grant scope required."""
    await browser.accept()
    if not settings.deepgram_api_key:
        await browser.close()
        return
    import websockets

    dg_url = (
        "wss://api.deepgram.com/v1/listen?model=nova-2&language=en-IN&"
        "encoding=linear16&sample_rate=16000&interim_results=true&smart_format=true"
    )
    try:
        dg = await websockets.connect(
            dg_url, subprotocols=["token", settings.deepgram_api_key]
        )
    except Exception as e:
        await browser.send_json({"error": f"deepgram connect failed: {e}"})
        await browser.close()
        return

    async def pump_audio():
        try:
            while True:
                chunk = await browser.receive_bytes()
                await dg.send(chunk)
        except Exception:
            with contextlib.suppress(Exception):
                await dg.close()

    async def pump_transcripts():
        try:
            async for msg in dg:
                await browser.send_text(msg if isinstance(msg, str) else msg.decode())
        except Exception:
            pass

    with contextlib.suppress(Exception):
        await asyncio.gather(pump_audio(), pump_transcripts())


class Session:
    """Per-connection state: selected asset + what each asset was built from."""

    def __init__(self, ws: WebSocket):
        self.ws = ws
        self.selected_id: Optional[str] = None
        self.assets: Dict[str, dict] = {}         # asset_id -> {intent, src, prompt}
        self.job: Optional[asyncio.Task] = None    # the single in-flight generation

    async def send(self, **msg):
        with contextlib.suppress(Exception):
            await self.ws.send_json(msg)

    def cancel_inflight(self):
        if self.job and not self.job.done():
            self.job.cancel()


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    s = Session(ws)
    await s.send(type="status", stage="ready", message="Relay connected",
                 mock_mode=settings.use_mocks)
    try:
        while True:
            data = await ws.receive_json()
            kind = data.get("type")

            if kind == "select_asset":
                s.selected_id = data.get("asset_id")

            elif kind == "upload_avatar":
                # Dress a REAL creator photo: store it as the selected avatar so
                # the next "put on ..." command does a photorealistic try-on on it.
                aid = f"av_{uuid.uuid4().hex[:8]}"
                s.assets[aid] = {"intent": Intent(action="wardrobe"),
                                 "src": data.get("src"), "kind": "avatar"}
                s.selected_id = aid
                await s.send(type="asset", asset_id=aid, src=data.get("src"),
                             aspect="9:16", overlay={"text": "", "lang": "en"})
                await s.send(type="status", stage="done",
                             message="Photo loaded — say what to wear")

            elif kind == "interrupt":
                s.cancel_inflight()
                await s.send(type="status", stage="interrupted",
                             message="Cancelled — go ahead")

            elif kind == "utterance" and data.get("final", True):
                # a new final utterance always supersedes any running job
                s.cancel_inflight()
                s.job = asyncio.create_task(handle_utterance(s, data.get("text", "")))
    except WebSocketDisconnect:
        s.cancel_inflight()


async def handle_utterance(s: Session, text: str):
    try:
        # 1. INTENT (the brain) --------------------------------------------
        await s.send(type="status", stage="thinking",
                     message="Parsing intent…", budget_ms=settings.budget_intent_ms)
        intent = await pipeline.parse_intent(text, s.selected_id)
        await s.send(type="intent", intent=intent.model_dump(), transcript=text)

        if intent.interrupt:
            await s.send(type="status", stage="interrupted", message="Redirecting…")

        # 2. ROUTE ----------------------------------------------------------
        if intent.action in ("create", "edit"):
            await route_image(s, intent)
        elif intent.action == "wardrobe":
            await route_wardrobe(s, intent)
        elif intent.action == "animate":
            await route_video(s, intent)
        elif intent.action == "localize":
            await route_localize(s, intent)
        else:
            await s.send(type="status", stage="idle",
                         message="Didn't catch that — try again")
    except asyncio.CancelledError:
        await s.send(type="status", stage="cancelled", message="Superseded")
        raise
    except Exception as e:  # never let one bad turn kill the socket
        await s.send(type="error", message=str(e))


async def route_image(s: Session, intent: Intent):
    asset_id = intent.target_asset_id if intent.action == "edit" else f"a_{uuid.uuid4().hex[:8]}"
    await s.send(type="placeholder", asset_id=asset_id, aspect=intent.aspect)
    await s.send(type="status", stage="image", message="Rendering ad (NB2 Lite)…",
                 budget_ms=settings.budget_image_ms)
    # For edits, pass the original prompt so the model keeps product identity.
    prior = s.assets.get(asset_id, {}).get("prompt") if intent.action == "edit" else None
    src = await pipeline.generate_image(intent, prior_prompt=prior)
    prompt_used = prior or nb2_image_prompt_str(intent)
    s.assets[asset_id] = {"intent": intent, "src": src, "prompt": prompt_used}
    s.selected_id = asset_id
    await s.send(type="asset", asset_id=asset_id, src=src, aspect=intent.aspect,
                 overlay=_overlay(intent))
    await s.send(type="status", stage="done", message="Ad ready")


async def route_video(s: Session, intent: Intent):
    asset_id = intent.target_asset_id or s.selected_id

    # No existing asset? Auto-create the image anchor first, then animate it.
    # This makes "create a video campaign for X" work in one command.
    if not asset_id or asset_id not in s.assets:
        asset_id = f"a_{uuid.uuid4().hex[:8]}"
        await s.send(type="placeholder", asset_id=asset_id, aspect=intent.aspect)
        await s.send(type="status", stage="image",
                     message="Rendering anchor frame (NB2 Lite)…",
                     budget_ms=settings.budget_image_ms)
        src = await pipeline.generate_image(intent)
        s.assets[asset_id] = {"intent": intent, "src": src,
                               "prompt": nb2_image_prompt_str(intent)}
        s.selected_id = asset_id
        await s.send(type="asset", asset_id=asset_id, src=src,
                     aspect=intent.aspect, overlay=_overlay(intent))

    asset = s.assets[asset_id]

    # A->B->C stateful chaining: if this asset ALREADY has a clip, the user is
    # asking for the NEXT beat. We feed the previous clip's final frame in as the
    # input so the two clips read as one continuous take (no visible cut).
    chaining = bool(asset.get("video"))
    if chaining:
        await s.send(type="status", stage="video",
                     message="Extracting final frame → chaining next scene…",
                     budget_ms=settings.budget_video_ms)
        ref = await pipeline.extract_final_frame(asset["video"])
        video = await pipeline.generate_video(intent, ref, chain_from=asset["video"])
        beat = intent.motion or "next scene"
        await s.send(type="status", stage="chained",
                     message=f"Continuous cut extended · beat: {beat[:40]}")
    else:
        await s.send(type="status", stage="video",
                     message="Animating (Omni Flash)…", budget_ms=settings.budget_video_ms)
        ref = asset["src"]
        video = await pipeline.generate_video(intent, ref)

    asset["video"] = video
    await s.send(type="video", asset_id=asset_id, src=video,
                 poster=asset["src"], overlay=_overlay(asset["intent"]),
                 chained=chaining)

    # voiceover if a spoken line was requested
    script = _quote_in(intent.motion or "")
    if script:
        audio = await pipeline.synthesize_voice(script)
        await s.send(type="audio", asset_id=asset_id, src=audio, script=script)
    await s.send(type="status", stage="done",
                 message="Continuous clip extended" if chaining else "Clip ready")


async def route_wardrobe(s: Session, intent: Intent):
    """Feature 3. Loads/uses an avatar and swaps apparel on it via Omni Flash.
    If no avatar is on the canvas yet, we spin up a base figure first, then dress
    it — so a single 'put on a black oversized tee' command just works."""
    asset_id = intent.target_asset_id or s.selected_id
    base = s.assets.get(asset_id) if asset_id else None

    if not base or base.get("kind") != "avatar":
        # create a fresh avatar to dress
        asset_id = f"av_{uuid.uuid4().hex[:8]}"
        await s.send(type="placeholder", asset_id=asset_id, aspect="9:16")
        await s.send(type="status", stage="avatar", message="Loading avatar…")
        base_src = await pipeline.generate_avatar()
        s.assets[asset_id] = {"intent": intent, "src": base_src, "kind": "avatar"}

    await s.send(type="status", stage="wardrobe",
                 message="Styling (Omni Flash try-on)…", budget_ms=settings.budget_image_ms)
    src = await pipeline.generate_wardrobe(intent, s.assets[asset_id]["src"])
    s.assets[asset_id]["src"] = src
    s.assets[asset_id]["intent"] = intent
    s.selected_id = asset_id
    await s.send(type="asset", asset_id=asset_id, src=src, aspect="9:16",
                 overlay={"text": intent.wardrobe or "", "lang": "en", "aspect": "9:16"})
    await s.send(type="status", stage="done", message="Look applied")


async def route_localize(s: Session, intent: Intent):
    asset_id = intent.target_asset_id or s.selected_id
    if not asset_id or asset_id not in s.assets:
        await s.send(type="error", message="No campaign selected to localize")
        return
    base = s.assets[asset_id]["intent"]
    lang = intent.language or "hi"
    translated = await pipeline.translate_copy(base.copy_text or "", lang)
    # KEY TRICK: localization is a text-OVERLAY swap, not a re-render. Instant,
    # spelling-guaranteed, and it keeps the layout identical.
    await s.send(type="overlay_update", asset_id=asset_id,
                 overlay={"text": translated, "lang": lang})
    await s.send(type="status", stage="done", message=f"Localized → {lang}")


def _overlay(intent: Intent) -> dict:
    return {"text": intent.copy_text or "", "lang": intent.language or "en",
            "aspect": intent.aspect}


def _quote_in(s: str) -> str:
    import re
    m = re.search(r"['\"]([^'\"]{2,80})['\"]", s)
    return m.group(1) if m else ""


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)
