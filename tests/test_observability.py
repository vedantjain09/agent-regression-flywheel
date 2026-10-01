"""Tests for the observability layer (app/observability/metrics.py and
langsmith_tracing.py). This sandbox has no DATADOG_API_KEY, POSTHOG_API_KEY,
or LANGCHAIN_API_KEY set, so these tests exercise the real no-op fallback
path — the same path a developer running the backend locally without those
keys actually hits. That's a legitimate, important code path to test, not
a placeholder: every call site (FastAPI, Django, the mining worker) calls
these functions unconditionally and must not raise or block when
observability isn't configured."""
from __future__ import annotations

import importlib
import os

import pytest


@pytest.fixture
def metrics_module(monkeypatch):
    # Reload fresh each test so DATADOG_API_KEY / POSTHOG_API_KEY changes
    # in one test don't leak into the next via the module-level singletons.
    for key in ("DATADOG_API_KEY", "DATADOG_APP_KEY", "POSTHOG_API_KEY", "POSTHOG_HOST"):
        monkeypatch.delenv(key, raising=False)
    from app.observability import metrics

    return importlib.reload(metrics)


def test_is_live_reports_false_when_no_keys_configured(metrics_module):
    assert metrics_module.is_live() == {"datadog": False, "posthog": False}


def test_record_agent_run_does_not_raise_without_datadog_key(metrics_module):
    metrics_module.record_agent_run(duration_seconds=1.23, status="finished")


def test_record_mining_batch_does_not_raise_without_datadog_key(metrics_module):
    metrics_module.record_mining_batch(batch_size=50, clusters_found=3, clusters_promoted=1)


def test_record_regression_run_does_not_raise_without_datadog_key(metrics_module):
    metrics_module.record_regression_run(n_pairs=40, p_value=0.0123, promoted=True)


def test_track_task_reviewed_does_not_raise_without_posthog_key(metrics_module):
    metrics_module.track_task_reviewed(reviewer="vedant", task_id="t-1", decision="approved")


def test_track_version_compared_does_not_raise_without_posthog_key(metrics_module):
    metrics_module.track_version_compared(user="vedant", baseline="v1", candidate="v2", promote=True)


def test_configure_tracing_returns_false_without_api_key(monkeypatch):
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    from app.observability.langsmith_tracing import configure_tracing

    assert configure_tracing() is False
    assert os.environ.get("LANGCHAIN_TRACING_V2") != "true"


def test_configure_tracing_sets_env_vars_when_key_present(monkeypatch):
    monkeypatch.setenv("LANGCHAIN_API_KEY", "fake-key-for-test")
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    monkeypatch.delenv("LANGCHAIN_PROJECT", raising=False)
    from app.observability.langsmith_tracing import configure_tracing

    enabled = configure_tracing(project="test-project")

    assert enabled is True
    assert os.environ["LANGCHAIN_TRACING_V2"] == "true"
    assert os.environ["LANGCHAIN_PROJECT"] == "test-project"


def test_fetch_recent_failed_runs_returns_empty_without_api_key(monkeypatch):
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    from app.observability.langsmith_tracing import fetch_recent_failed_runs

    assert fetch_recent_failed_runs(project="test-project", hours=24) == []
