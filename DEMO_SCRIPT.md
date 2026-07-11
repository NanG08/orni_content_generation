# VoiceCanvas AI — 3-minute live demo + 60-second video script

Golden rule: **run the reliable spine flawlessly; treat video + wardrobe as
bonus-with-fallback.** A 2-model demo that never stalls beats a 5-model demo
that spins. Rehearse the exact four spine lines below until they're muscle memory.

## Pre-stage checklist
- [ ] Backend running, `USE_MOCKS=false`, key in `.env` (NOT `.env.example`).
- [ ] `curl /healthz` shows `mock_mode:false`.
- [ ] One scenario pre-warmed; `fallback.mp4` ready if you show Omni Flash.
- [ ] Mobile hotspot as WiFi backup.
- [ ] Transcript overlay visible so judges see intent even if audio misfires.

## Opening line (before 0:00) — pre-empts the DQ question
> "Everything you're about to see was built today from scratch, and our repo has
> been public since the first commit."

## The 3-minute sequence (escalating difficulty)

**0:00–0:45 — Voice → crisp-text ad (PS3 + PS1 core).**
Say: *"Instagram story for a cold brew coffee, rustic café table in Indiranagar,
headline 'Brewed in Bengaluru'."*
→ Real 1K ad lands in seconds, text pixel-crisp.
Then interrupt mid-thought: *"Wait — make it bright morning sun."*
→ Show the barge-in cancel + re-render. **This proves interruption is real.**

**0:45–1:15 — Instant localization (Impact in India, 25%).**
Say: *"Translate the whole campaign into Kannada."*
→ Headline swaps to Kannada instantly (overlay swap, not a re-render). Land the
line: *"Same layout, spelling guaranteed, in the language your market speaks."*

**1:15–2:15 — The chain / video finale (Technical Depth moment).**
Say: *"Turn that into a cinematic clip, deep voice says 'The city never sleeps'."*
→ Omni Flash animates the exact frame + synced voiceover.
(Optional continuation, proves A→B→C): *"Now push in slowly as it starts to rain."*
→ Feeds the previous clip's final frame in — one continuous take.
**If it stalls, cut to `fallback.mp4` and say "same pipeline, pre-rendered."**

**2:15–3:00 — Wardrobe generalization + close.**
Say: *"Put on a black oversized t-shirt with beige cargo pants."*
→ Shows the voice pattern generalizes beyond ads. Then close on the hook.

## 30-second hook (closing line)
> "Every AI video tool can make something move — almost none can make it *say*
> something legible, and almost none feel instant. VoiceCanvas fixes both: you
> talk, it draws your ad with perfect text in seconds, animates that exact frame
> into a synced video, and localizes it into any Indian language — no forms, no
> waiting your turn. Just describe the ad, and watch it build itself, live."

## 60-second submission video (tighter cut)
1. **0–10s** — hook line over a screen recording of the ad landing from voice.
2. **10–25s** — interrupt + re-render (barge-in), on screen.
3. **25–40s** — instant Kannada localization.
4. **40–55s** — Omni Flash clip with voiceover (use the clean pre-rendered take).
5. **55–60s** — one-line close + repo/public + "built today."

## Q&A defense (have these ready)
- *"Isn't this a dashboard?"* → "The canvas is the product — every pixel is a
  generated asset or a live-editable layer, no charts or metrics views."
- *"What did you actually build?"* → "A real-time speech-to-intent router with
  self-correction and interruption handling, routing between a typography-first
  image model and a stateful video model — not a single-API wrapper."
- *"How is the text always correct?"* → "NB2 Lite renders the anchor frame, and
  we lock the headline as a client-side overlay layer, so it can't garble and
  localization is an instant swap."
