import type { LoadStatus } from "./types";

export function formatDateTime(value?: string | null, fallback = "TBD") {
  if (!value) return fallback;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return fallback;
  return new Intl.DateTimeFormat(undefined, {
    weekday: "short",
    month: "numeric",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

export function formatClock(value?: string | null, fallback = "time unknown") {
  if (!value) return fallback;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return fallback;
  return new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

export function cityState(city?: string | null, state?: string | null) {
  if (!city && !state) return "TBD";
  if (!city) return state ?? "TBD";
  return state ? `${city}, ${state}` : city;
}

export function formatMoney(value?: number | string | null) {
  if (value === undefined || value === null || value === "") return "—";
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "—";
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(amount);
}

export function statusLabel(status: LoadStatus | string) {
  const labels: Record<LoadStatus, string> = {
    new: "New",
    posted: "Posted",
    booked: "Booked",
    picked_up: "Picked up",
    in_transit: "In transit",
    delayed: "Delayed",
    delivered: "Delivered",
  };
  return labels[status as LoadStatus] ?? status.replaceAll("_", " ");
}
