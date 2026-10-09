import type { LoadStatus } from "./types";

let brokerTimeZone = "America/Chicago";

export function setBrokerTimeZone(tz: string) {
  brokerTimeZone = tz;
}

export function getBrokerTimeZone() {
  return brokerTimeZone;
}

function brokerDateTimeFormat(options: Intl.DateTimeFormatOptions) {
  try {
    return new Intl.DateTimeFormat(undefined, {
      ...options,
      timeZone: brokerTimeZone,
      timeZoneName: "shortGeneric",
    });
  } catch (error) {
    if (!(error instanceof RangeError)) throw error;
    return new Intl.DateTimeFormat(undefined, {
      ...options,
      timeZone: brokerTimeZone,
      timeZoneName: "short",
    });
  }
}

export function formatDateTime(value?: string | null, fallback = "TBD") {
  if (!value) return fallback;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return fallback;
  return brokerDateTimeFormat({
    weekday: "short",
    month: "numeric",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

export function formatShortDateTime(value?: string | null, fallback = "") {
  if (!value) return fallback;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return fallback;
  return brokerDateTimeFormat({
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

export function formatClock(value?: string | null, fallback = "time unknown") {
  if (!value) return fallback;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return fallback;
  return brokerDateTimeFormat({
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

export function brokerZoneLabel() {
  return (
    brokerDateTimeFormat({}).formatToParts(new Date()).find((part) => part.type === "timeZoneName")
      ?.value ?? brokerTimeZone
  );
}

export function toZoneInputValue(iso: string, zone: string) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso.slice(0, 16);
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: zone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const values = Object.fromEntries(parts.map(({ type, value }) => [type, value]));
  return `${values.year}-${values.month}-${values.day}T${values.hour}:${values.minute}`;
}

export function toBrokerInputValue(iso: string) {
  return toZoneInputValue(iso, brokerTimeZone);
}

function zoneOffsetAt(date: Date, zone: string) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: zone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const values = Object.fromEntries(parts.map(({ type, value }) => [type, value]));
  const asUtc = Date.UTC(
    Number(values.year),
    Number(values.month) - 1,
    Number(values.day),
    Number(values.hour),
    Number(values.minute),
    Number(values.second),
  );
  return asUtc - date.getTime();
}

export function zonedInputToDate(value: string, zone: string): Date {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value);
  if (!match) return new Date(Number.NaN);
  const [, year, month, day, hour, minute] = match;
  const wallTime = Date.UTC(
    Number(year),
    Number(month) - 1,
    Number(day),
    Number(hour),
    Number(minute),
  );
  const first = wallTime - zoneOffsetAt(new Date(wallTime), zone);
  const corrected = wallTime - zoneOffsetAt(new Date(first), zone);
  return new Date(corrected);
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
