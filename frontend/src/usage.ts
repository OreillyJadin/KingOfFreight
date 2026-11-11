const pages = new Set(["dashboard", "tracking", "loads", "customers", "branches", "carriers", "sales", "inbox", "customer-updates", "truckstop", "status", "settings", "users", "usage", "set-password"]);

export function trackUsage(event: "page_view" | "assistant_opened" | "assistant_question_submitted" | "suggestion_clicked", path = window.location.pathname) {
  try {
    const page = path.split(/[?#]/)[0].split("/")[1];
    if (!pages.has(page)) return;
    void fetch("/api/usage/events", { method: "POST", credentials: "include", keepalive: true, headers: { "Content-Type": "application/json" }, body: JSON.stringify({ event, path: `/${page}` }) }).catch(() => {});
  } catch { return; }
}
