export function watchClientErrors(target: Window = window) {
  let sent = 0;
  let since = Date.now();
  const report = (message: string) => {
    if (Date.now() - since >= 60_000) {
      since = Date.now();
      sent = 0;
    }
    if (sent >= 5) return;
    sent++;
    try {
      void target.fetch("/api/usage/client-error", {
        method: "POST",
        credentials: "include",
        keepalive: true,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: message.slice(0, 1000),
          path: target.location.pathname,
        }),
      }).catch(() => {});
    } catch {
      return;
    }
  };
  const onError = (event: ErrorEvent) =>
    report(event.message || "Unhandled browser error");
  const onRejection = (event: PromiseRejectionEvent) => {
    const reason = event.reason;
    report(
      reason instanceof Error
        ? reason.message
        : typeof reason === "string"
          ? reason
          : "Unhandled promise rejection",
    );
  };
  target.addEventListener("error", onError);
  target.addEventListener("unhandledrejection", onRejection);
  return () => {
    target.removeEventListener("error", onError);
    target.removeEventListener("unhandledrejection", onRejection);
  };
}
