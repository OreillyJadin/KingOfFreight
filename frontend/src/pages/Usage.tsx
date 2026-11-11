import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { api } from "../api";
import { PageHeading } from "../components/common";
import { Button, Card, Select, Tabs } from "../components/ui";
import { money, pct } from "../kof/format";
import { LivePanel, UsersPanel, PeoplePanel, TimelinePanel, TrendsPanel, FlowsPanel, HealthPanel } from "./UsageVisuals";
import { activeTime, activityTime, brokerToday, periodLabel, periodStart, responseTime, shiftPeriod, type UsageFilters, type UsageOutput, type UsagePeriod, type UsageResponses } from "../usage-analytics";

const tabs = ["Live", "Overview", "People", "Activity", "Trends", "Output", "Features", "Health"] as const;
type Tab = typeof tabs[number];

function useReport<K extends keyof UsageResponses>(section: K, filters: UsageFilters, enabled: boolean) {
  return useQuery({ queryKey: ["usage-analytics", section, filters], queryFn: () => api.usageAnalytics(section, filters), enabled });
}

function ReportState({ pending, error, retry, children }: { pending: boolean; error: Error | null; retry: () => void; children: ReactNode }) {
  if (pending) return <p role="status" className="py-8 text-sm text-muted">Loading activity…</p>;
  if (error) return <Card className="p-5"><p role="alert" className="text-sm text-danger-ink">{error.message}</p><Button className="mt-3" onClick={retry}>Retry</Button></Card>;
  return <>{children}</>;
}

function Empty({ children = "No activity in this period." }: { children?: ReactNode }) {
  return <p className="py-4 text-sm text-muted">{children}</p>;
}

function OutputTable({ title, rows }: { title: string; rows: UsageOutput[] }) {
  return <Card className="min-w-0 p-4"><h2 className="text-lg font-bold">{title}</h2>{!rows.length ? <Empty>No KOF output in this period.</Empty> : <div role="region" aria-label={`${title}; scroll for financial columns`} tabIndex={0} className="mt-3 overflow-x-auto"><table className="w-full min-w-[640px] text-left text-sm"><thead className="border-b border-line text-xs text-muted"><tr>{["Name", "Loads", "Revenue", "Carrier cost", "Profit", "Margin"].map(label => <th className="px-3 py-3 first:pl-0" key={label}>{label}</th>)}</tr></thead><tbody className="divide-y divide-line">{rows.map(row => <tr key={row.name ?? "unassigned"}><td className="py-4 pr-3 font-semibold">{row.name ?? "Unassigned"}</td><td className="p-3">{row.loads}</td><td className="p-3">{money(row.revenue)}</td><td className="p-3">{money(row.carrier_cost)}</td><td className="p-3 font-semibold">{money(row.profit)}</td><td className="p-3">{pct(row.margin_pct)}</td></tr>)}</tbody></table></div>}</Card>;
}

export default function Usage() {
  const auth = useQuery({ queryKey: ["auth"], queryFn: api.me });
  const admin = auth.data?.role === "admin";
  const zone = auth.data?.broker_timezone ?? "America/Chicago";
  const today = brokerToday(zone);
  const [tab, setTab] = useState<Tab>("Overview");
  const [period, setPeriod] = useState<UsagePeriod>("week");
  const [anchor, setAnchor] = useState<string | null>(null);
  const [includeAdmin, setIncludeAdmin] = useState(false);
  const [selectedPerson, setSelectedPerson] = useState("");
  const [activityDay, setActivityDay] = useState<string | null>(null);
  const [ranking, setRanking] = useState<"active_minutes" | "actions" | "kof_profit">("active_minutes");
  const date = anchor && anchor <= today ? anchor : today;
  const filters = { period, date, exclude_admins: !includeAdmin };
  const people = useReport("people", filters, admin);
  const leaderboard = useReport("leaderboard", filters, admin && tab === "Overview");
  const output = useReport("kof_output", filters, admin && tab === "Output");
  const speed = useReport("response_speed", filters, admin && tab === "Output");
  const features = useReport("features", filters, admin && tab === "Features");
  const feedFilters = activityDay ? { ...filters, period: "day" as const, date: activityDay } : filters;
  const feed = useInfiniteQuery({
    queryKey: ["usage-analytics", "feed", feedFilters, selectedPerson],
    queryFn: ({ pageParam }) => api.usageAnalytics("feed", feedFilters, { identity: selectedPerson || undefined, limit: 50, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: last => last.has_more ? last.offset + last.items.length : undefined,
    enabled: admin && tab === "Activity",
  });
  if (auth.isPending) return <p className="text-muted">Loading…</p>;
  if (!admin) return <Navigate to="/dashboard" replace />;
  const persons = people.data?.people ?? [];
  const identities = [...new Set([...persons.map(person => person.identity), selectedPerson].filter(Boolean))].sort();
  const items = feed.data?.pages.flatMap(page => page.items) ?? [];
  const questions = items.filter(item => item.event === "assistant_question").slice(0, 50);
  const leaders = [...(leaderboard.data?.people ?? [])].sort((a, b) => (a[`${ranking}_rank`] ?? Infinity) - (b[`${ranking}_rank`] ?? Infinity));
  const openPerson = (identity: string) => { setSelectedPerson(identity); setActivityDay(null); setTab("Activity"); };
  const openDay = (identity: string, day: string) => { setSelectedPerson(identity); setActivityDay(day); setTab("Activity"); };
  const personSelect = (value: string, onChange: (value: string) => void, label: string) => <label className="flex min-w-0 flex-col gap-2 text-sm font-semibold"><span>{label}</span><Select value={value} onChange={event => onChange(event.target.value)}><option value="">Everyone</option>{identities.map(identity => <option value={identity} key={identity}>{identity}</option>)}</Select></label>;
  return <div className="mx-auto min-w-0 max-w-6xl space-y-5">
    <PageHeading eyebrow="Administration" title="Usage" description="See where the team spends time and what gets done." />
    <Card className="space-y-4 p-4">
      <div className="flex flex-wrap items-center gap-3"><Tabs ariaLabel="Usage period" value={period} onChange={value => { setPeriod(value); setAnchor(null); setActivityDay(null); }} items={[{ value: "day", label: "Day" }, { value: "week", label: "Week" }, { value: "month", label: "Month" }]} />
        <div role="group" aria-label="Choose usage period" className="flex min-w-0 max-w-full items-center gap-1"><Button variant="ghost" className="shrink-0 px-3" aria-label="Previous period" onClick={() => { setAnchor(shiftPeriod(period, date, -1)); setActivityDay(null); }}>←</Button><span className="min-w-0 text-center text-sm font-semibold">{periodLabel(period, date, today)}</span><Button variant="ghost" className="shrink-0 px-3" aria-label="Next period" disabled={periodStart(period, date) >= periodStart(period, today)} onClick={() => { setAnchor(shiftPeriod(period, date, 1)); setActivityDay(null); }}>→</Button></div>
      </div>
      <label className="flex min-h-11 cursor-pointer items-center gap-3 text-sm font-semibold"><input type="checkbox" className="h-4 w-4 accent-accent" checked={includeAdmin} onChange={event => setIncludeAdmin(event.target.checked)} />Include my activity</label>
      <p className="text-xs leading-relaxed text-muted">Times in {zone}. Excludes all admin accounts unless included above. Active time requires visible, recent interaction. Detailed activity is retained for 180 days; daily contributions for 365 days.</p>
    </Card>
    <Tabs ariaLabel="Usage reports" value={tab} onChange={setTab} items={tabs.map(value => ({ value, label: value }))} />
    {tab === "Live" && <LivePanel filters={filters} zone={zone} />}
    {tab === "Health" && <HealthPanel filters={filters} zone={zone} />}
    {tab === "Trends" && <TrendsPanel filters={filters} />}
    <ReportState pending={["Overview", "People"].includes(tab) && people.isPending} error={["Overview", "People"].includes(tab) ? people.error : null} retry={() => void people.refetch()}>
      {tab === "Overview" && <div className="space-y-5">
        <UsersPanel filters={filters} zone={zone} />
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">{[["Active time", activeTime(persons.reduce((sum, p) => sum + p.active_minutes, 0)), "hours:minutes"], ["People", String(persons.length), "with recorded activity"], ["Actions", String(persons.reduce((sum, p) => sum + p.actions, 0)), "feature events"], ["Questions", String(persons.reduce((sum, p) => sum + p.chat_questions, 0)), "counted by the server"]].map(([label, value, hint]) => <Card className="p-4" key={label}><p className="text-xs font-semibold text-muted">{label}</p><p className="mt-2 text-3xl font-extrabold tabular-nums">{value}</p><p className="mt-1 text-xs text-muted">{hint}</p></Card>)}</div>
        <Card className="min-w-0 p-4"><h2 className="text-lg font-bold">Leaderboard</h2><label className="mt-3 flex flex-col gap-2 text-sm font-semibold">Rank by<Select value={ranking} onChange={event => setRanking(event.target.value as typeof ranking)}><option value="active_minutes">Active time</option><option value="actions">Actions</option><option value="kof_profit">KOF profit</option></Select></label><ReportState pending={leaderboard.isPending} error={leaderboard.error} retry={() => void leaderboard.refetch()}>{!leaders.length ? <Empty /> : <ol className="mt-4 divide-y divide-line">{leaders.map(row => <li key={row.identity} className="py-4"><button type="button" className="flex min-h-11 w-full items-center gap-3 text-left" onClick={() => openPerson(row.identity)}><span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent/10 text-sm font-bold text-accent-ink">{row[`${ranking}_rank`] ?? "—"}</span><span className="min-w-0 flex-1 break-words font-bold">{row.identity}</span><span className="shrink-0 font-bold tabular-nums">{ranking === "active_minutes" ? activeTime(row.active_minutes) : ranking === "actions" ? row.actions : money(row.kof_profit)}</span></button><p className="ml-11 text-xs leading-relaxed text-muted">{activeTime(row.active_minutes)} active · {row.actions} actions · {row.kof_profit === null ? "No matching KOF booker" : `${money(row.kof_profit)} KOF profit`}</p></li>)}</ol>}</ReportState><p className="mt-3 text-xs text-muted">KOF profit matches the booker name case-insensitively. Tap a name to see activity.</p></Card>
      </div>}
      {tab === "People" && <PeoplePanel filters={filters} persons={persons} onDay={openDay} onPerson={openPerson} zone={zone} />}
      {tab === "Activity" && <div className="space-y-5"><TimelinePanel filters={{ ...filters, date: activityDay ?? date }} today={today} onDay={setActivityDay} />{activityDay && <Card className="p-4"><p className="text-sm">Feed filtered to {activityDay}</p><Button className="mt-2" onClick={() => setActivityDay(null)}>Use shared period</Button></Card>}<Card className="p-4">{personSelect(selectedPerson, setSelectedPerson, "Filter activity by person")}</Card><ReportState pending={feed.isPending} error={feed.isError && !feed.data ? feed.error : null} retry={() => void feed.refetch()}>
        <Card className="min-w-0 p-4"><h2 className="text-lg font-bold">Recent activity</h2><p className="mt-1 text-xs text-muted">{feed.data?.pages[0]?.total ?? 0} events in this period</p>{!items.length ? <Empty /> : <ol className="mt-3 divide-y divide-line">{items.map(item => <li key={item.id} className="py-4"><div className="flex flex-wrap justify-between gap-1 text-xs text-muted"><span className="font-semibold text-fg-2">{item.identity}</span><time dateTime={item.time}>{activityTime(item.time, zone)}</time></div><p className="mt-2 break-words text-sm font-semibold leading-relaxed">{item.summary}</p><p className="mt-1 text-xs capitalize text-muted">{item.device}{item.path ? ` · ${item.path}` : ""}</p></li>)}</ol>}{feed.isFetchNextPageError && <p role="alert" className="my-3 text-sm text-danger-ink">Could not load more activity. Please retry.</p>}{feed.hasNextPage && <Button className="mt-4 w-full" loading={feed.isFetchingNextPage} onClick={() => void feed.fetchNextPage()}>{feed.isFetchNextPageError ? "Retry loading more" : "Load more"}</Button>}</Card>
        <Card className="min-w-0 p-4"><h2 className="text-lg font-bold">Recent questions</h2><p className="mt-1 text-xs text-muted">From loaded activity · up to 50 · load more activity for older questions</p>{!questions.length ? <Empty>No questions in loaded activity.</Empty> : <ol className="mt-3 divide-y divide-line">{questions.map(item => <li key={item.id} className="py-4"><p className="text-xs text-muted">{item.identity} · {activityTime(item.time, zone)}</p><p className="mt-2 whitespace-pre-wrap break-words text-sm leading-relaxed">{typeof item.detail.question === "string" ? item.detail.question : "(No question text recorded)"}</p></li>)}</ol>}</Card>
      </ReportState></div>}
      {tab === "Output" && <div className="space-y-5"><p className="text-xs leading-relaxed text-muted">KOF output uses date of sale, not pickup or delivery. Booker and rep are KOF labels, independent of selected operators.</p><TrendsPanel filters={filters} outputOnly /><ReportState pending={output.isPending} error={output.error} retry={() => void output.refetch()}><OutputTable title="KOF output by booker" rows={output.data?.booker ?? []} /><OutputTable title="KOF output by rep" rows={output.data?.rep ?? []} /></ReportState><Card className="p-4"><h2 className="text-lg font-bold">Customer-update response speed</h2><p className="mt-1 text-xs leading-relaxed text-muted">Carrier message to approval; draft creation when no source is linked.</p><ReportState pending={speed.isPending} error={speed.error} retry={() => void speed.refetch()}>{!speed.data?.people.length ? <Empty>No linked approvals in this period.</Empty> : <ul className="mt-3 divide-y divide-line">{speed.data.people.map(person => <li className="flex flex-wrap justify-between gap-2 py-4 text-sm" key={person.identity}><span className="font-semibold">{person.identity}</span><span className="text-right"><strong>{responseTime(person.median_seconds)} median</strong><span className="mt-1 block text-xs text-muted">{responseTime(person.avg_seconds)} avg · {person.count} approvals</span></span></li>)}</ul>}{!!speed.data?.unlinked_approval_events && <p className="mt-3 text-xs text-muted">{speed.data.unlinked_approval_events} historical approval events have no usable draft/source link.</p>}</ReportState></Card></div>}
      {tab === "Features" && <div className="space-y-5"><FlowsPanel filters={filters} /><ReportState pending={features.isPending} error={features.error} retry={() => void features.refetch()}><div className="grid min-w-0 gap-3 sm:grid-cols-2">{!features.data?.features.length && <Empty />}{features.data?.features.map(feature => <Card className={`min-w-0 p-4 ${feature.uses === 0 ? "border-dashed border-accent/40 bg-accent/5" : ""}`} key={feature.feature}><div className="flex items-start justify-between gap-3"><h2 className="min-w-0 break-words text-sm font-bold">{feature.label}</h2>{feature.uses === 0 && <span className="shrink-0 rounded bg-accent/10 px-2 py-1 text-xs font-semibold text-accent-ink">Unused</span>}</div><p className="mt-3 text-sm"><strong>{feature.uses}</strong> uses · <strong>{feature.distinct_people}</strong> people</p><p className="mt-2 text-xs text-muted">Last used: {activityTime(feature.last_used, zone)}</p></Card>)}</div></ReportState></div>}
    </ReportState>
  </div>;
}
