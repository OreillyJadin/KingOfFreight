import type { ChangeEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { loadFieldGroups, type LoadDraft } from "../load-form";
import {
  brokerZoneLabel,
  formatShortDateTime,
  getBrokerTimeZone,
  zonedInputToDate,
} from "../utils";

export default function LoadFields({
  value,
  onChange,
  includeDriver = true,
}: {
  value: LoadDraft;
  onChange: (key: string, next: string) => void;
  includeDriver?: boolean;
}) {
  const groups = includeDriver ? loadFieldGroups : loadFieldGroups.slice(0, 2);
  const timezones = useQuery({
    queryKey: ["stop-timezones"],
    queryFn: api.stopTimezones,
    staleTime: Infinity,
  });
  const metadata = timezones.data;
  const brokerTimezone = getBrokerTimeZone();
  return (
    <div className="space-y-5">
      {groups.map((group) => (
        <fieldset key={group.title}>
          <legend className="mb-2 text-xs font-bold uppercase tracking-[0.12em] text-slate-500">
            {group.title}
          </legend>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {group.fields.map(([key, label, type]) => (
              (() => {
                const stop =
                  key === "pickup_datetime"
                    ? "pickup"
                    : key === "delivery_datetime"
                      ? "delivery"
                      : null;
                const timezoneKey = stop ? `${stop}_timezone` : null;
                const state = stop ? value[`${stop}_state`]?.trim() : "";
                const stateTimezone = state
                  ? metadata?.states[state.toUpperCase()]
                  : undefined;
                const timezone = stop
                  ? value[timezoneKey!] || stateTimezone || brokerTimezone
                  : brokerTimezone;
                const zoneLabel = metadata?.zones.find(
                  (zone) => zone.id === stateTimezone,
                )?.label;
                const autoLabel = stateTimezone
                  ? `Auto (${zoneLabel ?? stateTimezone}, from ${state})`
                  : `Auto (${brokerZoneLabel()})`;
                let preview = "";
                if (
                  stop &&
                  value[key] &&
                  timezone !== brokerTimezone
                ) {
                  const date = zonedInputToDate(value[key], timezone);
                  if (!Number.isNaN(date.getTime())) {
                    preview = formatShortDateTime(date.toISOString());
                  }
                }
                const datetimeLabel =
                  stop === "pickup"
                    ? "Pickup date & time (facility local)"
                    : "Delivery date & time (facility local)";
                return (
                  <label key={key} className="block">
                    <span className="mb-1.5 block text-xs font-semibold text-slate-600">
                      {stop ? datetimeLabel : label}
                    </span>
                    <input
                      type={type}
                      step={type === "number" ? "any" : undefined}
                      value={value[key] ?? ""}
                      onChange={(event: ChangeEvent<HTMLInputElement>) =>
                        onChange(key, event.target.value)
                      }
                      className="h-10 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                    />
                    {stop && (
                      <div className="mt-1.5">
                        <select
                          aria-label={`${stop} facility timezone`}
                          value={value[timezoneKey!] ?? ""}
                          onChange={(event) =>
                            onChange(timezoneKey!, event.target.value)
                          }
                          className="h-9 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-700 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                        >
                          <option value="">{autoLabel}</option>
                          {metadata?.zones.map((zone) => (
                            <option key={zone.id} value={zone.id}>
                              {zone.label}
                            </option>
                          ))}
                          {value[timezoneKey!] &&
                            !metadata?.zones.some(
                              (zone) => zone.id === value[timezoneKey!],
                            ) && (
                              <option value={value[timezoneKey!]}>
                                {value[timezoneKey!]}
                              </option>
                            )}
                        </select>
                        {preview && (
                          <p className="mt-1 text-xs text-slate-500">= {preview}</p>
                        )}
                      </div>
                    )}
                  </label>
                );
              })()
            ))}
          </div>
        </fieldset>
      ))}
    </div>
  );
}
