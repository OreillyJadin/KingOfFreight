import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDownToLine,
  Check,
  ChevronDown,
  Clipboard,
  Plus,
  Truck,
} from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useToast } from "../useToast";
import LoadFields from "../components/LoadFields";
import { ListDetail, ListRow, ListRowSkeleton } from "../components/ListDetail";
import Modal from "../components/Modal";
import { EmptyState, ErrorState, FlagBadge, Lane, PageHeading, StatusBadge } from "../components/common";
import { Button, Card, Input, Select } from "../components/ui";
import { cityState, formatDateTime, formatMoney } from "../utils";
import { draftFrom, payloadFromDraft, type LoadDraft } from "../load-form";
import type { BookPayload, Carrier, Load, NewLoad } from "../types";
import { useMediaQuery } from "../useMediaQuery";

function BookingModal({
  load,
  onClose,
}: {
  load: Load;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const navigate = useNavigate();
  const { showToast } = useToast();
  const [mc, setMc] = useState("");
  const [carrier, setCarrier] = useState<Carrier | null>(null);
  const [override, setOverride] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    carrier_rate: load.carrier_rate ? String(load.carrier_rate) : "",
    customer_rate: load.customer_rate ? String(load.customer_rate) : "",
    driver_name: "",
    driver_phone: "",
    driver_email: "",
    dispatcher_name: "",
    dispatcher_phone: "",
    dispatcher_email: "",
    checkin_offset_minutes: "",
    checkin_channel: "",
  });
  const verify = useMutation({
    mutationFn: () => api.verifyCarrier(mc),
    onSuccess: (result) => {
      setCarrier(result);
      setOverride(false);
      setError("");
    },
    onError: (issue: Error) => setError(issue.message),
  });
  const book = useMutation({
    mutationFn: (payload: BookPayload) => api.bookLoad(load.id, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries();
      showToast("Carrier booked. Check-ins are scheduled.");
      onClose();
      navigate("/status");
    },
    onError: (issue: Error) => setError(issue.message),
  });
  const contactReady = Boolean(
    form.driver_phone.trim() ||
      form.driver_email.trim() ||
      form.dispatcher_phone.trim() ||
      form.dispatcher_email.trim(),
  );
  const margin =
    (Number(form.customer_rate) || 0) - (Number(form.carrier_rate) || 0);
  const marginPct = Number(form.customer_rate)
    ? (margin / Number(form.customer_rate)) * 100
    : 0;
  function change(key: keyof typeof form, value: string) {
    setForm((current) => ({ ...current, [key]: value }));
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (!carrier) {
      setError("Verify a carrier before booking.");
      return;
    }
    if (carrier.flag === "red" && !override) {
      setError("A red-flag carrier requires an explicit override.");
      return;
    }
    if (!contactReady) {
      setError("Need at least one driver or dispatcher phone/email.");
      return;
    }
    book.mutate({
      carrier_mc: mc,
      carrier_rate: Number(form.carrier_rate),
      customer_rate: Number(form.customer_rate),
      driver_name: form.driver_name || undefined,
      driver_phone: form.driver_phone || undefined,
      driver_email: form.driver_email || undefined,
      dispatcher_name: form.dispatcher_name || undefined,
      dispatcher_phone: form.dispatcher_phone || undefined,
      dispatcher_email: form.dispatcher_email || undefined,
      ...(form.checkin_offset_minutes
        ? { checkin_offset_minutes: Number(form.checkin_offset_minutes) }
        : {}),
      ...(form.checkin_channel
        ? { checkin_channel: form.checkin_channel as "sms" | "email" }
        : {}),
      override_red_flag: override,
    });
  }
  return (
    <Modal
      title={`Book carrier · ${load.reference}`}
      eyebrow="Carrier assignment"
      onClose={onClose}
      size="max-w-3xl"
      footer={
        <div className="flex w-full flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="submit"
            form="book-carrier-form"
            variant="primary"
            disabled={!carrier || !contactReady || book.isPending || (carrier.flag === "red" && !override)}
            loading={book.isPending}
          >
            {book.isPending ? "Booking…" : "Book carrier"}
          </Button>
        </div>
      }
    >
      <form id="book-carrier-form" onSubmit={submit} className="space-y-5">
        <div>
          <label className="mb-1.5 block text-xs font-semibold text-fg-2">Carrier MC number</label>
          <div className="flex gap-2">
            <Input
              value={mc}
              onChange={(event) => {
                setMc(event.target.value);
                setCarrier(null);
              }}
              placeholder="e.g. 123456"
              className="h-11 min-w-0 flex-1 rounded-xl"
            />
            <Button
              type="button"
              onClick={() => verify.mutate()}
              disabled={!mc.trim() || verify.isPending}
              loading={verify.isPending}
              variant="secondary"
              className="shrink-0"
            >
              {verify.isPending ? "Checking…" : "Verify"}
            </Button>
          </div>
          {carrier && (
            <div className="mt-3 rounded-xl border border-line bg-surface-2 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="font-bold text-fg">{carrier.legal_name || "Carrier record"}</p>
                  <p className="mt-0.5 text-xs text-muted">
                    MC {carrier.mc_number}{carrier.dot_number ? ` · DOT ${carrier.dot_number}` : ""}
                  </p>
                </div>
                <FlagBadge flag={carrier.flag} />
              </div>
              <ul className="mt-2 space-y-1 text-xs text-fg-2">
                {carrier.flag_reasons.map((reason) => <li key={reason}>• {reason}</li>)}
              </ul>
              {carrier.flag === "red" && (
                <label className="mt-3 flex min-h-11 cursor-pointer items-center gap-2 rounded-lg border border-danger/30 bg-danger/10 px-3 text-sm font-semibold text-danger-ink">
                  <input
                    type="checkbox"
                    checked={override}
                    onChange={(event) => setOverride(event.target.checked)}
                    className="h-4 w-4 accent-danger"
                  />
                  Override red flag
                </label>
              )}
            </div>
          )}
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label>
            <span className="mb-1.5 block text-xs font-semibold text-fg-2">Carrier rate ($)</span>
            <Input
              type="number"
              min="0"
              step="0.01"
              required
              value={form.carrier_rate}
              onChange={(event) => change("carrier_rate", event.target.value)}
              className="h-11 rounded-xl tabular-nums"
            />
          </label>
          <label>
            <span className="mb-1.5 block text-xs font-semibold text-fg-2">Customer rate ($)</span>
            <Input
              type="number"
              min="0"
              step="0.01"
              required
              value={form.customer_rate}
              onChange={(event) => change("customer_rate", event.target.value)}
              className="h-11 rounded-xl tabular-nums"
            />
          </label>
        </div>
        <div className={`flex items-center justify-between rounded-xl px-4 py-3 ${margin < 0 ? "bg-danger/10 text-danger-ink" : "bg-ok/10 text-fg-2"}`}>
          <span className="text-sm font-semibold">Estimated margin</span>
          <span className="text-sm font-extrabold tabular-nums">
            {formatMoney(margin)} <span className="ml-1 text-xs font-semibold tabular-nums">({marginPct.toFixed(1)}%)</span>
          </span>
        </div>
        <section>
          <h3 className="mb-2 text-xs font-bold uppercase tracking-[0.12em] text-muted">Driver contact</h3>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {([
              ["driver_name", "Driver name", "text"],
              ["driver_phone", "Driver phone", "tel"],
              ["driver_email", "Driver email", "email"],
              ["dispatcher_name", "Dispatcher name", "text"],
              ["dispatcher_phone", "Dispatcher phone", "tel"],
              ["dispatcher_email", "Dispatcher email", "email"],
            ] as const).map(([key, label, type]) => (
              <label key={key}>
                <span className="mb-1.5 block text-xs font-semibold text-fg-2">{label}</span>
                <Input
                  type={type}
                  value={form[key]}
                  onChange={(event) => change(key, event.target.value)}
                  className="h-10"
                />
              </label>
            ))}
          </div>
          {!contactReady && (
            <p className="mt-2 text-xs text-warn-ink">
              Need at least one driver or dispatcher phone/email.
            </p>
          )}
        </section>
        <details open={advanced} onToggle={(event) => setAdvanced(event.currentTarget.open)} className="rounded-xl border border-line">
          <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between px-3 text-sm font-semibold text-fg-2">
            Advanced check-in settings
            <ChevronDown className="h-4 w-4" />
          </summary>
          <div className="grid gap-3 border-t border-line/60 p-3 sm:grid-cols-2">
            <label>
              <span className="mb-1.5 block text-xs font-semibold text-fg-2">Offset minutes</span>
              <Input
                type="number"
                min="0"
                placeholder={String(settings.data?.checkin_offset_minutes ?? 60)}
                value={form.checkin_offset_minutes}
                onChange={(event) => change("checkin_offset_minutes", event.target.value)}
                className="h-10"
              />
              <span className="mt-1 block text-xs text-muted">
                Default: {settings.data?.checkin_offset_minutes ?? 60} min
              </span>
            </label>
            <label>
              <span className="mb-1.5 block text-xs font-semibold text-fg-2">Check-in channel</span>
              <Select
                value={form.checkin_channel}
                onChange={(event) => change("checkin_channel", event.target.value)}
                className="h-10"
              >
                <option value="">Auto</option>
                <option value="sms">SMS</option>
                <option value="email">Email</option>
              </Select>
            </label>
          </div>
        </details>
        {error && <p className="text-sm text-danger-ink">{error}</p>}
      </form>
    </Modal>
  );
}

function NewLoadModal({ onClose }: { onClose: () => void }) {
  const [draft, setDraft] = useState<LoadDraft>(() => draftFrom());
  const [error, setError] = useState("");
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const create = useMutation({
    mutationFn: () => api.createLoad(payloadFromDraft(draft) as NewLoad),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["loads"] });
      showToast("New load added.");
      onClose();
    },
    onError: (issue: Error) => setError(issue.message),
  });
  return (
    <Modal
      title="Create a load"
      eyebrow="Manual entry"
      onClose={onClose}
      size="max-w-3xl"
      footer={
        <div className="flex w-full flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="submit"
            form="new-load-form"
            variant="primary"
            disabled={!draft.reference.trim() || create.isPending}
            loading={create.isPending}
          >
            {create.isPending ? "Saving…" : "Create load"}
          </Button>
        </div>
      }
    >
      <form id="new-load-form" onSubmit={(event) => { event.preventDefault(); create.mutate(); }}>
        <div className="max-h-[58dvh] overflow-y-auto pr-1">
          <LoadFields
            value={draft}
            includeDriver={false}
            onChange={(key, value) => setDraft((current) => ({ ...current, [key]: value }))}
          />
        </div>
        {error && <p className="mt-3 text-sm text-danger-ink">{error}</p>}
      </form>
    </Modal>
  );
}

function TruckStopListRow({
  load,
  selected,
  onSelect,
}: {
  load: Load;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <ListRow selected={selected} onSelect={onSelect}>
      <div className="flex items-center justify-between gap-2">
        <span className="truncate font-bold text-fg tabular-nums">{load.reference}</span>
        <StatusBadge status={load.status} />
      </div>
      <div className="mt-1">
        <Lane
          from={cityState(load.pickup_city, load.pickup_state)}
          to={cityState(load.delivery_city, load.delivery_state)}
          compact
        />
      </div>
      <div className="mt-1 flex min-w-0 items-center gap-1 text-xs text-fg-2">
        <span className="shrink-0">Pickup {formatDateTime(load.pickup_datetime)}</span>
        <span aria-hidden="true">·</span>
        <span className="truncate">{load.equipment_type || "Equipment TBD"}</span>
      </div>
      {load.customer_rate !== null && load.customer_rate !== undefined && load.customer_rate !== "" && (
        <p className="mt-1 text-xs text-muted">
          Customer rate <span className="font-semibold text-fg-2 tabular-nums">{formatMoney(load.customer_rate)}</span>
        </p>
      )}
    </ListRow>
  );
}

function LoadDetailPanel({
  load,
  onBook,
}: {
  load: Load;
  onBook: (load: Load) => void;
}) {
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const post = useMutation({
    mutationFn: () => api.postLoad(load.id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["loads"] });
      showToast(`${load.reference} marked as posted.`);
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });
  async function copyPost() {
    try {
      const text = await api.postText(load.id);
      await navigator.clipboard.writeText(text);
      showToast("Copied");
    } catch (error) {
      showToast(error instanceof Error ? error.message : "Unable to copy post.", "error");
    }
  }
  return (
    <div>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-bold uppercase tracking-[0.12em] text-subtle">Load</p>
          <h2 className="mt-1 text-lg font-extrabold text-fg tabular-nums">{load.reference}</h2>
        </div>
        <StatusBadge status={load.status} />
      </div>
      <div className="mt-4 rounded-xl bg-surface-2 p-3">
        <Lane
          from={cityState(load.pickup_city, load.pickup_state)}
          to={cityState(load.delivery_city, load.delivery_state)}
        />
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-subtle">Pickup</p>
          <p className="mt-1 font-semibold text-fg tabular-nums">{formatDateTime(load.pickup_datetime)}</p>
        </div>
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-subtle">Delivery</p>
          <p className="mt-1 font-semibold text-fg tabular-nums">{formatDateTime(load.delivery_datetime)}</p>
        </div>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 border-t border-line/60 pt-3 text-xs">
        <div><span className="text-subtle">Equipment</span><p className="mt-1 font-semibold text-fg-2">{load.equipment_type || "TBD"}</p></div>
        <div><span className="text-subtle">Weight</span><p className="mt-1 font-semibold text-fg-2">{load.weight_lbs ? `${Number(load.weight_lbs).toLocaleString()} lb` : "TBD"}</p></div>
        <div className="col-span-2"><span className="text-subtle">Customer</span><p className="mt-1 font-semibold text-fg-2">{load.customer_name || "Not assigned"}</p></div>
        {load.customer_rate !== null && load.customer_rate !== undefined && load.customer_rate !== "" && (
          <div><span className="text-subtle">Customer rate</span><p className="mt-1 font-semibold text-fg-2 tabular-nums">{formatMoney(load.customer_rate)}</p></div>
        )}
      </div>
      {(load.commodity || load.special_requirements || load.notes) && (
        <div className="mt-4 space-y-3 border-t border-line/60 pt-3 text-sm">
          {load.commodity && <p><span className="text-subtle">Commodity</span><br /><span className="font-medium text-fg-2">{load.commodity}</span></p>}
          {load.special_requirements && <p><span className="text-subtle">Special requirements</span><br /><span className="font-medium text-fg-2">{load.special_requirements}</span></p>}
          {load.notes && <p><span className="text-subtle">Notes</span><br /><span className="font-medium text-fg-2">{load.notes}</span></p>}
        </div>
      )}
      <div className="mt-5 flex flex-col gap-2 border-t border-line/60 pt-4 sm:flex-row">
        <Button
          onClick={() => void copyPost()}
          variant="secondary"
          icon={Clipboard}
          className="flex-1"
        >
          Copy TruckStop post
        </Button>
        {load.status === "new" && (
          <Button
            onClick={() => post.mutate()}
            disabled={post.isPending}
            loading={post.isPending}
            variant="secondary"
            icon={ArrowDownToLine}
          >
            Mark posted
          </Button>
        )}
        <Button
          onClick={() => onBook(load)}
          variant="primary"
          icon={Check}
        >
          Book carrier
        </Button>
      </div>
    </div>
  );
}

export default function TruckStop() {
  const [searchParams, setSearchParams] = useSearchParams();
  const wide = useMediaQuery("(min-width: 1280px)");
  const loads = useQuery({
    queryKey: ["loads", "truckstop", false],
    queryFn: () => api.loads("truckstop"),
    refetchInterval: 30_000,
  });
  const [booking, setBooking] = useState<Load | null>(null);
  const [newLoad, setNewLoad] = useState(false);
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
  function bookFromDetail(load: Load) {
    if (!wide) {
      const next = new URLSearchParams(searchParams);
      next.delete("load");
      setSearchParams(next);
    }
    setBooking(load);
  }
  const list = loads.isPending ? (
    <ListRowSkeleton />
  ) : (
    <Card className="p-2">
      <ul role="list" aria-label="Open loads" className="space-y-1">
        {loads.data?.map((load) => (
          <li key={load.id}>
            <TruckStopListRow
              load={load}
              selected={selectedLoad?.id === load.id}
              onSelect={() => selectLoad(load.id)}
            />
          </li>
        ))}
      </ul>
    </Card>
  );
  return (
    <div>
      <PageHeading
        eyebrow="Open freight"
        title="TruckStop"
        description="Prepare, post, and book your available loads."
        action={
          <Button
            onClick={() => setNewLoad(true)}
            variant="primary"
            icon={Plus}
            className="self-start sm:self-auto"
          >
            New load
          </Button>
        }
      />
      {loads.isError ? (
        <ErrorState
          message={(loads.error as Error).message}
          onRetry={() => void loads.refetch()}
        />
      ) : !loads.isPending && loads.data.length === 0 ? (
        <EmptyState
          icon={Truck}
          title="No open loads"
          description="Create a load or review a BOL to add freight to TruckStop."
          action={
            <Button onClick={() => setNewLoad(true)} variant="primary" icon={Plus}>
              New load
            </Button>
          }
        />
      ) : (
        <ListDetail
          list={list}
          detailKey={selectedLoad?.id ?? null}
          detail={
            selectedLoad ? (
              <LoadDetailPanel key={selectedLoad.id} load={selectedLoad} onBook={bookFromDetail} />
            ) : null
          }
          detailTitle={selectedLoad?.reference ?? "Load details"}
          onCloseDetail={closeDetail}
        />
      )}
      {booking && <BookingModal load={booking} onClose={() => setBooking(null)} />}
      {newLoad && <NewLoadModal onClose={() => setNewLoad(false)} />}
    </div>
  );
}
