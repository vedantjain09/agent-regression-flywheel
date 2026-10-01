"""Real FastMCP tool server — these are the tools the production agent (and
regression-trial agents) call. Each one runs against the sandbox filesystem
so a trial's verifier can check real on-disk state, not a mocked return value.

Run standalone with: python -m app.tools.mcp_server
"""
from __future__ import annotations

import pathlib
import subprocess

from fastmcp import FastMCP

mcp = FastMCP("agent-regression-flywheel-tools")

# Tools operate relative to a sandbox root so a trial can be pointed at an
# isolated directory (the Modal sandbox mount, in production) without any
# tool code change.
_SANDBOX_ROOT = pathlib.Path("/tmp/agent_sandbox")
_SANDBOX_ROOT.mkdir(parents=True, exist_ok=True)


def _resolve(path: str) -> pathlib.Path:
    resolved = (_SANDBOX_ROOT / path).resolve()
    if _SANDBOX_ROOT.resolve() not in resolved.parents and resolved != _SANDBOX_ROOT.resolve():
        raise ValueError(f"path escapes sandbox root: {path}")
    return resolved


@mcp.tool()
def read_file(path: str) -> str:
    """Read a file's contents from the sandbox."""
    target = _resolve(path)
    if not target.exists():
        return f"ERROR: {path} does not exist"
    return target.read_text()


@mcp.tool()
def write_file(path: str, content: str) -> str:
    """Write content to a file in the sandbox, creating parent dirs as needed."""
    target = _resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return f"wrote {len(content)} bytes to {path}"

@mcp.tool()
def list_files(path: str = ".") -> list[str]:
    """List files under a sandbox-relative directory."""
    target = _resolve(path)
    if not target.exists():
        return []
    return sorted(str(p.relative_to(_SANDBOX_ROOT)) for p in target.rglob("*") if p.is_file())


@mcp.tool()
def run_shell(command: str, timeout_seconds: int = 30) -> dict:
    """Run a shell command inside the sandbox root and return exit code + output.
    This is what deterministic verifiers ultimately call too (see
    stats/significance and workflows/regression_run for how a Trial's
    check_command gets executed the same way)."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=_SANDBOX_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-4000:],
        }
    except subprocess.TimeoutExpired:
        return {"exit_code": -1, "stdout": "", "stderr": f"timed out after {timeout_seconds}s"}


if __name__ == "__main__":
    mcp.run()
