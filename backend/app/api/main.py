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

import os
import time
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

from fastapi import FastAPI, HTTPException, Depends, status, Request
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field, field_validator

from app.agent.graph import run_agent
from app.observability import metrics
from app.observability.langsmith_tracing import configure_tracing
from app.schemas.task import Task, Trial
from app.stats.significance import PairedOutcome, mcnemar_exact, should_promote

app = FastAPI(title="Agent Regression Flywheel API")

# Security: token-based authentication (configurable via API_TOKEN env var)
# If API_TOKEN is not set, authentication is disabled for local development
security = HTTPBearer(auto_error=False)

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify Bearer token if API_TOKEN is set. Returns credentials if valid."""
    api_token = os.environ.get("API_TOKEN")
    if not api_token:
        # No token configured - allow access for local development
        return None
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
        )
    if credentials.credentials != api_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )
    return credentials.credentials

# Simple in-memory rate limiter for agent run endpoint
# In production, use Redis-backed rate limiting
_rate_limit_store: dict[str, list[datetime]] = defaultdict(list)
_RATE_LIMIT_REQUESTS = 10
_RATE_LIMIT_WINDOW = timedelta(minutes=1)

def check_rate_limit(request: Request) -> None:
    """Simple in-memory rate limiter: 10 requests per minute per IP."""
    client_ip = request.client.host if request.client else "unknown"
    now = datetime.utcnow()
    
    # Clean old requests outside the window
    _rate_limit_store[client_ip] = [
        timestamp for timestamp in _rate_limit_store[client_ip]
        if now - timestamp < _RATE_LIMIT_WINDOW
    ]
    
    if len(_rate_limit_store[client_ip]) >= _RATE_LIMIT_REQUESTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: {_RATE_LIMIT_REQUESTS} requests per minute",
        )
    
    _rate_limit_store[client_ip].append(now)

# No-op without LANGCHAIN_API_KEY/LANGSMITH_API_KEY set — see
# observability/langsmith_tracing.py.
configure_tracing()


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
async def agent_run(req: AgentRunRequest, request: Request, token: str = Depends(verify_token)) -> AgentRunResponse:
    """The production agent entrypoint — runs the LangGraph agent on a
    live instruction. Every call is traced to LangSmith in production
    (see observability/langsmith_tracing.py); that trace stream is what
    the mining service in app/mining consumes. Duration and outcome are
    also recorded to Datadog (observability/metrics.py) as an
    operational metric, independent of the LangSmith trace."""
    check_rate_limit(request)
    started = time.perf_counter()
    result = run_agent(req.instruction, max_steps=req.max_steps)
    metrics.record_agent_run(duration_seconds=time.perf_counter() - started, status=result["status"])
    return AgentRunResponse(
        status=result["status"],
        observations=result["observations"],
        steps_taken=result["steps_taken"],
    )


# --- dashboard read API ---


@app.get("/tasks", response_model=list[Task])
async def list_tasks(token: str = Depends(verify_token)) -> list[Task]:
    return _task_repo.list_approved()


@app.get("/tasks/{task_id}", response_model=Task)
async def get_task(task_id: str, token: str = Depends(verify_token)) -> Task:
    task = _task_repo.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task


class PairedOutcomeInput(BaseModel):
    task_id: str
    seed: int = Field(ge=0, description="Non-negative seed for reproducibility")
    baseline_passed: bool
    candidate_passed: bool

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, v: str) -> str:
        try:
            UUID(v)
        except ValueError:
            raise ValueError("task_id must be a valid UUID")
        return v


class CompareRequest(BaseModel):
    baseline_version: str
    candidate_version: str
    pairs: list[PairedOutcomeInput]


class CompareResponse(BaseModel):
    n_pairs: int
    n_concordant: int
    baseline_only_passed: int
    candidate_only_passed: int
    p_value: float
    significant: bool
    direction: str
    promote: bool
    reason: str
    summary: str


@app.post("/runs/compare", response_model=CompareResponse)
async def compare_versions(req: CompareRequest, token: str = Depends(verify_token)) -> CompareResponse:
    """The promotion-decision endpoint the dashboard's version-comparison
    view calls — this is where the statistical significance gate (not a
    raw pass-rate diff) actually decides whether a candidate is promotable."""
    outcomes = [
        PairedOutcome(
            task_id=p.task_id,
            seed=p.seed,
            baseline_passed=p.baseline_passed,
            candidate_passed=p.candidate_passed,
        )
        for p in req.pairs
    ]
    if not outcomes:
        raise HTTPException(status_code=400, detail="at least one paired outcome is required")
    result = mcnemar_exact(outcomes)
    promote, reason = should_promote(result)
    metrics.record_regression_run(n_pairs=result.n_pairs, p_value=result.p_value, promoted=promote)
    return CompareResponse(
        n_pairs=result.n_pairs,
        n_concordant=result.n_concordant,
        baseline_only_passed=result.baseline_only_passed,
        candidate_only_passed=result.candidate_only_passed,
        p_value=result.p_value,
        significant=result.significant,
        direction=result.direction,
        promote=promote,
        reason=reason,
        summary=result.summary(),
    )


@app.get("/health")
async def health() -> dict:
    """Health check that verifies system status."""
    health_status = {"status": "ok", "checks": {}}
    
    # Check if API token is configured
    api_token = os.environ.get("API_TOKEN")
    health_status["checks"]["authentication"] = "configured" if api_token else "disabled"
    
    # Check database if DATABASE_URL is set
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        health_status["checks"]["database"] = "configured"
        # In production, would actually test the connection
        # For now, just check it's set
    else:
        health_status["checks"]["database"] = "not configured"
    
    return health_status
