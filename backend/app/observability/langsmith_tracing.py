"""LangSmith tracing for the LangGraph agent (app/agent/graph.py).

LangSmith's tracing is enabled by environment variables alone
(LANGCHAIN_TRACING_V2, LANGCHAIN_API_KEY, LANGCHAIN_PROJECT) — LangGraph
and LangChain's runnables pick them up automatically with no code change
to graph.py, so there's nothing to wrap there. What this module owns is
the other half: making the project name configurable per environment and
giving the mining service a typed way to pull recent traces out of
LangSmith for mining/cluster.py to consume, instead of each caller
reaching for the raw LangSmith SDK and guessing at the run schema.

Like every other external integration in this backend (LLMClient,
SnowflakeTraceStore, get_sandbox_runner), this has a live path gated on
an API key and a deterministic offline fallback — here, an empty list
rather than fabricated trace data, since "no traces available" is a
legitimate and distinguishable state for the mining worker to see.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def configure_tracing(project: str = "agent-regression-flywheel") -> bool:
    """Call once at process startup (before any LangGraph agent runs) to
    turn on LangSmith tracing for this run, if LANGCHAIN_API_KEY is set.
    Returns whether tracing was actually enabled."""
    api_key = os.environ.get("LANGCHAIN_API_KEY") or os.environ.get("LANGSMITH_API_KEY")
    if not api_key:
        return False
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ.setdefault("LANGCHAIN_PROJECT", project)
    if "LANGCHAIN_API_KEY" not in os.environ:
        os.environ["LANGCHAIN_API_KEY"] = api_key
    return True


@dataclass
class RecentRun:
    run_id: str
    trace_url: str
    status: str  # "success" | "error"
    error: str | None


def fetch_recent_failed_runs(project: str, hours: int, limit: int = 200) -> list[RecentRun]:
    """The feed that would populate the mining service's trace queue in
    production: pulls recently-errored LangGraph runs out of LangSmith so
    app/mining/cluster.py has real failure summaries to cluster, instead
    of this project's offline TraceSummary fixtures. Returns [] (not an
    exception) when LangSmith isn't configured, so the mining worker can
    run against its Snowflake/DuckDB-backed queue alone without this
    being wired up."""
    api_key = os.environ.get("LANGCHAIN_API_KEY") or os.environ.get("LANGSMITH_API_KEY")
    if not api_key:
        return []

    try:
        from langsmith import Client
    except ImportError:
        return []

    client = Client(api_key=api_key)
    runs = client.list_runs(
        project_name=project,
        error=True,
        limit=limit,
    )
    results = []
    for run in runs:
        results.append(
            RecentRun(
                run_id=str(run.id),
                trace_url=client.get_run_url(run) if hasattr(client, "get_run_url") else "",
                status="error",
                error=str(getattr(run, "error", None)),
            )
        )
    return results
