"use client";

import { useState } from "react";
import { approvePendingTask, rejectPendingTask } from "@/lib/api";
import type { PendingReviewTask } from "@/lib/types";

const STATUS_STYLES: Record<PendingReviewTask["status"], string> = {
  pending: "bg-neutral-800 text-neutral-300 ring-1 ring-neutral-700",
  approved: "bg-emerald-950 text-emerald-400 ring-1 ring-emerald-800",
  rejected: "bg-red-950 text-red-400 ring-1 ring-red-800",
};

export default function ReviewQueue({
  initialTasks,
  live,
}: {
  initialTasks: PendingReviewTask[];
  live: boolean;
}) {
  const [tasks, setTasks] = useState(initialTasks);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleDecision(id: number, decision: "approve" | "reject") {
    if (!live) {
      setError(
        "Django back-office isn't connected in this deployment, so approve/reject can't write back. Set NEXT_PUBLIC_DJANGO_BASE to enable it.",
      );
      return;
    }
    setBusyId(id);
    setError(null);
    try {
      const fn = decision === "approve" ? approvePendingTask : rejectPendingTask;
      const updated = await fn(id, "vedant", `${decision}d from the dashboard review queue`);
      if (updated) {
        setTasks((prev) => prev.map((t) => (t.id === id ? updated : t)));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "request failed");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="space-y-3">
      {error && (
        <div className="rounded-md bg-red-950 px-3 py-2 text-sm text-red-300 ring-1 ring-red-800">
          {error}
        </div>
      )}
      {tasks.length === 0 && (
        <p className="text-sm text-neutral-500">No mined clusters are awaiting review.</p>
      )}
      {tasks.map((task) => (
        <div
          key={task.id}
          className="rounded-lg border border-neutral-800 bg-neutral-900/60 p-4"
        >
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-mono text-sm text-neutral-100">{task.name}</span>
                <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[task.status]}`}>
                  {task.status}
                </span>
              </div>
              <p className="mt-1 text-sm text-neutral-400">{task.instruction}</p>
              {task.origin_cluster_id && (
                <p className="mt-2 text-xs text-neutral-500">
                  mined from <span className="font-mono">{task.origin_cluster_id}</span> &middot;{" "}
                  {task.origin_cluster_size} production traces &middot; &ldquo;
                  {task.origin_representative_summary}&rdquo;
                </p>
              )}
              {task.review_notes && (
                <p className="mt-2 text-xs italic text-neutral-500">
                  reviewed by {task.reviewed_by}: {task.review_notes}
                </p>
              )}
            </div>
            {task.status === "pending" && (
              <div className="flex shrink-0 gap-2">
                <button
                  onClick={() => handleDecision(task.id, "approve")}
                  disabled={busyId === task.id}
                  className="rounded-md bg-emerald-900 px-3 py-1.5 text-xs font-medium text-emerald-200 hover:bg-emerald-800 disabled:opacity-50"
                >
                  Approve
                </button>
                <button
                  onClick={() => handleDecision(task.id, "reject")}
                  disabled={busyId === task.id}
                  className="rounded-md bg-red-950 px-3 py-1.5 text-xs font-medium text-red-300 hover:bg-red-900 disabled:opacity-50"
                >
                  Reject
                </button>
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
