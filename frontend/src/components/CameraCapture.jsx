// REAL-TIME WARDROBE entry point: capture the creator from the front camera,
// snap a frame, and load it as the avatar. Every subsequent "put on ..." voice
// command performs a photorealistic try-on edit on THIS real photo (identity,
// pose, and lighting preserved — garment folds re-rendered by the edit model).
import React, { useEffect, useRef, useState } from "react";

export default function CameraCapture({ onCapture, onClose }) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "user", width: { ideal: 720 }, height: { ideal: 1280 } },
        });
        streamRef.current = stream;
        if (videoRef.current) videoRef.current.srcObject = stream;
      } catch {
        setErr("Camera unavailable — check permissions");
      }
    })();
    return () => streamRef.current?.getTracks().forEach((t) => t.stop());
  }, []);

  function snap() {
    const v = videoRef.current;
    if (!v || !v.videoWidth) return;
    const c = document.createElement("canvas");
    c.width = v.videoWidth;
    c.height = v.videoHeight;
    c.getContext("2d").drawImage(v, 0, 0);
    onCapture(c.toDataURL("image/jpeg", 0.9)); // -> upload_avatar over WS
    onClose();
  }

  return (
    <div className="camera-modal">
      <div className="camera-box">
        {err ? (
          <p className="camera-err">{err}</p>
        ) : (
          <video ref={videoRef} autoPlay playsInline muted />
        )}
        <div className="camera-actions">
          <button className="snap" onClick={snap} disabled={!!err}>
            📸 Snap — then say what to wear
          </button>
          <button className="cancel" onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  );
}
