/* eslint-disable react-refresh/only-export-components */
import { useSearchParams } from "react-router-dom";
import { Tabs } from "../components/ui";
import { rangeForDays } from "./format";

export const rangePresets = [
  { value: "30", label: "30 days", days: 30 },
  { value: "90", label: "90 days", days: 90 },
  { value: "180", label: "6 months", days: 180 },
  { value: "365", label: "12 months", days: 365 },
  { value: "all", label: "All time", days: 0 },
] as const;

export type RangeValue = (typeof rangePresets)[number]["value"];

export function useRange(defaultValue: RangeValue = "90") {
  const [params, setParams] = useSearchParams();
  const raw = params.get("range") as RangeValue | null;
  const value: RangeValue =
    raw && rangePresets.some((preset) => preset.value === raw) ? raw : defaultValue;
  const preset = rangePresets.find((item) => item.value === value)!;
  const range = preset.days ? rangeForDays(preset.days) : {};

  function setValue(next: RangeValue) {
    const updated = new URLSearchParams(params);
    if (next === defaultValue) updated.delete("range");
    else updated.set("range", next);
    setParams(updated, { replace: true });
  }

  return { value, setValue, range, label: preset.label };
}

export function RangeTabs({
  value,
  onChange,
}: {
  value: RangeValue;
  onChange: (value: RangeValue) => void;
}) {
  return (
    <Tabs
      ariaLabel="Date range"
      value={value}
      onChange={onChange}
      items={rangePresets.map((preset) => ({ value: preset.value, label: preset.label }))}
    />
  );
}
