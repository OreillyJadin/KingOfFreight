import type { VisualResponses } from "./usage-visuals";

export type UsagePeriod = "day" | "week" | "month";
export type UsageFilters = { period: UsagePeriod; date: string; exclude_admins: boolean };
export type UsageMeta = UsageFilters & { timezone: string; start: string; end_exclusive: string };
export type UsagePerson = {
  identity: string; active_minutes: number; sessions: number; first_activity: string | null;
  last_activity: string | null; avg_session_minutes: number; days_active: number;
  current_streak: number; actions: number; action_counts: Record<string, number>; chat_questions: number;
};
export type UsagePage = { identity: string; path: string; active_minutes: number };
export type HeatCell = { weekday: number; hour: number; active_minutes: number };
export type UsageFeedItem = { id: number; identity: string; event: string; path: string | null; device: string; time: string; summary: string; detail: Record<string, unknown> };
export type UsageOutput = { name: string | null; loads: number; revenue: number; carrier_cost: number; profit: number; margin_pct: number | null };
export type UsageResponses = VisualResponses & {
  people: UsageMeta & { people: UsagePerson[] };
  pages: UsageMeta & { pages: UsagePage[] };
  heatmap: UsageMeta & { cells: (HeatCell & { identity: string })[]; total: HeatCell[] };
  feed: UsageMeta & { items: UsageFeedItem[]; total: number; limit: number; offset: number; has_more: boolean };
  kof_output: UsageMeta & { booker: UsageOutput[]; rep: UsageOutput[] };
  response_speed: UsageMeta & { people: { identity: string; count: number; median_seconds: number; avg_seconds: number }[]; unlinked_approval_events: number };
  features: UsageMeta & { features: { feature: string; label: string; uses: number; distinct_people: number; last_used: string | null }[] };
  leaderboard: UsageMeta & { people: { identity: string; active_minutes: number; actions: number; kof_profit: number | null; active_minutes_rank: number; actions_rank: number; kof_profit_rank: number | null }[] };
};

export type UsageExtra = { identity?: string; limit?: number; offset?: number; days?: number; interval?: "day" | "week" };
export function usageQuery(filters: UsageFilters, extra: UsageExtra = {}) {
  const params = new URLSearchParams({ period: filters.period, date: filters.date, exclude_admins: String(filters.exclude_admins) });
  for (const [key, value] of Object.entries(extra)) if (value !== undefined) params.set(key, String(value));
  return params.toString();
}

export function brokerToday(timeZone: string, now = new Date()) {
  const parts = new Intl.DateTimeFormat("en-US", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(now);
  const part = (type: string) => parts.find(p => p.type === type)!.value;
  return `${part("year")}-${part("month")}-${part("day")}`;
}

function shiftDay(day: string, amount: number) {
  const stamp = new Date(`${day}T12:00:00Z`);
  stamp.setUTCDate(stamp.getUTCDate() + amount);
  return stamp.toISOString().slice(0, 10);
}

export function periodStart(period: UsagePeriod, day: string) {
  if (period === "month") return `${day.slice(0, 7)}-01`;
  if (period === "day") return day;
  return shiftDay(day, -((new Date(`${day}T12:00:00Z`).getUTCDay() + 6) % 7));
}

export function shiftPeriod(period: UsagePeriod, day: string, amount: number) {
  const start = periodStart(period, day);
  if (period !== "month") return shiftDay(start, amount * (period === "week" ? 7 : 1));
  const stamp = new Date(`${start}T12:00:00Z`);
  stamp.setUTCMonth(stamp.getUTCMonth() + amount);
  return stamp.toISOString().slice(0, 10);
}

export function periodLabel(period: UsagePeriod, day: string, today: string) {
  const start = periodStart(period, day);
  if (start === periodStart(period, today)) return period === "day" ? "Today" : period === "week" ? "This week" : "This month";
  const label = (value: string, monthOnly = false) => new Date(`${value}T12:00:00Z`).toLocaleDateString("en-US", { timeZone: "UTC", month: "short", ...(monthOnly ? {} : { day: "numeric" }), year: "numeric" });
  return period === "week" ? `${label(start)} – ${label(shiftDay(start, 6))}` : label(start, period === "month");
}

export function activeTime(minutes: number) {
  const rounded = Math.max(0, Math.round(minutes));
  return `${Math.floor(rounded / 60)}:${String(rounded % 60).padStart(2, "0")}`;
}

export function responseTime(seconds: number) {
  return seconds < 60 ? `${Math.round(seconds)}s` : `${Math.round(seconds / 60)}m`;
}

export function activityTime(stamp: string | null, timeZone: string) {
  if (!stamp) return "—";
  return new Date(stamp).toLocaleString("en-US", { timeZone, month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}
