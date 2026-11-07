/* eslint-disable react-refresh/only-export-components */
import { useSearchParams } from "react-router-dom";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button, Tabs } from "../components/ui";
import type { DateRange } from "./api";
import { localIsoDay } from "./format";

const rangeValues = ["month", "year", "all"] as const;

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

export function useRange(defaultValue: RangeValue = "month") {
  const [params, setParams] = useSearchParams();
  const now = new Date();
  const currentMonth = currentMonthValue(now);
  const currentYear = now.getFullYear();
  const rawValue = params.get("period");
  const value: RangeValue = rangeValues.includes(rawValue as RangeValue)
    ? (rawValue as RangeValue)
    : defaultValue;
  const month = clampMonth(params.get("month"), currentMonth);
  const year = clampYear(params.get("year"), currentYear);
  let range: DateRange;

  if (value === "all") {
    range = { start: "2000-01-01" };
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
    value === "all" ? "All time" : value === "year" ? String(year) : monthLabel(month);

  function setValue(next: RangeValue) {
    const updated = new URLSearchParams(params);
    updated.delete("range");
    if (next === defaultValue) updated.delete("period");
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

  return { value, setValue, range, label, month, year, setMonth, setYear };
}

export function RangeTabs({
  value,
  onChange,
  month,
  year,
  setMonth,
  setYear,
}: {
  value: RangeValue;
  onChange: (value: RangeValue) => void;
  month: string;
  year: number;
  setMonth: (month: string) => void;
  setYear: (year: number) => void;
}) {
  const currentMonth = currentMonthValue(new Date());
  const currentYear = new Date().getFullYear();

  return (
    <div className="flex min-w-0 max-w-full flex-wrap items-center gap-2">
      <Tabs
        ariaLabel="Date range"
        value={value}
        onChange={onChange}
        items={[
          { value: "month", label: "Month" },
          { value: "year", label: "Year" },
          { value: "all", label: "All time" },
        ]}
      />
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
