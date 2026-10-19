"""Entry point for the mining-service Kubernetes deployment
(k8s/11-mining-service.yaml): drains queued trace IDs from Redis, looks
up their summaries in the trace store, clusters the batch with
app.mining.cluster.cluster_failures, and promotes clusters past the size
threshold into the environment registry as candidate regression tasks.

The actual network I/O (Redis, the trace store) is pushed to the edges via
small Protocols, so the core loop (`drain_and_cluster`) is a plain function
over in-memory data and is fully unit-testable without a live Redis or
DuckDB/Snowflake connection — the same shape as run_trial_activity in
workflows/regression_run.py.
"""
from __future__ import annotations

import logging
import time
from typing import Protocol

from app.mining.cluster import FailureCluster, TraceSummary, cluster_failures
from app.registry.environment_registry import EnvironmentRegistry

logger = logging.getLogger("mining_worker")


class TraceQueue(Protocol):
    def dequeue_batch(self, batch_size: int = 100) -> list[str]: ...
    def queue_depth(self) -> int: ...


class TraceLookup(Protocol):
    def summaries_for(self, trace_ids: list[str]) -> list[TraceSummary]: ...


def drain_and_cluster(
    queue: TraceQueue,
    lookup: TraceLookup,
    registry: EnvironmentRegistry,
    batch_size: int = 100,
    min_cluster_size: int = 3,
    promote_threshold: int = 5,
) -> list[FailureCluster]:
    """Pulls one batch off the queue, clusters it, and promotes clusters
    at or above `promote_threshold` into the registry as pending tasks
    (approved=False — still requires human review via the Django
    back-office before entering the regression suite). Returns every
    cluster found in this batch, promoted or not, for observability."""
    trace_ids = queue.dequeue_batch(batch_size)
    if not trace_ids:
        return []

    traces = lookup.summaries_for(trace_ids)
    clusters = cluster_failures(traces, min_cluster_size=min_cluster_size)

    registry.promote_clusters(clusters, size_threshold=promote_threshold)
    return clusters


def run_forever(
    queue: TraceQueue,
    lookup: TraceLookup,
    registry: EnvironmentRegistry,
    poll_interval_seconds: float = 5.0,
) -> None:  # pragma: no cover - thin I/O loop, exercised via drain_and_cluster
    logger.info("mining worker started, polling every %.1fs", poll_interval_seconds)
    while True:
        clusters = drain_and_cluster(queue, lookup, registry)
        if clusters:
            logger.info("clustered batch into %d failure cluster(s)", len(clusters))
        else:
            logger.debug("queue empty (depth=%d), sleeping", queue.queue_depth())
        time.sleep(poll_interval_seconds)


if __name__ == "__main__":  # pragma: no cover
    import os

    from app.models.queue import RedisQueue

    logging.basicConfig(level=logging.INFO)

    class _DuckDBLookup:
        """Minimal adapter wiring the DuckDB trace store into the
        TraceLookup protocol above, for local/dev runs. A real deployment
        would read through the Snowflake-backed path once the mining
        pipeline is promoted to run against full production history."""

        def __init__(self, store) -> None:
            self._store = store

        def summaries_for(self, trace_ids: list[str]) -> list[TraceSummary]:
            records = self._store.query_recent(hours=24 * 7, limit=len(trace_ids) * 2)
            by_id = {r.trace_id: r for r in records}
            missing_ids = set(trace_ids) - set(by_id.keys())
            if missing_ids:
                logger.warning(f"Skipping {len(missing_ids)} trace IDs not found in trace store: {missing_ids}")
            return [
                TraceSummary(trace_id=tid, summary=by_id[tid].summary, agent_version=by_id[tid].agent_version)
                for tid in trace_ids
                if tid in by_id
            ]

    from app.models.analytics_store import DuckDBTraceStore

    redis_url = f"redis://{os.environ.get('REDIS_HOST', 'localhost')}:6379/0"
    run_forever(
        queue=RedisQueue(redis_url),
        lookup=_DuckDBLookup(DuckDBTraceStore()),
        registry=EnvironmentRegistry(),
    )
