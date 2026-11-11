import type { UsageMeta } from "./usage-analytics";

export type ContributionDay = { date: string; active_minutes: number; actions: number; count: number };
export type TrendPerson = { identity: string; devices: Record<string, number>; series: { date: string; active_minutes: number; actions: number; categories: Record<string, number> }[] };
export type VisualResponses = {
  contributions: UsageMeta & { people: { identity: string; days: ContributionDay[]; current_streak: number; longest_streak: number }[] };
  timeline: UsageMeta & { people: { identity: string; spans: { start: string; end_exclusive: string; active_minutes: number }[]; actions: { time: string; event: string; summary: string }[] }[] };
  trend: UsageMeta & { interval: "day" | "week"; event_retention_days: number; people: TrendPerson[]; kof: { booker: { name: string | null; series: { date: string; loads: number; profit: number }[] }[]; rep: { name: string | null; series: { date: string; loads: number; profit: number }[] }[] }; feature_adoption: { week: string; features: { feature: string; distinct_people: number }[] }[]; response_speed: { week: string; people: { identity: string; count: number; median_seconds: number; avg_seconds: number }[] }[] };
  live: UsageMeta & { as_of: string; people: { identity: string; path: string; device: string; last_heartbeat: string; last_action: { time: string; event: string; summary: string } | null }[] };
  flows: UsageMeta & { transitions: { from: string; to: string; count: number }[] };
  users_overview: UsageMeta & { week_start: string; users: { kind: string; id: number; identity: string; role: string | null; is_active: boolean; last_seen: string | null; active_minutes_this_week: number; actions_this_week: number; sparkline: { date: string; active_minutes: number; actions: number }[] }[] };
  health: UsageMeta & {
    errors_per_day: { date: string; count: number }[];
    failing_endpoints: { method: string; path: string; count: number }[];
    slowest_endpoints: { method: string; path: string; count: number; p50_ms: number; p95_ms: number }[];
    latency_basis: string; client_errors: { id: number; identity: string; time: string; message: string; path: string }[]; client_error_total: number;
    failed_sends: { kof_messages: { id: number; order_no: number; time: string }[]; kof_message_total: number; communications_status_available: boolean; attribution_available: boolean };
    kof_sync: { last_success: string | null; freshness_seconds: number | null; failures: number; runs: { id: number; status: string; started_at: string; finished_at: string | null }[] };
    llm_errors: { identity: string; time: string; detail: Record<string, unknown> }[]; llm_error_total: number;
    integrations: Record<string, unknown>; workspace_metrics_note: string;
  };
};

export const categories = ["bol", "checkins", "approvals", "chat", "edits", "messages", "sync", "other"];
export function personColor(identity: string) {
  let hash = 0;
  for (const char of identity.toLowerCase()) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return `hsl(${hash % 360} 65% 46%)`;
}
export function categoryMix(person?: TrendPerson) {
  const totals = categories.map(key => person?.series.reduce((sum, row) => sum + (row.categories[key] ?? 0), 0) ?? 0);
  const total = totals.reduce((sum, count) => sum + count, 0);
  return totals.map(count => total ? count / total : 0);
}
export function timeAgo(stamp: string | null, now = Date.now()) {
  if (!stamp) return "Never";
  const seconds = Math.max(0, Math.floor((now - Date.parse(stamp)) / 1000));
  return seconds < 60 ? `${seconds}s ago` : seconds < 3600 ? `${Math.floor(seconds / 60)}m ago` : seconds < 86400 ? `${Math.floor(seconds / 3600)}h ago` : `${Math.floor(seconds / 86400)}d ago`;
}
export function localHour(stamp: string, zone: string) {
  const parts = new Intl.DateTimeFormat("en-GB", { timeZone: zone, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(new Date(stamp));
  return Number(parts.find(p => p.type === "hour")?.value) + Number(parts.find(p => p.type === "minute")?.value) / 60;
}
export function contributionCells(days: ContributionDay[]) {
  if (!days.length) return [];
  const weekday = (new Date(days[0].date + "T12:00:00Z").getUTCDay() + 6) % 7;
  return [...Array<ContributionDay | null>(weekday).fill(null), ...days];
}
export function freshness(seconds: number | null) {
  return seconds === null ? { label: "No successful sync", color: "#dc2626" } : seconds <= 3600 ? { label: "Fresh", color: "#15803d" } : seconds <= 86400 ? { label: "Delayed", color: "#b45309" } : { label: "Stale", color: "#dc2626" };
}
