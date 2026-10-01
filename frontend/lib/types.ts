// Shared types mirroring backend/app/schemas/task.py and
// backend/app/stats/significance.py. Kept hand-written (not codegen'd)
// since the surface is small and stable; if it drifts, the FastAPI
// response_model validation on the backend is the source of truth.

export interface Task {
  id: string;
  name: string;
  category: string;
  instruction: string;
  approved: boolean;
  created_at: string;
  origin: {
    cluster_id: string;
    source_trace_ids: string[];
    discovered_at: string;
    cluster_size: number;
    representative_summary: string;
  } | null;
}

export interface PairedOutcomeInput {
  task_id: string;
  seed: number;
  baseline_passed: boolean;
  candidate_passed: boolean;
}

export interface CompareResponse {
  n_pairs: number;
  n_concordant: number;
  baseline_only_passed: number;
  candidate_only_passed: number;
  p_value: number;
  significant: boolean;
  direction: "improved" | "regressed" | "no significant difference";
  promote: boolean;
  reason: string;
}

// Shape of a mined failure cluster, as produced by
// backend/app/mining/cluster.py::FailureCluster and surfaced through the
// Django back-office's PendingTask model before human approval.
export interface PendingReviewTask {
  id: number;
  external_id: string;
  name: string;
  category: string;
  instruction: string;
  check_command: string;
  origin_cluster_id: string | null;
  origin_cluster_size: number | null;
  origin_representative_summary: string | null;
  status: "pending" | "approved" | "rejected";
  reviewed_by: string | null;
  review_notes: string | null;
  created_at: string;
  reviewed_at: string | null;
}
