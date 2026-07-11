"""
The generation layer. Every function has two paths:
  - MOCK  (settings.use_mocks=True):  runs now, no key, returns real renderable
          data so you can demo the full loop today.
  - REAL  (settings.use_mocks=False): google-genai calls. Structure is correct;
          confirm model ids + response fields against the SDK on the day.

Keeping both behind one function means the router, main.py, and the frontend
never change when you flip the switch.
"""
from __future__ import annotations

import asyncio
import base64
import html
import logging
import random
from typing import Optional

log = logging.getLogger("voicecanvas.pipeline")

from .config import settings
from .prompts import (
    INTENT_SYSTEM_PROMPT,
    intent_user_turn,
    nb2_image_prompt,
    nb2_edit_prompt,
    omni_motion_prompt,
    omni_chain_prompt,
    omni_wardrobe_prompt,
    tts_prompt,
)
from .schemas import Intent

# Lazily created google-genai client (only when real mode is on).
_client = None

_VIDEO_TERMS = ("video", "clip", "animation", "animated", "reel", "cinematic")

# Words/patterns that signal HIGH energy (user is emphatic)
_HIGH_ENERGY = ("really", "very", "super", "extremely", "so much", "flashier",
                "bolder", "louder", "bigger", "more intense", "dramatic", "epic",
                "maximum", "insane", "crazy", "wild", "!!")
_LOW_ENERGY  = ("subtle", "minimal", "calm", "quiet", "soft", "gentle",
                "simple", "clean", "understated", "muted")


def _detect_energy(text: str) -> str:
    """Infer emphasis from transcript text — caps words, exclamation marks,
    intensifier words. Works with any STT provider including Deepgram."""
    t = text.lower()
    # ALL-CAPS words in original text = shouted/stressed
    caps_words = sum(1 for w in text.split() if w.isupper() and len(w) > 1)
    exclamations = text.count("!")
    high_words = sum(1 for w in _HIGH_ENERGY if w in t)
    low_words  = sum(1 for w in _LOW_ENERGY  if w in t)
    score = caps_words * 2 + exclamations * 2 + high_words - low_words
    if score >= 2:
        return "high"
    if score <= -1 or low_words > 0:
        return "low"
    return "medium"


def _genai_client():
    global _client
    if _client is None:
        from google import genai  # google-genai unified SDK

        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


# =============================================================================
# INTENT  (Gemini Live / structured output)
# =============================================================================
async def parse_intent(text: str, selected_id: Optional[str]) -> Intent:
    if settings.use_mocks:
        return _mock_intent(text, selected_id)

    # --- REAL: structured output via response_schema -------------------------
    # NOTE: In production the audio is streamed to the Live API and this parse
    # happens continuously. For the router we use text->structured-JSON, which
    # is the same schema the Live session emits. Wire the live audio session in
    # voice/ on the frontend; this stays the single source of truth for shape.
    client = _genai_client()
    try:
        resp = await asyncio.to_thread(
            client.models.generate_content,
            model=settings.model_intent,  # NOT model_live — live model is audio-only
            contents=intent_user_turn(text, selected_id),
            config={
                "system_instruction": INTENT_SYSTEM_PROMPT.format(selected_id=selected_id or "none"),
                "response_mime_type": "application/json",
                "response_schema": Intent,
            },
        )
        try:
            intent = Intent.model_validate_json(resp.text)
        except Exception:
            intent = Intent(action="unknown", confidence=0.0)
        return intent.model_copy(update={"energy": _detect_energy(text)})
    except Exception:
        # Intent keeps a heuristic fallback (it stays usable), but LOG so a real
        # API failure is visible instead of silently looking like it "worked".
        log.exception("intent model failed; using heuristic parser")
        return _mock_intent(text, selected_id)


# =============================================================================
# NB2 LITE  (image anchor)
# =============================================================================
async def generate_image(intent: Intent, prior_prompt: Optional[str] = None) -> str:
    """Returns an image src. prior_prompt signals an edit — keeps product identity,
    changes only what was asked (lighting, copy, background)."""
    if settings.use_mocks:
        await asyncio.sleep(random.uniform(0.5, 1.2))
        return _mock_ad_svg(intent)

    client = _genai_client()
    try:
        if prior_prompt:
            prompt = nb2_edit_prompt(intent, prior_prompt)
            model = settings.model_edit
        else:
            prompt = nb2_image_prompt(intent)
            model = settings.model_image
        resp = await asyncio.to_thread(
            client.models.generate_content,
            model=model,
            contents=prompt,
            config={"response_modalities": ["IMAGE"]},
        )
        return _first_image(resp)
    except Exception:
        # Surface the REAL error to the UI instead of silently faking a mock —
        # a silent fallback is what made real failures look like "mock mode".
        log.exception("NB2 image generation failed (model=%s)", model)
        raise


# =============================================================================
# OMNI FLASH  (video, + final-frame chaining)
# =============================================================================
async def generate_video(intent: Intent, reference_src: str, chain_from: Optional[str] = None) -> str:
    if settings.use_mocks:
        await asyncio.sleep(random.uniform(1.5, 3.0))
        return _mock_video_placeholder()

    # Omni Flash video goes through the Interactions API (client.interactions),
    # NOT generate_content. Chaining feeds the previous clip's final frame in as
    # the reference so the two clips read as one continuous take.
    prompt = (omni_chain_prompt(intent.motion or "continue the scene")
              if chain_from else omni_motion_prompt(intent))
    return await _omni_video(prompt, reference_src)


async def _omni_video(prompt: str, image_src: str) -> str:
    """Create a background Omni Flash interaction, poll to completion, return the
    generated clip as a data-uri. Video gen takes ~30s — pre-cache for the demo."""
    from google.genai._gaos.types.interactions.createmodelinteraction import CreateModelInteraction
    from google.genai._gaos.types.interactions.imagecontent import ImageContent
    from google.genai._gaos.types.interactions.textcontent import TextContent

    client = _genai_client()
    header, b64 = image_src.split(",", 1)
    mime = header.split(";")[0].removeprefix("data:")
    body = CreateModelInteraction(
        model=settings.model_video,
        input=[TextContent(text=prompt), ImageContent(data=b64, mime_type=mime)],
        background=True,
    )
    created = await asyncio.to_thread(
        lambda: client.interactions.create(request={"body": body}))
    iid = created.id
    log.info("Omni Flash interaction %s started", iid)

    for _ in range(40):  # ~4 min ceiling; poll every 6s
        await asyncio.sleep(6)
        g = await asyncio.to_thread(lambda: client.interactions.get(iid))
        status = getattr(g, "status", None)
        if status == "completed":
            ov = getattr(g, "output_video", None)
            if ov and getattr(ov, "data", None):
                return f"data:{ov.mime_type or 'video/mp4'};base64,{ov.data}"
            raise RuntimeError("Omni Flash completed but returned no video")
        if status in ("failed", "cancelled", "error"):
            raise RuntimeError(f"Omni Flash interaction {status}")
    raise RuntimeError("Omni Flash timed out (>4 min)")


async def extract_final_frame(video_src: str) -> str:
    """For A->B->C chaining: last frame of clip N == input of clip N+1."""
    if settings.use_mocks:
        return _mock_frame_svg()
    # REAL: grab the terminal frame with ffmpeg, return as a data-uri PNG.
    return await asyncio.to_thread(_ffmpeg_last_frame, video_src)


# =============================================================================
# WARDROBE  (Feature 3 — avatar + apparel swap)
# =============================================================================
async def generate_avatar() -> str:
    """A base figure to dress. Mock: a simple avatar SVG. Real: NB2 Lite renders
    a neutral full-body model shot the wardrobe edits then build on."""
    if settings.use_mocks:
        await asyncio.sleep(0.6)
        return _mock_avatar_svg("plain grey tee, neutral studio")
    client = _genai_client()
    try:
        # Photorealistic full-body model shot to dress.
        prompt = ("Photorealistic full-body photograph of a fashion model standing in "
                  "a neutral pose, plain fitted outfit, seamless studio backdrop, soft "
                  "even lighting, sharp focus, 9:16 vertical. Realistic skin and fabric.")
        resp = await asyncio.to_thread(
            client.models.generate_content, model=settings.model_image,
            contents=prompt, config={"response_modalities": ["IMAGE"]})
        return _first_image(resp)
    except Exception:
        log.exception("avatar generation failed (model=%s)", settings.model_image)
        raise


async def generate_wardrobe(intent: Intent, reference_src: str) -> str:
    """Photorealistic virtual try-on. Edits the reference PHOTO in place, keeping
    the person's identity, pose, body shape, and lighting; changes only the
    garment (folds, drape, shadows follow the new clothing). This is an image
    EDIT on a real photo — not a drawing or animation."""
    if settings.use_mocks:
        await asyncio.sleep(random.uniform(0.8, 1.6))
        return _mock_avatar_svg(intent.wardrobe or "new outfit")
    client = _genai_client()
    try:
        # model_edit accepts the input photo and returns a photorealistic edited image.
        resp = await asyncio.to_thread(
            client.models.generate_content, model=settings.model_edit,
            contents=[omni_wardrobe_prompt(intent), _as_part(reference_src)],
            config={"response_modalities": ["IMAGE"]})
        return _first_image(resp)
    except Exception:
        log.exception("wardrobe try-on failed (model=%s)", settings.model_edit)
        raise


# =============================================================================
# TTS
# =============================================================================
async def synthesize_voice(script: str, tone: str = "deep, cinematic narrator") -> str:
    # ElevenLabs takes priority for TTS if a key is present — this works even
    # while the generative models are still mocked, so you can test voice early.
    if settings.elevenlabs_api_key and script:
        return await asyncio.to_thread(_elevenlabs_tts, script)
    if settings.use_mocks:
        await asyncio.sleep(0.4)
        return ""  # frontend falls back to browser SpeechSynthesis in mock mode
    client = _genai_client()
    try:
        resp = await asyncio.to_thread(
            client.models.generate_content,
            model=settings.model_tts,
            contents=tts_prompt(script, tone),
        )
        return _extract_audio_data_uri(resp)
    except Exception:
        return ""


# =============================================================================
# LIVE TRANSLATE
# =============================================================================
_MOCK_DICT = {
    "hi": {"Hydrate Smart": "स्मार्ट हाइड्रेशन", "Brewed in Bengaluru": "बेंगलुरु में बना",
            "The city never sleeps": "शहर कभी नहीं सोता"},
    "kn": {"Hydrate Smart": "ಸ್ಮಾರ್ಟ್ ಹೈಡ್ರೇಟ್", "Brewed in Bengaluru": "ಬೆಂಗಳೂರಿನಲ್ಲಿ ತಯಾರಿಸಲಾಗಿದೆ",
            "The city never sleeps": "ನಗರ ಎಂದೂ ನಿದ್ರಿಸುವುದಿಲ್ಲ"},
    "ta": {"Hydrate Smart": "ஸ்மார்ட் ஹைட்ரேட்", "Brewed in Bengaluru": "பெங்களூருவில் தயாரிக்கப்பட்டது",
            "The city never sleeps": "நகரம் ஒருபோதும் தூங்குவதில்லை"},
}


async def translate_copy(text: str, language: str) -> str:
    if settings.use_mocks:
        await asyncio.sleep(0.3)
        return _MOCK_DICT.get(language, {}).get(text, f"[{language}] {text}")
    client = _genai_client()
    try:
        resp = await asyncio.to_thread(
            client.models.generate_content,
            model=settings.model_translate,
            contents=f"Translate to {language}. Return ONLY the translation:\n{text}",
        )
        return resp.text.strip()
    except Exception:
        return _MOCK_DICT.get(language, {}).get(text, f"[{language}] {text}")


# =============================================================================
# ---- mock helpers (render real, visible assets with zero credentials) -------
# =============================================================================
_PALETTES = [
    ("#0f172a", "#38bdf8", "#f8fafc"), ("#1a120b", "#e0a458", "#fff7ec"),
    ("#12100e", "#ff3b6b", "#ffffff"), ("#0b132b", "#5bc0be", "#ffffff"),
]


def _mock_intent(text: str, selected_id: Optional[str]) -> Intent:
    """Tiny heuristic parser so the loop is demonstrable pre-event."""
    t = text.lower()
    interrupt = any(w in t for w in ("wait", "no,", "actually", "stop", "change"))
    aspect = "1:1" if "post" in t or "square" in t else "16:9" if "banner" in t or "youtube" in t else "9:16"

    if any(w in t for w in ("wear", "put on", "t-shirt", "tshirt", "shirt", "outfit",
                            "cargo", "jacket", "hoodie", "dress ", "wardrobe", "corduroy")):
        return Intent(action="wardrobe", target_asset_id=selected_id, wardrobe=text,
                      interrupt=interrupt)
    if any(w in t for w in ("kannada", "hindi", "tamil", "translate")):
        lang = "kn" if "kannada" in t else "hi" if "hindi" in t else "ta" if "tamil" in t else "hi"
        return Intent(action="localize", target_asset_id=selected_id, language=lang)

    animate_cues = ("video", "clip", "animate", "animated", "animation", "cinematic",
                    "reel", "turn that", "into a clip", "trailer", "panning", " pan ",
                    "zoom", "rain", "promo", "short film", "motion")
    continue_cues = ("now ", "then ", "next ", " enters", " walks", " runs",
                     " drives", " opens", "he ", "she ")
    energy = _detect_energy(text)
    if any(w in t for w in animate_cues) or (
        selected_id and any(w in t for w in continue_cues)
    ):
        return Intent(action="animate", target_asset_id=selected_id,
                      motion=text, interrupt=interrupt, energy=energy,
                      product=_guess_product(text), background=_guess_bg(text),
                      copy_text=_between_quotes(text), style=_guess_style(text),
                      aspect=aspect)

    action = "edit" if (selected_id and interrupt) else "create"
    return Intent(action=action, target_asset_id=selected_id if action == "edit" else None,
                  product=_guess_product(text), background=_guess_bg(text),
                  copy_text=_between_quotes(text), style=_guess_style(text),
                  aspect=aspect, interrupt=interrupt, energy=energy)


def _between_quotes(s: str) -> Optional[str]:
    import re
    m = re.search(r"['\"]([^'\"]{1,40})['\"]", s)
    if m:
        return m.group(1)
    m = re.search(r"\b(?:says?|text|headline|copy)\b[:\s]+(.{2,40})", s, re.I)
    return m.group(1).strip(" .") if m else None


def _guess_product(s: str) -> str:
    for kw in ("coffee shop", "café", "cafe", "cold brew", "coffee", "water bottle",
               "bottle", "sneaker", "perfume", "phone", "watch"):
        if kw in s.lower():
            return kw
    return "the product"


def _guess_bg(s: str) -> Optional[str]:
    for kw in ("bangalore", "bengaluru", "mumbai street", "indiranagar", "cafe",
               "wooden table", "beach", "neon", "studio"):
        if kw in s.lower():
            return kw
    return None


def _guess_style(s: str) -> Optional[str]:
    for kw in ("morning sun", "night", "bright", "moody", "warm", "flashier", "minimal"):
        if kw in s.lower():
            return kw
    return None


def _mock_ad_svg(intent: Intent) -> str:
    w, h = {"9:16": (540, 960), "1:1": (720, 720), "16:9": (960, 540)}.get(intent.aspect, (540, 960))
    bg, accent, fg = random.choice(_PALETTES)
    copy = html.escape(intent.copy_text or "")
    product = html.escape((intent.product or "product").title())
    bgline = html.escape((intent.background or "studio").title())
    svg = f"""<svg xmlns='http://www.w3.org/2000/svg' width='{w}' height='{h}' viewBox='0 0 {w} {h}'>
      <defs><radialGradient id='g' cx='50%' cy='35%' r='75%'>
        <stop offset='0%' stop-color='{accent}' stop-opacity='0.35'/>
        <stop offset='100%' stop-color='{bg}'/></radialGradient></defs>
      <rect width='{w}' height='{h}' fill='url(#g)'/>
      <circle cx='{w/2}' cy='{h*0.4}' r='{w*0.22}' fill='{accent}' opacity='0.9'/>
      <text x='{w/2}' y='{h*0.41}' font-family='Inter,Arial' font-size='{w*0.05}'
        fill='{bg}' text-anchor='middle' font-weight='700'>{product}</text>
      <text x='{w/2}' y='{h*0.72}' font-family='Inter,Arial' font-size='{w*0.085}'
        fill='{fg}' text-anchor='middle' font-weight='800'>{copy}</text>
      <text x='{w/2}' y='{h*0.8}' font-family='Inter,Arial' font-size='{w*0.032}'
        fill='{fg}' opacity='0.7' text-anchor='middle'>{bgline}</text>
      <text x='{w/2}' y='{h*0.95}' font-family='Inter,Arial' font-size='{w*0.026}'
        fill='{accent}' text-anchor='middle'>NB2 Lite · mock render</text>
    </svg>"""
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


def _mock_avatar_svg(outfit: str) -> str:
    """A simple dressed figure so the wardrobe flow is demonstrable pre-event."""
    w, h = 540, 960
    bg, accent, fg = random.choice(_PALETTES)
    outfit_txt = html.escape(outfit)
    svg = f"""<svg xmlns='http://www.w3.org/2000/svg' width='{w}' height='{h}' viewBox='0 0 {w} {h}'>
      <rect width='{w}' height='{h}' fill='{bg}'/>
      <rect x='40' y='40' width='{w-80}' height='{h-80}' rx='24' fill='none'
        stroke='{accent}' stroke-opacity='0.3'/>
      <circle cx='{w/2}' cy='{h*0.22}' r='{w*0.11}' fill='#e8c9a0'/>
      <path d='M {w*0.32} {h*0.34} Q {w/2} {h*0.30} {w*0.68} {h*0.34}
        L {w*0.72} {h*0.66} L {w*0.28} {h*0.66} Z' fill='{accent}'/>
      <rect x='{w*0.34}' y='{h*0.66}' width='{w*0.13}' height='{h*0.24}' fill='{fg}' opacity='0.85'/>
      <rect x='{w*0.53}' y='{h*0.66}' width='{w*0.13}' height='{h*0.24}' fill='{fg}' opacity='0.85'/>
      <text x='{w/2}' y='{h*0.94}' font-family='Inter,Arial' font-size='{w*0.038}'
        fill='{fg}' text-anchor='middle' font-weight='700'>{outfit_txt}</text>
      <text x='{w/2}' y='{h*0.975}' font-family='Inter,Arial' font-size='{w*0.024}'
        fill='{accent}' text-anchor='middle'>Omni Flash try-on · mock</text>
    </svg>"""
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


def _mock_frame_svg() -> str:
    return _mock_ad_svg(Intent(product="scene", copy_text="", aspect="16:9"))


def _mock_video_placeholder() -> str:
    # Tiny valid data-uri poster; frontend shows an animated 'rendering' shimmer
    # over it. Swap for a real cached fallback.mp4 before the event.
    return "MOCK_VIDEO"


# ---- real-mode extraction stubs (fill against SDK on the day) ---------------
def _as_part(src: str):
    from google.genai import types
    if src.startswith("data:"):
        header, b64 = src.split(",", 1)
        mime = header.split(";")[0].removeprefix("data:")
        return types.Part.from_bytes(data=base64.b64decode(b64), mime_type=mime)
    return src


def _elevenlabs_tts(script: str) -> str:
    """Real ElevenLabs call -> audio data-uri. Stable public API (safe to wire
    now). Key stays server-side; the browser only ever receives the audio."""
    import json
    import urllib.request

    voice = settings.elevenlabs_voice_id or "21m00Tcm4TlvDq8ikWAM"  # default preset
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
        data=json.dumps({"text": script, "model_id": "eleven_turbo_v2_5"}).encode(),
        headers={
            "xi-api-key": settings.elevenlabs_api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        audio = r.read()
    return "data:audio/mpeg;base64," + base64.b64encode(audio).decode()


def _first_image(resp) -> str:
    """Pull the first inline image part from a generate_content response -> data-uri.
    CONFIRM the part path against the SDK on the day (inline_data is typical)."""
    for part in resp.candidates[0].content.parts:
        blob = getattr(part, "inline_data", None)
        if blob and blob.data:
            return f"data:{blob.mime_type};base64," + base64.b64encode(blob.data).decode()
    raise RuntimeError("no image part in response")


def _extract_video_url(resp) -> str:
    """Omni Flash -> playable src. Preview APIs return video either inline (bytes)
    or as a file handle/URI. Handle both; CONFIRM field names on the day."""
    for part in resp.candidates[0].content.parts:
        blob = getattr(part, "inline_data", None)
        if blob and blob.data and (blob.mime_type or "").startswith("video"):
            return f"data:{blob.mime_type};base64," + base64.b64encode(blob.data).decode()
        fd = getattr(part, "file_data", None)
        if fd and getattr(fd, "file_uri", None):
            return fd.file_uri
    raise RuntimeError("no video part in Omni Flash response")


def _extract_audio_data_uri(resp) -> str:
    """Flash TTS -> audio data-uri (typically PCM/L16 or mp3 inline bytes)."""
    for part in resp.candidates[0].content.parts:
        blob = getattr(part, "inline_data", None)
        if blob and blob.data and (blob.mime_type or "").startswith("audio"):
            return f"data:{blob.mime_type};base64," + base64.b64encode(blob.data).decode()
    raise RuntimeError("no audio part in Flash TTS response")


def _ffmpeg_last_frame(video_src: str) -> str:
    """Grab the final frame of a clip for A->B->C chaining. Works on a file path
    or an http(s) url; for a data-uri, write bytes to a temp file first."""
    import subprocess
    import tempfile

    src = video_src
    tmp_in = None
    if video_src.startswith("data:"):
        b64 = video_src.split(",", 1)[1]
        tmp_in = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp_in.write(base64.b64decode(b64))
        tmp_in.close()
        src = tmp_in.name
    out = tempfile.NamedTemporaryFile(suffix=".png", delete=False).name
    # -sseof -0.1 seeks near the end; -update grabs the last decoded frame
    subprocess.run(["ffmpeg", "-y", "-sseof", "-0.1", "-i", src,
                    "-update", "1", "-q:v", "2", out],
                   check=True, capture_output=True)
    with open(out, "rb") as f:
        data = f.read()
    return "data:image/png;base64," + base64.b64encode(data).decode()
