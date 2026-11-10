import { MessageCircle, Send, RotateCcw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, ApiError, type AssistantMessage, type AssistantReply } from "../api";
import Modal from "./Modal";
import KofTextActionCard, { type TextDraft } from "./KofTextActionCard";
import KofEmailActionCard, { type EmailDraft } from "./KofEmailActionCard";
import { Button, Textarea, buttonClass } from "./ui";

type ChatMessage = AssistantMessage & { loads?: AssistantReply["loads"]; actions?: (TextDraft | EmailDraft)[] };
const starters = [
  "Did order/PO # … get loaded?",
  "Which loads have no update in 4 hours?",
  "What's delivering today?",
];

function LoadChip({ load, onOpen }: { load: AssistantReply["loads"][number]; onOpen: () => void }) {
  const detail = useQuery({
    queryKey: ["assistant", "load-link", load.id],
    queryFn: () => api.load(load.id),
    enabled: load.source === "operational",
  });
  const unbooked = detail.data?.status === "new" || detail.data?.status === "posted";
  const path = load.source === "kof" ? `/loads?order=${load.id}` : unbooked ? `/truckstop?load=${load.id}` : `/status?load=${load.id}&include_delivered=true`;
  return <Link to={path} onClick={onOpen} className={buttonClass("secondary", "sm", "min-h-11 max-w-full whitespace-normal break-words text-xs tabular-nums")}>{load.source === "kof" ? "KOF" : "Operational"} · {load.label}</Link>;
}

export default function AssistantWidget() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [thinking, setThinking] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const end = useRef<HTMLDivElement>(null);
  const busy = useRef(false);

  useEffect(() => {
    if (open) end.current?.scrollIntoView({ block: "nearest" });
  }, [messages, thinking, error, open]);

  async function send() {
    const content = draft.trim();
    if (!content || busy.current) return;
    const next: ChatMessage[] = [...messages, { role: "user", content }];
    const history = next.slice(-29).map(({ role, content: text }) => ({ role, content: text.slice(0, 8000) }));
    while (history.length > 1 && history.reduce((size, message) => size + message.content.length, 0) > 32000) history.shift();
    busy.current = true;
    setThinking(true);
    setError(null);
    setMessages(next);
    setDraft("");
    try {
      const result = await api.assistantChat(history);
      setMessages((current) => [...current, { role: "assistant", content: result.reply, loads: result.loads, actions: result.actions?.map((action) => ({ ...action, state: "draft" })) }]);
    } catch (issue) {
      setError(issue instanceof Error ? issue : new Error("Unable to reach the assistant. Try again."));
      setMessages((current) => current.slice(0, -1));
      setDraft(content);
    } finally {
      busy.current = false;
      setThinking(false);
    }
  }

  return (
    <>
      {!open && <Button icon={MessageCircle} className="fixed bottom-[calc(5.25rem+env(safe-area-inset-bottom))] right-4 z-40 min-h-12 rounded-full border-line-strong bg-surface px-5 shadow-xl md:bottom-6 md:right-6" onClick={() => setOpen(true)} aria-haspopup="dialog">Ask</Button>}
      {open && (
        <Modal title="Ask Fifth Wheel" eyebrow="AI assistant · Review before sending" layout="side" onClose={() => setOpen(false)}>
          <div className="flex shrink-0 items-center justify-between gap-3 border-b border-line px-5 py-2">
            <p className="text-xs text-muted">Answers from your recorded load data.</p>
            <Button icon={RotateCcw} variant="ghost" className="min-h-11 text-xs" disabled={thinking || messages.some((message) => message.actions?.some((action) => action.state === "sending")) || (!messages.length && !draft && !error)} onClick={() => { setMessages([]); setDraft(""); setError(null); input.current?.focus(); }}>New chat</Button>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
            {!messages.length && (
              <div className="space-y-4">
                <div>
                  <h3 className="text-base font-semibold text-fg">A quick answer for the next call.</h3>
                  <p className="mt-2 text-sm leading-relaxed text-fg-2">Look up a BOL, PO or order number, check delivery status, or find loads waiting on an update.</p>
                </div>
                <div className="flex flex-col gap-2">
                  {starters.map((prompt) => <Button key={prompt} className="min-h-11 justify-start whitespace-normal text-left text-sm" onClick={() => { setDraft(prompt); input.current?.focus(); }}>{prompt}</Button>)}
                </div>
                <p className="text-xs leading-relaxed text-muted">Read records or draft a KOF carrier email or text. Nothing sends until you review the exact preview and tap Send. Load stages are never changed.</p>
              </div>
            )}
            <div role="log" aria-label="Conversation" aria-live="polite" className="space-y-5">
              {messages.map((message, index) => (
                <div key={index} className={`rounded-xl border border-line p-4 ${message.role === "user" ? "ml-6 bg-surface-3" : "mr-2 bg-surface-2"}`}>
                  <p className="mb-2 text-xs font-semibold text-muted">{message.role === "user" ? "You" : "Fifth Wheel"}</p>
                  <p className="whitespace-pre-wrap break-words text-sm leading-relaxed text-fg">{message.content}</p>
                  {!!message.loads?.length && <div className="mt-3 flex flex-wrap gap-2" aria-label="Referenced loads">
                    {message.loads.map((load) => <LoadChip key={`${load.source}-${load.id}`} load={load} onOpen={() => setOpen(false)} />)}
                  </div>}
                  {message.actions?.map((action, actionIndex) => {
                    const onChange = (update: Partial<TextDraft> | Partial<EmailDraft>) => setMessages((current) => current.map((item, messageIndex) => messageIndex === index ? { ...item, actions: item.actions?.map((draftAction, draftIndex) => draftIndex === actionIndex ? { ...draftAction, ...update } as TextDraft | EmailDraft : draftAction) } : item));
                    return action.type === "send_kof_email" ? <KofEmailActionCard key={actionIndex} action={action} onSettings={() => setOpen(false)} onChange={onChange} /> : <KofTextActionCard key={actionIndex} action={action} onSettings={() => setOpen(false)} onChange={onChange} />;
                  })}
                </div>
              ))}
            </div>
            {thinking && <p role="status" className="mt-4 text-sm text-muted motion-safe:animate-pulse">Thinking… Checking your records.</p>}
            {error && <div role="alert" className="mt-4 rounded-xl border border-danger/40 bg-surface-2 p-4 text-sm text-danger-ink">
              {error instanceof ApiError && error.status === 503 ? <><p>Assistant not set up — add a Claude API key in Settings</p><Link to="/settings#assistant" onClick={() => setOpen(false)} className={buttonClass("secondary", "sm", "mt-3 min-h-11")}>Open Settings</Link></> : <p>{error.message}</p>}
            </div>}
            <div ref={end} />
          </div>
          <form className="shrink-0 space-y-3 border-t border-line bg-surface px-5 py-4" onSubmit={(event) => { event.preventDefault(); void send(); }}>
            <label htmlFor="assistant-message" className="block text-sm font-semibold text-fg-2">Ask about a load</label>
            <Textarea id="assistant-message" ref={input} rows={3} maxLength={8000} value={draft} disabled={thinking} onChange={(event) => setDraft(event.target.value)} placeholder="Try a BOL, PO or order number…" className="max-h-40 resize-none text-base" onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing && window.matchMedia("(hover: hover) and (pointer: fine)").matches) { event.preventDefault(); void send(); }
            }} />
            <div className="flex items-center justify-between gap-3">
              <p className="text-xs text-muted">AI can make mistakes. Check the source.</p>
              <Button type="submit" variant="primary" icon={Send} className="min-h-11" disabled={!draft.trim() || thinking}>Send</Button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}
