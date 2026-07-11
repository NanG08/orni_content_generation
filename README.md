# VoiceCanvas AI

Voice-driven, real-time multimodal **ad production canvas**. Speak → a crisp-text
ad renders → interrupt to edit it → animate it → localize it into Indian
languages. Built for the Google DeepMind Bangalore Hackathon (PS3 + PS4 + PS1).

> **The whole loop runs today with NO Google credentials** (mock mode). On the
> day you flip one flag and paste your key. That means you spend the 6 hours on
> the *real APIs and the pitch*, not on scaffolding.

---

## Run it now (mock mode, ~2 min)

**Backend** (Python 3.10+):
```bash
cd backend
python -m venv .venv && . .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # USE_MOCKS stays true; no key needed
python -m app.main            # relay on http://127.0.0.1:8000
```

**Frontend** (Node 18+), in a second terminal:
```bash
cd frontend
npm install
npm run dev                    # open http://localhost:5173 in CHROME
```

Click **🎙 Hold to talk** (Chrome asks for mic permission) and say:
> "Instagram story for a cold brew coffee, rustic café table, headline 'Brewed in Bengaluru'."

Then: *"Wait, make it bright morning sun"* (barge-in edit) →
*"Turn that into a cinematic clip"* → *"Translate into Kannada."*

No mic? Type commands in the box. Voice uses the browser Web Speech API in mock
mode, so the full pipeline is demonstrable before kickoff.

---

## The architecture in one screen

```
Browser (React + Canvas)                    FastAPI relay              Google AI
──────────────────────────                  ─────────────              ─────────
🎙 voice ─Web Speech / Gemini Live─►  utterance ─► parse_intent ──────► gemini-live   (structured JSON)
   text overlay (crisp, swappable)                   │ route
   canvas render ◄── asset/video ◄── generate_image ─┼──────────────► NB2 Lite image
                                     generate_video ──┼──────────────► Omni Flash video
                                     translate_copy ──┼──────────────► Live Translate
                                     synth_voice ─────┴──────────────► Flash TTS
```

- **Intent router** (`app/pipeline.parse_intent` + `app/prompts.INTENT_SYSTEM_PROMPT`)
  is the brain: self-correction, create-vs-edit routing, interrupt flag.
- **Typography-first**: NB2 Lite renders the anchor frame; the headline is *also*
  drawn as a **client-side overlay** (`components/TextOverlay.jsx`) so text can
  never garble and localization is an instant swap, not a re-render.
- **Interruption is real**: each generation is a cancellable asyncio task
  (`app/main.py`); a barge-in cancels the in-flight job.
- **Optimistic UI**: a placeholder/shimmer paints the instant intent is parsed.

---

## Flip to real Gemini (do this in the first hour on the day)

1. `backend/.env`: set `USE_MOCKS=false`, paste `GEMINI_API_KEY`.
2. **Confirm every model id** in `.env` against the organizer docs / Discord.
   A wrong model string is the #1 first-hour blocker.
3. `pip install google-genai` (already in requirements).
4. Fill the three clearly-marked `NotImplementedError` stubs in `app/pipeline.py`
   (`_extract_video_url`, `_extract_audio_data_uri`, final-frame extraction) once
   you see the real response shapes — everything else is already wired.
5. Swap `frontend/src/lib/voice.js` `startBrowserVoice` for a Gemini Live audio
   session. The app only consumes `onTranscript`/`onInterrupt`, so nothing else
   changes.

Everything reads model ids from `app/config.py` — no model name is hardcoded
anywhere else.

---

## Team split (4 people, define the contract first)

`app/schemas.py` is the shared contract. Agree on it at 10:30, then parallelize:

| Owner | Area | Files |
|---|---|---|
| A — Orchestration | relay, router, cancellation, fallbacks | `app/main.py`, `app/config.py` |
| B — Voice/Live | Gemini Live audio session, interrupt, intent tuning | `lib/voice.js`, `app/prompts.py` (intent), `app/pipeline.parse_intent` |
| C — Frontend | canvas, overlay, optimistic UI, localization swap | `src/**` |
| D — GenMedia | NB2 Lite + Omni Flash + TTS prompts, chaining, fallbacks | `app/prompts.py` (media), `app/pipeline.py` (generate_*) |

Everyone develops against mock mode; one integration push ~2h before submission.

---

## Reliability plan (this is how you win Live Demo — 25%)

- **Spine that always works:** voice → NB2 ad → interrupt/edit → localize. All
  fast, all reliable. If everything else fails, this alone is a full demo.
- **Omni Flash video** is the *finale*, not the spine. Keep a pre-rendered
  `fallback.mp4` and disclose it if the live call stalls.
- **Chaining (A→B→C):** show ONE continuation live; pre-render the long
  continuous piece.
- Latency budgets live in `app/config.py`; the UI shows an optimistic
  placeholder so perceived latency stays near-zero even when a model is slow.

## Rules compliance
Public repo from commit #1 · from-scratch build · no Streamlit (React) · the
canvas is the product, not a dashboard · all demo assets team-made or licensed.
See the PRD §2 for the full anti-project clearance table.
