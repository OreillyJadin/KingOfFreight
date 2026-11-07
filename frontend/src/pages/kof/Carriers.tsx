import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Search } from "lucide-react";
import { kof } from "../../kof/api";
import { ErrorState, PageHeading } from "../../components/common";
import { Card, Input, Tabs } from "../../components/ui";
import { CountCell, DataTable, MarginCell, MoneyCell, TableSkeleton } from "../../kof/components";
import { pct, shortDate } from "../../kof/format";
import { RangeTabs, useRange } from "../../kof/useRange";

export default function Carriers() {
  const { value, setValue, range, label, month, year, setMonth, setYear } =
    useRange("year");
  const [filter, setFilter] = useState("");
  const [view, setView] = useState<"carriers" | "lanes">("carriers");
  useEffect(() => {
    document.title = "Carriers & lanes · Fifth Wheel";
  }, []);
  const carriers = useQuery({
    queryKey: ["kof", "carriers", range],
    queryFn: () => kof.carriers(range),
    enabled: view === "carriers",
  });
  const lanes = useQuery({
    queryKey: ["kof", "lanes", range, "city"],
    queryFn: () => kof.lanes(range, "city", 1, 200),
    enabled: view === "lanes",
  });
  const needle = filter.trim().toLowerCase();
  const carrierRows = useMemo(
    () => (carriers.data ?? []).filter((row) => `${row.carrier} ${row.mc ?? ""}`.toLowerCase().includes(needle)),
    [carriers.data, needle],
  );
  const laneRows = useMemo(
    () => (lanes.data ?? []).filter((row) => `${row.origin} ${row.destination}`.toLowerCase().includes(needle)),
    [lanes.data, needle],
  );
  const active = view === "carriers" ? carriers : lanes;
  const hasOnTime = carrierRows.some((row) => row.on_time_pct !== null);

  return (
    <>
      <PageHeading
        eyebrow="Capacity"
        title="Carriers & lanes"
        description={`What you pay, who you use, and where. ${label}.`}
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
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Tabs
          ariaLabel="View"
          value={view}
          onChange={setView}
          items={[
            { value: "carriers", label: "Carriers" },
            { value: "lanes", label: "Lane rates" },
          ]}
        />
        <label className="relative min-w-[220px] max-w-sm flex-1">
          <span className="sr-only">Filter</span>
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-subtle" />
          <Input
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            placeholder={view === "carriers" ? "Carrier or MC #" : "City or state"}
            className="pl-9"
          />
        </label>
      </div>
      {active.isError && <ErrorState message={(active.error as Error).message} onRetry={() => active.refetch()} />}
      <Card>
        {active.isPending ? (
          <TableSkeleton />
        ) : view === "carriers" ? (
          <DataTable
            caption="Carriers"
            rows={carrierRows}
            rowKey={(row) => `${row.carrier}-${row.mc ?? ""}`}
            emptyMessage="No carriers in this range."
            columns={[
              {
                key: "carrier",
                header: "Carrier",
                render: (row) => (
                  <div className="min-w-0">
                    <Link to={`/loads?q=${encodeURIComponent(row.carrier)}`} className="font-semibold text-fg hover:text-accent-ink">
                      {row.carrier}
                    </Link>
                    <p className="text-xs text-muted">{row.mc ? `MC ${row.mc}` : "No MC"}</p>
                  </div>
                ),
              },
              { key: "loads", header: "Loads", align: "right", render: (row) => <CountCell value={row.loads} /> },
              { key: "avg", header: "Avg carrier cost", align: "right", render: (row) => <MoneyCell value={row.avg_cost} /> },
              { key: "total", header: "Total paid", align: "right", render: (row) => <MoneyCell value={row.total_cost} /> },
              ...(hasOnTime
                ? [
                    {
                      key: "ontime",
                      header: "On time",
                      align: "right" as const,
                      render: (row: (typeof carrierRows)[number]) => (
                        <span className="tabular-nums text-fg-2">{pct(row.on_time_pct, 0)}</span>
                      ),
                    },
                  ]
                : []),
              {
                key: "lanes",
                header: "Top lanes",
                render: (row) => <span className="text-xs text-muted">{row.top_lanes.slice(0, 2).join(" · ") || "—"}</span>,
              },
              { key: "last", header: "Last load", align: "right", render: (row) => <span className="text-muted">{shortDate(row.last_load_date)}</span> },
            ]}
          />
        ) : (
          <DataTable
            caption="Lane rates"
            rows={laneRows}
            rowKey={(row) => `${row.origin}-${row.destination}`}
            emptyMessage="No lanes in this range."
            columns={[
              { key: "lane", header: "Lane", render: (row) => <span className="font-semibold text-fg">{row.origin} → {row.destination}</span> },
              { key: "loads", header: "Loads", align: "right", render: (row) => <CountCell value={row.loads} /> },
              { key: "avg", header: "Avg carrier cost", align: "right", render: (row) => <MoneyCell value={row.avg_cost} /> },
              {
                key: "range",
                header: "Cost range",
                align: "right",
                render: (row) => (
                  <span className="tabular-nums text-muted">
                    <MoneyCell value={row.min_cost} />–<MoneyCell value={row.max_cost} />
                  </span>
                ),
              },
              { key: "last", header: "Last paid", align: "right", render: (row) => <MoneyCell value={row.last_cost} /> },
              { key: "sell", header: "Avg freight cost", align: "right", render: (row) => <MoneyCell value={row.avg_price} /> },
              { key: "margin", header: "Margin", align: "right", render: (row) => <MarginCell value={row.margin_pct} /> },
            ]}
          />
        )}
      </Card>
    </>
  );
}
