/* eslint-disable react-refresh/only-export-components */
import { useSearchParams } from "react-router-dom";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button, Tabs } from "../components/ui";
import type { DateRange } from "./api";
import { localIsoDay } from "./format";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { brokerDay, clampDay, dayLabel, shiftDay, weekStart } from "./rangeDates";

const rangeValues = ["day", "week", "month", "year", "all"] as const;

export type RangeValue = (typeof rangeValues)[number];

function currentMonthValue(now: Date) {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

function clampMonth(value: string | null, currentMonth: string) {
  if (!value || !/^\d{4}-\d{2}$/.test(value)) return currentMonth;
  const year = Number(value.slice(0, 4));
  const month = Number(value.slice(5, 7));
  if (year < 1000 || month < 1 || month > 12) return currentMonth;
  return value > currentMonth ? currentMonth : value;
}

function clampYear(value: string | null, currentYear: number) {
  if (!value || !/^\d{4}$/.test(value)) return currentYear;
  const year = Number(value);
  return year < 1000 || year > currentYear ? currentYear : year;
}

function monthLabel(value: string) {
  const year = Number(value.slice(0, 4));
  const month = Number(value.slice(5, 7));
  return new Date(year, month - 1, 1).toLocaleDateString(undefined, {
    month: "long",
    year: "numeric",
  });
}

function shiftMonth(value: string, amount: number) {
  const year = Number(value.slice(0, 4));
  const month = Number(value.slice(5, 7));
  return currentMonthValue(new Date(year, month - 1 + amount, 1));
}

export function useRange(defaultValue: RangeValue = "month", remember = false) {
  const [params, setParams] = useSearchParams();
  const auth = useQuery({ queryKey: ["auth"], queryFn: api.me });
  const today = brokerDay(auth.data?.broker_timezone ?? "America/Chicago");
  const now = new Date(`${today}T12:00:00`);
  const currentMonth = currentMonthValue(now);
  const currentYear = now.getFullYear();
  let saved: string | null = null;
  try { if (remember) saved = localStorage.getItem("dashboard-period"); } catch { saved = null; }
  const rawValue = params.get("period") ?? saved;
  const value: RangeValue = rangeValues.includes(rawValue as RangeValue)
    ? (rawValue as RangeValue)
    : defaultValue;
  const month = clampMonth(params.get("month"), currentMonth);
  const year = clampYear(params.get("year"), currentYear);
  const day = clampDay(params.get("day"), today);
  const week = weekStart(clampDay(params.get("week"), today));
  const currentWeek = weekStart(today);
  let range: DateRange;

  if (value === "day") {
    range = { start: day, end: day };
  } else if (value === "week") {
    range = { start: week, end: shiftDay(week, 6) };
  } else if (value === "all") {
    range = { start: "2000-01-01", end: today };
  } else if (value === "year") {
    range = {
      start: `${year}-01-01`,
      end: `${year}-12-31`,
    };
  } else {
    const monthYear = Number(month.slice(0, 4));
    const monthNumber = Number(month.slice(5, 7));
    range = {
      start: localIsoDay(new Date(monthYear, monthNumber - 1, 1)),
      end: localIsoDay(new Date(monthYear, monthNumber, 0)),
    };
  }

  const label =
    value === "day" ? (day === today ? "Today" : dayLabel(day)) :
    value === "week" ? (week === currentWeek ? "This week" : `${dayLabel(week)} – ${dayLabel(shiftDay(week, 6))}`) :
    value === "all" ? "All time" : value === "year" ? String(year) : monthLabel(month);

  function setValue(next: RangeValue) {
    try { if (remember) localStorage.setItem("dashboard-period", next); } catch { /* Storage may be unavailable. */ }
    const updated = new URLSearchParams(params);
    updated.delete("range");
    if (next === defaultValue && !remember) updated.delete("period");
    else updated.set("period", next);
    if (params.has("month") && params.get("month") !== month) {
      if (month === currentMonth) updated.delete("month");
      else updated.set("month", month);
    }
    if (params.has("year") && params.get("year") !== String(year)) {
      if (year === currentYear) updated.delete("year");
      else updated.set("year", String(year));
    }
    setParams(updated, { replace: true });
  }

  function setMonth(next: string) {
    const selectedMonth = clampMonth(next, currentMonth);
    const updated = new URLSearchParams(params);
    updated.delete("range");
    if (selectedMonth === currentMonth) updated.delete("month");
    else updated.set("month", selectedMonth);
    setParams(updated, { replace: true });
  }

  function setYear(next: number) {
    const selectedYear = clampYear(String(next), currentYear);
    const updated = new URLSearchParams(params);
    updated.delete("range");
    if (selectedYear === currentYear) updated.delete("year");
    else updated.set("year", String(selectedYear));
    setParams(updated, { replace: true });
  }

  function shiftPeriod(amount: number) {
    const updated = new URLSearchParams(params);
    updated.set(value === "day" ? "day" : "week", shiftDay(value === "day" ? day : week, amount * (value === "day" ? 1 : 7)));
    setParams(updated, { replace: true });
  }

  return { value, setValue, range, label, month, year, setMonth, setYear, today, shiftPeriod, canNext: value === "day" ? day < today : week < currentWeek };
}

export function RangeTabs({
  value,
  onChange,
  month,
  year,
  setMonth,
  setYear,
  daily,
}: {
  value: RangeValue;
  onChange: (value: RangeValue) => void;
  month: string;
  year: number;
  setMonth: (month: string) => void;
  setYear: (year: number) => void;
  daily?: { label: string; today: string; shiftPeriod: (amount: number) => void; canNext: boolean };
}) {
  const today = daily?.today ?? brokerDay("America/Chicago");
  const currentMonth = today.slice(0, 7);
  const currentYear = Number(today.slice(0, 4));

  return (
    <div className="flex min-w-0 max-w-full flex-wrap items-center gap-2">
      <Tabs
        ariaLabel="Date range"
        value={value}
        onChange={onChange}
        items={[
          ...(daily ? [{ value: "day" as const, label: "Day" }, { value: "week" as const, label: "Week" }] : []),
          { value: "month", label: "Month" },
          { value: "year", label: "Year" },
          { value: "all", label: "All time" },
        ]}
      />
      {daily && (value === "day" || value === "week") && (
        <div role="group" aria-label={`Choose ${value}`} className="inline-flex h-12 max-w-full items-center gap-1 rounded-xl border border-line bg-surface px-1">
          <Button variant="ghost" size="sm" className="h-11 w-11 px-0" aria-label={`Previous ${value}`} onClick={() => daily.shiftPeriod(-1)}><ChevronLeft className="h-4 w-4" /></Button>
          <span className="text-center text-sm font-semibold">{daily.label}</span>
          <Button variant="ghost" size="sm" className="h-11 w-11 px-0" aria-label={`Next ${value}`} disabled={!daily.canNext} onClick={() => daily.shiftPeriod(1)}><ChevronRight className="h-4 w-4" /></Button>
        </div>
      )}
      {value === "month" && (
        <div
          role="group"
          aria-label="Choose month"
          className="inline-flex h-12 max-w-full items-center gap-1 rounded-xl border border-line bg-surface px-1"
        >
          <Button
            variant="ghost"
            size="sm"
            className="h-11 w-11 px-0 md:h-9 md:w-9"
            aria-label="Previous month"
            onClick={() => setMonth(shiftMonth(month, -1))}
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="min-w-[120px] text-center text-sm font-semibold text-fg">
            {monthLabel(month)}
          </span>
          <Button
            variant="ghost"
            size="sm"
            className="h-11 w-11 px-0 md:h-9 md:w-9"
            aria-label="Next month"
            disabled={month >= currentMonth}
            onClick={() => setMonth(shiftMonth(month, 1))}
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      )}
      {value === "year" && (
        <div
          role="group"
          aria-label="Choose year"
          className="inline-flex h-12 max-w-full items-center gap-1 rounded-xl border border-line bg-surface px-1"
        >
          <Button
            variant="ghost"
            size="sm"
            className="h-11 w-11 px-0 md:h-9 md:w-9"
            aria-label="Previous year"
            onClick={() => setYear(year - 1)}
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="min-w-[72px] text-center text-sm font-semibold tabular-nums text-fg">
            {year}
          </span>
          <Button
            variant="ghost"
            size="sm"
            className="h-11 w-11 px-0 md:h-9 md:w-9"
            aria-label="Next year"
            disabled={year >= currentYear}
            onClick={() => setYear(year + 1)}
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      )}
    </div>
  );
}
