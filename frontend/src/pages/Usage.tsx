import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Navigate } from "react-router-dom";
import { api } from "../api";
import { PageHeading } from "../components/common";
import { Button, Card, Tabs } from "../components/ui";
import { formatDateTime } from "../utils";

const featureLabels: Record<string, string> = {
  operator_switched: "Operator switches",
  assistant_opened: "Assistant opened", assistant_question: "Assistant questions", suggestion_clicked: "Suggestion chips",
  bol_upload_extract: "BOL upload & extract", kof_manual_sync: "Manual KOF sync", kof_text_send: "KOF texts sent",
  kof_email_send: "KOF emails sent", customer_update_approve: "Customer updates approved", customer_update_dismiss: "Customer updates dismissed",
  operational_send: "Operational sends", login_success: "Successful sign-ins", outlook_connect: "Outlook connected",
};

function RankedList({ title, rows, features = false }: { title: string; rows: { name: string; count: number }[]; features?: boolean }) {
  return <Card className="min-w-0 p-5"><h2 className="text-lg font-bold">{title}</h2>
    {rows.length ? <ol className="mt-4 divide-y divide-line">{rows.map(row => <li key={row.name} className="flex items-center justify-between gap-3 py-3 text-sm"><span className="min-w-0 break-words text-fg-2">{features ? featureLabels[row.name] ?? row.name.replaceAll("_", " ") : row.name}</span><span className="font-bold tabular-nums">{row.count.toLocaleString()}</span></li>)}</ol> : <p className="mt-3 text-sm text-muted">No activity in this range.</p>}
  </Card>;
}

export default function Usage() {
  const [days, setDays] = useState<7 | 30 | 90>(7);
  const auth = useQuery({ queryKey: ["auth"], queryFn: api.me });
  const query = useQuery({ queryKey: ["usage", days], queryFn: () => api.usage(days), enabled: auth.data?.role === "admin" });
  if (auth.isPending) return <p className="text-muted">Loading…</p>;
  if (auth.data?.role !== "admin") return <Navigate to="/dashboard" replace />;
  const data = query.data;
  const max = data ? Math.max(1, ...data.daily.flatMap(day => [day.active_users, day.questions])) : 1;
  return <div className="mx-auto max-w-5xl space-y-5">
    <PageHeading eyebrow="Administration" title="Usage" description="See who uses Fifth Wheel, what they use, and the questions they ask." />
    <Tabs ariaLabel="Usage range" items={(["7", "30", "90"] as const).map(value => ({ value, label: `${value} days` }))} value={String(days) as "7" | "30" | "90"} onChange={value => setDays(Number(value) as 7 | 30 | 90)} />
    {query.isPending ? <p className="text-muted">Loading usage…</p> : query.isError ? <Card className="p-5"><p role="alert" className="text-sm text-danger-ink">{query.error.message}</p><Button className="mt-3" onClick={() => void query.refetch()}>Retry</Button></Card> : data && <>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {([["Events", data.totals.events], ["Active users", data.totals.active_users], ["Questions", data.totals.chat_questions], ["Page views", data.totals.page_views]] as const).map(([label, count]) => <Card key={label} className="p-4"><p className="text-xs font-semibold text-muted">{label}</p><p className="mt-2 text-3xl font-extrabold tabular-nums">{count.toLocaleString()}</p></Card>)}
      </div>
      <p className="text-xs leading-relaxed text-muted">Calendar days and times use {data.timezone}. Activity is grouped by selected operator, then username, then “shared login”. Operator names are self-selected, not separate accounts. Questions are counted once by the server, including provider failures. Activity is retained for 180 days.</p>
      <Card className="min-w-0 p-5">
        <h2 className="text-lg font-bold">Daily activity</h2>
        <div className="mt-2 flex flex-wrap gap-4 text-xs text-muted"><span><span className="mr-1 inline-block h-2 w-2 rounded-sm bg-st-booked" />Active users</span><span><span className="mr-1 inline-block h-2 w-2 rounded-sm bg-st-picked" />Questions</span></div>
        {data.totals.events === 0 && <p className="mt-3 text-sm text-muted">No activity yet. Usage will appear as brokers use the app.</p>}
        <div className="mt-5 overflow-x-auto pb-2" tabIndex={0} role="region" aria-label="Daily activity chart; scroll for more days">
          <div className="flex h-44 items-end gap-2" style={{ minWidth: Math.max(260, data.daily.length * 24) }}>
            {data.daily.map(day => <div key={day.date} className="flex h-full min-w-4 flex-1 flex-col justify-end" title={`${day.date}: ${day.active_users} users, ${day.questions} questions`}>
              <div className="flex h-36 items-end justify-center gap-0.5" role="img" aria-label={`${day.date}: ${day.active_users} active users, ${day.questions} questions`}>
                <div className="w-2 max-w-4 flex-1 rounded-t bg-st-booked" style={{ height: `${day.active_users / max * 100}%` }} />
                <div className="w-2 max-w-4 flex-1 rounded-t bg-st-picked" style={{ height: `${day.questions / max * 100}%` }} />
              </div>
              <span className="mt-2 text-center text-[11px] text-muted">{day.date.slice(5).replace("-", "/")}</span>
            </div>)}
          </div>
        </div>
      </Card>
      <Card className="min-w-0 p-5">
        <h2 className="text-lg font-bold">By user</h2>
        {!data.users.length ? <p className="mt-3 text-sm text-muted">No users active in this range.</p> : <div className="mt-4 overflow-x-auto" tabIndex={0} role="region" aria-label="Per-user activity; scroll for all columns">
          <table className="w-full min-w-[650px] text-left text-sm"><thead className="border-b border-line text-xs text-muted"><tr>{["User / last seen", "Views", "Questions", "Top page", "Device events"].map(label => <th key={label} className="px-3 py-3 font-semibold first:pl-0">{label}</th>)}</tr></thead>
            <tbody className="divide-y divide-line">{data.users.map(user => <tr key={`${user.team_member_id}:${user.operator_name}:${user.user_id}:${user.username}`}><td className="max-w-52 py-4 pr-3"><p className="break-words font-semibold">{user.label}</p><p className="mt-1 text-xs text-muted">{formatDateTime(user.last_seen)}</p></td><td className="px-3 py-4 tabular-nums">{user.page_views}</td><td className="px-3 py-4 tabular-nums">{user.questions}</td><td className="px-3 py-4 text-fg-2">{user.top_page ?? "—"}</td><td className="px-3 py-4 text-xs text-muted">{Object.entries(user.devices).map(([device, count]) => `${device}: ${count}`).join(" · ")}</td></tr>)}</tbody>
          </table>
        </div>}
      </Card>
      <div className="grid min-w-0 gap-5 md:grid-cols-2"><RankedList title="Top pages" rows={data.top_pages} /><RankedList title="Top features" rows={data.top_features} features /></div>
      <RankedList title="Events by device" rows={Object.entries(data.devices).map(([name, count]) => ({ name, count }))} />
      <Card className="p-5"><h2 className="text-lg font-bold">Recent questions</h2><p className="mt-1 text-xs text-muted">Latest 50 in this range · first 300 characters · admin only</p>
        {data.questions.length ? <ol className="mt-4 divide-y divide-line">{data.questions.map((question, index) => <li key={`${question.time}:${index}`} className="py-4"><div className="flex flex-wrap justify-between gap-1 text-xs text-muted"><span className="font-semibold text-fg-2">{question.user}</span><time dateTime={question.time}>{formatDateTime(question.time)}</time></div><p className="mt-2 whitespace-pre-wrap break-words text-sm leading-relaxed text-fg">{question.text || "(No question text recorded)"}</p></li>)}</ol> : <p className="mt-4 text-sm text-muted">No questions in this range.</p>}
      </Card>
    </>}
  </div>;
}
