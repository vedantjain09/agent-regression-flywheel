"""Tests for the Temporal activity logic and the sandbox runner.

The `run_trial_activity` function is Temporal-decorated but is still a
plain async function underneath, so it's tested directly here rather than
through a live Temporal server (see the module docstring in
app/workflows/regression_run.py for why: this sandbox has no network path
to temporal.io's ephemeral test-server download endpoint). An integration
test showing the intended live-server usage is included below, marked
skip, as documentation of the real deployment path.
"""
import pytest

from app.schemas.task import DeterministicVerifierSpec, EnvironmentSpec, Task, TrialStatus
from app.workflows.regression_run import run_trial_activity
from app.workflows.sandbox_runner import LocalSandboxRunner, get_sandbox_runner


def _make_task(check_command: str, timeout: int = 5) -> Task:
    return Task(
        name="t",
        category="c",
        instruction="i",
        environment=EnvironmentSpec(max_runtime_seconds=timeout),
        verifier=DeterministicVerifierSpec(check_command=check_command),
    )


@pytest.mark.asyncio
async def test_run_trial_activity_passes_on_exit_zero():
    task = _make_task("exit 0")
    result = await run_trial_activity(task.model_dump(mode="json"), "v1", seed=0)
    assert result["status"] == TrialStatus.PASSED.value
    assert result["verifier_output"]["exit_code"] == 0


@pytest.mark.asyncio
async def test_run_trial_activity_fails_on_nonzero_exit():
    task = _make_task("exit 1")
    result = await run_trial_activity(task.model_dump(mode="json"), "v1", seed=0)
    assert result["status"] == TrialStatus.FAILED.value


@pytest.mark.asyncio
async def test_run_trial_activity_times_out():
    task = _make_task("sleep 5", timeout=1)
    result = await run_trial_activity(task.model_dump(mode="json"), "v1", seed=0)
    assert result["status"] == TrialStatus.TIMED_OUT.value


@pytest.mark.asyncio
async def test_run_trial_activity_records_agent_version_and_seed():
    task = _make_task("exit 0")
    result = await run_trial_activity(task.model_dump(mode="json"), "candidate-v2", seed=3)
    assert result["agent_version"] == "candidate-v2"
    assert result["seed"] == 3


def test_get_sandbox_runner_falls_back_to_local_without_modal_token(monkeypatch):
    monkeypatch.delenv("MODAL_TOKEN_ID", raising=False)
    runner = get_sandbox_runner()
    assert isinstance(runner, LocalSandboxRunner)


def test_local_sandbox_runner_runs_setup_commands_before_check():
    runner = LocalSandboxRunner()
    result = runner.run(
        setup_commands=["echo setup_marker > marker.txt"],
        check_command="cat marker.txt",
        timeout_seconds=5,
    )
    assert result.exit_code == 0
    assert "setup_marker" in result.stdout


@pytest.mark.skip(
    reason="requires a live Temporal server / network access to the ephemeral "
    "test-server download endpoint, unavailable in this build environment. "
    "Documents the intended integration-test shape for a real deployment."
)
@pytest.mark.asyncio
async def test_regression_run_workflow_against_live_temporal_server():
    from temporalio.testing import WorkflowEnvironment
    from temporalio.worker import Worker

    from app.workflows.regression_run import RegressionRunWorkflow, run_trial_activity

    task = _make_task("exit 0")
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue="test-queue",
            workflows=[RegressionRunWorkflow],
            activities=[run_trial_activity],
        ):
            result = await env.client.execute_workflow(
                RegressionRunWorkflow.run,
                args=[[task.model_dump(mode="json")], "v1", "v2", 2],
                id="test-run",
                task_queue="test-queue",
            )
            assert len(result) == 4  # 1 task x 2 seeds x 2 versions
