"""FastAPI service: the agent-facing API and the dashboard's read API.

Both are latency-sensitive and benefit from async, which is why they live
here rather than in the Django back-office (see django_admin/ for the
task-approval/CRUD side, which is the opposite trade-off: infrequent,
form-heavy, benefits from Django admin instead of hand-rolled React forms).

In-memory stores are used here so the service is runnable and testable
without a live Postgres instance; swapping in the real SQLAlchemy session
from models/orm.py is a drop-in change at the repository boundary (see
`TaskRepository` / `RunRepository` below — the FastAPI routes only depend
on that interface, not on in-memory dicts specifically).
"""
from __future__ import annotations

import uuid
from typing import Protocol

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.agent.graph import run_agent
from app.schemas.task import Task, Trial
from app.stats.significance import PairedOutcome, mcnemar_exact, should_promote

app = FastAPI(title="Agent Regression Flywheel API")


# --- repository interfaces (swap for Postgres-backed impls in production) ---


class TaskRepository(Protocol):
    def list_approved(self) -> list[Task]: ...
    def get(self, task_id: str) -> Task | None: ...
    def add(self, task: Task) -> Task: ...


class InMemoryTaskRepository:
    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}

    def list_approved(self) -> list[Task]:
        return [t for t in self._tasks.values() if t.approved]

    def get(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def add(self, task: Task) -> Task:
        self._tasks[str(task.id)] = task
        return task


_task_repo = InMemoryTaskRepository()
_trials: dict[str, Trial] = {}


# --- agent-facing API ---


class AgentRunRequest(BaseModel):
    instruction: str
    max_steps: int = 10


class AgentRunResponse(BaseModel):
    status: str
    observations: list[str]
    steps_taken: int


@app.post("/agent/run", response_model=AgentRunResponse)
def agent_run(req: AgentRunRequest) -> AgentRunResponse:
    """The production agent entrypoint — runs the LangGraph agent on a
    live instruction. Every call is traced to LangSmith in production
    (see observability/langsmith_tracing.py); that trace stream is what
    the mining service in app/mining consumes."""
    result = run_agent(req.instruction, max_steps=req.max_steps)
    return AgentRunResponse(
        status=result["status"],
        observations=result["observations"],
        steps_taken=result["steps_taken"],
    )


# --- dashboard read API ---


@app.get("/tasks", response_model=list[Task])
def list_tasks() -> list[Task]:
    return _task_repo.list_approved()


@app.get("/tasks/{task_id}", response_model=Task)
def get_task(task_id: str) -> Task:
    task = _task_repo.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task


class CompareRequest(BaseModel):
    baseline_version: str
    candidate_version: str
    pairs: list[dict]  # [{task_id, seed, baseline_passed, candidate_passed}, ...]


class CompareResponse(BaseModel):
    p_value: float
    significant: bool
    direction: str
    promote: bool
    reason: str
    summary: str


@app.post("/runs/compare", response_model=CompareResponse)
def compare_versions(req: CompareRequest) -> CompareResponse:
    """The promotion-decision endpoint the dashboard's version-comparison
    view calls — this is where the statistical significance gate (not a
    raw pass-rate diff) actually decides whether a candidate is promotable."""
    outcomes = [
        PairedOutcome(
            task_id=p["task_id"],
            seed=p["seed"],
            baseline_passed=p["baseline_passed"],
            candidate_passed=p["candidate_passed"],
        )
        for p in req.pairs
    ]
    if not outcomes:
        raise HTTPException(status_code=400, detail="at least one paired outcome is required")
    result = mcnemar_exact(outcomes)
    promote, reason = should_promote(result)
    return CompareResponse(
        p_value=result.p_value,
        significant=result.significant,
        direction=result.direction,
        promote=promote,
        reason=reason,
        summary=result.summary(),
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
