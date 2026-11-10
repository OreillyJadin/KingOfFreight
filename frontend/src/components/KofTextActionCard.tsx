import { useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type KofTextAction } from "../api";
import { Button, Card, Textarea } from "./ui";

export type TextDraft = KofTextAction & {
  state: "draft" | "sending" | "sent" | "failed" | "cancelled";
  error?: string;
};

export default function KofTextActionCard({ action, onChange }: {
  action: TextDraft; onChange: (update: Partial<TextDraft>) => void; onSettings: () => void;
}) {
  const queryClient = useQueryClient();
  const status = useQuery({ queryKey: ["integrations", "status"], queryFn: api.integrationsStatus });
  const busy = useRef(false);
  const editable = action.state === "draft";

  async function send() {
    if (!editable || busy.current || !action.body.trim() || !status.data?.sms_live) return;
    busy.current = true;
    onChange({ state: "sending", error: undefined });
    try {
      const result = await api.sendKofText(action.order_no, action.recipient, action.body);
      onChange({ state: result.status === "sent" ? "sent" : "failed", error: result.error ?? undefined });
      void queryClient.invalidateQueries({ queryKey: ["kof", "messages", action.order_no] });
    } catch (issue) {
      onChange({ state: "failed", error: `${issue instanceof Error ? issue.message : "Unable to send"}. Check the order's Messages before trying again.` });
    } finally { busy.current = false; }
  }

  if (!status.data?.sms_live) return null;
  return (
    <Card className="mt-4 space-y-3 p-4">
      <h4 className="text-sm font-semibold text-fg">Review text · KOF #{action.order_no}</h4>
      <p className="break-words text-xs text-fg-2">To: {action.to_label} ({action.recipient})</p>
      {status.isError && <p className="text-xs text-danger-ink">Could not check texting setup. <Button className="min-h-11" onClick={() => void status.refetch()}>Retry</Button></p>}
      <label className="block"><span className="mb-2 block text-xs font-semibold text-fg-2">Exact message to send</span><Textarea rows={6} value={action.body} maxLength={1600} disabled={!editable} onChange={(event) => onChange({ body: event.target.value })} className="resize-y text-base" /></label>
      {editable && <p className="text-xs text-muted">Nothing has been sent. Review or edit this preview, then tap Send to approve.</p>}
      {(editable || action.state === "sending") && <div className="flex flex-wrap gap-2"><Button variant="primary" className="min-h-11" disabled={!editable || !action.body.trim() || !status.data || status.isError} loading={action.state === "sending"} onClick={() => void send()}>Send</Button><Button className="min-h-11" disabled={!editable} onClick={() => onChange({ state: "cancelled" })}>Cancel</Button></div>}
      {action.state === "sent" && <p role="status" className="text-sm text-ok-ink">Sent — accepted by the SMS provider.</p>}
      {action.state === "cancelled" && <p role="status" className="text-sm text-muted">Cancelled — nothing sent.</p>}
      {action.state === "failed" && <p role="alert" className="break-words text-sm text-danger-ink">Failed: {action.error || "The provider could not send this text."}</p>}
    </Card>
  );
}
