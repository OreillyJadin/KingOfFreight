import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import KofEmailActionCard, { type EmailDraft } from "./KofEmailActionCard";
import { Button } from "./ui";
import { useCapabilities } from "../useCapabilities";

export default function KofEmailThread({ orderNo }: { orderNo: number }) {
  const capabilities = useCapabilities();
  const thread = useQuery({ queryKey: ["kof", "emails", orderNo], queryFn: () => api.kofEmails(orderNo), refetchInterval: 30000 });
  const [draft, setDraft] = useState<EmailDraft | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  async function compose() {
    setLoading(true); setError("");
    try { setDraft({ ...await api.kofEmailDraft(orderNo), state: "draft" }); }
    catch (issue) { setError(issue instanceof Error ? issue.message : "No dispatcher email is on file in KOF"); }
    finally { setLoading(false); }
  }
  if (!capabilities.data?.email_live && !thread.data?.length) return null;
  return <section className="space-y-3">
    <h3 className="text-sm font-semibold text-fg">Emails</h3>
    {capabilities.data?.email_live && <Button className="min-h-11" loading={loading} disabled={draft?.state === "draft" || draft?.state === "sending"} onClick={() => void compose()}>Email dispatcher</Button>}
    {error && <p role="alert" className="text-sm text-danger-ink">{error}</p>}
    {draft && capabilities.data?.email_live && <KofEmailActionCard action={draft} onSettings={() => {}} onChange={(update) => setDraft((value) => value ? { ...value, ...update } : value)} />}
    {thread.isError ? <p role="alert" className="text-sm text-danger-ink">{thread.error.message}<Button onClick={() => void thread.refetch()}>Retry</Button></p> : thread.isPending ? <p className="text-xs text-muted">Loading emails…</p> : !thread.data.length ? <p className="text-xs text-muted">No emails recorded for this order.</p> : <ol className="space-y-3">{thread.data.map((email) => <li key={email.id} className="rounded-xl border border-line bg-surface-2 p-3">
      <p className="text-xs text-muted">{email.direction} · {new Date(email.created_at).toLocaleString()}</p>
      <p className="break-words text-xs text-fg-2">{email.direction === "outbound" ? `To: ${email.to_addr || "—"}` : `From: ${email.from_addr || "—"}`}</p>
      <p className="mt-1 break-words text-sm font-semibold text-fg">{email.subject}</p><p className="mt-1 whitespace-pre-wrap break-words text-sm text-fg-2">{email.content}</p>
    </li>)}</ol>}
  </section>;
}
