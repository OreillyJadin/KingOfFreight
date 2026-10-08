import type { ChangeEvent } from "react";
import { loadFieldGroups, type LoadDraft } from "../load-form";

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
  return (
    <div className="space-y-5">
      {groups.map((group) => (
        <fieldset key={group.title}>
          <legend className="mb-2 text-xs font-bold uppercase tracking-[0.12em] text-slate-500">
            {group.title}
          </legend>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {group.fields.map(([key, label, type]) => (
              <label key={key} className="block">
                <span className="mb-1.5 block text-xs font-semibold text-slate-600">
                  {label}
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
              </label>
            ))}
          </div>
        </fieldset>
      ))}
    </div>
  );
}
