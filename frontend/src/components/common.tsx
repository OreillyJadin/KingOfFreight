import { AlertTriangle, ArrowRight, MapPin } from "lucide-react";
import type { ComponentType, ReactNode } from "react";
import type { LoadStatus } from "../types";
import { statusLabel } from "../utils";
import { Badge, Button, type BadgeTone } from "./ui";

const statusTone: Record<LoadStatus, BadgeTone> = {
  new: "neutral",
  posted: "neutral",
  booked: "info",
  picked_up: "neutral",
  in_transit: "neutral",
  delayed: "warn",
  delivered: "ok",
};

const statusClass: Partial<Record<LoadStatus, string>> = {
  picked_up: "bg-st-picked/15 text-st-picked-ink",
  in_transit: "bg-st-transit/15 text-st-transit-ink",
};

export function StatusBadge({ status }: { status: LoadStatus | string }) {
  return (
    <Badge
      tone={statusTone[status as LoadStatus] ?? "neutral"}
      className={statusClass[status as LoadStatus]}
    >
      {statusLabel(status)}
    </Badge>
  );
}

export function FlagBadge({ flag }: { flag: "green" | "yellow" | "red" }) {
  const tone = { green: "ok", yellow: "warn", red: "danger" }[flag] as BadgeTone;
  return (
    <Badge tone={tone} className="uppercase">
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {flag}
    </Badge>
  );
}

export function Lane({
  from,
  to,
  compact = false,
}: {
  from: string;
  to: string;
  compact?: boolean;
}) {
  return (
    <div className="flex min-w-0 items-center gap-2 text-sm font-semibold text-fg-2">
      {!compact && <MapPin className="h-4 w-4 shrink-0 text-muted" />}
      <span className="truncate">{from}</span>
      <ArrowRight className="h-3.5 w-3.5 shrink-0 text-subtle" />
      <span className="truncate">{to}</span>
    </div>
  );
}

export function PageHeading({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-col gap-4 sm:mb-7 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-accent-ink">
          {eyebrow}
        </p>
        <h1 className="mt-1 text-2xl font-extrabold tracking-tight text-fg sm:text-[30px]">
          {title}
        </h1>
        <p className="mt-1.5 text-sm text-muted">{description}</p>
      </div>
      {action}
    </div>
  );
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
}: {
  icon: ComponentType<{ className?: string }>;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-dashed border-line-strong bg-surface/50 px-6 py-14 text-center">
      <span className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-surface-3 text-muted">
        <Icon className="h-5 w-5" />
      </span>
      <h2 className="mt-4 font-bold text-fg">{title}</h2>
      <p className="mx-auto mt-1 max-w-sm text-sm text-muted">{description}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-danger/30 bg-danger/10 p-4 text-sm text-danger-ink">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <span className="flex-1">{message}</span>
      {onRetry && (
        <Button size="sm" variant="secondary" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}
