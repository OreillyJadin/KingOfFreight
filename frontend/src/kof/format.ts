import type { KofStage } from "./api";

export const stageLabels: Record<KofStage, string> = {
  pending: "Pending",
  booked: "Booked",
  confirmation: "Confirmation",
  awaiting_pickup: "Awaiting pickup",
  in_transit: "In transit",
  awaiting_delivery: "Awaiting delivery",
  delivered: "Delivered",
  billed: "Billed",
  paid: "Paid",
};

export const stageOrder: KofStage[] = [
  "pending",
  "booked",
  "confirmation",
  "awaiting_pickup",
  "in_transit",
  "awaiting_delivery",
  "delivered",
  "billed",
  "paid",
];

export function stageClass(stage: KofStage) {
  const map: Partial<Record<KofStage, string>> = {
    booked: "bg-st-booked/15 text-st-booked-ink",
    confirmation: "bg-st-booked/15 text-st-booked-ink",
    awaiting_pickup: "bg-st-picked/15 text-st-picked-ink",
    in_transit: "bg-st-transit/15 text-st-transit-ink",
    awaiting_delivery: "bg-st-transit/15 text-st-transit-ink",
    delivered: "bg-st-delivered/15 text-st-delivered-ink",
    billed: "bg-st-delivered/15 text-st-delivered-ink",
    paid: "bg-ok/15 text-ok-ink",
  };
  return map[stage] ?? "bg-surface-3 text-fg-2";
}

export function money(value?: number | null, digits = 0) {
  if (value === undefined || value === null || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(value);
}

export function compactMoney(value?: number | null) {
  if (value === undefined || value === null || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "USD",
    notation: Math.abs(value) >= 10000 ? "compact" : "standard",
    maximumFractionDigits: Math.abs(value) >= 10000 ? 1 : 0,
  }).format(value);
}

export function pct(value?: number | null, digits = 1) {
  if (value === undefined || value === null || !Number.isFinite(value)) return "—";
  return `${value.toFixed(digits)}%`;
}

export function count(value?: number | null) {
  if (value === undefined || value === null || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat().format(value);
}

export function shortDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value.length <= 10 ? `${value}T00:00:00` : value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export function monthDay(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value.length <= 10 ? `${value}T00:00:00` : value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function relativeHours(hours?: number | null) {
  if (hours === undefined || hours === null || !Number.isFinite(hours)) return "no updates";
  if (hours < 1) return "updated just now";
  if (hours < 24) return `updated ${Math.round(hours)}h ago`;
  const days = Math.round(hours / 24);
  return `updated ${days}d ago`;
}

export function place(city?: string | null, state?: string | null) {
  if (!city && !state) return "—";
  if (!city) return state ?? "—";
  return state ? `${city}, ${state}` : city;
}

export function isoDay(date: Date) {
  return date.toISOString().slice(0, 10);
}

export function localIsoDay(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function rangeForDays(days: number) {
  const end = new Date();
  const start = new Date(end.getTime() - days * 86400000);
  return { start: isoDay(start), end: isoDay(end) };
}
