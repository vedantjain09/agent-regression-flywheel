"use client";

import { useState, useMemo } from "react";
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
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "pending" | "approved" | "rejected">("all");
  const [categoryFilter, setCategoryFilter] = useState<string>("all");
  const [currentUser, setCurrentUser] = useState("anonymous");

  // Extract unique categories
  const categories = useMemo(() => {
    const cats = new Set(tasks.map((t) => t.category));
    return Array.from(cats).sort();
  }, [tasks]);

  // Filter tasks based on search and filters
  const filteredTasks = useMemo(() => {
    return tasks.filter((task) => {
      const matchesSearch = 
        searchQuery === "" ||
        task.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        task.instruction.toLowerCase().includes(searchQuery.toLowerCase());
      
      const matchesStatus = statusFilter === "all" || task.status === statusFilter;
      
      const matchesCategory = categoryFilter === "all" || task.category === categoryFilter;

      return matchesSearch && matchesStatus && matchesCategory;
    });
  }, [tasks, searchQuery, statusFilter, categoryFilter]);

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
      const updated = await fn(id, currentUser, `${decision}d from the dashboard review queue`);
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
    <div className="space-y-4">
      {error && (
        <div className="rounded-md bg-red-950 px-3 py-2 text-sm text-red-300 ring-1 ring-red-800">
          {error}
        </div>
      )}
      
      {/* Search and Filter Controls */}
      <div className="rounded-lg border border-neutral-800 bg-neutral-900/60 p-4">
        <div className="mb-3">
          <label className="block text-xs font-medium uppercase tracking-wide text-neutral-500 mb-1">
            Search
          </label>
          <input
            type="text"
            placeholder="Search by name or instruction..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full rounded-md border border-neutral-700 bg-neutral-950 px-3 py-1.5 text-sm text-neutral-200 placeholder:text-neutral-600"
          />
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label className="block text-xs font-medium uppercase tracking-wide text-neutral-500 mb-1">
              Status
            </label>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as "all" | "pending" | "approved" | "rejected")}
              className="w-full rounded-md border border-neutral-700 bg-neutral-950 px-3 py-1.5 text-sm text-neutral-200"
            >
              <option value="all">All statuses</option>
              <option value="pending">Pending</option>
              <option value="approved">Approved</option>
              <option value="rejected">Rejected</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium uppercase tracking-wide text-neutral-500 mb-1">
              Category
            </label>
            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              className="w-full rounded-md border border-neutral-700 bg-neutral-950 px-3 py-1.5 text-sm text-neutral-200"
            >
              <option value="all">All categories</option>
              {categories.map((cat) => (
                <option key={cat} value={cat}>{cat}</option>
              ))}
            </select>
          </div>
        </div>
        <p className="mt-2 text-xs text-neutral-500">
          Showing {filteredTasks.length} of {tasks.length} tasks
        </p>
      </div>

      {filteredTasks.length === 0 && (
        <p className="text-sm text-neutral-500">
          {tasks.length === 0 
            ? "No mined clusters are awaiting review." 
            : "No tasks match your search and filter criteria."}
        </p>
      )}
      {filteredTasks.map((task) => (
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
