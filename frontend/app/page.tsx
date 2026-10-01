import { getApprovedTasks, getPendingReview } from "@/lib/api";
import LiveBadge from "@/components/LiveBadge";
import ReviewQueue from "@/components/ReviewQueue";

// The mining funnel: production failure clusters (discovered by
// app/mining/cluster.py) flow into the Django review queue, and only
// human-approved tasks make it into the regression suite that
// app/workflows/regression_run.py actually runs. This page makes that
// three-stage funnel visible end to end.
export default async function MiningFunnelPage() {
  const [{ tasks: pending, live: pendingLive }, { tasks: approved, live: approvedLive }] =
    await Promise.all([getPendingReview(), getApprovedTasks()]);

  const pendingCount = pending.filter((t) => t.status === "pending").length;
  const rejectedCount = pending.filter((t) => t.status === "rejected").length;
  const totalMinedTraces = pending.reduce((sum, t) => sum + (t.origin_cluster_size ?? 0), 0);

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-neutral-100">Mining Funnel</h1>
          <p className="mt-1 text-sm text-neutral-400">
            Failure clusters discovered in production traces, waiting on or past human review,
            and finally promoted into the regression suite.
          </p>
        </div>
      </div>

      <div className="mb-10 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <FunnelStat
          label="Production traces clustered"
          value={totalMinedTraces || "—"}
          hint="across all mined failure clusters"
        />
        <FunnelStat
          label="Awaiting review"
          value={pendingCount}
          hint="in the Django back-office queue"
        />
        <FunnelStat
          label="Promoted to regression suite"
          value={approved.length}
          hint="approved tasks, replayed every version comparison"
        />
      </div>

      <section className="mb-10">
        <div className="mb-3 flex items-center gap-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-400">
            Review queue
          </h2>
          <LiveBadge live={pendingLive} label="Django back-office" />
        </div>
        <ReviewQueue initialTasks={pending} live={pendingLive} />
        {rejectedCount > 0 && (
          <p className="mt-3 text-xs text-neutral-500">
            {rejectedCount} cluster{rejectedCount === 1 ? "" : "s"} rejected as infra noise, not
            shown as actionable.
          </p>
        )}
      </section>

      <section>
        <div className="mb-3 flex items-center gap-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-400">
            Approved regression tasks
          </h2>
          <LiveBadge live={approvedLive} label="FastAPI /tasks" />
        </div>
        <div className="divide-y divide-neutral-800 rounded-lg border border-neutral-800 bg-neutral-900/60">
          {approved.map((task) => (
            <div key={task.id} className="p-4">
              <div className="flex items-center gap-2">
                <span className="font-mono text-sm text-neutral-100">{task.name}</span>
                <span className="rounded-full bg-neutral-800 px-2 py-0.5 text-xs text-neutral-400">
                  {task.category}
                </span>
              </div>
              <p className="mt-1 text-sm text-neutral-400">{task.instruction}</p>
              {task.origin && (
                <p className="mt-2 text-xs text-neutral-500">
                  originally mined from {task.origin.cluster_size} traces in{" "}
                  <span className="font-mono">{task.origin.cluster_id}</span>
                </p>
              )}
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}

function FunnelStat({
  label,
  value,
  hint,
}: {
  label: string;
  value: string | number;
  hint: string;
}) {
  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-900/60 p-4">
      <p className="text-xs uppercase tracking-wide text-neutral-500">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-neutral-100">{value}</p>
      <p className="mt-1 text-xs text-neutral-500">{hint}</p>
    </div>
  );
}
