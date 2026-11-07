import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { Briefcase } from "lucide-react";
import { kof } from "../../kof/api";
import { EmptyState, ErrorState, PageHeading } from "../../components/common";
import { Card, Tabs } from "../../components/ui";
import { TableSkeleton } from "../../kof/components";

function cleanCell(value?: string) {
  return (value ?? "").replace(/\s*More\s*\.\.\.\s*$/, "").trim();
}

export default function Sales() {
  const [params, setParams] = useSearchParams();
  useEffect(() => {
    document.title = "Sales · Fifth Wheel";
  }, []);
  const sales = useQuery({ queryKey: ["kof", "sales"], queryFn: kof.sales });
  const lists = sales.data?.lists ?? [];
  const activeKey = params.get("list") ?? lists[0]?.key ?? "";
  const active = lists.find((list) => list.key === activeKey) ?? lists[0];
  const visibleColumns = active
    ? active.columns
        .map((column, index) => ({ column, index }))
        .filter(({ index }) => active.rows.some((row) => cleanCell(row[index])))
    : [];

  return (
    <>
      <PageHeading
        eyebrow="Pipeline"
        title="Sales"
        description="Leads, callbacks, past-due accounts and charge-backs from King of Freight."
      />
      {sales.isError && <ErrorState message={(sales.error as Error).message} onRetry={() => sales.refetch()} />}
      {sales.isPending ? (
        <Card><TableSkeleton /></Card>
      ) : lists.length === 0 ? (
        <EmptyState icon={Briefcase} title="No sales data yet" description="Sales lists appear after the first sync with King of Freight." />
      ) : (
        <>
          <div className="mb-4 overflow-x-auto">
            <Tabs
              ariaLabel="Sales list"
              value={active.key}
              onChange={(key) => {
                const updated = new URLSearchParams(params);
                updated.set("list", key);
                setParams(updated, { replace: true });
              }}
              items={lists.map((list) => ({ value: list.key, label: list.label, count: list.count }))}
            />
          </div>
          <Card>
            {active.rows.length === 0 ? (
              <p className="px-4 py-10 text-center text-sm text-muted">Nothing in {active.label.toLowerCase()} right now.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[640px] border-collapse text-sm">
                  <caption className="sr-only">{active.label}</caption>
                  <thead>
                    <tr className="border-b border-line">
                      {visibleColumns.map(({ column }) => (
                        <th key={column} scope="col" className="whitespace-nowrap px-3 py-2.5 text-left text-[11px] font-bold uppercase tracking-[0.12em] text-muted">
                          {column}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {active.rows.map((row, index) => (
                      <tr key={index} className="border-b border-line/60 last:border-0">
                        {visibleColumns.map(({ index: cellIndex }) => (
                          <td key={cellIndex} className="max-w-[280px] px-3 py-2.5 align-top text-fg-2">
                            <span className="line-clamp-3">{cleanCell(row[cellIndex]) || "—"}</span>
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}
    </>
  );
}
