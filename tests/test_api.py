"""Tests for the FastAPI agent + dashboard API."""
import pathlib
import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.main import app, _task_repo
from app.schemas.task import DeterministicVerifierSpec, EnvironmentSpec, Task


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def clean_state():
    sandbox = pathlib.Path("/tmp/agent_sandbox")
    for f in sandbox.glob("*"):
        if f.is_file():
            f.unlink()
    _task_repo._tasks.clear()
    yield


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "checks" in data


def test_agent_run_end_to_end(client):
    response = client.post("/agent/run", json={"instruction": "Write 'hi' to x.txt", "max_steps": 5})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "finished"
    assert any("wrote" in o for o in body["observations"])


def test_list_tasks_only_returns_approved(client):
    approved = Task(
        name="approved-task", category="c", instruction="i",
        environment=EnvironmentSpec(), verifier=DeterministicVerifierSpec(check_command="true"), approved=True,
    )
    unapproved = Task(
        name="pending-task", category="c", instruction="i",
        environment=EnvironmentSpec(), verifier=DeterministicVerifierSpec(check_command="true"), approved=False,
    )
    _task_repo.add(approved)
    _task_repo.add(unapproved)

    response = client.get("/tasks")
    names = [t["name"] for t in response.json()]
    assert "approved-task" in names
    assert "pending-task" not in names


def test_get_task_404_for_missing(client):
    response = client.get("/tasks/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_compare_versions_promotes_on_significant_improvement(client):
    pairs = []
    for i in range(30):
        baseline_passed = i % 3 == 0
        candidate_passed = True if baseline_passed else (i % 4 != 0)
        pairs.append({"task_id": str(uuid.uuid4()), "seed": i, "baseline_passed": baseline_passed, "candidate_passed": candidate_passed})
    response = client.post(
        "/runs/compare",
        json={"baseline_version": "v1", "candidate_version": "v2", "pairs": pairs},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["significant"] is True
    assert body["promote"] is True


def test_compare_versions_rejects_empty_pairs(client):
    response = client.post(
        "/runs/compare",
        json={"baseline_version": "v1", "candidate_version": "v2", "pairs": []},
    )
    assert response.status_code == 400


def test_compare_versions_inconclusive_on_tiny_sample(client):
    pairs = [{"task_id": "00000000-0000-0000-0000-000000000000", "seed": 0, "baseline_passed": True, "candidate_passed": False}]
    response = client.post(
        "/runs/compare",
        json={"baseline_version": "v1", "candidate_version": "v2", "pairs": pairs},
    )
    body = response.json()
    assert body["promote"] is False
