import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { AlertTriangle, Radar } from "lucide-react";
import { kof, type KofTrackingLoad } from "../../kof/api";
import { EmptyState, ErrorState, PageHeading } from "../../components/common";
import { Badge, Button, Card, CardListSkeleton } from "../../components/ui";
import { money, place, relativeHours, shortDate, stageClass } from "../../kof/format";

function LoadCard({ load }: { load: KofTrackingLoad }) {
  return (
    <Card className="p-3.5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <Link
            to={`/loads?order=${load.order_no}`}
            className="font-bold tabular-nums text-fg hover:text-accent-ink"
          >
            #{load.order_no}
          </Link>
          <p className="truncate text-sm text-fg-2">{load.customer || "No customer"}</p>
        </div>
        {load.late && (
          <Badge tone="danger">
            <AlertTriangle className="h-3 w-3" />
            Late
          </Badge>
        )}
      </div>
      <p className="mt-2 text-sm font-semibold text-fg-2">
        {place(load.origin_city, load.origin_state)} → {place(load.dest_city, load.dest_state)}
      </p>
      <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-muted">
        <div>
          <dt className="inline">Pick </dt>
          <dd className="inline text-fg-2">{shortDate(load.pick_at)}</dd>
        </div>
        <div>
          <dt className="inline">Drop </dt>
          <dd className="inline text-fg-2">{shortDate(load.delivery_at)}</dd>
        </div>
        <div>
          <dt className="inline">Carrier </dt>
          <dd className="inline truncate text-fg-2">{load.carrier || "—"}</dd>
        </div>
        <div>
          <dt className="inline">Cost </dt>
          <dd className="inline tabular-nums text-fg-2">{money(load.cost)}</dd>
        </div>
      </dl>
      <p className="mt-2.5 border-t border-line pt-2 text-xs text-muted">
        <span className={load.hours_since_update && load.hours_since_update > 24 ? "text-warn-ink" : ""}>
          {relativeHours(load.hours_since_update)}
        </span>
        {load.last_note?.text && (
          <span className="mt-1 block line-clamp-2 text-fg-2">{load.last_note.text}</span>
        )}
      </p>
    </Card>
  );
}

export default function KofTracking() {
  const [params, setParams] = useSearchParams();
  const lateOnly = params.get("late") === "1";

  useEffect(() => {
    document.title = "Tracking · Fifth Wheel";
  }, []);

  const tracking = useQuery({
    queryKey: ["kof", "tracking"],
    queryFn: kof.tracking,
    refetchInterval: 120000,
  });

  const stages = (tracking.data?.stages ?? []).map((stage) => ({
    ...stage,
    loads: lateOnly ? stage.loads.filter((load) => load.late) : stage.loads,
  }));
  const total = stages.reduce((sum, stage) => sum + stage.loads.length, 0);
  const lateCount = (tracking.data?.stages ?? []).reduce(
    (sum, stage) => sum + stage.loads.filter((load) => load.late).length,
    0,
  );

  function toggleLate() {
    const updated = new URLSearchParams(params);
    if (lateOnly) updated.delete("late");
    else updated.set("late", "1");
    setParams(updated, { replace: true });
  }

  return (
    <>
      <PageHeading
        eyebrow="Live freight"
        title="Tracking"
        description="Every load in motion, by stage, with how long since the last check call."
        action={
          <Button variant={lateOnly ? "warn" : "secondary"} onClick={toggleLate}>
            <AlertTriangle className="h-4 w-4" />
            {lateOnly ? "Showing late only" : `Late (${lateCount})`}
          </Button>
        }
      />

      {tracking.isError && (
        <ErrorState message={(tracking.error as Error).message} onRetry={() => tracking.refetch()} />
      )}

      {tracking.isPending ? (
        <CardListSkeleton count={4} />
      ) : total === 0 ? (
        <EmptyState
          icon={Radar}
          title={lateOnly ? "Nothing is running late" : "No loads in motion"}
          description={
            lateOnly
              ? "Every active load has hit its appointments so far."
              : "Active loads appear here as soon as they are picked up."
          }
        />
      ) : (
        <div className="grid gap-5 lg:grid-cols-3">
          {stages.map((stage) => (
            <section key={stage.key} aria-labelledby={`stage-${stage.key}`}>
              <h2
                id={`stage-${stage.key}`}
                className="mb-2.5 flex items-center gap-2 text-sm font-bold text-fg"
              >
                <span className={`rounded-md px-2 py-0.5 text-[11px] font-bold ${stageClass(stage.key)}`}>
                  {stage.label}
                </span>
                <span className="tabular-nums text-muted">{stage.loads.length}</span>
              </h2>
              <div className="space-y-2.5">
                {stage.loads.length === 0 ? (
                  <p className="rounded-xl border border-dashed border-line-strong px-3 py-6 text-center text-xs text-muted">
                    Nothing here
                  </p>
                ) : (
                  stage.loads.map((load) => <LoadCard key={load.order_no} load={load} />)
                )}
              </div>
            </section>
          ))}
        </div>
      )}
    </>
  );
}
