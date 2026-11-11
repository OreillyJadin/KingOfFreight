type HeartbeatEnvironment = {
  document: Pick<Document, "visibilityState" | "addEventListener" | "removeEventListener">;
  input: Pick<Window, "addEventListener" | "removeEventListener">;
  now: () => number;
  setInterval: (callback: () => void, milliseconds: number) => number;
  clearInterval: (id: number) => void;
};

export function startHeartbeat(send: () => Promise<unknown>, environment: HeartbeatEnvironment = {
  document,
  input: window,
  now: Date.now,
  setInterval: window.setInterval.bind(window),
  clearInterval: window.clearInterval.bind(window),
}) {
  let lastInput = -Infinity;
  let timer: number | undefined;
  const inputEvents = ["pointerdown", "pointermove", "keydown", "scroll", "touchstart"];
  const onInput = () => {
    if (environment.document.visibilityState === "visible") lastInput = environment.now();
  };
  const tick = () => {
    if (environment.document.visibilityState !== "visible" || environment.now() - lastInput > 120_000) return;
    try { void send().catch(() => {}); } catch { return; }
  };
  const onVisibility = () => {
    if (timer !== undefined) environment.clearInterval(timer);
    timer = environment.document.visibilityState === "visible" ? environment.setInterval(tick, 30_000) : undefined;
  };
  for (const event of inputEvents) environment.input.addEventListener(event, onInput, { passive: true, capture: true });
  environment.document.addEventListener("visibilitychange", onVisibility);
  onVisibility();
  return () => {
    if (timer !== undefined) environment.clearInterval(timer);
    for (const event of inputEvents) environment.input.removeEventListener(event, onInput, { capture: true });
    environment.document.removeEventListener("visibilitychange", onVisibility);
  };
}
