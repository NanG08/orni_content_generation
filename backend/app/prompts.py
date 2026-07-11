"""
THE 20% THAT WINS.

Everything else is plumbing; this file is the actual AI engineering. Do not
improvise prompts live on stage — tune them here, pre-test them, and let the
demo only 'improvise' the voice and the rendering. Deterministic prompts are
how you make an unpredictable model chain look reliable.
"""
from __future__ import annotations

from .schemas import Intent

# =============================================================================
# 1. INTENT ROUTER  (Gemini Live -> structured JSON)
# =============================================================================
# This is the brain. It must survive self-correction inside one sentence
# ("a red bottle, no make it blue") and decide create-vs-edit routing.

INTENT_SYSTEM_PROMPT = """You are the intent parser for a voice-driven ad studio.
You receive a short spoken utterance (already transcribed) and output ONE JSON
object matching the Intent schema. Nothing else — no prose, no markdown.

Rules:
- RESOLVE self-corrections. "a red bottle, no, blue" -> the FINAL value wins
  (blue). Never emit both. The user thinking out loud is normal.
- action:
    create   -> a brand new asset is being described (new product/scene).
    edit     -> modify the CURRENTLY SELECTED asset (lighting, copy, background,
                color) WITHOUT changing what the product is.
    animate  -> turn the current still into motion/video.
    localize -> translate the current campaign into another language.
    wardrobe -> apparel change on the current avatar/subject.
    unknown  -> you genuinely cannot tell; ask nothing, just set low confidence.
- If the user references "this", "that", "the ad", "it" -> it is an edit/animate/
  localize on target_asset_id (the currently selected asset id, given below).
- copy_text is the LITERAL on-image words, transcribed verbatim, no paraphrase.
- language uses ISO codes: hindi->hi, kannada->kn, tamil->ta, english->en.
- aspect: "instagram story"/"reel"/"vertical" -> 9:16 ; "post"/"square" -> 1:1 ;
  "banner"/"youtube"/"landscape" -> 16:9. Default 9:16.
- interrupt: set true if the utterance starts with a correction of something in
  progress ("wait", "no", "actually", "stop", "change that").
- confidence: 0..1, honest.

Current selected asset id: {selected_id}
"""


def intent_user_turn(text: str, selected_id: str | None) -> str:
    return f'Selected asset: {selected_id or "none"}\nUtterance: "{text}"'


# =============================================================================
# 2. NB2 LITE  (typography-first image anchor)
# =============================================================================
# The 'garbled text' fix is a PROMPT discipline: quote the copy exactly, pin the
# layout, keep copy short, demand high legibility. We still lock it with a
# client-side text overlay (frontend) — but the baked frame should be crisp too.

_ASPECT_DIMS = {"9:16": "1080x1920 vertical", "1:1": "1080x1080 square", "16:9": "1920x1080 landscape"}


def nb2_image_prompt(intent: Intent) -> str:
    dims = _ASPECT_DIMS.get(intent.aspect, "1080x1920 vertical")
    product = intent.product or "the product"
    background = intent.background or "a clean, on-brand studio background"
    style = intent.style or "bright, editorial, high-end commercial photography"
    copy = (intent.copy_text or "").strip()
    energy = getattr(intent, "energy", "medium")
    energy_dir = {
        "high": "bold, high-contrast, vivid colours, dramatic lighting, maximum visual impact",
        "low":  "soft, minimal, muted tones, understated elegance",
    }.get(energy, "balanced, clean, commercial")

    copy_block = (
        f'Render this EXACT headline text, spelled letter-for-letter, crisp and '
        f'perfectly legible, bold sans-serif, high contrast against its backdrop: '
        f'"{copy}". Do not alter, translate, or paraphrase the words.'
        if copy else "No on-image text in this frame."
    )
    return (
        f"High-resolution 1K advertising creative, {dims}.\n"
        f"Subject: {product}, hero-lit, sharp product focus, commercially appealing.\n"
        f"Environment: {background}.\n"
        f"Art direction: {style}. {energy_dir}. Clean negative space reserved for the headline.\n"
        f"Typography: {copy_block}\n"
        f"Constraints: single clear focal product, no watermark, no lorem ipsum, "
        f"no gibberish glyphs, print-ready composition."
    )


def nb2_edit_prompt(intent: Intent, prior_prompt: str) -> str:
    """An edit keeps the product identity, changes only what was asked."""
    change = ", ".join(
        p for p in [
            f"background -> {intent.background}" if intent.background else "",
            f"lighting/style -> {intent.style}" if intent.style else "",
            f'headline -> "{intent.copy_text}"' if intent.copy_text else "",
        ] if p
    ) or "apply the requested refinement"
    return (
        f"{prior_prompt}\n\nEDIT (keep the SAME product, identity, and layout; "
        f"change only): {change}. Preserve everything else pixel-consistent."
    )


# =============================================================================
# 3. OMNI FLASH  (motion on top of the anchor + stateful A->B->C chaining)
# =============================================================================
# Separate WHAT (locked by the reference frame) from HOW IT MOVES (this prompt).

def omni_motion_prompt(intent: Intent) -> str:
    motion = intent.motion or "slow, subtle cinematic push-in with gentle parallax"
    energy = getattr(intent, "energy", "medium")
    energy_dir = {
        "high": "fast cuts, dynamic camera moves, high energy, punchy pacing",
        "low":  "slow drift, gentle parallax, calm atmospheric pacing",
    }.get(energy, "smooth cinematic movement, balanced pacing")
    return (
        f"Animate the provided reference image into a ~5s, 720p cinematic clip.\n"
        f"Motion: {motion}. Pacing: {energy_dir}.\n"
        f"Keep the product, composition, and any on-frame text identical to the "
        f"reference — animate the scene, do not regenerate or restyle the subject. "
        f"Respect real-world physics: gravity, consistent lighting direction, "
        f"believable perspective."
    )


def omni_chain_prompt(next_beat: str) -> str:
    """Feed the FINAL FRAME of the previous clip back in for continuity."""
    return (
        f"Continue directly from the provided frame (it is the last frame of the "
        f"previous shot). New beat: {next_beat}. Maintain the same character, "
        f"wardrobe, color grade, and lighting so the two clips read as one "
        f"continuous take with no visible cut."
    )


def omni_wardrobe_prompt(intent: Intent) -> str:
    change = intent.wardrobe or "swap the outfit as described"
    return (
        f"On the provided reference figure, {change}. Keep the person's identity, "
        f"pose, body shape, and the scene lighting consistent; adjust cloth folds, "
        f"drape, and shadows to match the new garment realistically. Change only "
        f"the apparel, nothing else."
    )


# =============================================================================
# 4. TTS  (expressive voiceover)
# =============================================================================

def tts_prompt(script: str, tone: str = "deep, cinematic narrator") -> str:
    return f"Voice: {tone}. Read expressively, ad-trailer pacing:\n{script}"
