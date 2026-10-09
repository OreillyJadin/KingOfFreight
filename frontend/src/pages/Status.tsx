import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
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
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useToast } from "../useToast";
import Modal from "../components/Modal";
import { ListDetail, ListRow, ListRowSkeleton } from "../components/ListDetail";
import {
  EmptyState,
  ErrorState,
  Lane,
  PageHeading,
  StatusBadge,
} from "../components/common";
import {
  Badge,
  Button,
  Card,
  Input,
  Select,
  Skeleton,
  Textarea,
  buttonClass,
} from "../components/ui";
import type { Alert, CheckIn, Load, LoadDetail, LoadStatus, StatusUpdate } from "../types";
import { cityState, formatClock, formatDateTime, formatMoney } from "../utils";
import { useMediaQuery } from "../useMediaQuery";

const railStatuses: LoadStatus[] = ["booked", "picked_up", "in_transit", "delivered"];
const railStyles: Partial<
  Record<LoadStatus, { dot: string; connector: string; ink: string }>
> = {
  booked: {
    dot: "border-st-booked bg-st-booked",
    connector: "bg-st-booked",
    ink: "text-st-booked-ink",
  },
  picked_up: {
    dot: "border-st-picked bg-st-picked",
    connector: "bg-st-picked",
    ink: "text-st-picked-ink",
  },
  in_transit: {
    dot: "border-st-transit bg-st-transit",
    connector: "bg-st-transit",
    ink: "text-st-transit-ink",
  },
  delivered: {
    dot: "border-st-delivered bg-st-delivered",
    connector: "bg-st-delivered",
    ink: "text-st-delivered-ink",
  },
};
const statusButtonStyles: Partial<Record<LoadStatus, string>> = {
  booked: "bg-st-booked/15 text-st-booked-ink",
  picked_up: "bg-st-picked/15 text-st-picked-ink",
  in_transit: "bg-st-transit/15 text-st-transit-ink",
  delayed: "bg-st-delayed/15 text-st-delayed-ink",
  delivered: "bg-st-delivered/15 text-st-delivered-ink",
};
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
  const resend = useMutation({
    mutationFn: api.sendCheckin,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["alerts"] }),
        queryClient.invalidateQueries({ queryKey: ["loads"] }),
      ]);
      showToast("Check-in sent again.");
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const dismiss = useMutation({
    mutationFn: api.dismissAlert,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["alerts"] });
      showToast("Alert marked as handled.");
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });
  if (alerts.isError) {
    return (
      <ErrorState
        message={(alerts.error as Error).message}
        onRetry={() => void alerts.refetch()}
      />
    );
  }
  if (!alerts.data?.length) return null;
  return (
    <section className="mb-6 overflow-hidden rounded-2xl border border-warn/30 bg-warn/10">
      <div className="flex items-center gap-2 border-b border-warn/30 px-4 py-3">
        <AlertCircle className="h-4 w-4 text-warn-ink" />
        <h2 className="text-sm font-extrabold text-warn-ink">Needs attention</h2>
        <Badge tone="warn" className="rounded-full px-2 py-0.5 text-[10px] font-bold">
          {alerts.data.length}
        </Badge>
      </div>
      <div className="divide-y divide-warn/20">
        {alerts.data.map((alert) => (
            <div key={alert.id} className="flex flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-bold text-warn-ink tabular-nums">
                    {alert.state === "no_reply"
                      ? `No reply to ${alert.kind} check-in sent ${formatClock(alert.checkin_sent_at)}`
                      : `${alert.load.reference} · ${alert.parsed_status ?? "Unclear"} reply`}
                  </span>
                  <StatusBadge status={alert.load.status} />
                </div>
                <p className="mt-1 line-clamp-2 text-sm text-warn-ink/80 tabular-nums">
                  {alert.state === "no_reply"
                    ? `${alert.load.reference} · ${alert.kind} check-in`
                    : alert.reply_raw_text || alert.parsed_summary || "Driver reply needs review."}
                </p>
                {alert.state === "replied" && alert.reply_raw_text && (
                  <p className="mt-1 text-xs text-warn-ink/70">
                    Driver wrote: “{alert.reply_raw_text}”
                  </p>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-2">
                {alert.state === "no_reply" && (
                  <Button
                    onClick={() => resend.mutate(alert.id)}
                    disabled={resend.isPending}
                    loading={resend.isPending}
                    variant="secondary"
                    size="sm"
                    className="min-h-10"
                  >
                    Send check-in again
                  </Button>
                )}
                <Button
                  onClick={() => dismiss.mutate(alert.id)}
                  disabled={dismiss.isPending}
                  loading={dismiss.isPending}
                  variant="primary"
                  size="sm"
                  className="min-h-10"
                >
                  Mark handled
                </Button>
                <Link
                  to={`/status?load=${alert.load.id}`}
                  className={buttonClass("ghost", "sm", "min-h-10 !w-10 !px-0 text-warn-ink hover:bg-warn/20")}
                  aria-label={`View load ${alert.load.reference}`}
                >
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </div>
            </div>
        ))}
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
    return <p className="text-xs text-muted">No scheduled driver check-ins.</p>;
  }
  return (
    <div className="space-y-2">
      {checkins.map((checkin) => (
        <div key={checkin.id} className="rounded-xl border border-line p-3">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <p className="text-xs font-bold capitalize text-fg">
                {checkin.kind} check-in
                <span className="ml-2 font-medium text-subtle tabular-nums">
                  {formatDateTime(checkin.checkin_sent_at || checkin.send_at)}
                </span>
              </p>
              <p className="mt-1 text-[11px] text-muted">
                {checkin.state.replace("_", " ")} · {checkin.checkin_channel.toUpperCase()}
              </p>
            </div>
            {checkin.state === "scheduled" && (
              <Button
                onClick={() => send.mutate(checkin.id)}
                disabled={send.isPending}
                loading={send.isPending}
                variant="secondary"
                size="sm"
                className="min-h-9 px-2.5 text-[11px]"
              >
                Send check-in now
              </Button>
            )}
          </div>
          {checkin.reply_raw_text && (
            <div className="mt-2 rounded-lg bg-surface-2 px-3 py-2 text-xs text-fg-2">
              “{checkin.reply_raw_text}”
              {checkin.parsed_status && (
                <span className="ml-1 font-semibold text-fg">
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
      <div className="absolute left-3 right-3 top-[21px] flex h-0.5">
        {railStatuses.slice(0, -1).map((step, index) => (
          <div
            key={step}
            className={`flex-1 ${
              currentIndex >= index
                ? railStyles[step]?.connector
                : "bg-line-strong"
            }`}
          />
        ))}
      </div>
      {railStatuses.map((step, index) => {
        const isCurrent = step === status;
        const passed = currentIndex >= 0 && index <= currentIndex;
        const stepStyle = railStyles[step];
        return (
          <div key={step} className="relative flex min-w-0 flex-1 flex-col items-center gap-2">
            <span
              className={`grid h-6 w-6 place-items-center rounded-full border-2 ${
                passed
                  ? `${stepStyle?.dot} text-surface`
                  : "border-line-strong bg-surface text-subtle"
              }`}
            >
              {passed && !isCurrent ? <Check className="h-3 w-3" /> : <span className="h-1.5 w-1.5 rounded-full bg-current" />}
            </span>
            <span className={`text-center text-[10px] font-semibold leading-tight sm:text-[11px] ${isCurrent ? stepStyle?.ink : "text-muted"}`}>
              {statusNames[step]}
            </span>
          </div>
        );
      })}
      {status === "delayed" && (
        <span className="absolute -top-2 left-1/2 -translate-x-1/2 rounded-full bg-warn/20 px-2.5 py-1 text-[10px] font-bold text-warn-ink">
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
  const [step, setStep] = useState<"compose" | "preview">("compose");
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
  const hasContact = Boolean(
    channel === "email" ? detail.customer_email : detail.customer_phone,
  );
  const segments = body.length <= 160 ? 1 : Math.ceil(body.length / 153);
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
    <Modal
      title="Review customer update"
      eyebrow="Approval required"
      onClose={onClose}
      size="max-w-2xl"
      footer={
        step === "compose" ? (
          <div className="flex w-full flex-col gap-2 sm:flex-row sm:flex-wrap sm:justify-end">
            {!update.applied && (
              <Button
                onClick={() => skip.mutate(false)}
                disabled={skip.isPending}
                loading={skip.isPending}
                variant="secondary"
              >
                Discard
              </Button>
            )}
            <Button
              onClick={() => skip.mutate(true)}
              disabled={skip.isPending}
              loading={skip.isPending}
              variant="secondary"
            >
              Update status only, don’t notify
            </Button>
            <Button
              onClick={() => setStep("preview")}
              disabled={!body.trim() || !hasContact}
              variant="primary"
              icon={ArrowRight}
            >
              Preview message
            </Button>
          </div>
        ) : (
          <div className="flex w-full flex-col gap-2 sm:flex-row sm:justify-end">
            <Button
              onClick={() => setStep("compose")}
              variant="secondary"
              icon={ArrowLeft}
            >
              Back to edit
            </Button>
            <Button
              onClick={() => approve.mutate()}
              disabled={approve.isPending || !hasContact}
              loading={approve.isPending}
              variant="primary"
              icon={Send}
            >
              {approve.isPending ? "Sending…" : "Approve & Send"}
            </Button>
          </div>
        )
      }
    >
      <div className="mb-5 flex items-center gap-2 text-sm" aria-label="Approval steps">
        <span
          aria-current={step === "compose" ? "step" : undefined}
          className={step === "compose" ? "font-semibold text-fg" : "text-muted"}
        >
          1 Compose
        </span>
        <span className="text-muted" aria-hidden="true">·</span>
        <span
          aria-current={step === "preview" ? "step" : undefined}
          className={step === "preview" ? "font-semibold text-fg" : "text-muted"}
        >
          2 Preview
        </span>
      </div>
      {step === "compose" ? (
        <>
          {checkin && (
            <div className="mb-5 rounded-xl border border-line bg-surface-2 p-4">
              <p className="text-[11px] font-bold uppercase tracking-[0.12em] text-fg-2">Driver reply · parsed status</p>
              <p className="mt-1 text-sm font-bold text-fg-2 tabular-nums">
                “{checkin.reply_raw_text || checkin.parsed_summary || "Reply received"}”{" "}
                <span className="font-semibold">→ {statusNames[update.status]}</span>
                {update.eta && <span className="font-semibold tabular-nums"> · ETA {formatDateTime(update.eta)}</span>}
              </p>
              {checkin.parsed_summary && checkin.parsed_summary !== checkin.reply_raw_text && (
                <p className="mt-1 text-xs text-fg-2">{checkin.parsed_summary}</p>
              )}
            </div>
          )}
          <div className="mb-5 flex items-start gap-2 rounded-xl border border-warn/30 bg-warn/10 px-3 py-2.5 text-xs font-semibold text-warn-ink">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            Nothing is sent to the customer until you approve.
          </div>
          <div className="grid gap-4">
            <label>
              <span className="mb-1.5 block text-xs font-semibold text-fg-2">To</span>
              <Input
                readOnly
                value={channel === "email" ? detail.customer_email ?? "No customer email" : detail.customer_phone ?? "No customer phone"}
                className="h-10 bg-surface-2 text-fg-2"
              />
            </label>
            <div className="grid gap-4 sm:grid-cols-[1fr_140px]">
              {channel === "email" && (
                <label>
                  <span className="mb-1.5 block text-xs font-semibold text-fg-2">Subject</span>
                  <Input
                    value={subject}
                    onChange={(event) => setSubject(event.target.value)}
                    className="h-10"
                  />
                </label>
              )}
              <label className={channel === "email" ? "" : "sm:col-span-2"}>
                <span className="mb-1.5 block text-xs font-semibold text-fg-2">Channel</span>
                <Select
                  value={channel}
                  onChange={(event) => setChannel(event.target.value as "email" | "sms")}
                  className="h-10"
                >
                  <option value="email" disabled={!detail.customer_email}>Email</option>
                  <option value="sms" disabled={!detail.customer_phone}>SMS</option>
                </Select>
              </label>
            </div>
            <label>
              <span className="mb-1.5 block text-xs font-semibold text-fg-2">Message</span>
              <Textarea
                rows={6}
                value={body}
                onChange={(event) => setBody(event.target.value)}
                className="resize-y leading-6"
              />
              {channel === "sms" && (
                <span className="mt-1 block text-xs text-muted tabular-nums">
                  {body.length} characters · {segments} SMS segment{segments === 1 ? "" : "s"} (approx.)
                </span>
              )}
            </label>
          </div>
        </>
      ) : (
        <section>
          <h3 className="text-base font-bold text-fg">
            Exactly what {detail.customer_name || "the customer"} will receive
          </h3>
          <p className="mt-1 text-xs text-muted">
            Sent as plain text from your connected {channel === "email" ? "email mailbox" : "SMS number"}.
          </p>
          {channel === "email" ? (
            <div className="mt-4 overflow-hidden rounded-xl border border-line">
              <div className="space-y-3 bg-surface p-4 text-sm">
                <div className="flex gap-3">
                  <span className="w-16 shrink-0 text-muted">To</span>
                  <span className="break-all text-fg">{detail.customer_email}</span>
                </div>
                <div className="flex gap-3">
                  <span className="w-16 shrink-0 text-muted">Subject</span>
                  <span className="text-fg">{subject || "(no subject)"}</span>
                </div>
              </div>
              <div className="border-t border-line bg-surface-2 p-4 whitespace-pre-wrap text-sm text-fg">
                {body}
              </div>
            </div>
          ) : (
            <div className="mt-4">
              <p className="text-xs text-muted">To {detail.customer_phone}</p>
              <div className="mt-3 flex justify-end">
                <p className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-surface-3 px-4 py-3 text-sm text-fg">
                  {body}
                </p>
              </div>
              <p className="mt-2 text-right text-xs text-muted tabular-nums">
                {body.length} characters · {segments} SMS segment{segments === 1 ? "" : "s"} (approx.)
              </p>
            </div>
          )}
        </section>
      )}
    </Modal>
  );
}

function StatusListRow({
  load,
  selected,
  onSelect,
  alerts,
  pendingUpdates,
}: {
  load: Load;
  selected: boolean;
  onSelect: () => void;
  alerts: Alert[];
  pendingUpdates: StatusUpdate[];
}) {
  const detail = useQuery({
    queryKey: ["load", load.id],
    queryFn: () => api.load(load.id),
    refetchInterval: 30_000,
  });
  const alert = alerts.find((item) => item.load.id === load.id);
  const pending = pendingUpdates.find((item) => item.load_id === load.id);
  const latestStatusEta = [...(detail.data?.status_updates ?? [])]
    .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))
    .find((item) => item.eta)?.eta;
  const latestCheckinEta = [...(detail.data?.checkins ?? [])]
    .sort(
      (a, b) =>
        Date.parse(b.reply_received_at ?? b.send_at) -
        Date.parse(a.reply_received_at ?? a.send_at),
    )
    .find((item) => item.parsed_eta)?.parsed_eta;
  const eta = latestStatusEta ?? latestCheckinEta;
  const timeLine = eta
    ? `ETA ${formatDateTime(eta)}`
    : load.status === "booked"
      ? `Pickup ${formatDateTime(load.pickup_datetime)}`
      : load.status === "delivered"
        ? `Delivered ${formatDateTime(load.delivered_at)}`
        : `Delivery appt ${formatDateTime(load.delivery_datetime)}`;

  return (
    <ListRow selected={selected} onSelect={onSelect}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="truncate font-bold text-fg tabular-nums">{load.reference}</span>
          <StatusBadge status={load.status} />
        </div>
        {alert ? (
          <Badge tone="danger" className="shrink-0">No reply</Badge>
        ) : pending ? (
          <Badge tone="warn" className="shrink-0">
            {pending.source === "checkin" ? "Driver update" : "Draft to review"}
          </Badge>
        ) : null}
      </div>
      <div className="mt-1 flex min-w-0 items-center gap-1 text-xs text-fg-2">
        <span className="shrink-0">{load.customer_name || "Customer not set"}</span>
        <span aria-hidden="true">·</span>
        <span className="truncate">
          {cityState(load.pickup_city, load.pickup_state)} → {cityState(load.delivery_city, load.delivery_state)}
        </span>
      </div>
      <p className="mt-1 text-xs text-muted tabular-nums">{timeLine}</p>
    </ListRow>
  );
}

function LoadStatusDetail({ load }: { load: Load }) {
  const [preview, setPreview] = useState<StatusUpdate | null>(null);
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
  if (detail.isError) {
    return (
      <ErrorState
        message={(detail.error as Error).message}
        onRetry={() => void detail.refetch()}
      />
    );
  }
  if (!data) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="space-y-2">
            <Skeleton className="h-5 w-32" />
            <Skeleton className="h-4 w-40" />
          </div>
          <Skeleton className="h-14 w-20" />
        </div>
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-8 w-full" />
      </div>
    );
  }
  const margin = Number(data.margin ?? Number(data.customer_rate ?? 0) - Number(data.carrier_rate ?? 0));
  const marginPct = Number(data.margin_pct ?? 0);
  const ping = data.latest_location_ping;
  const from = cityState(data.pickup_city, data.pickup_state);
  const to = cityState(data.delivery_city, data.delivery_state);
  const statuses: LoadStatus[] = ["booked", "picked_up", "in_transit", "delayed", "delivered"];
  return (
    <>
      <div>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-lg font-extrabold text-fg tabular-nums">{data.reference}</h2>
                <StatusBadge status={data.status} />
              </div>
              <p className="mt-1 text-sm font-semibold text-fg-2">{data.customer_name || "Customer not set"}</p>
            </div>
            <div className={`shrink-0 rounded-xl px-3 py-2 text-right tabular-nums ${margin < 0 ? "bg-danger/10 text-danger-ink" : "bg-ok/10 text-ok-ink"}`}>
              <p className="text-[10px] font-bold uppercase tracking-wide">Margin</p>
              <p className="text-sm font-extrabold tabular-nums">{formatMoney(margin)}</p>
              <p className="text-[10px] font-semibold tabular-nums">{marginPct.toFixed(1)}%</p>
            </div>
          </div>
          <div className="mt-4 rounded-xl bg-surface-2 px-3 py-3">
            <Lane from={from} to={to} />
            <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-[11px] text-muted">
              <span className="tabular-nums">Pickup {formatDateTime(data.pickup_datetime)}</span>
              <span className="tabular-nums">Delivery {formatDateTime(data.delivery_datetime)}</span>
            </div>
          </div>
          <div className="mt-5">
            <StatusRail status={data.status} />
          </div>
          {pending && (
            <Button
              onClick={() => setPreview(pending)}
              variant="ghost"
              full
              className="mt-4 h-auto min-h-0 flex-col items-stretch justify-start whitespace-normal rounded-xl border border-warn/40 bg-warn/10 p-3 text-left hover:bg-warn/15"
            >
              <span className="flex items-center justify-between gap-3">
                <span className="text-xs font-bold uppercase tracking-wide text-warn-ink">
                  Pending {pending.source === "checkin" ? "driver update" : "draft"}
                </span>
                <span className="text-xs font-bold text-fg-2">Review message →</span>
              </span>
              {pending.source === "checkin" && (
                <span className="mt-1 block text-sm font-semibold text-fg-2 tabular-nums">
                  Driver replied: “{data.checkins.find((item) => item.id === pending.checkin_id)?.reply_raw_text || pending.note || "Update"}”
                  <span className="font-normal tabular-nums"> → {statusNames[pending.status]}{pending.eta ? ` · ETA ${formatDateTime(pending.eta)}` : ""}</span>
                </span>
              )}
            </Button>
          )}
          <div className="mt-4">
            <p className="mb-2 text-[11px] font-bold uppercase tracking-[0.12em] text-muted">Update status</p>
            <div className="flex gap-2 overflow-x-auto pb-1">
              {statuses.map((status) => (
                <button
                  key={status}
                  onClick={() => setStatus.mutate(status)}
                  disabled={setStatus.isPending}
                  className={buttonClass("secondary", "sm", `min-h-10 shrink-0 rounded-lg px-3 text-xs font-bold ${
                    data.status === status
                      ? statusButtonStyles[status] ?? "bg-surface-3 text-fg-2"
                      : status === "delayed"
                        ? "border border-st-delayed/30 bg-st-delayed/10 text-st-delayed-ink hover:bg-st-delayed/15"
                        : "border border-line bg-surface text-fg-2 hover:bg-surface-2"
                  }`)}
                >
                  {statusNames[status]}
                </button>
              ))}
            </div>
          </div>
          <details className="mt-4 border-t border-line/60 pt-3">
            <summary className="flex min-h-10 cursor-pointer list-none items-center justify-between text-sm font-bold text-fg-2">
              <span className="flex items-center gap-2"><Clock3 className="h-4 w-4 text-subtle" /> Check-ins</span>
              <ChevronDown className="h-4 w-4 text-subtle" />
            </summary>
            <div className="pb-2 pt-2">
              <CheckinTimeline checkins={data.checkins} load={data} />
            </div>
          </details>
          {ping && (
            <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line px-3 py-2.5">
              <div className="flex items-center gap-2 text-xs text-fg-2">
                <MapPin className="h-4 w-4 text-muted" />
                <span className="tabular-nums"><strong className="text-fg">Last location</strong> {elapsed(ping.captured_at)}</span>
                <span className="rounded bg-surface-3 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-muted">Internal only</span>
              </div>
              <a
                href={`https://maps.google.com/?q=${Number(ping.lat)},${Number(ping.lng)}`}
                target="_blank"
                rel="noreferrer"
                className={buttonClass("ghost", "sm", "min-h-9 px-2 text-fg-2")}
              >
                Map <ExternalLink className="h-3 w-3" />
              </a>
            </div>
          )}
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Button
              onClick={() => tracking.mutate()}
              disabled={tracking.isPending || (!data.driver_phone && !data.driver_email && !data.dispatcher_phone && !data.dispatcher_email)}
              loading={tracking.isPending}
              variant="secondary"
              size="sm"
              icon={Send}
              className="min-h-10"
            >
              {tracking.isPending ? "Sending…" : "Send tracking link"}
            </Button>
            <details className="group relative">
              <summary className="inline-flex min-h-10 cursor-pointer list-none items-center gap-2 rounded-lg px-3 text-xs font-semibold text-fg-2 hover:bg-surface-3">
                <MessageSquare className="h-4 w-4" />
                Communications ({data.communications.length})
                <ChevronDown className="h-3.5 w-3.5" />
              </summary>
              <Card className="mt-2 max-h-52 overflow-y-auto p-2 sm:absolute sm:left-0 sm:z-10 sm:w-80">
                {data.communications.length ? (
                  data.communications.map((communication) => (
                    <div key={communication.id} className="border-b border-line/60 px-2 py-2 last:border-0">
                      <p className="text-[10px] font-bold uppercase text-subtle">{communication.direction} · {communication.tag.replaceAll("_", " ")}</p>
                      <p className="mt-1 line-clamp-3 text-xs text-fg-2">{communication.content}</p>
                    </div>
                  ))
                ) : (
                  <p className="px-2 py-3 text-xs text-muted">No messages logged for this load.</p>
                )}
              </Card>
            </details>
          </div>
      </div>
      {preview && <PreviewModal update={preview} detail={data} onClose={() => setPreview(null)} />}
    </>
  );
}

export default function Status() {
  const [includeDelivered, setIncludeDelivered] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();
  const wide = useMediaQuery("(min-width: 1280px)");
  const loads = useQuery({
    queryKey: ["loads", "delivery", includeDelivered],
    queryFn: () => api.loads("delivery", includeDelivered),
    refetchInterval: 30_000,
  });
  const alerts = useQuery({
    queryKey: ["alerts"],
    queryFn: api.alerts,
    refetchInterval: 30_000,
  });
  const pendingUpdates = useQuery({
    queryKey: ["status-updates", "pending_approval"],
    queryFn: api.pendingUpdates,
    refetchInterval: 30_000,
  });
  const selectedId = searchParams.get("load");
  const selectedLoad = loads.data?.find((load) => String(load.id) === selectedId);
  useEffect(() => {
    if (!wide || !loads.data?.length || selectedLoad) return;
    const next = new URLSearchParams(searchParams);
    next.set("load", String(loads.data[0].id));
    setSearchParams(next, { replace: true });
  }, [wide, loads.data, selectedLoad, searchParams, setSearchParams]);
  function selectLoad(id: number) {
    const next = new URLSearchParams(searchParams);
    next.set("load", String(id));
    setSearchParams(next);
  }
  function closeDetail() {
    const next = new URLSearchParams(searchParams);
    next.delete("load");
    setSearchParams(next);
  }
  const list = loads.isPending ? (
    <ListRowSkeleton />
  ) : (
    <Card className="p-2">
      <ul role="list" aria-label="Delivery status loads" className="space-y-1">
        {loads.data?.map((load) => (
          <li key={load.id}>
            <StatusListRow
              load={load}
              selected={selectedLoad?.id === load.id}
              onSelect={() => selectLoad(load.id)}
              alerts={alerts.data ?? []}
              pendingUpdates={pendingUpdates.data ?? []}
            />
          </li>
        ))}
      </ul>
    </Card>
  );
  return (
    <div>
      <PageHeading
        eyebrow="Active freight"
        title="Delivery Status"
        description="Check-ins, live status, and customer updates for every booked load."
        action={
          <label className="inline-flex min-h-11 cursor-pointer items-center gap-2 self-start rounded-xl border border-line-strong bg-surface px-3 text-sm font-semibold text-fg-2 sm:self-auto">
            <input
              type="checkbox"
              checked={includeDelivered}
              onChange={(event) => setIncludeDelivered(event.target.checked)}
              className="h-4 w-4 accent-accent"
            />
            Show delivered
          </label>
        }
      />
      <AttentionStrip />
      {loads.isError ? (
        <ErrorState
          message={(loads.error as Error).message}
          onRetry={() => void loads.refetch()}
        />
      ) : !loads.isPending && loads.data.length === 0 ? (
        <EmptyState icon={Truck} title="No active deliveries" description="Booked loads will appear here once a carrier is assigned." />
      ) : (
        <ListDetail
          list={list}
          detail={
            selectedLoad ? (
              <LoadStatusDetail key={selectedLoad.id} load={selectedLoad} />
            ) : null
          }
          detailTitle={selectedLoad?.reference ?? "Delivery status"}
          onCloseDetail={closeDetail}
        />
      )}
    </div>
  );
}
