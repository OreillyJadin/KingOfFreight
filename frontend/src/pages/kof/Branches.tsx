import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { Search } from "lucide-react";
import { kof, type KofBranch } from "../../kof/api";
import { ErrorState, PageHeading } from "../../components/common";
import { ListDetail } from "../../components/ListDetail";
import { Badge, Card, Input, Skeleton } from "../../components/ui";
import { CountCell, DataTable, MarginCell, MoneyCell, TableSkeleton } from "../../kof/components";
import { money, pct, place, shortDate, stageClass, stageLabels } from "../../kof/format";
import { RangeTabs, useRange, type RangeValue } from "../../kof/useRange";

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-surface-2 px-3 py-2">
      <dt className="text-[11px] font-bold uppercase tracking-[0.12em] text-muted">{label}</dt>
      <dd className="mt-0.5 font-bold tabular-nums text-fg">{value}</dd>
    </div>
  );
}

function BranchDetail({ branch, range }: { branch: string; range: { start?: string; end?: string } }) {
  const detail = useQuery({
    queryKey: ["kof", "branch", branch, range],
    queryFn: () => kof.branch(branch, range),
  });
  if (detail.isPending) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-20" />
        <Skeleton className="h-40" />
      </div>
    );
  }
  if (detail.isError) {
    return <ErrorState message={(detail.error as Error).message} onRetry={() => detail.refetch()} />;
  }
  const data = detail.data;
  const t = data.totals;

  return (
    <div className="space-y-6">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-xl font-extrabold tracking-tight text-fg">{data.branch}</h2>
          {data.working_status && !/^\d+$/.test(data.working_status) && <Badge>{data.working_status}</Badge>}
        </div>
        <p className="mt-1 text-sm text-muted">
          {[data.customer, place(data.city, data.state)].filter(Boolean).join(" · ")}
        </p>
        {data.contact && (data.contact.name || data.contact.phone || data.contact.email) && (
          <p className="mt-1 text-sm text-fg-2">
            {[data.contact.name, data.contact.phone, data.contact.email].filter(Boolean).join(" · ")}
          </p>
        )}
      </div>

      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Loads" value={String(t.loads)} />
        <Stat label="Avg rate" value={money(t.avg_price)} />
        <Stat label="Avg carrier cost" value={money(t.avg_cost)} />
        <Stat label="Margin" value={pct(t.margin_pct)} />
      </dl>

      <section>
        <h3 className="mb-2 text-[11px] font-bold uppercase tracking-[0.14em] text-muted">
          Pickup sites (yards and job sites)
        </h3>
        <Card>
          <DataTable
            caption="Pickup sites"
            rows={data.pickup_sites}
            rowKey={(row) => `${row.company}-${row.city}-${row.state}`}
            emptyMessage="No pickups recorded."
            columns={[
              {
                key: "site",
                header: "Site",
                render: (row) => (
                  <div className="min-w-0">
                    <p className="font-semibold text-fg">{row.company || "Unnamed site"}</p>
                    <p className="text-xs text-muted">{place(row.city, row.state)}</p>
                  </div>
                ),
              },
              { key: "loads", header: "Loads", align: "right", render: (row) => <CountCell value={row.loads} /> },
              { key: "rate", header: "Avg rate", align: "right", render: (row) => <MoneyCell value={row.avg_price} /> },
              { key: "cost", header: "Avg cost", align: "right", render: (row) => <MoneyCell value={row.avg_cost} /> },
              { key: "margin", header: "Margin", align: "right", render: (row) => <MarginCell value={row.margin_pct} /> },
              { key: "last", header: "Last", align: "right", render: (row) => <span className="text-muted">{shortDate(row.last_date)}</span> },
            ]}
          />
        </Card>
      </section>

      <section>
        <h3 className="mb-2 text-[11px] font-bold uppercase tracking-[0.14em] text-muted">Lane rates</h3>
        <Card>
          <DataTable
            caption="Lane rates for this branch"
            rows={data.lanes}
            rowKey={(row) => `${row.origin}-${row.destination}`}
            emptyMessage="No lanes recorded."
            columns={[
              { key: "lane", header: "Lane", render: (row) => <span className="font-semibold text-fg">{row.origin} → {row.destination}</span> },
              { key: "loads", header: "Loads", align: "right", render: (row) => <CountCell value={row.loads} /> },
              { key: "rate", header: "Avg rate", align: "right", render: (row) => <MoneyCell value={row.avg_price} /> },
              { key: "cost", header: "Avg cost", align: "right", render: (row) => <MoneyCell value={row.avg_cost} /> },
              {
                key: "range",
                header: "Cost range",
                align: "right",
                render: (row) => (
                  <span className="text-muted">
                    <MoneyCell value={row.min_cost} />–<MoneyCell value={row.max_cost} />
                  </span>
                ),
              },
              { key: "margin", header: "Margin", align: "right", render: (row) => <MarginCell value={row.margin_pct} /> },
            ]}
          />
        </Card>
      </section>

      <section>
        <h3 className="mb-2 text-[11px] font-bold uppercase tracking-[0.14em] text-muted">Recent loads</h3>
        <ul className="divide-y divide-line rounded-2xl border border-line">
          {data.recent_loads.map((load) => (
            <li key={load.order_no}>
              <Link
                to={`/loads?order=${load.order_no}`}
                className="flex min-h-11 flex-wrap items-center justify-between gap-2 px-3 py-2.5 hover:bg-surface-2"
              >
                <span className="min-w-0">
                  <span className="font-bold tabular-nums text-fg">#{load.order_no}</span>
                  <span className="ml-2 text-sm text-fg-2">
                    {place(load.origin_city, load.origin_state)} → {place(load.dest_city, load.dest_state)}
                  </span>
                </span>
                <span className="flex items-center gap-2 text-sm">
                  <span className={`rounded-md px-2 py-0.5 text-[11px] font-bold ${stageClass(load.stage)}`}>
                    {stageLabels[load.stage]}
                  </span>
                  <span className="tabular-nums text-fg-2">{money(load.price)}</span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

export default function Branches() {
  const { value, setValue, range, label, month, year, setMonth, setYear } =
    useRange("year");
  const [params, setParams] = useSearchParams();
  const [filter, setFilter] = useState(params.get("q") ?? "");
  const customer = params.get("customer") ?? "united rentals";
  const selected = params.get("branch");

  useEffect(() => {
    document.title = "Branches · Fifth Wheel";
  }, []);

  const branches = useQuery({
    queryKey: ["kof", "branches", range, customer],
    queryFn: () => kof.branches(range, customer),
  });

  const needle = filter.trim().toLowerCase();
  const rows = useMemo(
    () =>
      (branches.data ?? []).filter((row: KofBranch) =>
        `${row.branch} ${row.city ?? ""} ${row.state ?? ""} ${row.top_lanes.join(" ")}`
          .toLowerCase()
          .includes(needle),
      ),
    [branches.data, needle],
  );
  const totals = rows.reduce(
    (acc, row) => ({ loads: acc.loads + row.loads, revenue: acc.revenue + row.revenue, cost: acc.cost + row.cost }),
    { loads: 0, revenue: 0, cost: 0 },
  );

  function update(changes: Record<string, string | null>) {
    const next = new URLSearchParams(params);
    for (const [key, val] of Object.entries(changes)) {
      if (val === null || val === "") next.delete(key);
      else next.set(key, val);
    }
    setParams(next, { replace: true });
  }

  const list = (
    <Card>
      {branches.isPending ? (
        <TableSkeleton />
      ) : (
        <DataTable
          caption="Branches"
          rows={rows}
          rowKey={(row) => row.branch}
          activeKey={selected}
          onRowClick={(row) => update({ branch: row.branch })}
          emptyMessage="No branches match."
          columns={[
            {
              key: "branch",
              header: "Branch",
              render: (row) => (
                <div className="min-w-0">
                  <p className="font-semibold text-fg">{row.branch}</p>
                  <p className="text-xs text-muted">
                    {place(row.city, row.state)} · last {shortDate(row.last_load_date)}
                  </p>
                </div>
              ),
            },
            { key: "loads", header: "Loads", align: "right", render: (row) => <CountCell value={row.loads} /> },
            { key: "rate", header: "Avg rate", align: "right", render: (row) => <MoneyCell value={row.avg_price} /> },
            { key: "cost", header: "Avg cost", align: "right", render: (row) => <MoneyCell value={row.avg_cost} /> },
            { key: "margin", header: "Margin", align: "right", render: (row) => <MarginCell value={row.margin_pct} /> },
          ]}
        />
      )}
    </Card>
  );

  return (
    <>
      <PageHeading
        eyebrow="Accounts"
        title="Branches"
        description={`Every ${customer === "united rentals" ? "United Rentals" : "customer"} branch you haul for, with average rate and cost. ${label}.`}
        action={
          <RangeTabs
            value={value}
            onChange={(next: RangeValue) => setValue(next)}
            month={month}
            year={year}
            setMonth={setMonth}
            setYear={setYear}
          />
        }
      />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <label className="relative min-w-[220px] max-w-sm flex-1">
          <span className="sr-only">Filter branches</span>
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-subtle" />
          <Input
            value={filter}
            onChange={(event) => {
              setFilter(event.target.value);
              update({ q: event.target.value });
            }}
            placeholder="Branch or city, e.g. Austin"
            className="pl-9"
          />
        </label>
        {!branches.isPending && (
          <p className="text-sm text-muted">
            <span className="tabular-nums text-fg-2">{rows.length}</span> branches ·{" "}
            <span className="tabular-nums text-fg-2">{totals.loads.toLocaleString()}</span> loads · avg rate{" "}
            <span className="tabular-nums text-fg-2">{money(totals.loads ? totals.revenue / totals.loads : null)}</span> · avg cost{" "}
            <span className="tabular-nums text-fg-2">{money(totals.loads ? totals.cost / totals.loads : null)}</span>
          </p>
        )}
      </div>
      {branches.isError && <ErrorState message={(branches.error as Error).message} onRetry={() => branches.refetch()} />}
      <ListDetail
        list={list}
        detail={selected ? <BranchDetail branch={selected} range={range} /> : null}
        detailKey={selected}
        detailTitle={selected ?? "Branch"}
        onCloseDetail={() => update({ branch: null })}
      />
    </>
  );
}
