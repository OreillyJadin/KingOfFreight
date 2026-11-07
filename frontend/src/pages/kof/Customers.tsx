import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Search } from "lucide-react";
import { kof } from "../../kof/api";
import { ErrorState, PageHeading } from "../../components/common";
import { Card, Input } from "../../components/ui";
import { CountCell, DataTable, MarginCell, MoneyCell, TableSkeleton } from "../../kof/components";
import { shortDate } from "../../kof/format";
import { RangeTabs, useRange } from "../../kof/useRange";

export default function Customers() {
  const { value, setValue, range, label } = useRange("365");
  const [filter, setFilter] = useState("");
  useEffect(() => {
    document.title = "Customers · Fifth Wheel";
  }, []);
  const customers = useQuery({
    queryKey: ["kof", "customers", range],
    queryFn: () => kof.customers(range),
  });
  const rows = useMemo(
    () =>
      (customers.data ?? []).filter((row) =>
        row.customer.toLowerCase().includes(filter.trim().toLowerCase()),
      ),
    [customers.data, filter],
  );

  return (
    <>
      <PageHeading
        eyebrow="Accounts"
        title="Customers"
        description={`Volume, revenue and margin by customer. ${label}.`}
        action={<RangeTabs value={value} onChange={setValue} />}
      />
      <label className="relative mb-4 block max-w-sm">
        <span className="sr-only">Filter customers</span>
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-subtle" />
        <Input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="Filter customers" className="pl-9" />
      </label>
      {customers.isError && <ErrorState message={(customers.error as Error).message} onRetry={() => customers.refetch()} />}
      <Card>
        {customers.isPending ? (
          <TableSkeleton />
        ) : (
          <DataTable
            caption="Customers"
            rows={rows}
            rowKey={(row) => row.customer}
            emptyMessage="No customers in this range."
            columns={[
              {
                key: "customer",
                header: "Customer",
                render: (row) => (
                  <Link to={`/loads?q=${encodeURIComponent(row.customer)}`} className="font-semibold text-fg hover:text-accent-ink">
                    {row.customer}
                  </Link>
                ),
              },
              { key: "loads", header: "Loads", align: "right", render: (row) => <CountCell value={row.loads} /> },
              { key: "revenue", header: "Revenue", align: "right", render: (row) => <MoneyCell value={row.revenue} /> },
              { key: "cost", header: "Cost", align: "right", render: (row) => <MoneyCell value={row.cost} /> },
              { key: "profit", header: "Profit", align: "right", render: (row) => <MoneyCell value={row.profit} /> },
              { key: "avg", header: "Avg sell", align: "right", render: (row) => <MoneyCell value={row.avg_price} /> },
              { key: "margin", header: "Margin", align: "right", render: (row) => <MarginCell value={row.margin_pct} /> },
              { key: "last", header: "Last load", align: "right", render: (row) => <span className="text-muted">{shortDate(row.last_load_date)}</span> },
            ]}
          />
        )}
      </Card>
    </>
  );
}
