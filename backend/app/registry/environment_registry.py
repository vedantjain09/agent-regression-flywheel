"""Environment registry, shaped after NeMo-Gym's separation of concerns:
dataset (what tasks exist) / harness (how the agent acts) / verifier (how a
run is scored) / state (per-task execution context).

The registry has two ways tasks enter it: hand-written (checked in, always
approved) and auto-generated from a FailureCluster (unapproved until a
human reviews it in the Django back-office — see backend/django_admin).
Keeping both paths unified under one registry means the regression runner
in workflows/ doesn't need to know or care where a task came from.
"""
from __future__ import annotations

from datetime import datetime

from app.mining.cluster import FailureCluster
from app.schemas.task import (
    DeterministicVerifierSpec,
    EnvironmentSpec,
    FailureClusterOrigin,
    Task,
)


class EnvironmentRegistry:
    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}

    def register(self, task: Task) -> Task:
        self._tasks[str(task.id)] = task
        return task

    def get(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def list_approved(self) -> list[Task]:
        return [t for t in self._tasks.values() if t.approved]

    def list_pending_review(self) -> list[Task]:
        return [t for t in self._tasks.values() if not t.approved]

    def approve(self, task_id: str) -> Task:
        task = self._tasks[task_id]
        task.approved = True
        return task

    def task_from_failure_cluster(
        self,
        cluster: FailureCluster,
        check_command: str,
        instruction: str | None = None,
    ) -> Task:
        """Converts a mined FailureCluster into a Harbor-style Task. The
        verifier defaults to a deterministic check_command the on-call
        engineer supplies when reviewing the cluster (e.g. "the agent's
        output file must contain X"); more sophisticated clusters can be
        promoted with an LLMJudgeVerifierSpec instead by constructing the
        Task directly and calling register().
        """
        origin = FailureClusterOrigin(
            cluster_id=cluster.cluster_id,
            source_trace_ids=cluster.trace_ids,
            discovered_at=cluster.discovered_at,
            cluster_size=cluster.size,
            representative_summary=cluster.representative_summary,
        )
        task = Task(
            name=f"auto-{cluster.cluster_id}",
            category="auto-generated",
            instruction=instruction or f"Reproduce and resolve: {cluster.representative_summary}",
            environment=EnvironmentSpec(),
            verifier=DeterministicVerifierSpec(check_command=check_command),
            origin=origin,
            approved=False,
        )
        return self.register(task)

    def promote_clusters(
        self,
        clusters: list[FailureCluster],
        size_threshold: int,
        default_check_command: str = "true",
    ) -> list[Task]:
        """Only clusters at or above size_threshold get auto-filed as
        pending-review tasks — small clusters are logged (see
        FailureClusterRow in models/orm.py) but not promoted, since a
        cluster of 3 near the HDBSCAN min_cluster_size floor is much
        weaker evidence of a real recurring failure mode than one of 30."""
        promoted = []
        for cluster in clusters:
            if cluster.size >= size_threshold:
                promoted.append(self.task_from_failure_cluster(cluster, default_check_command))
        return promoted
