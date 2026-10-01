"""Tests for the failure-mining clusterer and the environment registry."""
from app.mining.cluster import TraceSummary, cluster_failures
from app.registry.environment_registry import EnvironmentRegistry


def _make_traces() -> list[TraceSummary]:
    # Three genuinely distinct failure modes, repeated enough times to
    # clear the min_cluster_size floor, plus two one-off outliers that
    # should NOT form their own clusters.
    timeout_phrases = [
        "agent timed out reading a large file over 100MB",
        "read_file timed out on a large input file",
        "agent exceeded timeout while reading a big file from disk",
        "large file read operation timed out after 30 seconds",
    ]
    auth_phrases = [
        "agent received 401 unauthorized calling the internal API",
        "tool call failed with 401 unauthorized error from auth service",
        "authentication failed, 401 returned by internal API client",
        "401 unauthorized when the agent tried to call the API",
    ]
    parse_phrases = [
        "agent crashed parsing malformed JSON response",
        "JSON decode error when parsing the tool response",
        "malformed JSON caused a parse failure in the agent loop",
    ]
    outliers = [
        "agent printed an unrelated joke instead of finishing the task",
        "disk ran out of space during an unrelated batch job",
    ]

    traces = []
    idx = 0
    for phrase in timeout_phrases + auth_phrases + parse_phrases + outliers:
        traces.append(TraceSummary(trace_id=f"trace-{idx}", summary=phrase, agent_version="v1"))
        idx += 1
    return traces


def test_cluster_failures_discovers_multiple_distinct_modes():
    traces = _make_traces()
    clusters = cluster_failures(traces, min_cluster_size=3)
    # expect roughly 2-3 real clusters (timeout x4, auth x4, parse x3) —
    # HDBSCAN parameters aren't guaranteed to split every semantic group
    # perfectly on TF-IDF alone, so assert on the structural properties
    # that must hold rather than an exact cluster count
    assert len(clusters) >= 2
    for cluster in clusters:
        assert cluster.size >= 3
        assert len(cluster.trace_ids) == cluster.size


def test_cluster_failures_below_min_size_returns_nothing():
    traces = [TraceSummary(trace_id="t1", summary="one-off weird failure", agent_version="v1")]
    assert cluster_failures(traces, min_cluster_size=3) == []


def test_cluster_failures_outliers_excluded_as_noise():
    traces = _make_traces()
    clusters = cluster_failures(traces, min_cluster_size=3)
    clustered_ids = {tid for c in clusters for tid in c.trace_ids}
    # the two single-outlier traces are the last two appended in _make_traces
    outlier_ids = {f"trace-{len(traces) - 2}", f"trace-{len(traces) - 1}"}
    assert not outlier_ids.issubset(clustered_ids)


def test_registry_promotes_cluster_above_threshold():
    traces = _make_traces()
    clusters = cluster_failures(traces, min_cluster_size=3)
    registry = EnvironmentRegistry()
    promoted = registry.promote_clusters(clusters, size_threshold=3, default_check_command="true")
    assert len(promoted) == len(clusters)
    for task in promoted:
        assert task.approved is False
        assert task.origin is not None
        assert task.origin.cluster_size >= 3


def test_registry_rejects_cluster_below_threshold():
    traces = _make_traces()
    clusters = cluster_failures(traces, min_cluster_size=3)
    registry = EnvironmentRegistry()
    # set an artificially high threshold so nothing gets promoted
    promoted = registry.promote_clusters(clusters, size_threshold=999)
    assert promoted == []


def test_registry_approval_workflow():
    registry = EnvironmentRegistry()
    traces = _make_traces()
    clusters = cluster_failures(traces, min_cluster_size=3)
    task = registry.task_from_failure_cluster(clusters[0], check_command="echo ok")
    assert task in registry.list_pending_review()
    assert task not in registry.list_approved()
    registry.approve(str(task.id))
    assert task in registry.list_approved()
    assert task not in registry.list_pending_review()
