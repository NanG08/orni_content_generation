// THE SPELLING-GUARANTEE TRICK.
// The headline is rendered as a crisp DOM layer ON TOP of the generated frame,
// never baked into the model pixels. So: (1) text can never garble, and
// (2) localization is an instant text swap — no re-render — which is exactly
// what makes "translate the whole campaign, keep the layout" feel instant.
import React from "react";

const FONT = {
  en: "'Inter', system-ui, sans-serif",
  hi: "'Noto Sans Devanagari', 'Inter', sans-serif",
  kn: "'Noto Sans Kannada', 'Inter', sans-serif",
  ta: "'Noto Sans Tamil', 'Inter', sans-serif",
};

export default function TextOverlay({ overlay }) {
  if (!overlay?.text) return null;
  return (
    <div className="overlay" key={overlay.lang + overlay.text}>
      <span
        className="overlay-headline"
        style={{ fontFamily: FONT[overlay.lang] || FONT.en }}
      >
        {overlay.text}
      </span>
      {overlay.lang && overlay.lang !== "en" && (
        <span className="overlay-lang">{overlay.lang.toUpperCase()}</span>
      )}
    </div>
  );
}
