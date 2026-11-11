import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useToast } from "../useToast";
import { Button, Card, Field, Input, Skeleton } from "./ui";

export default function OutlookSettings({ isAdmin = false }: { isAdmin?: boolean }) {
  const cache = useQueryClient();
  const { showToast } = useToast();
  const [params] = useSearchParams();
  const query = useQuery({ queryKey: ["outlook", "connection"], queryFn: api.outlookConnection });
  const [clientId, setClientId] = useState("");
  const [secret, setSecret] = useState("");
  const [error, setError] = useState("");
  async function updated() {
    setSecret(""); setClientId(""); setError("");
    await cache.invalidateQueries({ queryKey: ["outlook", "connection"] });
    void cache.invalidateQueries({ queryKey: ["integrations", "status"] });
  }
  const save = useMutation({ mutationFn: api.saveOutlookConnection, onSuccess: async () => { await updated(); showToast("Outlook app settings saved. Connect your account next."); }, onError: (issue: Error) => { setSecret(""); setError(issue.message); } });
  const disconnect = useMutation({ mutationFn: api.disconnectOutlook, onSuccess: async () => { await updated(); showToast("Outlook disconnected. The saved token was deleted."); }, onError: (issue: Error) => setError(issue.message) });
  const remove = useMutation({ mutationFn: api.removeOutlookConnection, onSuccess: updated, onError: (issue: Error) => setError(issue.message) });
  const busy = save.isPending || disconnect.isPending || remove.isPending;
  const data = query.data;
  const callbackError = params.get("outlook") === "error" ? params.get("reason") || "Outlook could not connect. Please try again." : "";
  const status = data?.status === "connected" ? `Connected as ${data.account?.email}` : data?.status === "needs_reconnect" ? "Needs reconnect" : data?.status === "ready" ? "Ready to connect" : "Not set up";
  async function copy() {
    try { await navigator.clipboard.writeText(data!.redirect_uri); showToast("Redirect URI copied."); }
    catch { showToast("Could not copy. Select and copy the URI below.", "error"); }
  }
  return <Card as="section" id="outlook" className="scroll-mt-24 p-5 sm:p-6" aria-labelledby="outlook-title">
    <h2 id="outlook-title" className="text-lg font-bold text-fg">Outlook email</h2>
    <p className="mt-1 text-sm leading-relaxed text-muted">Connect your work Microsoft 365 account. Microsoft requests permission to read your inbox and send as you, with offline access. This connection is shared by this broker workspace.</p>
    {query.isPending ? <Skeleton className="mt-4 h-11" /> : query.isError ? <div role="alert" className="mt-4 text-sm text-danger-ink"><p>{query.error.message}</p><Button className="mt-2 min-h-11" onClick={() => void query.refetch()}>Retry</Button></div> : <>
      <p className="mt-4 break-words text-sm font-semibold text-fg-2" role="status">{status}</p>
      {data?.status === "needs_reconnect" && <p className="mt-1 text-sm text-warn-ink">Microsoft authorization expired, was revoked, or needs renewed consent. Connect again to resume.</p>}
      {isAdmin && <>
      <p className="mt-1 text-xs text-muted">{data?.source === "app" ? `App client ID: ${data.client_id}` : data?.source === "env" ? "Using server app credentials — save here to override." : "Enter your Azure app registration credentials below."}</p>
      <form className="mt-4 space-y-3" onSubmit={(event) => { event.preventDefault(); setError(""); save.mutate({ client_id: clientId.trim(), client_secret: secret.trim() }); }}>
        <Field htmlFor="outlook-client" label="Azure client ID"><Input id="outlook-client" value={clientId} onChange={(event) => setClientId(event.target.value)} placeholder={data?.client_id || "Application (client) ID"} required maxLength={36} autoComplete="off" autoCapitalize="none" spellCheck={false} disabled={busy} className="min-h-11 text-base" /></Field>
        <Field htmlFor="outlook-secret" label="Client secret"><Input id="outlook-secret" type="password" value={secret} onChange={(event) => setSecret(event.target.value)} required maxLength={2000} autoComplete="new-password" autoCapitalize="none" spellCheck={false} disabled={busy} className="min-h-11 text-base" /></Field>
        <p className="text-xs leading-relaxed text-muted">The secret and refresh token are encrypted and never displayed. Saving credentials disconnects the current account; removing app credentials falls back to server settings.</p>
        <div className="flex flex-wrap gap-2"><Button type="submit" className="min-h-11" loading={save.isPending} disabled={busy || !clientId.trim() || !secret.trim()}>Save app settings</Button>{data?.source === "app" && <Button className="min-h-11" disabled={busy} onClick={() => remove.mutate()}>Remove app settings</Button>}</div>
      </form>
      <div className="mt-5 border-t border-line pt-5">
        <p className="text-sm font-semibold text-fg-2">Microsoft redirect URI</p>
        <p className="mt-1 text-xs leading-relaxed text-muted">Register a Web redirect URI in Azure. The app must support accounts in any organizational directory (authority: common).</p>
        <p className="mt-3 select-all break-all rounded-xl border border-line bg-surface-2 p-3 text-xs text-fg-2">{data?.redirect_uri}</p>
        <Button className="mt-2 min-h-11" onClick={() => void copy()}>Copy redirect URI</Button>
      </div>
      </>}
      {!isAdmin && !data?.configured && <p className="mt-3 text-sm text-muted">Ask your admin to set up the Outlook app, then connect your mailbox here.</p>}
      <p className="mt-4 text-xs leading-relaxed text-muted">Your company's consent policy may still require IT approval. If Microsoft offers “request approval”, use that option. Only identified BOL PDFs or messages matching a known load/order/PO are saved; unrelated mail is discarded.</p>
      <div className="mt-4 flex flex-wrap gap-2"><Button variant="primary" className="min-h-11" disabled={busy || !data?.configured} onClick={() => { window.location.assign("/api/email/oauth/start"); }}>Connect Outlook</Button>{data?.account && <Button className="min-h-11" loading={disconnect.isPending} disabled={busy} onClick={() => disconnect.mutate()}>Disconnect</Button>}</div>
    </>}
    {(error || callbackError) && <p role="alert" className="mt-4 break-words text-sm text-danger-ink">{error || callbackError}</p>}
  </Card>;
}
