// Thin typed client over the two live backends (FastAPI for agent-facing /
// dashboard-read paths, Django/DRF for the back-office review queue). Every
// function here has a real fetch call against the live service; if the
// service isn't reachable (no NEXT_PUBLIC_FASTAPI_BASE configured, or the
// request errors/times out), it falls back to the fixtures in demo-data.ts
// so the dashboard still renders a representative view instead of an error
// page. This is the same live/fallback split used throughout the backend.

import {
  DEMO_APPROVED_TASKS,
  DEMO_COMPARE_RESULT,
  DEMO_PENDING_REVIEW,
} from "./demo-data";
import type {
  CompareResponse,
  PairedOutcomeInput,
  PendingReviewTask,
  Task,
} from "./types";

const FASTAPI_BASE = process.env.NEXT_PUBLIC_FASTAPI_BASE ?? "";
const DJANGO_BASE = process.env.NEXT_PUBLIC_DJANGO_BASE ?? "";
const FETCH_TIMEOUT_MS = 2500;

async function fetchWithTimeout(url: string, init?: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    return await fetch(url, { ...init, signal: controller.signal, cache: "no-store" });
  } finally {
    clearTimeout(timer);
  }
}

export async function getApprovedTasks(): Promise<{ tasks: Task[]; live: boolean }> {
  if (!FASTAPI_BASE) return { tasks: DEMO_APPROVED_TASKS, live: false };
  try {
    const res = await fetchWithTimeout(`${FASTAPI_BASE}/tasks`);
    if (!res.ok) throw new Error(`FastAPI /tasks returned ${res.status}`);
    return { tasks: await res.json(), live: true };
  } catch {
    return { tasks: DEMO_APPROVED_TASKS, live: false };
  }
}

export async function getPendingReview(): Promise<{ tasks: PendingReviewTask[]; live: boolean }> {
  if (!DJANGO_BASE) return { tasks: DEMO_PENDING_REVIEW, live: false };
  try {
    const res = await fetchWithTimeout(`${DJANGO_BASE}/api/pending-tasks/`);
    if (!res.ok) throw new Error(`Django /api/pending-tasks/ returned ${res.status}`);
    const body = await res.json();
    return { tasks: Array.isArray(body) ? body : body.results, live: true };
  } catch {
    return { tasks: DEMO_PENDING_REVIEW, live: false };
  }
}

export async function approvePendingTask(
  id: number,
  reviewedBy: string,
  notes: string,
): Promise<PendingReviewTask | null> {
  if (!DJANGO_BASE) return null;
  const res = await fetchWithTimeout(`${DJANGO_BASE}/api/pending-tasks/${id}/approve/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reviewed_by: reviewedBy, notes }),
  });
  if (!res.ok) throw new Error(`approve failed: ${res.status}`);
  return res.json();
}

export async function rejectPendingTask(
  id: number,
  reviewedBy: string,
  notes: string,
): Promise<PendingReviewTask | null> {
  if (!DJANGO_BASE) return null;
  const res = await fetchWithTimeout(`${DJANGO_BASE}/api/pending-tasks/${id}/reject/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reviewed_by: reviewedBy, notes }),
  });
  if (!res.ok) throw new Error(`reject failed: ${res.status}`);
  return res.json();
}

export async function compareVersions(
  baselineVersion: string,
  candidateVersion: string,
  pairs: PairedOutcomeInput[],
): Promise<{ result: CompareResponse; live: boolean }> {
  if (!FASTAPI_BASE) return { result: DEMO_COMPARE_RESULT, live: false };
  try {
    const res = await fetchWithTimeout(`${FASTAPI_BASE}/runs/compare`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        baseline_version: baselineVersion,
        candidate_version: candidateVersion,
        pairs,
      }),
    });
    if (!res.ok) throw new Error(`FastAPI /runs/compare returned ${res.status}`);
    return { result: await res.json(), live: true };
  } catch {
    return { result: DEMO_COMPARE_RESULT, live: false };
  }
}
