import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { BarChart3 } from "lucide-react";
import { kof } from "../../kof/api";
import { ErrorState, PageHeading } from "../../components/common";
import { Card, Tabs } from "../../components/ui";
import {
  CountCell,
  DataTable,
  KofConnectionEmptyState,
  Kpi,
  KpiSkeleton,
  MarginCell,
  MoneyCell,
  RevenueChart,
  TableSkeleton,
} from "../../kof/components";
import { compactMoney, money, monthDay, pct, shortDate } from "../../kof/format";
import { RangeTabs, useRange } from "../../kof/useRange";

export default function Dashboard() {
  const { value, setValue, range, label } = useRange("90");
  const [params, setParams] = useSearchParams();
  const interval = params.get("interval") === "month" ? "month" : "week";

  useEffect(() => {
    document.title = "Dashboard · Fifth Wheel";
  }, []);

  const summary = useQuery({
    queryKey: ["kof", "summary", range, interval],
    queryFn: () => kof.summary(range, interval),
  });
  const lanes = useQuery({
    queryKey: ["kof", "lanes", range, "city"],
    queryFn: () => kof.lanes(range, "city", 2, 10),
  });
  const customers = useQuery({
    queryKey: ["kof", "customers", range],
    queryFn: () => kof.customers(range),
  });
  const connection = useQuery({
    queryKey: ["kof", "connection"],
    queryFn: kof.connection,
    retry: false,
  });
  const syncStatus = useQuery({
    queryKey: ["kof", "sync"],
    queryFn: kof.syncStatus,
    retry: false,
  });

  const totals = summary.data?.totals;
  const showConnectionEmpty =
    !connection.isPending &&
    !syncStatus.isPending &&
    connection.data?.configured === false &&
    syncStatus.data?.load_count === 0;

  function setInterval(next: "week" | "month") {
    const updated = new URLSearchParams(params);
    if (next === "week") updated.delete("interval");
    else updated.set("interval", next);
    setParams(updated, { replace: true });
  }

  const heading = (
    <PageHeading
      eyebrow="Performance"
      title="Dashboard"
      description={`Revenue, carrier cost and margin across your loads. ${label}.`}
      action={<RangeTabs value={value} onChange={setValue} />}
    />
  );
  if (showConnectionEmpty) {
    return (
      <>
        {heading}
        <KofConnectionEmptyState />
      </>
    );
  }

  return (
    <>
      {heading}
      <section aria-label="Key figures" className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {summary.isPending ? (
          Array.from({ length: 4 }, (_, index) => <KpiSkeleton key={index} />)
        ) : (
          <>
            <Kpi
              label="Revenue"
              value={compactMoney(totals?.revenue)}
              hint={`${totals?.loads ?? 0} loads`}
            />
            <Kpi label="Carrier cost" value={compactMoney(totals?.cost)} hint={`Avg ${money(totals?.avg_cost)} / load`} />
            <Kpi label="Profit" value={compactMoney(totals?.profit)} hint={`Avg ${money(totals?.avg_profit)} / load`} tone="accent" />
            <Kpi
              label="Margin"
              value={pct(totals?.margin_pct)}
              hint={
                totals?.on_time_pct !== null && totals?.on_time_pct !== undefined
                  ? `${pct(totals.on_time_pct, 0)} on time`
                  : `Avg sell ${money(totals?.avg_price)}`
              }
            />
          </>
        )}
      </section>

      {value === "all" && summary.data && summary.data.undated_loads > 0 && (
        <p className="mt-2 text-xs text-muted">
          {summary.data.undated_loads} loads without a sale date aren&apos;t included.
        </p>
      )}

      {summary.isError && (
        <div className="mt-4">
          <ErrorState message={(summary.error as Error).message} onRetry={() => summary.refetch()} />
        </div>
      )}

      <Card className="mt-5 p-4 sm:p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-bold text-fg">Revenue and profit over time</h2>
          <Tabs
            ariaLabel="Chart interval"
            value={interval}
            onChange={setInterval}
            items={[
              { value: "week", label: "Weekly" },
              { value: "month", label: "Monthly" },
            ]}
          />
        </div>
        {summary.isPending ? (
          <TableSkeleton rows={5} />
        ) : (
          <RevenueChart
            data={summary.data?.series ?? []}
            labelFor={(period) =>
              interval === "month"
                ? new Date(`${period}T00:00:00`).toLocaleDateString(undefined, { month: "short" })
                : monthDay(period)
            }
          />
        )}
      </Card>

      <div className="mt-5 grid gap-5 xl:grid-cols-2">
        <Card className="min-w-0 overflow-hidden">
          <h2 className="border-b border-line px-4 py-3 font-bold text-fg">Busiest lanes</h2>
          {lanes.isPending ? (
            <TableSkeleton rows={6} />
          ) : (
            <DataTable
              caption="Busiest lanes by load count"
              rows={lanes.data ?? []}
              rowKey={(row) => `${row.origin}-${row.destination}`}
              emptyMessage="No lanes with repeat loads in this range."
              columns={[
                {
                  key: "lane",
                  header: "Lane",
                  render: (row) => (
                    <span className="font-semibold text-fg">
                      {row.origin} → {row.destination}
                    </span>
                  ),
                },
                { key: "loads", header: "Loads", align: "right", render: (row) => <CountCell value={row.loads} /> },
                { key: "cost", header: "Avg cost", align: "right", render: (row) => <MoneyCell value={row.avg_cost} /> },
                { key: "price", header: "Avg sell", align: "right", render: (row) => <MoneyCell value={row.avg_price} /> },
                { key: "margin", header: "Margin", align: "right", render: (row) => <MarginCell value={row.margin_pct} /> },
              ]}
            />
          )}
        </Card>

        <Card className="min-w-0 overflow-hidden">
          <h2 className="border-b border-line px-4 py-3 font-bold text-fg">Top customers</h2>
          {customers.isPending ? (
            <TableSkeleton rows={6} />
          ) : (
            <DataTable
              caption="Top customers by revenue"
              rows={(customers.data ?? []).slice(0, 10)}
              rowKey={(row) => row.customer}
              emptyMessage="No customer activity in this range."
              columns={[
                {
                  key: "customer",
                  header: "Customer",
                  render: (row) => (
                    <div className="min-w-0">
                      <p className="truncate font-semibold text-fg">{row.customer}</p>
                      <p className="text-xs text-muted">Last load {shortDate(row.last_load_date)}</p>
                    </div>
                  ),
                },
                { key: "loads", header: "Loads", align: "right", render: (row) => <CountCell value={row.loads} /> },
                { key: "revenue", header: "Revenue", align: "right", render: (row) => <MoneyCell value={row.revenue} /> },
                { key: "profit", header: "Profit", align: "right", render: (row) => <MoneyCell value={row.profit} /> },
                { key: "margin", header: "Margin", align: "right", render: (row) => <MarginCell value={row.margin_pct} /> },
              ]}
            />
          )}
        </Card>
      </div>

      <Card className="mt-5">
        <h2 className="flex items-center gap-2 border-b border-line px-4 py-3 font-bold text-fg">
          <BarChart3 className="h-4 w-4 text-muted" />
          Cost by equipment
        </h2>
        {summary.isPending ? (
          <TableSkeleton rows={4} />
        ) : (
          <DataTable
            caption="Average cost and margin by equipment type"
            rows={summary.data?.by_equipment ?? []}
            rowKey={(row) => row.equipment ?? "unknown"}
            emptyMessage="No equipment data in this range."
            columns={[
              {
                key: "equipment",
                header: "Equipment",
                render: (row) => (
                  <span className="font-semibold text-fg">{row.equipment || "Not recorded"}</span>
                ),
              },
              { key: "loads", header: "Loads", align: "right", render: (row) => <CountCell value={row.loads} /> },
              { key: "cost", header: "Avg cost", align: "right", render: (row) => <MoneyCell value={row.avg_cost} /> },
              { key: "price", header: "Avg sell", align: "right", render: (row) => <MoneyCell value={row.avg_price} /> },
              { key: "margin", header: "Margin", align: "right", render: (row) => <MarginCell value={row.margin_pct} /> },
            ]}
          />
        )}
      </Card>
    </>
  );
}
