import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocation } from "react-router-dom";
import { api } from "./api";
import { trackUsage } from "./usage";

export default function UsageTracking() {
  const location = useLocation();
  const enabled = location.pathname !== "/login" && !location.pathname.startsWith("/t/");
  const auth = useQuery({ queryKey: ["auth"], queryFn: api.me, enabled, retry: false });
  useEffect(() => {
    if (!enabled || !auth.data?.authenticated) return;
    const path = `/${location.pathname.split("/")[1]}`;
    const key = `fw-usage:${auth.data.username ?? "shared"}:${path}`;
    try {
      const previous = Number(sessionStorage.getItem(key) || 0);
      if (Date.now() - previous < 5000) return;
      sessionStorage.setItem(key, String(Date.now()));
    } catch {
      trackUsage("page_view", path);
      return;
    }
    trackUsage("page_view", path);
  }, [enabled, location.pathname, auth.data?.authenticated, auth.data?.username]);
  return null;
}
