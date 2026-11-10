import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { Button, Skeleton } from "./ui";

export default function KofMessageThread({ orderNo }: { orderNo: number }) {
  const messages = useQuery({ queryKey: ["kof", "messages", orderNo], queryFn: () => api.kofMessages(orderNo), refetchInterval: 30000 });
  return <section>
    <h3 className="text-sm font-semibold text-fg">Messages</h3>
    <p className="mt-1 text-xs text-muted">Latest 100 texts. Driver-reported status is proposed, not confirmed. Nothing here changes KOF stages.</p>
    {messages.isPending ? <Skeleton className="mt-3 h-16" /> : messages.isError ? <div role="alert" className="mt-3 text-sm text-danger-ink"><p>{messages.error.message}</p><Button className="mt-2 min-h-11" onClick={() => void messages.refetch()}>Retry</Button></div> : !messages.data.length ? <p className="mt-3 text-sm text-muted">No messages recorded for this order.</p> : <ol className="mt-3 space-y-3">
      {messages.data.map((message) => <li key={message.id} className="rounded-xl border border-line bg-surface-2 p-3">
        <p className="text-xs font-semibold text-fg-2">{message.direction === "out" ? "Outbound" : "Inbound"} · {message.status} · <time dateTime={message.created_at}>{new Date(message.created_at).toLocaleString()}</time></p>
        <p className="mt-1 break-words whitespace-pre-wrap text-sm text-fg">{message.body}</p>
        {message.status === "ambiguous" && <p className="mt-2 text-xs text-warn-ink">Unmatched reply — candidate orders: {message.candidate_order_nos.join(", ")}. Not confirmed for this order.</p>}
        {message.direction === "in" && message.parsed_status && <p className="mt-2 text-xs text-muted">Unconfirmed report: {message.parsed_status.replaceAll("_", " ")}{message.parsed_eta && ` · ETA ${new Date(message.parsed_eta).toLocaleString()}`}</p>}
        {message.parsed_summary && <p className="mt-1 text-xs text-muted">{message.parsed_summary}</p>}
        {message.error && <p className="mt-2 text-xs text-danger-ink">{message.error}</p>}
      </li>)}
    </ol>}
  </section>;
}
