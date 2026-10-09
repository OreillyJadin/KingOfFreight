import { AlertTriangle, ArrowRight, MapPin } from "lucide-react";
import type { ComponentType, ReactNode } from "react";
import type { LoadStatus } from "../types";
import { statusLabel } from "../utils";

const statusStyle: Record<LoadStatus, string> = {
  new: "bg-surface-3 text-fg-2",
  posted: "bg-surface-3 text-fg-2",
  booked: "bg-st-booked/15 text-st-booked-ink",
  picked_up: "bg-st-picked/15 text-st-picked-ink",
  in_transit: "bg-st-transit/15 text-st-transit-ink",
  delayed: "bg-st-delayed/15 text-st-delayed-ink",
  delivered: "bg-st-delivered/15 text-st-delivered-ink",
};

export function StatusBadge({ status }: { status: LoadStatus | string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-bold ${
        statusStyle[status as LoadStatus] ?? "bg-surface-3 text-fg-2"
      }`}
    >
      {statusLabel(status)}
    </span>
  );
}

export function FlagBadge({ flag }: { flag: "green" | "yellow" | "red" }) {
  const style = {
    green: "bg-ok/15 text-ok-ink",
    yellow: "bg-warn/15 text-warn-ink",
    red: "bg-danger/15 text-danger-ink",
  }[flag];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-bold uppercase ${style}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {flag}
    </span>
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
      {!compact && <MapPin className="h-4 w-4 shrink-0 text-accent-ink" />}
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
}: {
  icon: ComponentType<{ className?: string }>;
  title: string;
  description: string;
}) {
  return (
    <div className="rounded-2xl border border-dashed border-line-strong bg-surface px-6 py-14 text-center">
      <span className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-surface-3 text-muted">
        <Icon className="h-5 w-5" />
      </span>
      <h2 className="mt-4 font-bold text-fg">{title}</h2>
      <p className="mx-auto mt-1 max-w-sm text-sm text-muted">{description}</p>
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-danger/30 bg-danger/10 p-4 text-sm text-danger-ink">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{message}</span>
    </div>
  );
}
