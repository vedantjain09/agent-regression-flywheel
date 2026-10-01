"""In-process tool registry used by the LangGraph agent at runtime.

These wrap the exact same sandbox-filesystem logic as tools/mcp_server.py.
In production the agent calls these tools over MCP (a separate FastMCP
server process, potentially running inside the Modal sandbox itself); for
the graph's unit tests and for regression trials running in-process, this
registry lets app.agent.graph call the same tool behavior directly without
needing a live MCP server socket for every test run. The MCP server remains
the real, separately-runnable interface described in the README.
"""
from __future__ import annotations

import pathlib
import subprocess
from typing import Callable

_SANDBOX_ROOT = pathlib.Path("/tmp/agent_sandbox")
_SANDBOX_ROOT.mkdir(parents=True, exist_ok=True)


def _resolve(path: str) -> pathlib.Path:
    resolved = (_SANDBOX_ROOT / path).resolve()
    if _SANDBOX_ROOT.resolve() not in resolved.parents and resolved != _SANDBOX_ROOT.resolve():
        raise ValueError(f"path escapes sandbox root: {path}")
    return resolved


def read_file(path: str) -> str:
    target = _resolve(path)
    if not target.exists():
        return f"ERROR: {path} does not exist"
    return target.read_text()


def write_file(path: str, content: str) -> str:
    target = _resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return f"wrote {len(content)} bytes to {path}"


def list_files(path: str = ".") -> list[str]:
    target = _resolve(path)
    if not target.exists():
        return []
    return sorted(str(p.relative_to(_SANDBOX_ROOT)) for p in target.rglob("*") if p.is_file())


def run_shell(command: str, timeout_seconds: int = 30) -> dict:
    try:
        result = subprocess.run(
            command, shell=True, cwd=_SANDBOX_ROOT, capture_output=True, text=True, timeout=timeout_seconds
        )
        return {"exit_code": result.returncode, "stdout": result.stdout[-4000:], "stderr": result.stderr[-4000:]}
    except subprocess.TimeoutExpired:
        return {"exit_code": -1, "stdout": "", "stderr": f"timed out after {timeout_seconds}s"}


TOOL_REGISTRY: dict[str, Callable] = {
    "read_file": read_file,
    "write_file": write_file,
    "list_files": list_files,
    "run_shell": run_shell,
}
