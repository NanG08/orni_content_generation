import React, { useEffect, useRef, useState } from "react";
import CameraCapture from "./components/CameraCapture.jsx";
import CanvasStage from "./components/CanvasStage.jsx";
import { connect } from "./lib/socket.js";
import { startVoice, speak } from "./lib/voice.js";

export default function App() {
  const [asset, setAsset] = useState(null);       // the single canvas asset
  const [status, setStatus] = useState("connecting…");
  const [transcript, setTranscript] = useState("");
  const [intent, setIntent] = useState(null);
  const [listening, setListening] = useState(false);
  const [mock, setMock] = useState(true);
  const [camera, setCamera] = useState(false);    // real-time wardrobe capture
  const sockRef = useRef(null);
  const voiceRef = useRef(null);

  // ---- socket wiring -------------------------------------------------------
  useEffect(() => {
    const sock = connect((msg) => handleServer(msg));
    sockRef.current = sock;
    sock.raw.onopen = () => setStatus("connected");
    sock.raw.onclose = () => setStatus("disconnected");
    return () => sock.raw.close();
  }, []);

  function handleServer(msg) {
    switch (msg.type) {
      case "status":
        setStatus(msg.message);
        if (typeof msg.mock_mode === "boolean") setMock(msg.mock_mode);
        break;
      case "intent":
        setIntent(msg.intent);
        setTranscript(msg.transcript || "");
        break;
      case "placeholder":
        setAsset({ id: msg.asset_id, aspect: msg.aspect, pending: true, src: null });
        break;
      case "asset":
        setAsset({
          id: msg.asset_id, src: msg.src, aspect: msg.aspect,
          overlay: msg.overlay, pending: false,
        });
        break;
      case "video":
        setAsset((a) => ({ ...(a || {}), id: msg.asset_id, video: msg.src,
          src: msg.poster, overlay: msg.overlay, pending: false,
          chained: !!msg.chained }));
        break;
      case "audio":
        if (msg.kind === "music") {
          // background music — play at low volume under the video
          if (msg.src) {
            const music = new Audio(msg.src);
            music.volume = 0.25;
            music.loop = true;
            music.play().catch(() => {});
          }
        } else {
          // voiceover — full volume, no loop
          if (msg.src) new Audio(msg.src).play().catch(() => {});
          else if (msg.script) speak(msg.script);
        }
        break;
      case "overlay_update":
        setAsset((a) => (a && a.id === msg.asset_id ? { ...a, overlay: msg.overlay } : a));
        break;
      case "error":
        setStatus("⚠ " + msg.message);
        break;
      default:
        break;
    }
  }

  // ---- voice wiring --------------------------------------------------------
  async function toggleMic() {
    if (listening) {
      voiceRef.current?.stop();
      setListening(false);
      return;
    }
    setStatus("Starting mic…");
    voiceRef.current = await startVoice({
      onTranscript: (text) => sockRef.current?.utterance(text, true),
      onInterrupt: () => sockRef.current?.interrupt(),
      onState: (st) => {
        setListening(st === "listening");
        if (st === "error:mic-denied") setStatus("⚠ Mic blocked — allow microphone in Chrome and try again");
        else if (st === "unsupported") setStatus("⚠ Speech not supported — use the text box");
        else if (st.startsWith("error:")) setStatus("⚠ Voice error: " + st.split(":")[1]);
        else if (st === "listening") setStatus("Listening…");
      },
    });
  }

  function sendTyped(e) {
    e.preventDefault();
    const text = new FormData(e.target).get("t").toString().trim();
    if (text) sockRef.current?.utterance(text, true);
    e.target.reset();
  }

  function onUploadPhoto(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => sockRef.current?.uploadAvatar(reader.result);
    reader.readAsDataURL(file); // -> data:image/...;base64,...
  }

  return (
    <div className="app">
      <header>
        <div className="brand">🎨 VoiceCanvas <span>AI</span></div>
        <div className={`pill ${mock ? "mock" : "live"}`}>
          {mock ? "MOCK MODE — no credentials" : "LIVE — Gemini"}
        </div>
      </header>

      <main>
        <CanvasStage asset={asset} />

        <aside className="rail">
          <button className={`mic ${listening ? "on" : ""}`} onClick={toggleMic}>
            {listening ? "● Listening — speak / interrupt" : "🎙 Hold to talk"}
          </button>

          {/* typed fallback for noisy rooms / no-mic laptops */}
          <form onSubmit={sendTyped} className="typed">
            <input name="t" placeholder="…or type a command" autoComplete="off" />
            <button>Send</button>
          </form>

          {/* REAL-TIME WARDROBE: snap yourself, then voice-swap outfits */}
          <button className="upload" onClick={() => setCamera(true)}>
            🤳 Use camera — real-time wardrobe
          </button>

          {/* or upload a REAL creator photo to dress (photorealistic try-on) */}
          <label className="upload">
            📷 Upload a photo to try on clothes
            <input type="file" accept="image/*" hidden onChange={onUploadPhoto} />
          </label>

          <div className="status">{status}</div>

          {transcript && (
            <div className="transcript">
              <label>Heard</label>
              <p>{transcript}</p>
            </div>
          )}

          {intent && (
            <div className="intent">
              <label>Parsed intent</label>
              <table>
                <tbody>
                  {Object.entries(intent)
                    .filter(([, v]) => v !== null && v !== "" && v !== false)
                    .map(([k, v]) => (
                      <tr key={k}>
                        <td>{k}</td>
                        <td>{String(v)}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          )}

          <details className="cheats">
            <summary>Demo script</summary>
            <ol>
              <li>“Instagram story for cold brew coffee, rustic café table, headline ‘Brewed in Bengaluru’.”</li>
              <li>“Wait — make it bright morning sun.” <em>(interrupt + edit)</em></li>
              <li>“Turn that into a cinematic clip, deep voice says ‘The city never sleeps’.”</li>
              <li>“Translate the campaign into Kannada.” <em>(instant overlay swap)</em></li>
            </ol>
          </details>
        </aside>
      </main>

      {camera && (
        <CameraCapture
          onCapture={(dataUri) => sockRef.current?.uploadAvatar(dataUri)}
          onClose={() => setCamera(false)}
        />
      )}
    </div>
  );
}
