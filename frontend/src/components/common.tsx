import { AlertTriangle, ArrowRight, MapPin } from "lucide-react";
import type { ComponentType, ReactNode } from "react";
import type { LoadStatus } from "../types";
import { statusLabel } from "../utils";

const statusStyle: Record<LoadStatus, string> = {
  new: "bg-slate-100 text-slate-700",
  posted: "bg-slate-100 text-slate-700",
  booked: "bg-slate-100 text-slate-700",
  picked_up: "bg-brand-100 text-brand-800",
  in_transit: "bg-indigo-100 text-indigo-800",
  delayed: "bg-amber-100 text-amber-800",
  delivered: "bg-emerald-100 text-emerald-800",
};

export function StatusBadge({ status }: { status: LoadStatus | string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-bold ${
        statusStyle[status as LoadStatus] ?? "bg-slate-100 text-slate-700"
      }`}
    >
      {statusLabel(status)}
    </span>
  );
}

export function FlagBadge({ flag }: { flag: "green" | "yellow" | "red" }) {
  const style = {
    green: "bg-emerald-100 text-emerald-800",
    yellow: "bg-amber-100 text-amber-800",
    red: "bg-rose-100 text-rose-800",
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
    <div className="flex min-w-0 items-center gap-2 text-sm font-semibold text-slate-700">
      {!compact && <MapPin className="h-4 w-4 shrink-0 text-brand-600" />}
      <span className="truncate">{from}</span>
      <ArrowRight className="h-3.5 w-3.5 shrink-0 text-slate-400" />
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
        <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-gold-700">
          {eyebrow}
        </p>
        <h1 className="mt-1 text-2xl font-extrabold tracking-tight text-ink sm:text-[30px]">
          {title}
        </h1>
        <p className="mt-1.5 text-sm text-slate-500">{description}</p>
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
    <div className="rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-14 text-center">
      <span className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-slate-100 text-slate-500">
        <Icon className="h-5 w-5" />
      </span>
      <h2 className="mt-4 font-bold text-slate-800">{title}</h2>
      <p className="mx-auto mt-1 max-w-sm text-sm text-slate-500">{description}</p>
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{message}</span>
    </div>
  );
}
