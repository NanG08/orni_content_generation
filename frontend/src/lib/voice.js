// Voice input — two engines, one interface.
//
// The rest of the app only ever consumes { onTranscript, onInterrupt, onState },
// so nothing downstream cares which engine is live.
//
//   startVoice()  -> asks the backend /live-token:
//     • mock mode  -> browser Web Speech API (no key, works today)
//     • live mode  -> real Gemini Live session using a SHORT-LIVED EPHEMERAL
//                     TOKEN. The real API key NEVER reaches the browser.
//
// Key safety: per the hackathon account rules, the API key stays server-side.
// The browser only ever holds a one-use ephemeral token minted by /live-token.

const INTERRUPT_WORDS = ["wait", "no", "actually", "stop", "change that", "hold on"];

export async function startVoice(handlers) {
  // Request mic permission immediately inside the user gesture, before any
  // async fetch — Chrome blocks getUserMedia called after an await on some versions.
  let permStream;
  try {
    permStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    handlers.onState?.("error:mic-denied");
    return { stop: () => {} };
  }
  permStream.getTracks().forEach((t) => t.stop()); // release; each engine opens its own

  // GOOGLE MODELS ONLY (default): Gemini Live if a token is available, else
  // Google voice = browser Web Speech (Chrome's Google recognizer) + a Gemini
  // /transcribe recorded-audio fallback. Deepgram runs ONLY if the backend
  // explicitly reports STT_PROVIDER=deepgram.
  try {
    const cfg = await (await fetch("/live-token")).json();
    if (cfg.mode === "live" && cfg.token) {
      try {
        return startGeminiLiveVoice({ ...handlers, token: cfg.token, model: cfg.model });
      } catch {
        handlers.onState?.("error:live");
      }
    }
  } catch { /* backend down */ }

  try {
    const stt = await (await fetch("/stt-status")).json();
    if (stt.provider === "deepgram") return startDeepgramVoice(handlers);
  } catch { /* default to google */ }

  return startGoogleVoice(handlers);
}

// ---------------------------------------------------------------------------
// 0) GOOGLE VOICE  (Web Speech live + Gemini /transcribe recorded fallback)
// ---------------------------------------------------------------------------
// Merged from the team's Orni branch: while Web Speech streams interim results
// (interrupt detection + transcript), a MediaRecorder keeps a webm copy of the
// utterance. If Web Speech yields nothing (unsupported browser, noisy room),
// the recording is POSTed to /transcribe and Gemini itself transcribes it —
// so STT stays 100% Google end to end.
export function startGoogleVoice({ onTranscript, onInterrupt, onState }) {
  let gotText = false;
  let recorder = null;
  let recStream = null;
  const chunks = [];

  // background recorder (the Gemini fallback source)
  (async () => {
    try {
      recStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      recorder = new MediaRecorder(recStream);
      recorder.ondataavailable = (e) => e.data?.size > 0 && chunks.push(e.data);
      recorder.onstop = async () => {
        recStream?.getTracks().forEach((t) => t.stop());
        if (gotText || chunks.length === 0) return;
        // Web Speech produced nothing -> let Gemini transcribe the recording
        try {
          const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
          const b64 = await new Promise((res) => {
            const r = new FileReader();
            r.onloadend = () => res(r.result.split(",")[1]);
            r.readAsDataURL(blob);
          });
          const out = await (await fetch("/transcribe", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ audioBytes: b64, mimeType: blob.type }),
          })).json();
          if (out.text?.trim()) onTranscript?.(out.text.trim());
          else onState?.("error:no-speech");
        } catch {
          onState?.("error:transcribe");
        }
      };
      recorder.start(250);
    } catch { /* no mic for recorder; Web Speech may still work */ }
  })();

  const live = startBrowserVoice({
    onTranscript: (text) => {
      gotText = true;
      onTranscript?.(text);
    },
    onInterrupt,
    onState,
  });

  return {
    stop: () => {
      live.stop();
      try {
        if (recorder && recorder.state !== "inactive") recorder.stop();
      } catch { /* noop */ }
    },
  };
}

// ---------------------------------------------------------------------------
// 3) DEEPGRAM  (reliable STT — audio proxied through our backend)
// ---------------------------------------------------------------------------
// The browser streams PCM to the backend's /ws-stt, which relays to Deepgram
// with the key SERVER-SIDE. The Deepgram key never reaches the browser and no
// token-grant scope is needed. speech_final = one settled utterance.
export function startDeepgramVoice({ onTranscript, onInterrupt, onState }) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws-stt`);
  ws.binaryType = "arraybuffer";
  let stopMic = () => {};
  let stopped = false;

  ws.onopen = async () => {
    onState?.("listening");
    stopMic = await capturePCM((pcm16) => {
      if (ws.readyState === WebSocket.OPEN) ws.send(pcm16.buffer);
    });
  };
  ws.onmessage = (evt) => {
    let m;
    try { m = JSON.parse(evt.data); } catch { return; }
    if (m.error) { onState?.("error:deepgram"); return; }
    const alt = m.channel?.alternatives?.[0];
    const text = (alt?.transcript || "").trim();
    if (!text) return;
    if (!m.is_final) {
      if (INTERRUPT_WORDS.some((w) => text.toLowerCase().startsWith(w))) onInterrupt?.();
      return;
    }
    if (m.speech_final) onTranscript?.(text);
  };
  ws.onerror = () => onState?.("error:deepgram");
  ws.onclose = () => onState?.(stopped ? "idle" : "closed");

  return { stop: () => { stopped = true; stopMic(); ws.close(); } };
}

// ---------------------------------------------------------------------------
// 1) BROWSER Web Speech API  (mock / fallback — no credentials)
// ---------------------------------------------------------------------------
export function startBrowserVoice({ onTranscript, onInterrupt, onState }) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {
    onState?.("unsupported");
    return { stop: () => {} };
  }
  const rec = new SR();
  rec.continuous = true;
  rec.interimResults = true;
  rec.lang = "en-IN";
  let stopped = false;
  rec.onstart = () => onState?.("listening");
  rec.onend = () => {
    if (stopped) {
      onState?.("idle");
      return;
    }
    try {
      rec.start();
    } catch {
      onState?.("error:restart");
    }
  };
  rec.onerror = (e) => {
    if (e.error === "not-allowed") onState?.("error:mic-denied");
    else onState?.("error:" + e.error);
  };
  rec.onresult = (event) => {
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const r = event.results[i];
      const text = r[0].transcript.trim();
      if (!r.isFinal) {
        if (INTERRUPT_WORDS.some((w) => text.toLowerCase().startsWith(w))) onInterrupt?.();
        continue;
      }
      if (text) onTranscript?.(text);
    }
  };
  rec.start();
  return { stop: () => ((stopped = true), rec.stop()) };
}

// ---------------------------------------------------------------------------
// 2) GEMINI LIVE  (real — via ephemeral token, v1alpha, @google/genai SDK)
// ---------------------------------------------------------------------------
// The backend mints a short-lived token (authTokens.create, v1alpha).
// The browser passes it as apiKey — the master key never leaves the server.
export function startGeminiLiveVoice({ token, model, onTranscript, onInterrupt, onState }) {
  let session = null;
  let stopped = false;
  let buffer = "";
  let audioCtx, source, processor, stream;

  (async () => {
    try {
      // Dynamically import the JS SDK (loaded via CDN or bundled)
      const { GoogleGenAI } = await import("https://esm.sh/@google/genai");
      const ai = new GoogleGenAI({
        apiKey: token,                          // ephemeral token, not the master key
        httpOptions: { apiVersion: "v1alpha" }, // REQUIRED
      });

      session = await ai.live.connect({
        model: `models/${model}`,
        config: {
          responseModalities: ["TEXT"],
          inputAudioTranscription: {},          // get back user speech as text
        },
        callbacks: {
          onopen: () => onState?.("listening"),
          onmessage: (msg) => {
            if (msg.serverContent?.interrupted) onInterrupt?.();
            const t = msg.serverContent?.inputTranscription?.text;
            if (t) buffer += t;
            if (msg.serverContent?.turnComplete && buffer.trim()) {
              onTranscript?.(buffer.trim());
              buffer = "";
            }
          },
          onerror: () => onState?.("error:live"),
          onclose: () => onState?.(stopped ? "idle" : "closed"),
        },
      });

      // Stream mic audio into the session
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioCtx = new AudioContext({ sampleRate: 16000 });
      source = audioCtx.createMediaStreamSource(stream);
      processor = audioCtx.createScriptProcessor(4096, 1, 1);
      source.connect(processor);
      processor.connect(audioCtx.destination);
      processor.onaudioprocess = (e) => {
        if (!session) return;
        const pcm16 = floatTo16BitPCM(e.inputBuffer.getChannelData(0));
        session.sendRealtimeInput({
          mediaChunks: [{ mimeType: "audio/pcm;rate=16000", data: base64(pcm16) }],
        });
      };
    } catch (err) {
      onState?.("error:live");
    }
  })();

  return {
    stop: () => {
      stopped = true;
      processor?.disconnect();
      source?.disconnect();
      stream?.getTracks().forEach((t) => t.stop());
      audioCtx?.close();
      session?.close?.();
    },
  };
}

// ---- audio helpers ----------------------------------------------------------
// Opens the mic at 16kHz mono and calls onChunk(Int16Array) per frame.
// Returns a stop() that tears the whole graph down.
async function capturePCM(onChunk) {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const ctx = new AudioContext({ sampleRate: 16000 });
  const source = ctx.createMediaStreamSource(stream);
  const processor = ctx.createScriptProcessor(4096, 1, 1);
  source.connect(processor);
  processor.connect(ctx.destination);
  processor.onaudioprocess = (e) => onChunk(floatTo16BitPCM(e.inputBuffer.getChannelData(0)));
  return () => {
    processor.disconnect();
    source.disconnect();
    stream.getTracks().forEach((t) => t.stop());
    ctx.close();
  };
}

function floatTo16BitPCM(float32) {
  const out = new Int16Array(float32.length);
  for (let i = 0; i < float32.length; i++) {
    const s = Math.max(-1, Math.min(1, float32[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}
function base64(int16) {
  const bytes = new Uint8Array(int16.buffer);
  let bin = "";
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin);
}

// Mock voiceover for the video finale when the backend returns no TTS audio.
export function speak(text) {
  if (!("speechSynthesis" in window) || !text) return;
  const u = new SpeechSynthesisUtterance(text);
  u.rate = 0.95;
  u.pitch = 0.9;
  speechSynthesis.speak(u);
}
