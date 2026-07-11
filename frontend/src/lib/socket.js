// Thin WebSocket client to the relay. One reconnecting socket, JSON both ways.
export function connect(onMessage) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onmessage = (e) => {
    try {
      onMessage(JSON.parse(e.data));
    } catch {
      /* ignore non-json */
    }
  };
  return {
    raw: ws,
    ready: () => ws.readyState === WebSocket.OPEN,
    send: (obj) => ws.readyState === WebSocket.OPEN && ws.send(JSON.stringify(obj)),
    utterance: (text, final = true) =>
      ws.readyState === WebSocket.OPEN &&
      ws.send(JSON.stringify({ type: "utterance", text, final })),
    interrupt: () =>
      ws.readyState === WebSocket.OPEN && ws.send(JSON.stringify({ type: "interrupt" })),
    select: (asset_id) =>
      ws.readyState === WebSocket.OPEN &&
      ws.send(JSON.stringify({ type: "select_asset", asset_id })),
    uploadAvatar: (src) =>
      ws.readyState === WebSocket.OPEN &&
      ws.send(JSON.stringify({ type: "upload_avatar", src })),
  };
}
