export function brokerDay(timeZone: string, now = new Date()) {
  const parts = new Intl.DateTimeFormat("en-US", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(now);
  const part = (type: string) => parts.find((p) => p.type === type)!.value;
  return `${part("year")}-${part("month")}-${part("day")}`;
}

export function shiftDay(day: string, amount: number) {
  const date = new Date(`${day}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + amount);
  return date.toISOString().slice(0, 10);
}

export function weekStart(day: string) {
  const weekday = new Date(`${day}T12:00:00Z`).getUTCDay();
  return shiftDay(day, -((weekday + 6) % 7));
}

export function clampDay(value: string | null, today: string) {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value) || value < "1000-01-01" || value > today) return today;
  const date = new Date(`${value}T12:00:00Z`);
  return Number.isNaN(date.getTime()) || date.toISOString().slice(0, 10) !== value ? today : value;
}

export function dayLabel(day: string) {
  return new Date(`${day}T12:00:00Z`).toLocaleDateString("en-US", { timeZone: "UTC", month: "short", day: "numeric" });
}
