// The canvas = the product. A single generated asset with its live text overlay,
// an optimistic shimmer while the model is in flight, and the animated state
// when Omni Flash returns a clip. No charts, no panels — this is deliberately
// NOT a dashboard (see the anti-project compliance note in the PRD).
import React from "react";
import TextOverlay from "./TextOverlay.jsx";

const RATIO = { "9:16": 9 / 16, "1:1": 1, "16:9": 16 / 9 };

export default function CanvasStage({ asset }) {
  if (!asset) {
    return (
      <div className="stage empty">
        <p>🎙️ Hold the mic and describe an ad.</p>
        <p className="hint">
          e.g. “Instagram story for a cold brew coffee, rustic wooden table in an
          Indiranagar café, headline ‘Brewed in Bengaluru’.”
        </p>
      </div>
    );
  }

  const ar = RATIO[asset.aspect] || 9 / 16;
  const width = ar >= 1 ? 640 : 420;
  const height = width / ar;

  return (
    <div className="stage">
      <div
        className={`frame ${asset.pending ? "pending" : ""}`}
        style={{ width, height }}
      >
        {asset.video && asset.video !== "MOCK_VIDEO" ? (
          <video src={asset.video} poster={asset.src} autoPlay loop muted controls />
        ) : (
          <img src={asset.src} alt="generated ad" />
        )}

        {asset.video === "MOCK_VIDEO" && <div className="film-motion" />}
        {asset.pending && <div className="shimmer" />}

        <TextOverlay overlay={asset.overlay} />
        {asset.video === "MOCK_VIDEO" && (
          <div className="badge">
            {asset.chained ? "⛓ Continuous cut · scene extended" : "▶ Omni Flash · mock video (real key needed)"}
          </div>
        )}
        {asset.video && asset.video !== "MOCK_VIDEO" && (
          <div className="badge" style={{background: "rgba(34,211,238,0.9)"}}>
            ▶ Omni Flash · real video
          </div>
        )}
      </div>
    </div>
  );
}
