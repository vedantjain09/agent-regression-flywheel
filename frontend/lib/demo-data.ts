// Deterministic demo-mode fixtures.
//
// This mirrors the same "real client with a deterministic offline fallback"
// pattern used throughout the Python backend (LLMClient's OpenAI/rule-based
// split, SnowflakeTraceStore's live/no-op split, get_sandbox_runner's
// Modal/local split): the dashboard always renders something real-shaped
// even when FASTAPI_BASE/DJANGO_BASE aren't reachable from wherever it's
// deployed, instead of showing a blank screen or a stack trace. Every shape
// here matches the live API response types in lib/types.ts exactly, so
// swapping in a real backend is a config change, not a rewrite.

import type { CompareResponse, PendingReviewTask, Task } from "./types";

export const DEMO_APPROVED_TASKS: Task[] = [
  {
    id: "5f1b0b2a-1111-4a3e-9c9a-000000000001",
    name: "large-file-read-timeout",
    category: "auto-generated",
    instruction: "Reproduce and resolve: agent times out reading files larger than 50MB.",
    approved: true,
    created_at: "2026-09-12T18:04:00Z",
    origin: {
      cluster_id: "cluster-14",
      source_trace_ids: ["tr_8a21", "tr_8a2f", "tr_8a55", "tr_8a61", "tr_8a7c"],
      discovered_at: "2026-09-12T18:03:40Z",
      cluster_size: 11,
      representative_summary: "agent repeatedly times out on large file reads",
    },
  },
  {
    id: "5f1b0b2a-1111-4a3e-9c9a-000000000002",
    name: "auth-401-retry-loop",
    category: "auto-generated",
    instruction: "Reproduce and resolve: agent enters an infinite retry loop on a 401 from the tool server.",
    approved: true,
    created_at: "2026-09-14T09:22:00Z",
    origin: {
      cluster_id: "cluster-19",
      source_trace_ids: ["tr_9b02", "tr_9b19", "tr_9b4e"],
      discovered_at: "2026-09-14T09:21:55Z",
      cluster_size: 8,
      representative_summary: "agent retries the same tool call after a 401 instead of re-authenticating",
    },
  },
  {
    id: "5f1b0b2a-1111-4a3e-9c9a-000000000003",
    name: "malformed-json-tool-output",
    category: "manual",
    instruction: "Verify the agent gracefully recovers when a tool returns truncated JSON.",
    approved: true,
    created_at: "2026-09-20T15:11:00Z",
    origin: null,
  },
];

export const DEMO_PENDING_REVIEW: PendingReviewTask[] = [
  {
    id: 101,
    external_id: "5f1b0b2a-2222-4a3e-9c9a-000000000101",
    name: "cluster-27-nested-tool-call",
    category: "auto-generated",
    instruction: "Reproduce and resolve: agent emits a nested tool_call payload the parser rejects.",
    check_command: "python verify_nested_tool_call.py",
    origin_cluster_id: "cluster-27",
    origin_cluster_size: 6,
    origin_representative_summary: "agent emits malformed nested tool_calls under long contexts",
    status: "pending",
    reviewed_by: null,
    review_notes: null,
    created_at: "2026-09-27T11:40:00Z",
    reviewed_at: null,
  },
  {
    id: 102,
    external_id: "5f1b0b2a-2222-4a3e-9c9a-000000000102",
    name: "cluster-31-partial-write-crash",
    category: "auto-generated",
    instruction: "Reproduce and resolve: sandbox crash mid-write leaves a partial file that later steps misread.",
    check_command: "python verify_partial_write_recovery.py",
    origin_cluster_id: "cluster-31",
    origin_cluster_size: 4,
    origin_representative_summary: "sandbox termination mid-write corrupts downstream file reads",
    status: "pending",
    reviewed_by: null,
    review_notes: null,
    created_at: "2026-09-28T08:05:00Z",
    reviewed_at: null,
  },
  {
    id: 100,
    external_id: "5f1b0b2a-2222-4a3e-9c9a-000000000100",
    name: "cluster-22-stale-env-var",
    category: "auto-generated",
    instruction: "Reproduce and resolve: agent reads a stale cached env var after a tool restart.",
    check_command: "python verify_env_refresh.py",
    origin_cluster_id: "cluster-22",
    origin_cluster_size: 9,
    origin_representative_summary: "agent uses a stale environment snapshot after a mid-run tool restart",
    status: "rejected",
    reviewed_by: "vedant",
    review_notes: "infra flake on the runner, not a real agent bug — excluded from the suite",
    created_at: "2026-09-21T10:00:00Z",
    reviewed_at: "2026-09-22T14:30:00Z",
  },
];

export const DEMO_COMPARE_RESULT: CompareResponse = {
  n_pairs: 40,
  n_concordant: 31,
  baseline_only_passed: 1,
  candidate_only_passed: 8,
  p_value: 0.0390625,
  significant: true,
  direction: "improved",
  promote: true,
  reason: "promote: significant improvement",
};
