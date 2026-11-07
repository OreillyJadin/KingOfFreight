import { useId, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { Radar } from "lucide-react";
import { EmptyState } from "../components/common";
import { buttonClass, Card, Skeleton } from "../components/ui";
import { compactMoney, count, money, pct } from "./format";

export function KofConnectionEmptyState() {
  return (
    <EmptyState
      icon={Radar}
      title="Connect King of Freight to see your loads"
      description="Connect your King of Freight account in Settings to start syncing loads."
      action={
        <Link to="/settings" className={buttonClass("primary")}>
          Open Settings
        </Link>
      }
    />
  );
}

export function Kpi({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "default" | "accent";
}) {
  return (
    <Card className="p-4">
      <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-muted">{label}</p>
      <p
        className={`mt-1.5 text-2xl font-extrabold tabular-nums tracking-tight ${
          tone === "accent" ? "text-accent-ink" : "text-fg"
        }`}
      >
        {value}
      </p>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </Card>
  );
}

export function KpiSkeleton() {
  return (
    <Card className="space-y-2 p-4">
      <Skeleton className="h-3 w-20" />
      <Skeleton className="h-7 w-28" />
      <Skeleton className="h-3 w-16" />
    </Card>
  );
}

export type SeriesPoint = { period: string; revenue: number; cost: number; profit: number };

/** Grouped revenue/cost bars with a profit line, drawn as inline SVG (no chart dependency). */
export function RevenueChart({
  data,
  labelFor,
  height = 220,
}: {
  data: SeriesPoint[];
  labelFor: (period: string) => string;
  height?: number;
}) {
  const titleId = useId();
  if (!data.length) {
    return (
      <p className="py-10 text-center text-sm text-muted">No loads in this range.</p>
    );
  }
  const width = 760;
  const padding = { top: 16, right: 16, bottom: 34, left: 54 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const max = Math.max(...data.map((d) => Math.max(d.revenue, d.cost)), 1);
  const step = plotWidth / data.length;
  const barWidth = Math.max(4, Math.min(18, step / 3));
  const y = (value: number) => padding.top + plotHeight - (value / max) * plotHeight;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => t * max);
  const profitPoints = data
    .map((d, index) => `${padding.left + step * (index + 0.5)},${y(Math.max(d.profit, 0))}`)
    .join(" ");
  const labelEvery = Math.ceil(data.length / 8);

  return (
    <figure className="overflow-x-auto">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="h-[220px] w-full min-w-[520px]"
        role="img"
        aria-labelledby={titleId}
      >
        <title id={titleId}>
          Revenue, cost and profit by period. Latest period revenue {compactMoney(data[data.length - 1].revenue)}.
        </title>
        {ticks.map((tick) => (
          <g key={tick}>
            <line
              x1={padding.left}
              x2={width - padding.right}
              y1={y(tick)}
              y2={y(tick)}
              className="stroke-line"
              strokeWidth={1}
            />
            <text
              x={padding.left - 8}
              y={y(tick) + 4}
              textAnchor="end"
              className="fill-muted text-[11px] tabular-nums"
            >
              {compactMoney(tick)}
            </text>
          </g>
        ))}
        {data.map((point, index) => {
          const center = padding.left + step * (index + 0.5);
          return (
            <g key={point.period}>
              <rect
                x={center - barWidth - 1}
                y={y(point.revenue)}
                width={barWidth}
                height={Math.max(1, padding.top + plotHeight - y(point.revenue))}
                rx={2}
                className="fill-st-booked"
              />
              <rect
                x={center + 1}
                y={y(point.cost)}
                width={barWidth}
                height={Math.max(1, padding.top + plotHeight - y(point.cost))}
                rx={2}
                className="fill-surface-3"
              />
              {index % labelEvery === 0 && (
                <text
                  x={center}
                  y={height - 12}
                  textAnchor="middle"
                  className="fill-muted text-[11px]"
                >
                  {labelFor(point.period)}
                </text>
              )}
            </g>
          );
        })}
        <polyline
          points={profitPoints}
          fill="none"
          className="stroke-accent"
          strokeWidth={2}
          strokeLinejoin="round"
        />
      </svg>
      <figcaption className="mt-2 flex flex-wrap gap-4 text-xs text-muted">
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm bg-st-booked" /> Revenue
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm bg-surface-3" /> Carrier cost
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-0.5 w-4 rounded-full bg-accent" /> Profit
        </span>
      </figcaption>
    </figure>
  );
}

export type Column<T> = {
  key: string;
  header: string;
  align?: "left" | "right";
  width?: string;
  render: (row: T) => ReactNode;
};

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  caption,
  onRowClick,
  activeKey,
  emptyMessage = "Nothing to show yet.",
}: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string | number;
  caption: string;
  onRowClick?: (row: T) => void;
  activeKey?: string | number | null;
  emptyMessage?: string;
}) {
  if (!rows.length) {
    return <p className="px-4 py-10 text-center text-sm text-muted">{emptyMessage}</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] border-collapse text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="border-b border-line">
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                style={column.width ? { width: column.width } : undefined}
                className={`whitespace-nowrap px-3 py-2.5 text-[11px] font-bold uppercase tracking-[0.12em] text-muted ${
                  column.align === "right" ? "text-right" : "text-left"
                }`}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const key = rowKey(row);
            const selected = activeKey !== undefined && activeKey === key;
            return (
              <tr
                key={key}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                aria-current={selected ? "true" : undefined}
                className={`border-b border-line/60 last:border-0 ${
                  onRowClick ? "cursor-pointer hover:bg-surface-2" : ""
                } ${selected ? "bg-surface-3" : ""}`}
              >
                {columns.map((column) => (
                  <td
                    key={column.key}
                    className={`px-3 py-2.5 align-top ${
                      column.align === "right" ? "whitespace-nowrap text-right tabular-nums" : "text-left"
                    }`}
                  >
                    {column.render(row)}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function TableSkeleton({ rows = 8 }: { rows?: number }) {
  return (
    <div className="space-y-2 p-3">
      {Array.from({ length: rows }, (_, index) => (
        <Skeleton key={index} className="h-10" />
      ))}
    </div>
  );
}

export function MoneyCell({ value, digits = 0 }: { value?: number | null; digits?: number }) {
  return <span className="tabular-nums">{money(value, digits)}</span>;
}

export function MarginCell({ value }: { value?: number | null }) {
  const tone =
    value === null || value === undefined
      ? "text-muted"
      : value >= 15
        ? "text-ok-ink"
        : value >= 8
          ? "text-fg-2"
          : "text-warn-ink";
  return <span className={`tabular-nums font-semibold ${tone}`}>{pct(value)}</span>;
}

export function CountCell({ value }: { value?: number | null }) {
  return <span className="tabular-nums">{count(value)}</span>;
}
