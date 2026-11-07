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
  const { value, setValue, range, label, month, year, setMonth, setYear } =
    useRange("month");
  const [params, setParams] = useSearchParams();
  const intervalParam = params.get("interval");
  const interval =
    intervalParam === "week" || intervalParam === "month"
      ? intervalParam
      : value === "month"
        ? "week"
        : "month";
  const tableYear = value === "month" ? Number(month.slice(0, 4)) : year;
  const tableRange =
    value === "all"
      ? { start: "2000-01-01" }
      : { start: `${tableYear}-01-01`, end: `${tableYear}-12-31` };

  useEffect(() => {
    document.title = "Dashboard · Fifth Wheel";
  }, []);

  const summary = useQuery({
    queryKey: ["kof", "summary", range, interval],
    queryFn: () => kof.summary(range, interval),
  });
  const monthSummary = useQuery({
    queryKey: ["kof", "summary", tableRange, "month"],
    queryFn: () => kof.summary(tableRange, "month"),
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
    updated.set("interval", next);
    setParams(updated, { replace: true });
  }

  function selectMonth(nextMonth: string) {
    const updated = new URLSearchParams(params);
    const now = new Date();
    const currentMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
    updated.delete("range");
    updated.delete("period");
    if (nextMonth === currentMonth) updated.delete("month");
    else updated.set("month", nextMonth);
    setParams(updated, { replace: true });
  }

  const monthRows = [...(monthSummary.data?.series ?? [])].sort((a, b) =>
    b.period.localeCompare(a.period),
  );

  const heading = (
    <PageHeading
      eyebrow="Performance"
      title="Dashboard"
      description={`Freight cost, carrier cost and profit across your loads. ${label}.`}
      action={
        <RangeTabs
          value={value}
          onChange={setValue}
          month={month}
          year={year}
          setMonth={setMonth}
          setYear={setYear}
        />
      }
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
              label="Total freight cost"
              value={compactMoney(totals?.revenue)}
              hint={`${totals?.loads ?? 0} loads`}
            />
            <Kpi label="Total carrier cost" value={compactMoney(totals?.cost)} hint={`Avg ${money(totals?.avg_cost)} / load`} />
            <Kpi label="Total profit" value={compactMoney(totals?.profit)} hint={`Avg ${money(totals?.avg_profit)} / load`} tone="accent" />
            <Kpi
              label="Margin"
              value={pct(totals?.margin_pct)}
              hint={
                totals?.on_time_pct !== null && totals?.on_time_pct !== undefined
                  ? `${pct(totals.on_time_pct, 0)} on time`
                  : `Avg freight cost ${money(totals?.avg_price)}`
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

      <Card className="mt-5 min-w-0 overflow-hidden">
        <h2 className="border-b border-line px-4 py-3 font-bold text-fg">
          Month by month · {value === "all" ? "All time" : tableYear}
        </h2>
        {monthSummary.isPending ? (
          <TableSkeleton rows={5} />
        ) : monthSummary.isError ? (
          <div className="p-4">
            <ErrorState
              message={(monthSummary.error as Error).message}
              onRetry={() => monthSummary.refetch()}
            />
          </div>
        ) : (
          <DataTable
            caption="Month-by-month freight cost and profit summary"
            rows={monthRows}
            rowKey={(row) => row.period.slice(0, 7)}
            activeKey={value === "month" ? month : null}
            cellVerticalAlign="middle"
            emptyMessage="No loads in this period."
            columns={[
              {
                key: "month",
                header: "Month",
                render: (row) => {
                  const monthValue = row.period.slice(0, 7);
                  const monthLabel = new Date(`${monthValue}-01T00:00:00`).toLocaleDateString(
                    undefined,
                    { month: "short", year: "numeric" },
                  );
                  return (
                    <button
                      type="button"
                      aria-pressed={value === "month" && monthValue === month}
                      onClick={() => selectMonth(monthValue)}
                      className="inline-flex min-h-11 items-center rounded-lg px-1 text-left font-semibold text-accent hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                    >
                      {monthLabel}
                    </button>
                  );
                },
              },
              { key: "loads", header: "Loads", align: "right", render: (row) => <CountCell value={row.loads} /> },
              { key: "revenue", header: "Freight cost", align: "right", render: (row) => <MoneyCell value={row.revenue} /> },
              { key: "avg_price", header: "Avg freight cost", align: "right", render: (row) => <MoneyCell value={row.avg_price} /> },
              { key: "avg_cost", header: "Avg carrier cost", align: "right", render: (row) => <MoneyCell value={row.avg_cost} /> },
              { key: "profit", header: "Profit", align: "right", render: (row) => <MoneyCell value={row.profit} /> },
              { key: "margin", header: "Margin", align: "right", render: (row) => <MarginCell value={row.margin_pct} /> },
            ]}
          />
        )}
      </Card>

      <Card className="mt-5 p-4 sm:p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-bold text-fg">Freight cost, carrier cost and profit</h2>
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
                { key: "cost", header: "Avg carrier cost", align: "right", render: (row) => <MoneyCell value={row.avg_cost} /> },
                { key: "price", header: "Avg freight cost", align: "right", render: (row) => <MoneyCell value={row.avg_price} /> },
                { key: "profit", header: "Total profit", align: "right", render: (row) => <MoneyCell value={row.total_profit} /> },
                { key: "avg_profit", header: "Avg profit", align: "right", render: (row) => <MoneyCell value={row.avg_profit} /> },
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
              caption="Top customers by freight cost"
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
                { key: "revenue", header: "Freight cost", align: "right", render: (row) => <MoneyCell value={row.revenue} /> },
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
              { key: "cost", header: "Avg carrier cost", align: "right", render: (row) => <MoneyCell value={row.avg_cost} /> },
              { key: "price", header: "Avg freight cost", align: "right", render: (row) => <MoneyCell value={row.avg_price} /> },
              { key: "margin", header: "Margin", align: "right", render: (row) => <MarginCell value={row.margin_pct} /> },
            ]}
          />
        )}
      </Card>
    </>
  );
}
