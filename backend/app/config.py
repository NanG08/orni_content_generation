"""
Central config. ONE place to change model IDs and the mock/real switch.

At the hackathon (first hour): set USE_MOCKS=false in backend/.env, paste your
GEMINI_API_KEY, and CONFIRM every model id below against the organizer docs /
Discord. A wrong model string is the #1 first-hour blocker. Nothing else in the
codebase hardcodes a model name — they all read from here.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # dotenv is optional; env vars still work without it
    pass


def _flag(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # --- master switch -------------------------------------------------------
    # True  -> everything runs locally with fake generators (no API key needed).
    # False -> real google-genai calls. Flip this on the day.
    use_mocks: bool = _flag("USE_MOCKS", True)

    # --- auth ----------------------------------------------------------------
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")

    # --- model ids (verified against a live hackathon key, 2026-07-11) --------
    # IMPORTANT: the *-live-preview / *-live-translate-preview models are for the
    # bidi streaming Live API ONLY — they 404 on generateContent. So text→JSON
    # intent parsing and text translation use a normal generateContent model
    # (gemini-3.5-flash), while model_live is used only by the voice socket.
    model_intent: str = os.getenv("MODEL_INTENT", "gemini-2.0-flash")                      # intent + translate
    model_live: str = os.getenv("MODEL_LIVE", "gemini-2.0-flash-live-001")                  # bidi audio session
    model_translate: str = os.getenv("MODEL_TRANSLATE", "gemini-2.0-flash")                 # text translate
    model_image: str = os.getenv("MODEL_IMAGE", "gemini-2.0-flash-preview-image-generation") # text->image
    model_edit: str = os.getenv("MODEL_EDIT", "gemini-2.0-flash-preview-image-generation")   # image edit
    model_video: str = os.getenv("MODEL_VIDEO", "veo-2.0-generate-001")                      # Veo video gen
    model_tts: str = os.getenv("MODEL_TTS", "gemini-2.5-flash-preview-tts")                  # TTS

    # --- optional non-Google voice providers (reliable STT/TTS fallbacks) ----
    # Leave blank to use the Google/browser path. If a key is present it takes
    # priority for that leg only (STT or TTS); generative models stay Google.
    # Support both the usual DEEPGRAM_API_KEY name and the renamed key you use.
    # GOOGLE MODELS ONLY by default. Third-party providers exist as dormant
    # fallbacks and activate only when *_PROVIDER is explicitly set to them.
    stt_provider: str = os.getenv("STT_PROVIDER", "google")     # google | deepgram
    tts_provider: str = os.getenv("TTS_PROVIDER", "google")     # google | elevenlabs
    tts_voice: str = os.getenv("TTS_VOICE", "Kore")             # Flash TTS prebuilt voice
    deepgram_api_key: str = os.getenv("GEMINI_API_KEY_1", "")  # STT (Deepgram key)
    # Voice-INPUT language for Deepgram. "en-IN" = Indian English (default).
    # Set "hi"/"kn"/"ta" for those languages, or "multi" for code-switching.
    stt_language: str = os.getenv("STT_LANGUAGE", "en-IN")
    elevenlabs_api_key: str = os.getenv("ELEVENLABS_API_KEY", "")       # TTS
    elevenlabs_voice_id: str = os.getenv("ELEVENLABS_VOICE_ID", "")     # a voice id

    # --- latency budgets (ms) — used for status + regression watching --------
    budget_intent_ms: int = 300
    budget_image_ms: int = 4000
    image_hard_ceiling_ms: int = 6000
    budget_video_ms: int = 15000

    host: str = os.getenv("HOST", "127.0.0.1")
    port: int = int(os.getenv("PORT", "8000"))


settings = Settings()
