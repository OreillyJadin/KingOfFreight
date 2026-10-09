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
import { EmptyState, ErrorState, FlagBadge, PageHeading, StatusBadge } from "../components/common";
import {
  Badge,
  Button,
  Card,
  CardListSkeleton,
  Input,
  Tabs,
  buttonClass,
} from "../components/ui";
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
    <Card as="article" className="p-4 sm:p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Badge className="uppercase tracking-wide">
              {tagLabel}
            </Badge>
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
        <Button
          onClick={() => archive.mutate()}
          disabled={archive.isPending}
          loading={archive.isPending}
          variant="ghost"
          icon={Archive}
          className="!w-11 !px-0 shrink-0 text-muted hover:bg-surface-3"
          aria-label="Archive message"
          title="Archive"
        />
      </div>
      <p className="mt-4 whitespace-pre-line text-sm leading-6 text-fg-2">
        {item.content}
      </p>
      {item.tag === "bol" && (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line bg-surface-2 p-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-fg-2">
            <FileText className="h-4 w-4 text-muted" />
            Bill of lading
            {typeof item.extracted?.confidence === "number" && (
              <span className="text-xs font-medium text-fg-2">
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
                className={buttonClass("ghost", "sm", "text-fg-2")}
              >
                View PDF
              </a>
            )}
            <Button
              onClick={() => onReview(item)}
              variant="primary"
              size="sm"
              className="min-h-10"
            >
              Review BOL
            </Button>
          </div>
        </div>
      )}
      {(item.tag === "mc_provided" || mc) && mc && (
        <div className="mt-4 rounded-xl border border-line p-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm font-semibold text-fg">
              Carrier MC <span className="font-mono tabular-nums text-fg">{mc}</span>
            </p>
            {!carrier && (
              <Button
                onClick={() => verify.mutate()}
                disabled={verify.isPending}
                loading={verify.isPending}
                variant="secondary"
                size="sm"
                className="min-h-10"
              >
                {verify.isPending ? "Checking…" : "Verify MC"}
              </Button>
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
              <FlagBadge flag={carrier.flag} />
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
            className={buttonClass("ghost", "sm", "min-h-10 px-2 text-fg-2")}
          >
            View load
          </Link>
        </div>
      )}
    </Card>
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
      footer={
        <div className="flex w-full flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="submit"
            form="bol-review-form"
            variant="primary"
            disabled={create.isPending || !draft.reference.trim()}
            loading={create.isPending}
          >
            {create.isPending ? "Creating…" : "Create load"}
          </Button>
        </div>
      }
    >
      <div className="mb-5 rounded-xl border border-line bg-surface-2 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm font-bold text-fg tabular-nums">
            Extraction confidence: {Math.round(Number(extracted.confidence ?? 0) * 100)}%
          </p>
          {item.has_attachment && (
            <a
              className={buttonClass("ghost", "sm", "text-fg-2")}
              href={`/api/files/bol/${item.id}`}
              target="_blank"
              rel="noreferrer"
            >
              View original PDF
            </a>
          )}
        </div>
        {Boolean(extracted.notes) && (
          <p className="mt-1 text-xs leading-5 text-fg-2">{String(extracted.notes)}</p>
        )}
      </div>
      <form
        id="bol-review-form"
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
      <Button
        onClick={() => setOpen((value) => !value)}
        variant="secondary"
      >
        <WandSparkles className="h-4 w-4 text-muted" />
        Simulate
      </Button>
      {open && (
        <div className="absolute right-0 top-12 z-20 w-52 rounded-xl border border-line bg-surface p-1 shadow-xl">
          <Button onClick={() => void simulate("sms")} variant="ghost" full className="justify-start py-2.5 text-left">
            Simulate SMS reply
          </Button>
          <Button onClick={() => void simulate("email")} variant="ghost" full className="justify-start py-2.5 text-left">
            Simulate inbound email
          </Button>
          <Button onClick={() => void simulate("tick")} variant="ghost" full className="justify-start py-2.5 text-left">
            Run scheduler tick
          </Button>
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
            <Input
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
            <Button
              onClick={() => fileInput.current?.click()}
              disabled={upload.isPending}
              loading={upload.isPending}
              variant="primary"
              icon={Upload}
              className="shadow-sm"
            >
              {upload.isPending ? "Uploading…" : "Upload BOL"}
            </Button>
          </div>
        }
      />
      <div className="mb-5 flex gap-2 overflow-x-auto pb-1">
        <Tabs<Filter>
          items={(["All", "BOLs", "Carrier", "Check-in replies", "Other"] as Filter[]).map((item) => ({
            value: item,
            label: item,
          }))}
          value={filter}
          onChange={setFilter}
          ariaLabel="Inbox filters"
        />
        <span className="ml-auto hidden items-center gap-1.5 text-xs text-subtle sm:flex">
          <MoreHorizontal className="h-4 w-4" />
          {items.length} messages
        </span>
      </div>
      {inbox.isError ? (
        <ErrorState
          message={(inbox.error as Error).message}
          onRetry={() => void inbox.refetch()}
        />
      ) : inbox.isPending ? (
        <CardListSkeleton />
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
