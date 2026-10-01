"""Tests for the LangGraph agent graph and the local tool registry."""
import pathlib

import pytest

from app.agent.graph import run_agent
from app.agent.llm_client import LLMClient
from app.tools import local_tools


@pytest.fixture(autouse=True)
def clean_sandbox():
    sandbox = pathlib.Path("/tmp/agent_sandbox")
    for f in sandbox.glob("*"):
        if f.is_file():
            f.unlink()
    yield


def test_llm_client_falls_back_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = LLMClient()
    assert client.is_live is False
    response = client.invoke("Write 'x' to a.txt", ["write_file"], [])
    assert response.tool_calls[0]["name"] == "write_file"


def test_agent_writes_file_end_to_end():
    result = run_agent("Write 'hello world' to greeting.txt", max_steps=5)
    assert result["status"] == "finished"
    assert any("wrote" in o for o in result["observations"])
    assert (pathlib.Path("/tmp/agent_sandbox") / "greeting.txt").read_text() == "hello world"


def test_agent_respects_max_steps_budget():
    # an instruction the rule-based planner can't resolve to a concrete tool
    # call cycles until the step budget is exhausted rather than looping forever
    result = run_agent("do something totally unrecognizable xyz123", max_steps=3)
    assert result["steps_taken"] <= 3
    assert result["status"] in {"finished", "running"}


def test_agent_surfaces_tool_errors_as_observations():
    result = run_agent("Read missing_file.txt", max_steps=3)
    assert any("ERROR" in o for o in result["observations"])


def test_local_tools_sandbox_escape_is_blocked():
    with pytest.raises(ValueError):
        local_tools.read_file("../../etc/passwd")


def test_local_tools_write_then_read_roundtrip():
    local_tools.write_file("notes/a.txt", "content-123")
    assert local_tools.read_file("notes/a.txt") == "content-123"
    assert "notes/a.txt" in local_tools.list_files()


def test_local_tools_run_shell_captures_exit_code():
    result = local_tools.run_shell("exit 7")
    assert result["exit_code"] == 7


def test_local_tools_run_shell_timeout():
    result = local_tools.run_shell("sleep 5", timeout_seconds=1)
    assert result["exit_code"] == -1
    assert "timed out" in result["stderr"]
