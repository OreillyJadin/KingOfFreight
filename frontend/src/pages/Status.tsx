import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  ArrowRight,
  Check,
  ChevronDown,
  Clock3,
  ExternalLink,
  MapPin,
  MessageSquare,
  Send,
  Truck,
} from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useToast } from "../useToast";
import Modal from "../components/Modal";
import {
  EmptyState,
  ErrorState,
  Lane,
  PageHeading,
  StatusBadge,
} from "../components/common";
import type { CheckIn, Load, LoadDetail, LoadStatus, StatusUpdate } from "../types";
import { cityState, formatClock, formatDateTime, formatMoney } from "../utils";

const railStatuses: LoadStatus[] = ["booked", "picked_up", "in_transit", "delivered"];
const statusNames: Record<LoadStatus, string> = {
  new: "New",
  posted: "Posted",
  booked: "Booked",
  picked_up: "Picked Up",
  in_transit: "In Transit",
  delayed: "Delayed",
  delivered: "Delivered",
};

function elapsed(value: string) {
  const minutes = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 60_000));
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours} hr${hours === 1 ? "" : "s"} ago`;
}

function AttentionStrip() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const alerts = useQuery({
    queryKey: ["alerts"],
    queryFn: api.alerts,
    refetchInterval: 30_000,
  });
  const checkins = useQuery({
    queryKey: ["alert-checkins", (alerts.data ?? []).map((item) => item.id)],
    queryFn: () => Promise.all((alerts.data ?? []).map((item) => api.checkin(item.id))),
    enabled: Boolean(alerts.data?.length),
    refetchInterval: 30_000,
  });
  const dismiss = useMutation({
    mutationFn: api.dismissAlert,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["alerts"] });
      showToast("Alert marked as handled.");
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });
  if (alerts.isError) return <ErrorState message={(alerts.error as Error).message} />;
  if (!alerts.data?.length) return null;
  return (
    <section className="mb-6 overflow-hidden rounded-2xl border border-amber-200 bg-amber-50">
      <div className="flex items-center gap-2 border-b border-amber-200/70 px-4 py-3">
        <AlertCircle className="h-4 w-4 text-amber-700" />
        <h2 className="text-sm font-extrabold text-amber-950">Needs attention</h2>
        <span className="rounded-full bg-amber-200 px-2 py-0.5 text-[10px] font-bold text-amber-900">
          {alerts.data.length}
        </span>
      </div>
      <div className="divide-y divide-amber-200/60">
        {alerts.data.map((alert, index) => {
          const checkin = checkins.data?.[index];
          return (
            <div key={alert.id} className="flex flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-bold text-amber-950">
                    {alert.state === "no_reply"
                      ? `No reply to ${alert.kind} check-in sent ${formatClock(checkin?.checkin_sent_at)}`
                      : `${alert.load.reference} · ${alert.parsed_status ?? "Unclear"} reply`}
                  </span>
                  <StatusBadge status={alert.load.status} />
                </div>
                <p className="mt-1 line-clamp-2 text-sm text-amber-900/80">
                  {alert.state === "no_reply"
                    ? `${alert.load.reference} · ${alert.kind} check-in`
                    : alert.parsed_summary || "Driver reply needs review."}
                </p>
                {checkin?.reply_raw_text && (
                  <p className="mt-1 text-xs text-amber-900/70">
                    Driver wrote: “{checkin.reply_raw_text}”
                  </p>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-2">
                {alert.state === "no_reply" && (
                  <button
                    disabled
                    title="The API only permits send-now for scheduled check-ins."
                    className="min-h-10 rounded-lg border border-amber-300 bg-white/70 px-3 text-xs font-bold text-amber-900 opacity-60"
                  >
                    Send check-in again
                  </button>
                )}
                <button
                  onClick={() => dismiss.mutate(alert.id)}
                  disabled={dismiss.isPending}
                  className="min-h-10 rounded-lg bg-amber-900 px-3 text-xs font-bold text-white hover:bg-amber-950 disabled:opacity-60"
                >
                  Mark handled
                </button>
                <Link
                  to={`/status?load=${alert.load.id}`}
                  className="grid h-10 w-10 place-items-center rounded-lg text-amber-900 hover:bg-amber-200/70"
                  aria-label={`View load ${alert.load.reference}`}
                >
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function CheckinTimeline({ checkins, load }: { checkins: CheckIn[]; load: Load }) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const send = useMutation({
    mutationFn: api.sendCheckin,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["load", load.id] });
      showToast("Check-in sent.");
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });
  if (!checkins.length) {
    return <p className="text-xs text-slate-500">No scheduled driver check-ins.</p>;
  }
  return (
    <div className="space-y-2">
      {checkins.map((checkin) => (
        <div key={checkin.id} className="rounded-xl border border-slate-200 p-3">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <p className="text-xs font-bold capitalize text-slate-800">
                {checkin.kind} check-in
                <span className="ml-2 font-medium text-slate-400">
                  {formatDateTime(checkin.checkin_sent_at || checkin.send_at)}
                </span>
              </p>
              <p className="mt-1 text-[11px] text-slate-500">
                {checkin.state.replace("_", " ")} · {checkin.checkin_channel.toUpperCase()}
              </p>
            </div>
            {checkin.state === "scheduled" && (
              <button
                onClick={() => send.mutate(checkin.id)}
                disabled={send.isPending}
                className="min-h-9 rounded-lg border border-blue-200 px-2.5 text-[11px] font-bold text-blue-700 hover:bg-blue-50 disabled:opacity-50"
              >
                Send check-in now
              </button>
            )}
          </div>
          {checkin.reply_raw_text && (
            <div className="mt-2 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
              “{checkin.reply_raw_text}”
              {checkin.parsed_status && (
                <span className="ml-1 font-semibold text-slate-800">
                  · {statusNames[checkin.parsed_status as LoadStatus] ?? checkin.parsed_status}
                </span>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function StatusRail({ status }: { status: LoadStatus }) {
  const currentIndex = railStatuses.indexOf(status);
  return (
    <div className="relative flex items-center justify-between gap-1 py-2">
      <div className="absolute left-3 right-3 top-[21px] h-0.5 bg-slate-200" />
      {railStatuses.map((step, index) => {
        const isCurrent = step === status;
        const passed = currentIndex >= 0 && index <= currentIndex;
        return (
          <div key={step} className="relative flex min-w-0 flex-1 flex-col items-center gap-2">
            <span
              className={`grid h-6 w-6 place-items-center rounded-full border-2 ${
                isCurrent
                  ? "border-blue-600 bg-blue-600 text-white"
                  : passed
                    ? "border-blue-600 bg-white text-blue-600"
                    : "border-slate-300 bg-white text-slate-300"
              }`}
            >
              {passed && !isCurrent ? <Check className="h-3 w-3" /> : <span className="h-1.5 w-1.5 rounded-full bg-current" />}
            </span>
            <span className={`text-center text-[10px] font-semibold leading-tight sm:text-[11px] ${isCurrent ? "text-blue-700" : "text-slate-500"}`}>
              {statusNames[step]}
            </span>
          </div>
        );
      })}
      {status === "delayed" && (
        <span className="absolute -top-2 left-1/2 -translate-x-1/2 rounded-full bg-amber-100 px-2.5 py-1 text-[10px] font-bold text-amber-800">
          Delayed · off route
        </span>
      )}
    </div>
  );
}

function PreviewModal({
  update,
  detail,
  onClose,
}: {
  update: StatusUpdate;
  detail: LoadDetail;
  onClose: () => void;
}) {
  const [subject, setSubject] = useState(update.customer_message_subject ?? "");
  const [body, setBody] = useState(update.customer_message_preview ?? "");
  const defaultChannel = detail.customer_email
    ? update.customer_channel ?? "email"
    : "sms";
  const [channel, setChannel] = useState<"email" | "sms">(defaultChannel);
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const checkin = update.checkin_id
    ? detail.checkins.find((item) => item.id === update.checkin_id)
    : undefined;
  const afterMutation = async (message: string) => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["load", detail.id] }),
      queryClient.invalidateQueries({ queryKey: ["loads"] }),
      queryClient.invalidateQueries({ queryKey: ["status-updates"] }),
      queryClient.invalidateQueries({ queryKey: ["alerts"] }),
    ]);
    showToast(message);
    onClose();
  };
  const approve = useMutation({
    mutationFn: () => api.approve(update.id, { subject, body, channel }),
    onSuccess: () => afterMutation("Customer update approved and sent."),
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const skip = useMutation({
    mutationFn: (apply: boolean) => api.skip(update.id, apply),
    onSuccess: (_, apply) =>
      afterMutation(apply ? "Status updated without a customer message." : "Draft discarded."),
    onError: (error: Error) => showToast(error.message, "error"),
  });
  return (
    <Modal title="Review customer update" eyebrow="Approval required" onClose={onClose} size="max-w-2xl">
      {checkin && (
        <div className="mb-5 rounded-xl border border-blue-200 bg-blue-50 p-4">
          <p className="text-[11px] font-bold uppercase tracking-[0.12em] text-blue-700">Driver reply · parsed status</p>
          <p className="mt-1 text-sm font-bold text-blue-950">
            “{checkin.reply_raw_text || checkin.parsed_summary || "Reply received"}”{" "}
            <span className="font-semibold">→ {statusNames[update.status]}</span>
            {update.eta && <span className="font-semibold"> · ETA {formatDateTime(update.eta)}</span>}
          </p>
          {checkin.parsed_summary && checkin.parsed_summary !== checkin.reply_raw_text && (
            <p className="mt-1 text-xs text-blue-800">{checkin.parsed_summary}</p>
          )}
        </div>
      )}
      <div className="mb-5 flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs font-semibold text-amber-900">
        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
        Nothing is sent to the customer until you approve.
      </div>
      <div className="grid gap-4">
        <label>
          <span className="mb-1.5 block text-xs font-semibold text-slate-600">To</span>
          <input
            readOnly
            value={channel === "email" ? detail.customer_email ?? "No customer email" : detail.customer_phone ?? "No customer phone"}
            className="h-10 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 text-sm text-slate-600"
          />
        </label>
        <div className="grid gap-4 sm:grid-cols-[1fr_140px]">
          <label>
            <span className="mb-1.5 block text-xs font-semibold text-slate-600">Subject</span>
            <input
              value={subject}
              onChange={(event) => setSubject(event.target.value)}
              className="h-10 w-full rounded-lg border border-slate-300 px-3 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
            />
          </label>
          <label>
            <span className="mb-1.5 block text-xs font-semibold text-slate-600">Channel</span>
            <select
              value={channel}
              onChange={(event) => setChannel(event.target.value as "email" | "sms")}
              className="h-10 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
            >
              <option value="email" disabled={!detail.customer_email}>Email</option>
              <option value="sms" disabled={!detail.customer_phone}>SMS</option>
            </select>
          </label>
        </div>
        <label>
          <span className="mb-1.5 block text-xs font-semibold text-slate-600">Message</span>
          <textarea
            rows={6}
            value={body}
            onChange={(event) => setBody(event.target.value)}
            className="w-full resize-y rounded-xl border border-slate-300 px-3 py-2.5 text-sm leading-6 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
          />
        </label>
      </div>
      <div className="mt-5 flex flex-col gap-2 border-t border-slate-100 pt-4 sm:flex-row sm:flex-wrap sm:justify-end">
        {!update.applied && (
          <button
            onClick={() => skip.mutate(false)}
            disabled={skip.isPending}
            className="min-h-11 rounded-xl border border-slate-300 px-3 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            Discard
          </button>
        )}
        <button
          onClick={() => skip.mutate(true)}
          disabled={skip.isPending}
          className="min-h-11 rounded-xl border border-slate-300 px-3 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          Update status only, don’t notify
        </button>
        <button
          onClick={() => approve.mutate()}
          disabled={approve.isPending || (channel === "email" ? !detail.customer_email : !detail.customer_phone)}
          className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 text-sm font-bold text-white hover:bg-blue-700 disabled:opacity-50"
        >
          <Send className="h-4 w-4" />
          {approve.isPending ? "Sending…" : "Approve & send"}
        </button>
      </div>
    </Modal>
  );
}

function StatusCard({ load }: { load: Load }) {
  const [preview, setPreview] = useState<StatusUpdate | null>(null);
  const [searchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const detail = useQuery({
    queryKey: ["load", load.id],
    queryFn: () => api.load(load.id),
    refetchInterval: 30_000,
  });
  const setStatus = useMutation({
    mutationFn: (status: LoadStatus) => api.manualStatus(load.id, { status }),
    onSuccess: async (update) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["load", load.id] }),
        queryClient.invalidateQueries({ queryKey: ["loads"] }),
        queryClient.invalidateQueries({ queryKey: ["status-updates"] }),
      ]);
      setPreview(update);
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const tracking = useMutation({
    mutationFn: () => api.sendTrackingLink(load.id),
    onSuccess: () => showToast("Tracking link sent to the driver."),
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const data = detail.data;
  const pending = data?.status_updates.find((item) => item.state === "pending_approval");
  const isHighlighted = searchParams.get("load") === String(load.id);
  if (detail.isError) return <ErrorState message={(detail.error as Error).message} />;
  if (!data) {
    return <div className="h-52 animate-pulse rounded-2xl border border-slate-200 bg-white" />;
  }
  const margin = Number(data.margin ?? Number(data.customer_rate ?? 0) - Number(data.carrier_rate ?? 0));
  const marginPct = Number(data.margin_pct ?? 0);
  const ping = data.latest_location_ping;
  const from = cityState(data.pickup_city, data.pickup_state);
  const to = cityState(data.delivery_city, data.delivery_state);
  const statuses: LoadStatus[] = ["booked", "picked_up", "in_transit", "delayed", "delivered"];
  return (
    <>
      <article
        id={`load-${data.id}`}
        className={`overflow-hidden rounded-2xl border bg-white shadow-card ${
          isHighlighted ? "border-blue-400 ring-2 ring-blue-100" : "border-slate-200"
        }`}
      >
        <div className="p-4 sm:p-5">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-lg font-extrabold text-slate-900">{data.reference}</h2>
                <StatusBadge status={data.status} />
              </div>
              <p className="mt-1 text-sm font-semibold text-slate-600">{data.customer_name || "Customer not set"}</p>
            </div>
            <div className={`shrink-0 rounded-xl px-3 py-2 text-right ${margin < 0 ? "bg-rose-50 text-rose-700" : "bg-emerald-50 text-emerald-800"}`}>
              <p className="text-[10px] font-bold uppercase tracking-wide">Margin</p>
              <p className="text-sm font-extrabold">{formatMoney(margin)}</p>
              <p className="text-[10px] font-semibold">{marginPct.toFixed(1)}%</p>
            </div>
          </div>
          <div className="mt-4 rounded-xl bg-slate-50 px-3 py-3">
            <Lane from={from} to={to} />
            <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-[11px] text-slate-500">
              <span>Pickup {formatDateTime(data.pickup_datetime)}</span>
              <span>Delivery {formatDateTime(data.delivery_datetime)}</span>
            </div>
          </div>
          <div className="mt-5">
            <StatusRail status={data.status} />
          </div>
          {pending && (
            <button
              onClick={() => setPreview(pending)}
              className="mt-4 block w-full rounded-xl border border-blue-200 bg-blue-50 p-3 text-left transition hover:bg-blue-100"
            >
              <span className="flex items-center justify-between gap-3">
                <span className="text-xs font-bold uppercase tracking-wide text-blue-700">
                  Pending {pending.source === "checkin" ? "driver update" : "draft"}
                </span>
                <span className="text-xs font-bold text-blue-700">Review message →</span>
              </span>
              {pending.source === "checkin" && (
                <span className="mt-1 block text-sm font-semibold text-blue-950">
                  Driver replied: “{data.checkins.find((item) => item.id === pending.checkin_id)?.reply_raw_text || pending.note || "Update"}”
                  <span className="font-normal"> → {statusNames[pending.status]}{pending.eta ? ` · ETA ${formatDateTime(pending.eta)}` : ""}</span>
                </span>
              )}
            </button>
          )}
          <div className="mt-4">
            <p className="mb-2 text-[11px] font-bold uppercase tracking-[0.12em] text-slate-500">Update status</p>
            <div className="flex gap-2 overflow-x-auto pb-1">
              {statuses.map((status) => (
                <button
                  key={status}
                  onClick={() => setStatus.mutate(status)}
                  disabled={setStatus.isPending}
                  className={`min-h-10 shrink-0 rounded-lg px-3 text-xs font-bold transition ${
                    data.status === status
                      ? "bg-blue-600 text-white"
                      : status === "delayed"
                        ? "border border-amber-200 bg-amber-50 text-amber-800 hover:bg-amber-100"
                        : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                  }`}
                >
                  {statusNames[status]}
                </button>
              ))}
            </div>
          </div>
          <details className="mt-4 border-t border-slate-100 pt-3">
            <summary className="flex min-h-10 cursor-pointer list-none items-center justify-between text-sm font-bold text-slate-700">
              <span className="flex items-center gap-2"><Clock3 className="h-4 w-4 text-slate-400" /> Check-ins</span>
              <ChevronDown className="h-4 w-4 text-slate-400" />
            </summary>
            <div className="pb-2 pt-2">
              <CheckinTimeline checkins={data.checkins} load={data} />
            </div>
          </details>
          {ping && (
            <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 px-3 py-2.5">
              <div className="flex items-center gap-2 text-xs text-slate-600">
                <MapPin className="h-4 w-4 text-blue-600" />
                <span><strong className="text-slate-800">Last location</strong> {elapsed(ping.captured_at)}</span>
                <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-slate-500">Internal only</span>
              </div>
              <a
                href={`https://maps.google.com/?q=${Number(ping.lat)},${Number(ping.lng)}`}
                target="_blank"
                rel="noreferrer"
                className="inline-flex min-h-9 items-center gap-1 text-xs font-bold text-blue-700 hover:underline"
              >
                Map <ExternalLink className="h-3 w-3" />
              </a>
            </div>
          )}
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button
              onClick={() => tracking.mutate()}
              disabled={tracking.isPending || (!data.driver_phone && !data.driver_email && !data.dispatcher_phone && !data.dispatcher_email)}
              className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-blue-200 px-3 text-xs font-bold text-blue-700 hover:bg-blue-50 disabled:opacity-50"
            >
              <Send className="h-3.5 w-3.5" />
              {tracking.isPending ? "Sending…" : "Send tracking link"}
            </button>
            <details className="group relative">
              <summary className="inline-flex min-h-10 cursor-pointer list-none items-center gap-2 rounded-lg px-3 text-xs font-semibold text-slate-600 hover:bg-slate-100">
                <MessageSquare className="h-4 w-4" />
                Communications ({data.communications.length})
                <ChevronDown className="h-3.5 w-3.5" />
              </summary>
              <div className="mt-2 max-h-52 overflow-y-auto rounded-xl border border-slate-200 bg-white p-2 shadow-card sm:absolute sm:left-0 sm:z-10 sm:w-80">
                {data.communications.length ? (
                  data.communications.map((communication) => (
                    <div key={communication.id} className="border-b border-slate-100 px-2 py-2 last:border-0">
                      <p className="text-[10px] font-bold uppercase text-slate-400">{communication.direction} · {communication.tag.replaceAll("_", " ")}</p>
                      <p className="mt-1 line-clamp-3 text-xs text-slate-700">{communication.content}</p>
                    </div>
                  ))
                ) : (
                  <p className="px-2 py-3 text-xs text-slate-500">No messages logged for this load.</p>
                )}
              </div>
            </details>
          </div>
        </div>
      </article>
      {preview && <PreviewModal update={preview} detail={data} onClose={() => setPreview(null)} />}
    </>
  );
}

export default function Status() {
  const [includeDelivered, setIncludeDelivered] = useState(false);
  const loads = useQuery({
    queryKey: ["loads", "delivery", includeDelivered],
    queryFn: () => api.loads("delivery", includeDelivered),
    refetchInterval: 30_000,
  });
  return (
    <div>
      <PageHeading
        eyebrow="Active freight"
        title="Delivery Status"
        description="Check-ins, live status, and customer updates for every booked load."
        action={
          <label className="inline-flex min-h-11 cursor-pointer items-center gap-2 self-start rounded-xl border border-slate-300 bg-white px-3 text-sm font-semibold text-slate-700 sm:self-auto">
            <input
              type="checkbox"
              checked={includeDelivered}
              onChange={(event) => setIncludeDelivered(event.target.checked)}
              className="h-4 w-4 accent-blue-600"
            />
            Show delivered
          </label>
        }
      />
      <AttentionStrip />
      {loads.isError ? (
        <ErrorState message={(loads.error as Error).message} />
      ) : loads.isPending ? (
        <div className="grid min-h-40 place-items-center text-sm text-slate-500">Loading delivery status…</div>
      ) : loads.data.length === 0 ? (
        <EmptyState icon={Truck} title="No active deliveries" description="Booked loads will appear here once a carrier is assigned." />
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {loads.data.map((load) => <StatusCard key={load.id} load={load} />)}
        </div>
      )}
    </div>
  );
}
