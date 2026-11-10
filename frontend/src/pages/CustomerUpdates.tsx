import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Mail } from "lucide-react";
import { api, type CustomerUpdateDraft } from "../api";
import { EmptyState, ErrorState, PageHeading } from "../components/common";
import { Badge, Button, Card, Field, Input, Skeleton, Textarea } from "../components/ui";
import { formatDateTime } from "../utils";
import { useToast } from "../useToast";
import { useCapabilities } from "../useCapabilities";

function UpdateCard({ row }: { row: CustomerUpdateDraft }) {
  const cache = useQueryClient();
  const { showToast } = useToast();
  const [draft, setDraft] = useState(row);
  const [toEdited, setToEdited] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const stale = row.version > draft.version;
  const locked = Boolean(row.send_started_at);
  const latest = [...row.source_refs].sort((a, b) => b.received_at.localeCompare(a.received_at))[0];

  async function act(action: "save" | "approve" | "dismiss") {
    setBusy(true); setError("");
    try {
      if (action === "dismiss") {
        await api.dismissCustomerUpdate(row.id, draft.version);
      } else {
        const saved = await api.editCustomerUpdate(row.id, { version: draft.version, to_email: draft.to_email, subject: draft.subject, body: draft.body });
        setDraft(saved);
        setToEdited(false);
        if (action === "approve") await api.approveCustomerUpdate(saved.id, saved.version);
      }
      showToast(action === "dismiss" ? "Customer update dismissed." : action === "save" ? "Draft saved. Nothing was sent." : "Customer update sent.");
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not update this draft");
    } finally {
      await cache.invalidateQueries({ queryKey: ["customer-updates"] });
      setBusy(false);
    }
  }

  return <Card className="space-y-4 p-4 sm:p-6">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div><Link className="inline-flex min-h-11 items-center font-semibold underline underline-offset-4" to={`/loads?order=${row.order_no}`}>Order #{row.order_no}</Link><p className="text-sm text-muted">{row.customer || "Customer not recorded"}</p></div>
      <Badge tone="neutral">Needs approval</Badge>
    </div>
    {latest && <div className="rounded-xl border border-line bg-surface-2 p-3"><p className="mb-2 text-xs text-muted">Carrier message · {latest.channel.toUpperCase()} · <time dateTime={latest.received_at}>{formatDateTime(latest.received_at)}</time></p><blockquote className="whitespace-pre-wrap break-words text-sm text-fg-2">{latest.excerpt}</blockquote></div>}
    <div><p className="text-xs font-semibold uppercase tracking-wide text-muted">AI summary · unconfirmed</p><p className="mt-1 text-sm">{row.summary}</p><p className="mt-1 text-xs text-muted">{row.status.replaceAll("_", " ")} · {Math.round(row.confidence * 100)}% confidence{row.eta ? ` · ETA: ${row.eta}` : ""}</p></div>
    {stale && <div role="status" className="rounded-xl border border-line p-3 text-sm">A newer carrier update changed this draft. Review it before sending.<Button variant="secondary" className="mt-2" onClick={() => { setDraft({ ...row, to_email: toEdited ? draft.to_email : row.to_email }); setError(""); }}>Load latest preview</Button></div>}
    {locked && <p role="status" className="text-sm text-warn-ink">{row.error || "Sending started. If delivery is uncertain, check Sent mail before dismissing. Resending is blocked to prevent duplicates."}</p>}
    <fieldset disabled={busy || locked || stale} className="space-y-3">
      <Field label="To" htmlFor={`to-${row.id}`}><Input id={`to-${row.id}`} className="min-h-11 text-base" type="email" autoComplete="email" placeholder="customer@company.com" value={draft.to_email} onChange={e => { setToEdited(true); setDraft({ ...draft, to_email: e.target.value }); }} /></Field>
      <Field label="Subject" htmlFor={`subject-${row.id}`}><Input id={`subject-${row.id}`} className="min-h-11 text-base" value={draft.subject} maxLength={500} onChange={e => setDraft({ ...draft, subject: e.target.value })} /></Field>
      <Field label="Exact email preview" htmlFor={`body-${row.id}`}><Textarea id={`body-${row.id}`} className="text-base" rows={10} maxLength={20000} value={draft.body} onChange={e => setDraft({ ...draft, body: e.target.value })} /></Field>
    </fieldset>
    {error && <p role="alert" className="text-sm text-danger-ink">{error}</p>}
    <div className="flex flex-wrap gap-2">
      <Button variant="primary" disabled={busy || stale || locked || !draft.to_email.trim() || !draft.subject.trim() || !draft.body.trim()} onClick={() => void act("approve")}>{busy ? "Working…" : "Approve & Send"}</Button>
      <Button variant="secondary" disabled={busy || stale || locked} onClick={() => void act("save")}>Save draft</Button>
      <Button variant="ghost" disabled={busy || stale} onClick={() => void act("dismiss")}>Dismiss</Button>
    </div>
    <p className="text-xs text-muted">Only the exact To, subject and body above are sent after you approve. The recipient is remembered for this customer.</p>
  </Card>;
}

export default function CustomerUpdates() {
  const capabilities = useCapabilities();
  const query = useQuery({ queryKey: ["customer-updates"], queryFn: api.customerUpdates, refetchInterval: 30000, enabled: capabilities.data?.email_live === true });
  useEffect(() => { document.title = "Customer updates · Fifth Wheel"; }, []);
  if (!capabilities.data?.email_live) return <p className="text-sm text-muted">Connect Outlook in <Link className="underline" to="/settings">Settings</Link> to turn this on.</p>;
  return <div className="mx-auto max-w-3xl space-y-5">
    <PageHeading eyebrow="Approval queue" title="Customer updates" description="Carrier updates to pass along. Review and edit every email before approving." />
    {query.isPending ? <Skeleton className="h-80" /> : query.isError ? <ErrorState message="Could not load customer updates" onRetry={() => void query.refetch()} /> : <>
      <p aria-live="polite" className="text-sm text-muted">{query.data.count} awaiting approval</p>
      {query.data.drafts.length ? query.data.drafts.map(row => <UpdateCard key={row.id} row={row} />) : <EmptyState icon={Mail} title="All caught up" description="Matched carrier status updates will appear here. Nothing is sent automatically." />}
    </>}
  </div>;
}
