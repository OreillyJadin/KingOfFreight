import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  FileText,
  Inbox as InboxIcon,
  Mail,
  MoreHorizontal,
  Upload,
  WandSparkles,
} from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useToast } from "../useToast";
import LoadFields from "../components/LoadFields";
import Modal from "../components/Modal";
import { EmptyState, ErrorState, PageHeading, StatusBadge } from "../components/common";
import type { Carrier, Communication } from "../types";
import { draftFrom, payloadFromDraft, type LoadDraft } from "../load-form";
import { formatShortDateTime } from "../utils";

type Filter = "All" | "BOLs" | "Carrier" | "Check-in replies" | "Other";

function extractedMc(item: Communication) {
  return `${item.subject ?? ""} ${item.content}`.match(/\bMC[#\s-]*(\d{5,8})\b/i)?.[1];
}

function InboxItem({
  item,
  onReview,
}: {
  item: Communication;
  onReview: (item: Communication) => void;
}) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [carrier, setCarrier] = useState<Carrier | null>(null);
  const [verifyError, setVerifyError] = useState("");
  const mc = extractedMc(item);
  const loadQuery = useQuery({
    queryKey: ["load", item.load_id],
    queryFn: () => api.load(item.load_id!),
    enabled: item.tag === "checkin_reply" && item.load_id !== null,
  });
  const archive = useMutation({
    mutationFn: () => api.archive(item.id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["inbox"] });
      showToast("Message archived.");
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const verify = useMutation({
    mutationFn: () => api.verifyCarrier(mc ?? ""),
    onSuccess: (result) => {
      setCarrier(result);
      setVerifyError("");
    },
    onError: (error: Error) => setVerifyError(error.message),
  });
  const parsedCheckin = loadQuery.data?.checkins.find(
    (checkin) => checkin.reply_raw_text === item.content,
  );
  const tagLabel = item.tag.replaceAll("_", " ");
  return (
    <article className="rounded-2xl border border-line bg-surface p-4 shadow-card sm:p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-surface-3 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-fg-2">
              {tagLabel}
            </span>
            <span className="text-xs text-subtle">
              {formatShortDateTime(item.created_at)}
            </span>
          </div>
          <h2 className="mt-3 line-clamp-2 text-base font-bold text-fg">
            {item.subject || `${item.channel.toUpperCase()} message`}
          </h2>
          <p className="mt-1 truncate text-xs text-muted">
            From {item.from_addr || "Unknown sender"}
          </p>
        </div>
        <button
          onClick={() => archive.mutate()}
          disabled={archive.isPending}
          className="grid h-11 w-11 shrink-0 place-items-center rounded-xl text-muted hover:bg-surface-3 disabled:opacity-50"
          aria-label="Archive message"
          title="Archive"
        >
          <Archive className="h-4 w-4" />
        </button>
      </div>
      <p className="mt-4 whitespace-pre-line text-sm leading-6 text-fg-2">
        {item.content}
      </p>
      {item.tag === "bol" && (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl bg-accent/12 p-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-accent-ink">
            <FileText className="h-4 w-4" />
            Bill of lading
            {typeof item.extracted?.confidence === "number" && (
              <span className="text-xs font-medium text-accent-ink">
                · {Math.round(item.extracted.confidence * 100)}% confidence
              </span>
            )}
          </div>
          <div className="flex gap-2">
            {item.has_attachment && (
              <a
                href={`/api/files/bol/${item.id}`}
                target="_blank"
                rel="noreferrer"
                className="inline-flex min-h-10 items-center rounded-lg px-3 text-xs font-bold text-accent-ink hover:bg-accent/12"
              >
                View PDF
              </a>
            )}
            <button
              onClick={() => onReview(item)}
              className="min-h-10 rounded-lg bg-accent px-3 text-xs font-bold text-on-accent hover:bg-accent-hover"
            >
              Review BOL
            </button>
          </div>
        </div>
      )}
      {(item.tag === "mc_provided" || mc) && mc && (
        <div className="mt-4 rounded-xl border border-line p-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm font-semibold text-fg">
              Carrier MC <span className="font-mono text-accent-ink">{mc}</span>
            </p>
            {!carrier && (
              <button
                onClick={() => verify.mutate()}
                disabled={verify.isPending}
                className="min-h-10 rounded-lg border border-accent/40 px-3 text-xs font-bold text-accent-ink hover:bg-accent/12 disabled:opacity-50"
              >
                {verify.isPending ? "Checking…" : "Verify MC"}
              </button>
            )}
          </div>
          {carrier && (
            <div className="mt-3 flex items-start justify-between gap-3 border-t border-line/60 pt-3">
              <div>
                <p className="text-sm font-bold text-fg">
                  {carrier.legal_name || "Carrier record"}
                </p>
                <ul className="mt-1 space-y-1 text-xs text-fg-2">
                  {carrier.flag_reasons.map((reason) => <li key={reason}>• {reason}</li>)}
                </ul>
              </div>
              <span
                className={`rounded-full px-2.5 py-1 text-[10px] font-bold uppercase ${
                  carrier.flag === "green"
                    ? "bg-ok/15 text-ok-ink"
                    : carrier.flag === "yellow"
                      ? "bg-warn/20 text-warn-ink"
                      : "bg-danger/15 text-danger-ink"
                }`}
              >
                {carrier.flag}
              </span>
            </div>
          )}
          {verifyError && <p className="mt-2 text-xs text-danger-ink">{verifyError}</p>}
        </div>
      )}
      {item.tag === "checkin_reply" && item.load_id !== null && (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl bg-surface-2 p-3">
          <div className="text-sm text-fg-2">
            Parsed status:{" "}
            {parsedCheckin?.parsed_status ? (
              <StatusBadge status={parsedCheckin.parsed_status} />
            ) : (
              <span className="font-semibold">Unclear</span>
            )}
          </div>
          <Link
            to={`/status?load=${item.load_id}`}
            className="inline-flex min-h-10 items-center gap-1 rounded-lg px-2 text-xs font-bold text-accent-ink hover:bg-accent/12"
          >
            View load
          </Link>
        </div>
      )}
    </article>
  );
}

function BolReview({
  item,
  onClose,
  onCreated,
}: {
  item: Communication;
  onClose: () => void;
  onCreated: () => void;
}) {
  const extracted = (item.extracted ?? {}) as Record<string, unknown>;
  const [draft, setDraft] = useState<LoadDraft>(() => draftFrom(extracted));
  const [error, setError] = useState("");
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const create = useMutation({
    mutationFn: () =>
      api.createLoadFromInbox(item.id, payloadFromDraft(draft)),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["inbox"] }),
        queryClient.invalidateQueries({ queryKey: ["loads"] }),
      ]);
      showToast("Load created from BOL.");
      onCreated();
    },
    onError: (issue: Error) => setError(issue.message),
  });
  return (
    <Modal
      title="Review bill of lading"
      eyebrow="BOL intake"
      onClose={onClose}
      size="max-w-3xl"
    >
      <div className="mb-5 rounded-xl bg-accent/12 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm font-bold text-accent-ink tabular-nums">
            Extraction confidence: {Math.round(Number(extracted.confidence ?? 0) * 100)}%
          </p>
          {item.has_attachment && (
            <a
              className="text-xs font-bold text-accent-ink underline underline-offset-2"
              href={`/api/files/bol/${item.id}`}
              target="_blank"
              rel="noreferrer"
            >
              View original PDF
            </a>
          )}
        </div>
        {Boolean(extracted.notes) && (
          <p className="mt-1 text-xs leading-5 text-accent-ink">{String(extracted.notes)}</p>
        )}
      </div>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          setError("");
          create.mutate();
        }}
      >
        <div className="max-h-[52dvh] overflow-y-auto pr-1">
          <LoadFields
            value={draft}
            onChange={(key, value) =>
              setDraft((current) => ({ ...current, [key]: value }))
            }
          />
        </div>
        {error && <p className="mt-4 text-sm text-danger-ink">{error}</p>}
        <div className="sticky bottom-0 mt-5 flex flex-col-reverse gap-2 border-t border-line/60 bg-surface pt-4 sm:flex-row sm:justify-end">
          <button
            type="button"
            onClick={onClose}
            className="min-h-11 rounded-xl border border-line-strong px-4 text-sm font-semibold text-fg-2 hover:bg-surface-2"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={create.isPending || !draft.reference.trim()}
            className="min-h-11 rounded-xl bg-accent px-5 text-sm font-bold text-on-accent hover:bg-accent-hover disabled:opacity-50"
          >
            {create.isPending ? "Creating…" : "Create load"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function SimulationMenu() {
  const [open, setOpen] = useState(false);
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  async function simulate(action: "sms" | "email" | "tick") {
    setOpen(false);
    try {
      if (action === "tick") {
        await api.runTick();
      } else if (action === "sms") {
        const from = window.prompt("Driver phone", "+13125550111");
        if (!from) return;
        const body = window.prompt("Reply text", "Running an hour behind");
        if (!body) return;
        await api.simulateSms(from, body);
      } else {
        const from = window.prompt("Sender email", "driver@example.com");
        if (!from) return;
        const subject = window.prompt("Subject", "Load update");
        if (!subject) return;
        const body = window.prompt("Email body", "We are delayed in traffic");
        if (!body) return;
        await api.simulateEmail(from, subject, body);
      }
      await queryClient.invalidateQueries();
      showToast(action === "tick" ? "Scheduler tick complete." : "Demo message received.");
    } catch (error) {
      showToast(error instanceof Error ? error.message : "Simulation failed.", "error");
    }
  }
  if (!import.meta.env.DEV) return null;
  return (
    <div className="relative">
      <button
        onClick={() => setOpen((value) => !value)}
        className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-line-strong bg-surface px-3 text-sm font-semibold text-fg-2 hover:bg-surface-2"
      >
        <WandSparkles className="h-4 w-4 text-accent-ink" />
        Simulate
      </button>
      {open && (
        <div className="absolute right-0 top-12 z-20 w-52 rounded-xl border border-line bg-surface p-1 shadow-xl">
          <button onClick={() => void simulate("sms")} className="w-full rounded-lg px-3 py-2.5 text-left text-sm hover:bg-surface-2">
            Simulate SMS reply
          </button>
          <button onClick={() => void simulate("email")} className="w-full rounded-lg px-3 py-2.5 text-left text-sm hover:bg-surface-2">
            Simulate inbound email
          </button>
          <button onClick={() => void simulate("tick")} className="w-full rounded-lg px-3 py-2.5 text-left text-sm hover:bg-surface-2">
            Run scheduler tick
          </button>
        </div>
      )}
    </div>
  );
}

export default function Inbox() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { showToast } = useToast();
  const fileInput = useRef<HTMLInputElement>(null);
  const [filter, setFilter] = useState<Filter>("All");
  const [review, setReview] = useState<Communication | null>(null);
  const inbox = useQuery({
    queryKey: ["inbox"],
    queryFn: api.inbox,
    refetchInterval: 30_000,
  });
  const upload = useMutation({
    mutationFn: api.uploadBol,
    onSuccess: async (item) => {
      await queryClient.invalidateQueries({ queryKey: ["inbox"] });
      setReview(item);
      showToast("BOL uploaded. Review extracted fields.");
    },
    onError: (error: Error) => showToast(error.message, "error"),
  });
  const items = useMemo(() => {
    const all = inbox.data ?? [];
    if (filter === "BOLs") return all.filter((item) => item.tag === "bol");
    if (filter === "Carrier") {
      return all.filter((item) => ["mc_provided", "availability"].includes(item.tag));
    }
    if (filter === "Check-in replies") {
      return all.filter((item) => item.tag === "checkin_reply");
    }
    if (filter === "Other") {
      return all.filter(
        (item) => !["bol", "mc_provided", "availability", "checkin_reply"].includes(item.tag),
      );
    }
    return all;
  }, [filter, inbox.data]);
  return (
    <div>
      <PageHeading
        eyebrow="Communication hub"
        title="Inbox"
        description="BOLs, carrier notes, and driver updates in one place."
        action={
          <div className="flex items-center gap-2">
            <SimulationMenu />
            <input
              ref={fileInput}
              type="file"
              accept="application/pdf"
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) upload.mutate(file);
                event.target.value = "";
              }}
            />
            <button
              onClick={() => fileInput.current?.click()}
              disabled={upload.isPending}
              className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-accent px-4 text-sm font-bold text-on-accent shadow-sm hover:bg-accent-hover disabled:opacity-60"
            >
              <Upload className="h-4 w-4" />
              {upload.isPending ? "Uploading…" : "Upload BOL"}
            </button>
          </div>
        }
      />
      <div className="mb-5 flex gap-2 overflow-x-auto pb-1">
        {(["All", "BOLs", "Carrier", "Check-in replies", "Other"] as Filter[]).map((item) => (
          <button
            key={item}
            onClick={() => setFilter(item)}
            className={`min-h-10 shrink-0 rounded-full px-4 text-sm font-semibold ${
              filter === item
                ? "bg-accent text-on-accent"
                : "border border-line bg-surface text-fg-2 hover:bg-surface-2"
            }`}
          >
            {item}
          </button>
        ))}
        <span className="ml-auto hidden items-center gap-1.5 text-xs text-subtle sm:flex">
          <MoreHorizontal className="h-4 w-4" />
          {items.length} messages
        </span>
      </div>
      {inbox.isError ? (
        <ErrorState message={(inbox.error as Error).message} />
      ) : inbox.isPending ? (
        <div className="grid min-h-40 place-items-center text-sm text-muted">Loading inbox…</div>
      ) : items.length === 0 ? (
        <EmptyState
          icon={filter === "All" ? InboxIcon : Mail}
          title={filter === "All" ? "Your inbox is clear" : `No ${filter.toLowerCase()} yet`}
          description={
            filter === "All"
              ? "New BOLs, carrier messages, and driver replies will appear here."
              : "Try another filter or upload a BOL to get started."
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {items.map((item) => (
            <InboxItem key={item.id} item={item} onReview={setReview} />
          ))}
        </div>
      )}
      {review && (
        <BolReview
          item={review}
          onClose={() => setReview(null)}
          onCreated={() => {
            setReview(null);
            navigate("/truckstop");
          }}
        />
      )}
    </div>
  );
}
