import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { PageHeading } from "../components/common";
import { api } from "../api";
import type { BrokerPrefs, BrokerPrefsUpdate } from "../types";
import { setBrokerTimeZone } from "../utils";
import { useToast } from "../useToast";

const timezones = [
  ["Eastern", "America/New_York"],
  ["Central", "America/Chicago"],
  ["Mountain", "America/Denver"],
  ["Arizona", "America/Phoenix"],
  ["Pacific", "America/Los_Angeles"],
  ["Alaska", "America/Anchorage"],
  ["Hawaii", "Pacific/Honolulu"],
] as const;

const fields: (keyof BrokerPrefs)[] = [
  "broker_name",
  "broker_company",
  "broker_timezone",
  "checkin_offset_minutes",
  "no_reply_alert_minutes",
  "checkin_default_channel",
];

export default function Settings() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const query = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const [form, setForm] = useState<BrokerPrefs | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (query.data) setForm(query.data);
  }, [query.data]);
  const save = useMutation({
    mutationFn: (partial: BrokerPrefsUpdate) => api.updateSettings(partial),
    onSuccess: async (prefs) => {
      setForm(prefs);
      setBrokerTimeZone(prefs.broker_timezone);
      await queryClient.invalidateQueries({ queryKey: ["auth"] });
      await queryClient.invalidateQueries({ queryKey: ["settings"] });
      setError("");
      showToast("Settings saved.");
    },
    onError: (issue: Error) => setError(issue.message),
  });
  const dirty =
    form !== null &&
    query.data !== undefined &&
    fields.some((key) => form[key] !== query.data[key]);
  function change<K extends keyof BrokerPrefs>(key: K, value: BrokerPrefs[K]) {
    setForm((current) => (current ? { ...current, [key]: value } : current));
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!form || !query.data) return;
    const partial: BrokerPrefsUpdate = {};
    fields.forEach((key) => {
      if (form[key] !== query.data?.[key]) {
        Object.assign(partial, { [key]: form[key] });
      }
    });
    setError("");
    save.mutate(partial);
  }
  const zoneOptions = timezones.some(([, zone]) => zone === form?.broker_timezone)
    ? timezones
    : ([["Current timezone", form?.broker_timezone ?? "America/Chicago"], ...timezones] as const);
  if (query.isPending || !form) {
    return <div className="py-16 text-center text-sm text-slate-500">Loading settings…</div>;
  }
  return (
    <div>
      <PageHeading
        eyebrow="Workspace"
        title="Settings"
        description="Manage your broker details and driver check-in defaults."
      />
      <form onSubmit={submit} className="space-y-5">
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-card sm:p-6">
          <h2 className="text-lg font-bold text-slate-900">Check-ins</h2>
          <div className="mt-5 grid gap-5 sm:grid-cols-2">
            <label className="block">
              <span className="mb-2 block text-sm font-semibold text-slate-700">
                Send driver check-in
              </span>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  min={0}
                  max={720}
                  value={form.checkin_offset_minutes}
                  onChange={(event) => change("checkin_offset_minutes", Number(event.target.value))}
                  className="h-11 w-28 rounded-xl border border-slate-300 px-3 text-sm"
                  required
                />
                <span className="text-sm text-slate-600">minutes after the pickup/delivery appointment</span>
              </div>
              <span className="mt-2 block text-xs text-slate-500">
                Applies to loads booked after you save. Already-scheduled check-ins keep their time.
              </span>
            </label>
            <label className="block">
              <span className="mb-2 block text-sm font-semibold text-slate-700">
                Alert me if no reply within
              </span>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  min={5}
                  max={240}
                  value={form.no_reply_alert_minutes}
                  onChange={(event) => change("no_reply_alert_minutes", Number(event.target.value))}
                  className="h-11 w-28 rounded-xl border border-slate-300 px-3 text-sm"
                  required
                />
                <span className="text-sm text-slate-600">minutes</span>
              </div>
              <span className="mt-2 block text-xs text-slate-500">
                The new window applies at the next scheduler tick.
              </span>
            </label>
            <fieldset>
              <legend className="mb-2 text-sm font-semibold text-slate-700">Default check-in method</legend>
              <div className="inline-flex rounded-xl bg-slate-100 p-1">
                {(["sms", "email"] as const).map((channel) => (
                  <button
                    key={channel}
                    type="button"
                    aria-pressed={form.checkin_default_channel === channel}
                    onClick={() => change("checkin_default_channel", channel)}
                    className={`min-h-10 rounded-lg px-4 text-sm font-semibold capitalize ${
                      form.checkin_default_channel === channel
                        ? "bg-white text-blue-700 shadow-sm"
                        : "text-slate-600"
                    }`}
                  >
                    {channel === "sms" ? "SMS" : "Email"}
                  </button>
                ))}
              </div>
              <p className="mt-2 text-xs text-slate-500">
                Applies to loads booked after you save.
              </p>
            </fieldset>
          </div>
        </section>
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-card sm:p-6">
          <h2 className="text-lg font-bold text-slate-900">Your details</h2>
          <p className="mt-1 text-sm text-slate-500">Shown in customer emails and driver texts.</p>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            {([
              ["broker_name", "Name"],
              ["broker_company", "Company"],
            ] as const).map(([key, label]) => (
              <label key={key}>
                <span className="mb-1.5 block text-sm font-semibold text-slate-700">{label}</span>
                <input
                  value={form[key]}
                  onChange={(event) => change(key, event.target.value)}
                  maxLength={100}
                  minLength={1}
                  required
                  className="h-11 w-full rounded-xl border border-slate-300 px-3 text-sm"
                />
              </label>
            ))}
          </div>
        </section>
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-card sm:p-6">
          <h2 className="text-lg font-bold text-slate-900">Timezone</h2>
          <label className="mt-4 block max-w-md">
            <span className="mb-1.5 block text-sm font-semibold text-slate-700">Broker timezone</span>
            <select
              value={form.broker_timezone}
              onChange={(event) => change("broker_timezone", event.target.value)}
              className="h-11 w-full rounded-xl border border-slate-300 bg-white px-3 text-sm"
            >
              {zoneOptions.map(([label, zone]) => (
                <option key={zone} value={zone}>{label} ({zone})</option>
              ))}
            </select>
          </label>
          <p className="mt-2 text-xs text-slate-500">
            Changes affect display and new date/time inputs; stored dates remain unchanged.
          </p>
        </section>
        {error && <p role="alert" className="rounded-xl bg-rose-50 p-3 text-sm text-rose-700">{error}</p>}
        <button
          type="submit"
          disabled={!dirty || save.isPending}
          className="min-h-11 rounded-xl bg-blue-600 px-5 text-sm font-bold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {save.isPending ? "Saving…" : "Save settings"}
        </button>
      </form>
    </div>
  );
}
