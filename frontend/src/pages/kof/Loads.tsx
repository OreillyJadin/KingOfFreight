import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { Search } from "lucide-react";
import { kof, type KofLoadRow } from "../../kof/api";
import { ErrorState, PageHeading } from "../../components/common";
import { ListDetail } from "../../components/ListDetail";
import { Badge, Button, Card, Input, Select, Skeleton } from "../../components/ui";
import {
  DataTable,
  KofConnectionEmptyState,
  MarginCell,
  MoneyCell,
  TableSkeleton,
} from "../../kof/components";
import {
  appointment,
  money,
  place,
  shortDate,
  stageClass,
  stageLabels,
  stageOrder,
} from "../../kof/format";

const PAGE_SIZE = 50;

function Detail({ orderNo }: { orderNo: number }) {
  const detail = useQuery({
    queryKey: ["kof", "load", orderNo],
    queryFn: () => kof.load(orderNo),
  });

  if (detail.isPending) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-20" />
        <Skeleton className="h-36" />
      </div>
    );
  }
  if (detail.isError) {
    return <ErrorState message={(detail.error as Error).message} onRetry={() => detail.refetch()} />;
  }
  const load = detail.data;

  return (
    <div className="space-y-5">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-xl font-extrabold tabular-nums tracking-tight text-fg">#{load.order_no}</h2>
          <span className={`rounded-md px-2 py-0.5 text-[11px] font-bold ${stageClass(load.stage)}`}>
            {stageLabels[load.stage]}
          </span>
          {load.late && <Badge tone="danger">Late</Badge>}
        </div>
        <p className="mt-1 text-sm text-muted">
          {load.customer || "No customer"} · sold {shortDate(load.date_of_sale)}
        </p>
      </div>

      <dl className="grid grid-cols-3 gap-3">
        {[
          ["Freight cost", money(load.price)],
          ["Cost", money(load.cost)],
          ["Profit", money(load.profit)],
        ].map(([label, value]) => (
          <div key={label} className="rounded-xl bg-surface-2 px-3 py-2">
            <dt className="text-[11px] font-bold uppercase tracking-[0.12em] text-muted">{label}</dt>
            <dd className="mt-0.5 font-bold tabular-nums text-fg">{value}</dd>
          </div>
        ))}
      </dl>

      <div className="grid gap-4 sm:grid-cols-2">
        {[
          {
            title: "Pick up",
            party: load.shipper,
            at: load.pick_at,
            timeKnown: load.pick_time_known,
            tz: load.pick_tz,
          },
          {
            title: "Deliver",
            party: load.consignee,
            at: load.delivery_at,
            timeKnown: load.delivery_time_known,
            tz: load.drop_tz,
          },
        ].map((stop) => (
          <section key={stop.title}>
            <h3 className="text-[11px] font-bold uppercase tracking-[0.14em] text-muted">{stop.title}</h3>
            <p className="mt-1 font-semibold text-fg">{stop.party.company || "—"}</p>
            <p className="text-sm text-fg-2">{stop.party.address}</p>
            <p className="text-sm text-fg-2">{place(stop.party.city, stop.party.state)} {stop.party.zip}</p>
            <p className="mt-1 text-sm text-muted">{appointment(stop.at, stop.timeKnown, stop.tz)}</p>
            {stop.party.phone && <p className="text-sm text-muted">{stop.party.phone}</p>}
          </section>
        ))}
      </div>

      <section>
        <h3 className="text-[11px] font-bold uppercase tracking-[0.14em] text-muted">Carrier</h3>
        <p className="mt-1 font-semibold text-fg">
          {load.carrier || "—"} {load.mc && <span className="text-sm font-normal text-muted">MC {load.mc}</span>}
        </p>
        <p className="text-sm text-fg-2">
          {[load.carrier_contact.name, load.carrier_contact.phone, load.carrier_contact.email]
            .filter(Boolean)
            .join(" · ") || "No driver contact recorded"}
        </p>
        <p className="mt-1 text-sm text-muted">
          {[load.equipment, load.weight ? `${load.weight.toLocaleString()} lbs` : null, load.po ? `PO ${load.po}` : null]
            .filter(Boolean)
            .join(" · ")}
        </p>
      </section>

      {load.product_description && (
        <section>
          <h3 className="text-[11px] font-bold uppercase tracking-[0.14em] text-muted">Commodity</h3>
          <p className="mt-1 whitespace-pre-line text-sm text-fg-2">{load.product_description}</p>
        </section>
      )}

      <section>
        <h3 className="text-[11px] font-bold uppercase tracking-[0.14em] text-muted">
          Check calls and notes
        </h3>
        {load.notes.length === 0 ? (
          <p className="mt-1 text-sm text-muted">No notes on this load.</p>
        ) : (
          <ol className="mt-2 space-y-2.5 border-l border-line pl-4">
            {load.notes.map((note, index) => (
              <li key={index} className="relative">
                <span className="absolute -left-[21px] top-1.5 h-2 w-2 rounded-full bg-line-strong" />
                <p className="text-[11px] font-semibold uppercase tracking-wide text-muted">
                  {shortDate(note.at)}
                  {note.author && ` · ${note.author}`}
                </p>
                <p className="whitespace-pre-line text-sm text-fg-2">{note.text}</p>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}

export default function Loads() {
  const [params, setParams] = useSearchParams();
  const [draft, setDraft] = useState(params.get("q") ?? "");
  const query = params.get("q") ?? "";
  const stage = params.get("stage") ?? "";
  const page = Number(params.get("page") ?? "1");
  const selected = params.get("order") ? Number(params.get("order")) : null;

  useEffect(() => {
    document.title = "Loads · Fifth Wheel";
  }, []);

  const loads = useQuery({
    queryKey: ["kof", "loads", { query, stage, page }],
    queryFn: () =>
      kof.loads({
        q: query || undefined,
        stage: stage || undefined,
        page,
        page_size: PAGE_SIZE,
        sort: "-date_of_sale",
      }),
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

  function update(changes: Record<string, string | null>) {
    const updated = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value === null || value === "") updated.delete(key);
      else updated.set(key, value);
    }
    setParams(updated, { replace: true });
  }

  const total = loads.data?.total ?? 0;
  const showConnectionEmpty =
    !connection.isPending &&
    !syncStatus.isPending &&
    connection.data?.configured === false &&
    syncStatus.data?.load_count === 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const list = (
    <Card>
      {loads.isPending ? (
        <TableSkeleton />
      ) : (
        <DataTable
          caption="Loads"
          rows={loads.data?.items ?? []}
          rowKey={(row: KofLoadRow) => row.order_no}
          activeKey={selected}
          onRowClick={(row) => update({ order: String(row.order_no) })}
          emptyMessage="No loads match this search."
          columns={[
            {
              key: "order",
              header: "Order",
              render: (row) => (
                <div className="min-w-0">
                  <p className="font-bold tabular-nums text-fg">#{row.order_no}</p>
                  <p className="text-xs text-muted">{shortDate(row.date_of_sale)}</p>
                </div>
              ),
            },
            {
              key: "customer",
              header: "Customer",
              render: (row) => (
                <div className="min-w-0">
                  <p className="truncate font-semibold text-fg-2">{row.customer || "—"}</p>
                  <p className="truncate text-xs text-muted">
                    {place(row.origin_city, row.origin_state)} → {place(row.dest_city, row.dest_state)}
                  </p>
                </div>
              ),
            },
            {
              key: "carrier",
              header: "Carrier",
              render: (row) => <span className="text-fg-2">{row.carrier || "—"}</span>,
            },
            {
              key: "stage",
              header: "Stage",
              render: (row) => (
                <span className={`inline-block rounded-md px-2 py-0.5 text-[11px] font-bold ${stageClass(row.stage)}`}>
                  {stageLabels[row.stage]}
                </span>
              ),
            },
            { key: "price", header: "Freight cost", align: "right", render: (row) => <MoneyCell value={row.price} /> },
            { key: "cost", header: "Cost", align: "right", render: (row) => <MoneyCell value={row.cost} /> },
            {
              key: "margin",
              header: "Margin",
              align: "right",
              render: (row) => (
                <MarginCell value={row.price && row.profit !== null ? (row.profit / row.price) * 100 : null} />
              ),
            },
          ]}
        />
      )}
      {pages > 1 && (
        <div className="flex items-center justify-between gap-3 border-t border-line px-3 py-2.5">
          <p className="text-xs text-muted">
            Page <span className="tabular-nums">{page}</span> of{" "}
            <span className="tabular-nums">{pages}</span> ·{" "}
            <span className="tabular-nums">{total.toLocaleString()}</span> loads
          </p>
          <div className="flex gap-2">
            <Button
              size="sm"
              disabled={page <= 1}
              onClick={() => update({ page: String(page - 1), order: null })}
            >
              Previous
            </Button>
            <Button
              size="sm"
              disabled={page >= pages}
              onClick={() => update({ page: String(page + 1), order: null })}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </Card>
  );

  const heading = (
    <PageHeading
      eyebrow="History"
      title="Loads"
      description="Every load synced from King of Freight, searchable with full detail."
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
      <form
        className="mb-4 flex flex-wrap gap-2.5"
        onSubmit={(event) => {
          event.preventDefault();
          update({ q: draft, page: null, order: null });
        }}
      >
        <label className="relative min-w-[220px] flex-1">
          <span className="sr-only">Search loads</span>
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-subtle" />
          <Input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Order #, customer, carrier, city…"
            className="pl-9"
          />
        </label>
        <label>
          <span className="sr-only">Stage</span>
          <Select value={stage} onChange={(event) => update({ stage: event.target.value, page: null })}>
            <option value="">All stages</option>
            {stageOrder.map((key) => (
              <option key={key} value={key}>
                {stageLabels[key]}
              </option>
            ))}
          </Select>
        </label>
        <Button type="submit" variant="primary">
          Search
        </Button>
      </form>

      {loads.isError && (
        <ErrorState message={(loads.error as Error).message} onRetry={() => loads.refetch()} />
      )}

      <ListDetail
        list={list}
        detail={selected ? <Detail orderNo={selected} /> : null}
        detailKey={selected}
        detailTitle={selected ? `Load #${selected}` : "Load"}
        onCloseDetail={() => update({ order: null })}
      />
    </>
  );
}
