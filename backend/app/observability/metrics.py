"""Datadog metrics + PostHog product events for the flywheel.

Split by audience, not by vendor: Datadog gets operational metrics (is the
system healthy, how long do regression runs take, what's the mining
pipeline's throughput) for on-call and dashboards; PostHog gets product
events (who approved what, how often does promotion happen, what's the
engineer-review funnel look like) for the kind of usage analysis that
app/page.tsx's "Mining Funnel" view is a manual, in-app version of.

Same live/no-op split as every other external integration in this
backend: both clients are lazily constructed and silently no-op when
their API key isn't set, so none of the call sites (agent runner,
mining worker, regression workflow, dashboard API) need to branch on
whether observability is configured.
"""
from __future__ import annotations

import os
from typing import Any


class _NoOpStatsd:
    def increment(self, *a: Any, **k: Any) -> None: ...
    def gauge(self, *a: Any, **k: Any) -> None: ...
    def histogram(self, *a: Any, **k: Any) -> None: ...


class _NoOpPostHog:
    def capture(self, *a: Any, **k: Any) -> None: ...


def _build_statsd():
    if not os.environ.get("DATADOG_API_KEY"):
        return _NoOpStatsd()
    try:
        from datadog import initialize, statsd

        initialize(api_key=os.environ["DATADOG_API_KEY"], app_key=os.environ.get("DATADOG_APP_KEY"))
        return statsd
    except ImportError:
        return _NoOpStatsd()


def _build_posthog():
    api_key = os.environ.get("POSTHOG_API_KEY")
    if not api_key:
        return _NoOpPostHog()
    try:
        import posthog

        posthog.api_key = api_key
        posthog.host = os.environ.get("POSTHOG_HOST", "https://app.posthog.com")
        return posthog
    except ImportError:
        return _NoOpPostHog()


_statsd = _build_statsd()
_posthog = _build_posthog()


def is_live() -> dict[str, bool]:
    return {
        "datadog": not isinstance(_statsd, _NoOpStatsd),
        "posthog": not isinstance(_posthog, _NoOpPostHog),
    }


# --- operational metrics (Datadog) ---


def record_agent_run(duration_seconds: float, status: str) -> None:
    _statsd.histogram("flywheel.agent_run.duration_seconds", duration_seconds, tags=[f"status:{status}"])
    _statsd.increment("flywheel.agent_run.count", tags=[f"status:{status}"])


def record_mining_batch(batch_size: int, clusters_found: int, clusters_promoted: int) -> None:
    _statsd.gauge("flywheel.mining.batch_size", batch_size)
    _statsd.gauge("flywheel.mining.clusters_found", clusters_found)
    _statsd.increment("flywheel.mining.clusters_promoted", clusters_promoted)


def record_regression_run(n_pairs: int, p_value: float, promoted: bool) -> None:
    _statsd.gauge("flywheel.regression_run.n_pairs", n_pairs)
    _statsd.gauge("flywheel.regression_run.p_value", p_value)
    _statsd.increment("flywheel.regression_run.count", tags=[f"promoted:{promoted}"])


# --- product events (PostHog) ---


def track_task_reviewed(reviewer: str, task_id: str, decision: str) -> None:
    _posthog.capture(distinct_id=reviewer, event="flywheel_task_reviewed", properties={"task_id": task_id, "decision": decision})


def track_version_compared(user: str, baseline: str, candidate: str, promote: bool) -> None:
    _posthog.capture(
        distinct_id=user,
        event="flywheel_version_compared",
        properties={"baseline": baseline, "candidate": candidate, "promote": promote},
    )
