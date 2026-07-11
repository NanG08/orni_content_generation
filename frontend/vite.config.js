import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Proxy /ws to the FastAPI relay so the browser talks to one origin in dev.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/ws": { target: "ws://127.0.0.1:8000", ws: true },
      "/ws-stt": { target: "ws://127.0.0.1:8000", ws: true },
      "/healthz": "http://127.0.0.1:8000",
      "/stt-status": "http://127.0.0.1:8000",
      "/live-token": "http://127.0.0.1:8000",
    },
  },
});
