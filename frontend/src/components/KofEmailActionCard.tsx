import { useRef } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type KofEmailAction } from "../api";
import { Button, Card, Input, Textarea } from "./ui";

export type EmailDraft = KofEmailAction & { state: "draft" | "sending" | "sent" | "failed" | "cancelled"; error?: string };

export default function KofEmailActionCard({ action, onChange, onSettings }: { action: EmailDraft; onChange: (update: Partial<EmailDraft>) => void; onSettings: () => void }) {
  const status = useQuery({ queryKey: ["integrations", "status"], queryFn: api.integrationsStatus });
  const client = useQueryClient();
  const busy = useRef(false);
  const editable = action.state === "draft";
  const tagged = new RegExp(`Order #${action.order_no}(?!\\d)`, "i").test(action.subject);
  async function send() {
    if (!editable || busy.current || !tagged) return;
    busy.current = true;
    onChange({ state: "sending", error: undefined });
    try {
      await api.sendKofEmail(action);
      onChange({ state: "sent" });
      void client.invalidateQueries({ queryKey: ["kof", "emails", action.order_no] });
    } catch (error) {
      onChange({ state: "failed", error: `${error instanceof Error ? error.message : "Delivery unconfirmed"}. Check Sent mail before trying again.` });
    } finally { busy.current = false; }
  }
  return <Card className="mt-4 space-y-3 p-4">
    <h4 className="text-sm font-semibold text-fg">Review email · KOF #{action.order_no}</h4>
    <p className="break-words text-xs text-fg-2">To: {action.to_label} ({action.recipient})</p>
    {status.data?.email === "mock" && <p className="text-xs text-warn-ink">Email not set up — this won't actually send. <Link to="/settings" onClick={onSettings} className="underline">Open Settings</Link></p>}
    {status.isError && <p className="text-xs text-danger-ink">Could not check email setup. <Button onClick={() => void status.refetch()}>Retry</Button></p>}
    <label className="block text-xs font-semibold text-fg-2">Subject<Input className="mt-2 min-h-11 text-base" value={action.subject} maxLength={450} disabled={!editable} onChange={(event) => onChange({ subject: event.target.value })} /></label>
    {!tagged && <p className="text-xs text-warn-ink">Keep Order #{action.order_no} in the subject so replies match this order.</p>}
    <label className="block text-xs font-semibold text-fg-2">Exact email to send<Textarea className="mt-2 text-base" rows={8} value={action.body} maxLength={20000} disabled={!editable} onChange={(event) => onChange({ body: event.target.value })} /></label>
    {editable && <p className="text-xs text-muted">Nothing has been sent. Review the exact preview, then tap Send to approve.</p>}
    {(editable || action.state === "sending") && <div className="flex gap-2"><Button variant="primary" className="min-h-11" loading={action.state === "sending"} disabled={!editable || !tagged || !action.body.trim() || !status.data || status.isError} onClick={() => void send()}>Send</Button><Button className="min-h-11" disabled={!editable} onClick={() => onChange({ state: "cancelled" })}>Cancel</Button></div>}
    {action.state === "sent" && <p role="status" className="text-sm text-ok-ink">{status.data?.email === "mock" ? "Recorded in mock mode — no real email sent." : "Sent — accepted by the email provider."}</p>}
    {action.state === "cancelled" && <p role="status" className="text-sm text-muted">Cancelled — nothing sent.</p>}
    {action.state === "failed" && <p role="alert" className="break-words text-sm text-danger-ink">{action.error}</p>}
  </Card>;
}
