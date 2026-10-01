"""Tests for the mining-service worker loop (app/mining/worker.py), the
process Kubernetes runs as the `mining-service` deployment
(k8s/11-mining-service.yaml). Uses fake in-memory queue/lookup
implementations satisfying the TraceQueue/TraceLookup protocols so the
clustering-and-promotion loop is tested without a live Redis or trace
store, same pattern as the Modal/Temporal fakes in test_workflows.py."""
from __future__ import annotations

from app.mining.cluster import TraceSummary
from app.mining.worker import drain_and_cluster
from app.registry.environment_registry import EnvironmentRegistry


class FakeQueue:
    def __init__(self, trace_ids: list[str]) -> None:
        self._ids = list(trace_ids)

    def dequeue_batch(self, batch_size: int = 100) -> list[str]:
        batch, self._ids = self._ids[:batch_size], self._ids[batch_size:]
        return batch

    def queue_depth(self) -> int:
        return len(self._ids)


class FakeLookup:
    def __init__(self, traces: dict[str, TraceSummary]) -> None:
        self._traces = traces

    def summaries_for(self, trace_ids: list[str]) -> list[TraceSummary]:
        return [self._traces[t] for t in trace_ids if t in self._traces]


_TIMEOUT_PHRASES = [
    "agent timed out reading a large file over 100MB",
    "read_file timed out on a large input file",
    "agent exceeded timeout while reading a big file from disk",
    "large file read operation timed out after 30 seconds",
    "timeout occurred while the agent read a very large file",
    "agent read_file call timed out on an oversized file",
    "reading a big input file caused the agent to time out",
    "large file read exceeded the configured timeout threshold",
    "agent hit a timeout trying to read a huge file",
    "file read timed out because the input file was too large",
]

_AUTH_PHRASES = [
    "agent received 401 unauthorized calling the internal API",
    "tool call failed with 401 unauthorized error from auth service",
    "authentication failed, 401 returned by internal API client",
]


def _timeout_traces(n: int) -> dict[str, TraceSummary]:
    """n timeout-cluster traces plus a fixed 3-trace auth-cluster group.

    HDBSCAN's density estimate needs more than one group in the batch to
    find structure at all — a single homogeneous group with nothing to
    contrast against gets labelled noise even when every point is
    near-identical (verified directly against cluster_failures). Every
    real caller of this worker processes a mixed batch of multiple
    failure modes, so the auth-cluster traces here aren't a test
    artifact — they're normal input, just traces we don't assert on."""
    traces: dict[str, TraceSummary] = {
        f"tr_{i}": TraceSummary(trace_id=f"tr_{i}", summary=_TIMEOUT_PHRASES[i], agent_version="v1")
        for i in range(n)
    }
    traces.update(
        {
            f"au_{i}": TraceSummary(trace_id=f"au_{i}", summary=phrase, agent_version="v1")
            for i, phrase in enumerate(_AUTH_PHRASES)
        }
    )
    return traces


def test_drain_and_cluster_returns_empty_list_when_queue_is_empty():
    registry = EnvironmentRegistry()
    clusters = drain_and_cluster(FakeQueue([]), FakeLookup({}), registry)
    assert clusters == []


def test_drain_and_cluster_discovers_and_promotes_cluster_above_threshold():
    # 6 timeout traces + 3 auth traces: two clusters found, only the
    # larger (size 6) clears promote_threshold=5.
    traces = _timeout_traces(6)
    queue = FakeQueue(list(traces.keys()))
    registry = EnvironmentRegistry()

    clusters = drain_and_cluster(
        queue, FakeLookup(traces), registry, min_cluster_size=3, promote_threshold=5,
    )

    assert len(clusters) == 2
    sizes = sorted(c.size for c in clusters)
    assert sizes == [3, 6]
    promoted = registry.list_pending_review()
    assert len(promoted) == 1
    assert promoted[0].origin is not None
    assert promoted[0].origin.cluster_size == 6
    assert promoted[0].approved is False


def test_drain_and_cluster_does_not_promote_below_threshold():
    # 3 timeout traces + 3 auth traces: both clusters are size 3, neither
    # clears promote_threshold=5, so nothing enters the review queue.
    # (min_cluster_size=2 here, not 3 — HDBSCAN needs a little more slack
    # to resolve two size-3 clusters out of only 6 points total; see the
    # module docstring on _timeout_traces for why a contrast group is
    # needed in the first place.)
    traces = _timeout_traces(3)
    queue = FakeQueue(list(traces.keys()))
    registry = EnvironmentRegistry()

    clusters = drain_and_cluster(
        queue, FakeLookup(traces), registry, min_cluster_size=2, promote_threshold=5,
    )

    assert len(clusters) == 2
    assert all(c.size == 3 for c in clusters)
    assert registry.list_pending_review() == []


def test_drain_and_cluster_respects_batch_size_leaving_remainder_queued():
    traces = _timeout_traces(10)  # 10 timeout + 3 auth = 13 total
    queue = FakeQueue(list(traces.keys()))
    registry = EnvironmentRegistry()

    drain_and_cluster(queue, FakeLookup(traces), registry, batch_size=4, min_cluster_size=2, promote_threshold=100)

    assert queue.queue_depth() == 9


def test_drain_and_cluster_skips_trace_ids_missing_from_lookup():
    traces = _timeout_traces(5)  # 5 timeout + 3 auth = 8 known traces
    queue = FakeQueue(list(traces.keys()) + ["tr_missing"])
    registry = EnvironmentRegistry()

    clusters = drain_and_cluster(queue, FakeLookup(traces), registry, min_cluster_size=3, promote_threshold=100)

    # the missing trace is silently dropped by FakeLookup, not an error
    assert sum(c.size for c in clusters) <= 8
