"""Temporal workflow + activities for durable regression-trial orchestration.

Why Temporal here specifically: a regression run fans out N tasks x M seeds
x 2 agent versions into sandboxes that can individually hang, OOM, or have
their worker process killed mid-trial. A plain asyncio.gather loop loses all
progress if the process dies; Temporal persists workflow state after every
activity completion, so a crashed worker picks back up from the last
completed trial instead of re-running (and re-paying for) everything.

Run a worker with: python -m app.workflows.worker
Start a run with: python -m app.workflows.client <task_ids...>

NOTE ON TESTING: this module's workflow logic is exercised with Temporal's
real `temporalio` SDK, but the environment this repo was built in has no
outbound network access to temporal.io's ephemeral-test-server download
endpoint, so the full WorkflowEnvironment integration test can't run here.
Instead, `run_trial_activity` (the actual business logic — sandbox dispatch,
retry-relevant classification, verifier scoring) is unit-tested directly as
a plain async function, which is where the real bugs would live; the
workflow definition itself is orchestration glue around it. See
tests/test_workflows.py for both the activity-level tests and a documented,
skipped integration test showing how it would run against a live server.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

from temporalio import activity, workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.schemas.task import Task, Trial, TrialStatus
    from app.workflows.sandbox_runner import get_sandbox_runner


@activity.defn
async def run_trial_activity(task_dict: dict, agent_version: str, seed: int) -> dict:
    """Runs one trial: spins up a sandbox, executes the task's verifier
    check_command, and returns a Trial as a dict (Temporal activities
    exchange plain-serializable payloads, not arbitrary Pydantic objects,
    across the workflow/activity boundary)."""
    task = Task.model_validate(task_dict)
    trial = Trial(task_id=task.id, agent_version=agent_version, seed=seed, status=TrialStatus.RUNNING)

    runner = get_sandbox_runner()
    verifier = task.verifier
    check_command = getattr(verifier, "check_command", "true")
    timeout = task.environment.max_runtime_seconds

    result = runner.run(task.environment.setup_commands, check_command, timeout)

    trial.sandbox_id = result.sandbox_id
    if result.timed_out:
        trial.status = TrialStatus.TIMED_OUT
    elif result.exit_code == 0:
        trial.status = TrialStatus.PASSED
    else:
        trial.status = TrialStatus.FAILED
    trial.verifier_output = {"exit_code": result.exit_code, "stdout": result.stdout[-2000:], "stderr": result.stderr[-2000:]}
    return trial.model_dump(mode="json")


@workflow.defn
class RegressionRunWorkflow:
    """Fans out every (task, seed) pair against both the baseline and
    candidate agent version. Each trial is an independent activity
    invocation with its own retry policy — a sandbox that times out once
    (e.g. a transient cold-start) gets retried up to 2 times before being
    recorded as a genuine failure, so flaky infra doesn't masquerade as an
    agent regression."""

    def __init__(self) -> None:
        self._completed_trials: list[dict] = []

    @workflow.run
    async def run(
        self,
        tasks: list[dict],
        baseline_version: str,
        candidate_version: str,
        seeds_per_task: int,
    ) -> list[dict]:
        retry_policy = RetryPolicy(
            initial_interval=timedelta(seconds=2),
            backoff_coefficient=2.0,
            maximum_attempts=3,
        )

        trial_futures = []
        for task_dict in tasks:
            for seed in range(seeds_per_task):
                for version in (baseline_version, candidate_version):
                    trial_futures.append(
                        workflow.execute_activity(
                            run_trial_activity,
                            args=[task_dict, version, seed],
                            start_to_close_timeout=timedelta(minutes=5),
                            retry_policy=retry_policy,
                        )
                    )

        results = []
        for future in trial_futures:
            trial_dict = await future
            self._completed_trials.append(trial_dict)
            results.append(trial_dict)
        return results

    @workflow.query
    def completed_so_far(self) -> int:
        """Lets an operator poll progress mid-run without waiting for
        completion — useful when a nightly run covers hundreds of trials."""
        return len(self._completed_trials)
