import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api";
import { Card } from "./ui";

export default function CustomerUpdatesSummary() {
  const queue = useQuery({ queryKey: ["customer-updates"], queryFn: api.customerUpdates, refetchInterval: 30000 });
  return <Card className="p-4"><Link to="/customer-updates" className="flex min-h-11 flex-wrap items-center justify-between gap-2 text-sm font-semibold"><span>Customer updates</span><span>{queue.isError ? "Open queue to retry →" : queue.isPending ? "Loading…" : `${queue.data.count} awaiting approval →`}</span></Link><p className="text-sm text-muted">Carrier news ready for your review. Nothing sends without approval.</p></Card>;
}
