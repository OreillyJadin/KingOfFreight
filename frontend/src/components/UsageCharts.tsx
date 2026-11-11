import type { ReactNode } from "react";
import { Button, Card } from "./ui";
import { categories, categoryMix, contributionCells, personColor, type ContributionDay, type TrendPerson } from "../usage-visuals";

export function EmptyChart({ text = "No activity to chart." }: { text?: string }) {
  return <p className="py-7 text-sm text-muted">{text}</p>;
}
export function ChartCard({ title, pending, error, retry, children }: { title: string; pending?: boolean; error?: Error | null; retry?: () => void; children: ReactNode }) {
  return <Card className="min-w-0 space-y-3 p-4"><h2 className="text-lg font-bold">{title}</h2>{pending ? <p role="status" className="animate-pulse py-7 text-sm text-muted">Loading {title.toLowerCase()}…</p> : error ? <div role="alert"><p className="break-words text-sm text-danger-ink">{error.message}</p><Button className="mt-3" onClick={retry}>Retry</Button></div> : children}</Card>;
}
export function Legend({ names }: { names: string[] }) {
  return <ul className="flex flex-wrap gap-x-4 gap-y-2 text-xs">{names.map(name => <li className="flex min-w-0 items-center gap-1.5 break-all" key={name}><span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: personColor(name) }} />{name}</li>)}</ul>;
}
export type ChartSeries = { name: string; values: (number | null)[] };
export function SeriesChart({ labels, series, unit, stacked = false }: { labels: string[]; series: ChartSeries[]; unit: string; stacked?: boolean }) {
  if (!labels.length || !series.some(s => s.values.some(v => v !== null && v !== 0))) return <EmptyChart />;
  const width = 560, height = 230, left = 52, top = 14, bottom = 190, right = 540;
  const max = Math.max(1, ...labels.map((_, i) => stacked ? series.reduce((n, s) => n + (s.values[i] ?? 0), 0) : Math.max(...series.map(s => s.values[i] ?? 0))));
  const min = stacked ? 0 : Math.min(0, ...series.flatMap(s => s.values.filter((v): v is number => v !== null)));
  const x = (i: number) => left + i * (right - left) / Math.max(1, labels.length - 1);
  const y = (n: number) => bottom - (n - min) / (max - min) * (bottom - top);
  const cumulative = labels.map(() => 0);
  const ticks = [...new Set([0, Math.floor((labels.length - 1) / 2), labels.length - 1])];
  return <><div className="overflow-x-auto pb-2" role="region" aria-label={unit + " chart; scroll horizontally"} tabIndex={0}><svg role="img" aria-label={unit + (stacked ? " stacked by person" : " over time")} viewBox={`0 0 ${width} ${height}`} className="w-full min-w-[520px] text-muted"><title>{`${unit} over time`}</title>{[min, (max + min) / 2, max].map((n, i) => <g key={i}><line x1={left} x2={right} y1={y(n)} y2={y(n)} stroke="currentColor" opacity=".15" /><text x={left - 7} y={y(n) + 4} textAnchor="end" fill="currentColor" fontSize="10">{Math.round(n).toLocaleString()}</text></g>)}{series.map(s => {
    const lower = [...cumulative];
    if (stacked) s.values.forEach((n, i) => cumulative[i] += n ?? 0);
    const points = s.values.map((n, i) => `${x(i)},${y(stacked ? cumulative[i] : n ?? 0)}`);
    const area = stacked ? `M${points.join(" L")} L${lower.map((n, i) => `${x(i)},${y(n)}`).reverse().join(" L")} Z` : "";
    return <g key={s.name}>{stacked ? <path d={area} fill={personColor(s.name)} fillOpacity=".65" stroke={personColor(s.name)} /> : <path d={s.values.map((n, i) => n === null ? "" : `${i === 0 || s.values[i - 1] === null ? "M" : "L"}${x(i)},${y(n)}`).join(" ")} fill="none" stroke={personColor(s.name)} strokeWidth="2.5" />}{s.values.map((n, i) => n === null ? null : <circle key={i} cx={x(i)} cy={y(stacked ? cumulative[i] : n)} r={labels.length > 95 ? 1 : 3} fill={personColor(s.name)} tabIndex={0} aria-label={`${s.name}, ${labels[i]}: ${n} ${unit}`}><title>{`${s.name} · ${labels[i]}: ${n.toLocaleString()} ${unit}`}</title></circle>)}</g>;
  })}{ticks.map(i => <text key={i} x={x(i)} y={214} textAnchor={i === 0 ? "start" : i === labels.length - 1 ? "end" : "middle"} fill="currentColor" fontSize="11">{labels[i]}</text>)}</svg></div><p className="text-xs text-muted">{unit} · hover or focus a point for values</p><Legend names={series.map(s => s.name)} /></>;
}
export function Sparkline({ values, identity }: { values: number[]; identity: string }) {
  const max = Math.max(1, ...values);
  return <svg width="100" height="30" role="img" aria-label={`${identity}: seven daily active-minute counts ${values.join(", ")}`}><polyline fill="none" stroke={personColor(identity)} strokeWidth="2" points={values.map((v, i) => `${3 + i * 94 / Math.max(1, values.length - 1)},${27 - v / max * 24}`).join(" ")} /><title>{`${values.join(", ")} active minutes`}</title></svg>;
}
export function Contributions({ days, identity, onDay }: { days: ContributionDay[]; identity: string; onDay: (day: string) => void }) {
  if (!days.length) return <EmptyChart text="No contribution history." />;
  const cells = contributionCells(days), columns = Math.ceil(cells.length / 7);
  const max = Math.max(1, ...days.map(d => d.count));
  const months = new Map<number, string>();
  cells.forEach((day, i) => { if (day && (months.size === 0 || day.date.endsWith("-01"))) months.set(Math.floor(i / 7), new Date(day.date + "T12:00:00Z").toLocaleDateString("en-US", { month: "short", timeZone: "UTC" })); });
  return <><div className="overflow-x-auto pb-3" role="region" aria-label={identity + " contribution grid; scroll for the year"} tabIndex={0}><div style={{ width: columns * 14 + 28 }}><div className="relative ml-7 h-5 text-[10px] text-muted">{[...months].map(([week, label]) => <span key={week} className="absolute" style={{ left: week * 14 }}>{label}</span>)}</div><div className="flex gap-1"><div className="flex w-6 shrink-0 flex-col gap-[3px] text-[9px] text-muted">{["M", "", "W", "", "F", "", "S"].map((d, i) => <span key={i} className="h-[11px] leading-[11px]">{d}</span>)}</div><div className="grid gap-[3px]" style={{ gridTemplateRows: "repeat(7, 11px)", gridAutoColumns: "11px", gridAutoFlow: "column" }}>{cells.map((day, i) => day ? <button type="button" key={day.date} className="rounded-sm focus:outline focus:outline-2 focus:outline-offset-1" style={{ background: day.count ? personColor(identity) : "rgb(148 163 184 / .15)", opacity: day.count ? .25 + Math.ceil(day.count / max * 4) / 4 * .75 : 1 }} title={`${day.date}: ${day.active_minutes} active minutes, ${day.actions} actions`} aria-label={`Open ${identity} activity for ${day.date}: ${day.count} contributions`} onClick={() => onDay(day.date)} /> : <span key={i} />)}</div></div></div></div><p className="text-xs text-muted">365 days · tap a square for that day's feed · less ░ ▒ ▓ █ more</p>{!days.some(d => d.count) && <EmptyChart text="No contributions recorded in this year." />}</>;
}
export function Radar({ person, team }: { person?: TrendPerson; team: TrendPerson[] }) {
  const own = categoryMix(person);
  const all = categories.map((_, i) => team.reduce((sum, p) => sum + (categoryMix(p)[i] ?? 0), 0) / Math.max(1, team.length));
  if (![...own, ...all].some(Boolean)) return <EmptyChart text="No category actions for this range." />;
  const scale = Math.max(.25, Math.ceil(Math.max(...own, ...all) * 4) / 4);
  const point = (value: number, i: number, radius = 87) => `${150 + Math.sin(i * Math.PI / 4) * radius * value},${120 - Math.cos(i * Math.PI / 4) * radius * value}`;
  return <><svg viewBox="0 0 300 245" className="mx-auto w-full max-w-sm" role="img" aria-label="Category share compared with team average"><title>Category share compared with the average team member</title>{[.25, .5, .75, 1].map(level => <polygon key={level} points={categories.map((_, i) => point(level, i)).join(" ")} fill="none" stroke="currentColor" opacity=".15" />)}{categories.map((name, i) => <g key={name}><line x1="150" y1="120" x2={point(1, i).split(",")[0]} y2={point(1, i).split(",")[1]} stroke="currentColor" opacity=".15" /><text x={point(1, i, 108).split(",")[0]} y={Number(point(1, i, 108).split(",")[1]) + 3} textAnchor="middle" fill="currentColor" fontSize="10">{name}</text></g>)}<polygon points={all.map((n, i) => point(n / scale, i)).join(" ")} fill="#94a3b8" fillOpacity=".15" stroke="#64748b" strokeDasharray="4 3" /><polygon points={own.map((n, i) => point(n / scale, i)).join(" ")} fill={personColor(person?.identity ?? "")} fillOpacity=".3" stroke={personColor(person?.identity ?? "")} strokeWidth="2" /></svg><Legend names={[person?.identity ?? "Person"]} /><p className="text-xs text-muted">Dashed gray = average team member · category share, 0–{Math.round(scale * 100)}%.</p><details className="text-xs"><summary className="cursor-pointer py-2">Category percentages</summary>{categories.map((key, i) => <p key={key}>{key}: {Math.round(own[i] * 100)}% · team {Math.round(all[i] * 100)}%</p>)}</details></>;
}
export function ActionBars({ people }: { people: TrendPerson[] }) {
  const totals = people.map(p => ({ name: p.identity, counts: categories.map(key => p.series.reduce((n, s) => n + (s.categories[key] ?? 0), 0)) }));
  if (!totals.some(row => row.counts.some(Boolean))) return <EmptyChart />;
  const max = Math.max(1, ...totals.map(row => row.counts.reduce((n, v) => n + v, 0)));
  return <><div className="space-y-5">{totals.map(row => <div key={row.name}><p className="mb-2 text-sm font-semibold" style={{ color: personColor(row.name) }}>{row.name} · {row.counts.reduce((n, v) => n + v, 0)} actions</p><div className="flex h-7 rounded bg-surface-2">{row.counts.map((n, i) => n ? <span key={categories[i]} tabIndex={0} aria-label={`${row.name}: ${n} ${categories[i]} actions`} title={`${categories[i]}: ${n}`} style={{ width: `${n / max * 100}%`, background: personColor(categories[i]) }} /> : null)}</div></div>)}</div><Legend names={categories} /></>;
}
