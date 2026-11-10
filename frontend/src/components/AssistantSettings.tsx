import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import { useToast } from "../useToast";
import { Button, Card, Input, Skeleton } from "./ui";

export default function AssistantSettings() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const connection = useQuery({ queryKey: ["assistant", "connection"], queryFn: api.assistantConnection });
  const [key, setKey] = useState("");
  const [error, setError] = useState("");
  const save = useMutation({
    mutationFn: api.saveAssistantKey,
    onSuccess: async (data) => {
      setKey("");
      setError("");
      queryClient.setQueryData(["assistant", "connection"], data);
      showToast("Assistant API key saved.");
    },
    onError: (issue: Error) => { setKey(""); setError(issue.message); },
  });
  const remove = useMutation({
    mutationFn: api.removeAssistantKey,
    onSuccess: async () => {
      setKey("");
      setError("");
      await queryClient.invalidateQueries({ queryKey: ["assistant", "connection"] });
      showToast("Assistant API key removed.");
    },
    onError: (issue: Error) => setError(issue.message),
  });
  const busy = save.isPending || remove.isPending;
  const source = connection.data?.source;

  return (
    <Card as="section" id="assistant" className="scroll-mt-24 p-5 sm:p-6" aria-labelledby="assistant-settings-title">
      <h2 id="assistant-settings-title" className="text-lg font-bold text-fg">AI assistant and document processing</h2>
      <p className="mt-1 text-sm leading-relaxed text-muted">This Claude key powers the read-only assistant and, when the server uses Anthropic, BOL PDF extraction and driver-reply parsing. The assistant sends no messages and changes no loads.</p>
      {connection.isPending ? <Skeleton className="mt-4 h-11 w-full" /> : connection.isError ? <div role="alert" className="mt-4 text-sm text-danger-ink"><p>{connection.error.message}</p><Button className="mt-2 min-h-11" onClick={() => void connection.refetch()}>Retry</Button></div> : <>
        <p className="mt-4 text-sm font-semibold text-fg-2">{source === "env" ? "Using server key — save a key here to override" : source === "app" ? "Saved in app" : "Not set up"}</p>
          <form className="mt-4 space-y-3" onSubmit={(event) => { event.preventDefault(); setError(""); save.mutate(key.trim()); }}>
            <label htmlFor="assistant-api-key" className="block text-sm font-semibold text-fg-2">{source === "app" ? "Replace Claude API key" : "Claude API key"}</label>
            <Input id="assistant-api-key" type="password" autoComplete="new-password" spellCheck={false} autoCapitalize="none" value={key} maxLength={500} disabled={busy} onChange={(event) => setKey(event.target.value)} className="min-h-11 text-base" placeholder="Enter a Claude API key" aria-describedby="assistant-key-hint" />
            <p id="assistant-key-hint" className="text-xs leading-relaxed text-muted">Encrypted on the server. Saved keys override the server key; removing one falls back to the server key if available. Saved keys are never displayed. Relevant load records, uploaded PDFs and driver replies are sent to Anthropic when their respective AI features are used.</p>
            <div className="flex flex-wrap gap-2">
              <Button type="submit" variant="primary" className="min-h-11" disabled={busy || !key.trim()} loading={save.isPending}>Save key</Button>
              {source === "app" && <Button className="min-h-11" disabled={busy} loading={remove.isPending} onClick={() => { setError(""); remove.mutate(); }}>Remove key</Button>}
            </div>
          </form>
      </>}
      {error && <p role="alert" className="mt-4 text-sm text-danger-ink">{error}</p>}
    </Card>
  );
}
