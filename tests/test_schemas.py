"""Tests for the Harbor-style task/trial schemas and the ORM layer."""
import uuid
from datetime import datetime

import pytest
from pydantic import ValidationError

from app.schemas.task import (
    DeterministicVerifierSpec,
    EnvironmentSpec,
    FailureClusterOrigin,
    LLMJudgeVerifierSpec,
    RegressionRun,
    Task,
    Trial,
    TrialStatus,
)


def _make_env() -> EnvironmentSpec:
    return EnvironmentSpec(setup_commands=["pip install -r requirements.txt"])


def test_task_requires_non_empty_name():
    with pytest.raises(ValidationError):
        Task(
            name="   ",
            category="filesystem",
            instruction="do a thing",
            environment=_make_env(),
            verifier=DeterministicVerifierSpec(check_command="true"),
        )


def test_task_with_deterministic_verifier_roundtrip():
    task = Task(
        name="write-and-read-file",
        category="filesystem",
        instruction="Write 'hello' to out.txt",
        environment=_make_env(),
        verifier=DeterministicVerifierSpec(check_command="grep hello out.txt"),
    )
    dumped = task.model_dump_json()
    restored = Task.model_validate_json(dumped)
    assert restored.verifier.check_command == "grep hello out.txt"
    assert restored.approved is False


def test_task_with_llm_judge_verifier_and_calibration_set():
    verifier = LLMJudgeVerifierSpec(
        rubric="Did the agent correctly summarize the document?",
        calibration_set=[("summary covers all 3 key points", True), ("summary is empty", False)],
        pass_threshold=0.8,
    )
    task = Task(
        name="summarize-doc",
        category="nlp",
        instruction="Summarize the attached document.",
        environment=_make_env(),
        verifier=verifier,
    )
    assert len(task.verifier.calibration_set) == 2
    assert task.verifier.pass_threshold == 0.8


def test_task_origin_tracks_mining_provenance():
    origin = FailureClusterOrigin(
        cluster_id="cluster-42",
        source_trace_ids=["t1", "t2", "t3"],
        discovered_at=datetime.utcnow(),
        cluster_size=3,
        representative_summary="agent repeatedly times out on large file reads",
    )
    task = Task(
        name="large-file-read-timeout",
        category="auto-generated",
        instruction="Read a 500MB file within budget.",
        environment=_make_env(),
        verifier=DeterministicVerifierSpec(check_command="true"),
        origin=origin,
    )
    assert task.origin.cluster_size == 3
    assert task.approved is False  # auto-generated tasks start unapproved


def test_trial_passed_property():
    trial = Trial(task_id=uuid.uuid4(), agent_version="v1", seed=0, status=TrialStatus.PASSED)
    assert trial.passed is True
    trial.status = TrialStatus.FAILED
    assert trial.passed is False


def test_regression_run_pairs_task_ids():
    run = RegressionRun(
        baseline_version="v1",
        candidate_version="v2",
        task_ids=[uuid.uuid4(), uuid.uuid4()],
        seeds_per_task=3,
    )
    assert len(run.task_ids) == 2
    assert run.seeds_per_task == 3
