import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { PageHeading } from "../components/common";
import { Button, Card, Input, Select, Skeleton, Tabs } from "../components/ui";
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
    return (
      <Card className="space-y-5 p-5 sm:p-6">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-11 w-full" />
        <Skeleton className="h-11 w-full" />
        <Skeleton className="h-11 w-2/3" />
      </Card>
    );
  }
  return (
    <div>
      <PageHeading
        eyebrow="Workspace"
        title="Settings"
        description="Manage your broker details and driver check-in defaults."
      />
      <form onSubmit={submit} className="space-y-5">
        <Card as="section" className="p-5 sm:p-6">
          <h2 className="text-lg font-bold text-fg">Check-ins</h2>
          <div className="mt-5 grid gap-5 sm:grid-cols-2">
            <label className="block">
              <span className="mb-2 block text-sm font-semibold text-fg-2">
                Send driver check-in
              </span>
              <div className="flex items-center gap-2">
                <Input
                  type="number"
                  min={0}
                  max={720}
                  value={form.checkin_offset_minutes}
                  onChange={(event) => change("checkin_offset_minutes", Number(event.target.value))}
                  className="h-11 w-28"
                  required
                />
                <span className="text-sm text-fg-2">minutes after the pickup/delivery appointment</span>
              </div>
              <span className="mt-2 block text-xs text-muted">
                Applies to loads booked after you save. Already-scheduled check-ins keep their time.
              </span>
            </label>
            <label className="block">
              <span className="mb-2 block text-sm font-semibold text-fg-2">
                Alert me if no reply within
              </span>
              <div className="flex items-center gap-2">
                <Input
                  type="number"
                  min={5}
                  max={240}
                  value={form.no_reply_alert_minutes}
                  onChange={(event) => change("no_reply_alert_minutes", Number(event.target.value))}
                  className="h-11 w-28"
                  required
                />
                <span className="text-sm text-fg-2">minutes</span>
              </div>
              <span className="mt-2 block text-xs text-muted">
                The new window applies at the next scheduler tick.
              </span>
            </label>
            <fieldset>
              <legend className="mb-2 text-sm font-semibold text-fg-2">Default check-in method</legend>
              <Tabs
                items={(["sms", "email"] as const).map((channel) => ({
                  value: channel,
                  label: channel === "sms" ? "SMS" : "Email",
                }))}
                value={form.checkin_default_channel}
                onChange={(channel) => change("checkin_default_channel", channel)}
                ariaLabel="Default check-in method"
              />
              <p className="mt-2 text-xs text-muted">
                Applies to loads booked after you save.
              </p>
            </fieldset>
          </div>
        </Card>
        <Card as="section" className="p-5 sm:p-6">
          <h2 className="text-lg font-bold text-fg">Your details</h2>
          <p className="mt-1 text-sm text-muted">Shown in customer emails and driver texts.</p>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            {([
              ["broker_name", "Name"],
              ["broker_company", "Company"],
            ] as const).map(([key, label]) => (
              <label key={key}>
                <span className="mb-1.5 block text-sm font-semibold text-fg-2">{label}</span>
                <Input
                  value={form[key]}
                  onChange={(event) => change(key, event.target.value)}
                  maxLength={100}
                  minLength={1}
                  required
                  className="h-11"
                />
              </label>
            ))}
          </div>
        </Card>
        <Card as="section" className="p-5 sm:p-6">
          <h2 className="text-lg font-bold text-fg">Timezone</h2>
          <label className="mt-4 block max-w-md">
            <span className="mb-1.5 block text-sm font-semibold text-fg-2">Broker timezone</span>
            <Select
              value={form.broker_timezone}
              onChange={(event) => change("broker_timezone", event.target.value)}
              className="h-11"
            >
              {zoneOptions.map(([label, zone]) => (
                <option key={zone} value={zone}>{label} ({zone})</option>
              ))}
            </Select>
          </label>
          <p className="mt-2 text-xs text-muted">
            Changes affect display and new date/time inputs; stored dates remain unchanged.
          </p>
        </Card>
        {error && <p role="alert" className="rounded-xl bg-danger/10 p-3 text-sm text-danger-ink">{error}</p>}
        <Button
          type="submit"
          disabled={!dirty || save.isPending}
          loading={save.isPending}
          variant="primary"
        >
          {save.isPending ? "Saving…" : "Save settings"}
        </Button>
      </form>
    </div>
  );
}
