import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import { useToast } from "../useToast";
import { Button, Card, Field, Input, Skeleton } from "./ui";

const emptyCredentials = { account_sid: "", auth_token: "", from_number: "" };
const phonePattern = "\\+[1-9][0-9]{1,14}";

export default function TwilioSettings() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const connection = useQuery({ queryKey: ["twilio", "connection"], queryFn: api.twilioConnection });
  const [credentials, setCredentials] = useState(emptyCredentials);
  const [to, setTo] = useState("");
  const [error, setError] = useState("");
  const webhook = `${window.location.origin}/api/webhooks/twilio/sms`;
  const save = useMutation({
    mutationFn: api.saveTwilioConnection,
    onSuccess: (data) => {
      setCredentials(emptyCredentials);
      setError("");
      queryClient.setQueryData(["twilio", "connection"], data);
      void queryClient.invalidateQueries({ queryKey: ["integrations", "status"] });
      showToast("Twilio settings saved.");
    },
    onError: (issue: Error) => { setCredentials((value) => ({ ...value, auth_token: "" })); setError(issue.message); },
  });
  const remove = useMutation({
    mutationFn: api.removeTwilioConnection,
    onSuccess: async () => {
      setCredentials(emptyCredentials);
      setError("");
      await queryClient.invalidateQueries({ queryKey: ["twilio", "connection"] });
      void queryClient.invalidateQueries({ queryKey: ["integrations", "status"] });
      showToast("App Twilio settings removed. Server settings are the fallback.");
    },
    onError: (issue: Error) => setError(issue.message),
  });
  const test = useMutation({
    mutationFn: api.testTwilio,
    onSuccess: () => { setError(""); showToast("Test text accepted by Twilio. Check your phone."); },
    onError: (issue: Error) => setError(issue.message),
  });
  const busy = save.isPending || remove.isPending || test.isPending;
  const data = connection.data;

  async function copyWebhook() {
    try { await navigator.clipboard.writeText(webhook); showToast("Webhook URL copied."); }
    catch { showToast("Could not copy. Select and copy the URL below.", "error"); }
  }

  return (
    <Card as="section" id="twilio" className="scroll-mt-24 p-5 sm:p-6" aria-labelledby="twilio-title">
      <h2 id="twilio-title" className="text-lg font-bold text-fg">Texting (Twilio)</h2>
      <p className="mt-1 text-sm leading-relaxed text-muted">Connect Twilio to send driver check-ins and receive replies. Sending texts may incur Twilio charges.</p>
      {connection.isPending ? <Skeleton className="mt-4 h-11 w-full" /> : connection.isError ? (
        <div role="alert" className="mt-4 text-sm text-danger-ink"><p>{connection.error.message}</p><Button className="mt-2 min-h-11" onClick={() => void connection.refetch()}>Retry</Button></div>
      ) : <>
        <p className="mt-4 text-sm font-semibold text-fg-2">{data?.source === "app" ? "Saved in app" : data?.source === "env" ? "Using server settings — save here to override" : "Not set up"}</p>
        {data?.configured && <p className="mt-1 text-sm text-muted tabular-nums">Account {data.account_sid} · From {data.from_number}</p>}
        <p className="mt-1 text-xs text-muted">{data?.sms === "twilio" ? "Twilio is active. Credentials have not been verified; send a test below." : "Mock texting is active — scheduled messages do not send real SMS."}</p>
        <form className="mt-4 space-y-3" onSubmit={(event) => { event.preventDefault(); setError(""); save.mutate({ account_sid: credentials.account_sid.trim(), auth_token: credentials.auth_token.trim(), from_number: credentials.from_number.trim() }); }}>
          <Field label="Account SID" htmlFor="twilio-sid"><Input id="twilio-sid" value={credentials.account_sid} onChange={(event) => setCredentials({ ...credentials, account_sid: event.target.value })} required pattern="AC[0-9a-fA-F]{32}" maxLength={34} autoComplete="off" autoCapitalize="none" spellCheck={false} disabled={busy} placeholder="AC…" className="min-h-11 text-base" /></Field>
          <Field label="Auth Token" htmlFor="twilio-token"><Input id="twilio-token" type="password" value={credentials.auth_token} onChange={(event) => setCredentials({ ...credentials, auth_token: event.target.value })} required maxLength={500} autoComplete="new-password" autoCapitalize="none" spellCheck={false} disabled={busy} className="min-h-11 text-base" /></Field>
          <Field label="From number" htmlFor="twilio-from" hint="Twilio SMS-capable number in E.164 format, e.g. +15551234567."><Input id="twilio-from" type="tel" value={credentials.from_number} onChange={(event) => setCredentials({ ...credentials, from_number: event.target.value })} required pattern={phonePattern} maxLength={16} autoComplete="off" disabled={busy} placeholder="+15551234567" className="min-h-11 text-base" /></Field>
          <p className="text-xs leading-relaxed text-muted">The Auth Token is encrypted and never displayed. Enter all three fields to save or replace. App settings override server settings; removing them falls back to server settings.</p>
          <div className="flex flex-wrap gap-2"><Button type="submit" variant="primary" className="min-h-11" loading={save.isPending} disabled={busy || !credentials.account_sid.trim() || !credentials.auth_token.trim() || !credentials.from_number.trim()}>Save</Button>{data?.source === "app" && <Button className="min-h-11" loading={remove.isPending} disabled={busy} onClick={() => { setError(""); remove.mutate(); }}>Remove</Button>}</div>
        </form>
        <form className="mt-5 space-y-3 border-t border-line pt-5" onSubmit={(event) => { event.preventDefault(); setError(""); test.mutate(to.trim()); }}>
          <Field label="Send a test to" htmlFor="twilio-test-to" hint="Sends one real SMS using the saved/server settings, even if mock texting is selected."><Input id="twilio-test-to" type="tel" value={to} onChange={(event) => setTo(event.target.value)} required pattern={phonePattern} maxLength={16} disabled={busy} placeholder="+15551234567" className="min-h-11 text-base" /></Field>
          <Button type="submit" className="min-h-11" disabled={busy || !data?.configured || !to.trim()} loading={test.isPending}>Send test text</Button>
        </form>
      </>}
      {error && <p role="alert" className="mt-4 break-words text-sm text-danger-ink">{error}</p>}
      <div className="mt-5 border-t border-line pt-5">
        <p className="text-sm font-semibold text-fg-2">Incoming-message webhook</p>
        <p className="mt-1 text-xs leading-relaxed text-muted">Phone Number → Messaging → “A message comes in” · select HTTP POST.</p>
        <p className="mt-3 select-all break-all rounded-xl border border-line bg-surface-2 p-3 text-xs text-fg-2">{webhook}</p>
        <Button className="mt-2 min-h-11" onClick={() => void copyWebhook()}>Copy webhook URL</Button>
      </div>
    </Card>
  );
}
