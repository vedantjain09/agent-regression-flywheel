"""Sandboxed trial execution. Real Modal Sandbox when MODAL_TOKEN_ID is
configured; a subprocess-isolated local fallback otherwise, so the
regression pipeline is runnable and testable without a live Modal account.
Both implementations satisfy the same SandboxRunner protocol, which is all
the Temporal activity in workflows/regression_run.py depends on.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from typing import Protocol


@dataclass
class SandboxResult:
    sandbox_id: str
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False


class SandboxRunner(Protocol):
    def run(self, setup_commands: list[str], check_command: str, timeout_seconds: int) -> SandboxResult:
        ...


class ModalSandboxRunner:
    """Each trial gets its own isolated Modal Sandbox — real per-trial
    container isolation, matching Harbor's container-per-task model."""

    def __init__(self, image: str = "python:3.11-slim") -> None:
        import modal  # imported lazily so this module loads without the
        # modal package's auth state mattering unless this class is used

        self._modal = modal
        self._app = modal.App.lookup("agent-regression-flywheel", create_if_missing=True)
        self._image = modal.Image.from_registry(image)

    def run(self, setup_commands: list[str], check_command: str, timeout_seconds: int) -> SandboxResult:
        full_command = " && ".join([*setup_commands, check_command]) or check_command
        sandbox = self._modal.Sandbox.create(
            "bash",
            "-c",
            full_command,
            app=self._app,
            image=self._image,
            timeout=timeout_seconds,
        )
        sandbox.wait()
        stdout = sandbox.stdout.read()
        stderr = sandbox.stderr.read()
        return SandboxResult(
            sandbox_id=sandbox.object_id,
            exit_code=sandbox.returncode,
            stdout=stdout,
            stderr=stderr,
            timed_out=sandbox.returncode is None,
        )


class LocalSandboxRunner:
    """Subprocess-isolated fallback used when Modal isn't configured
    (local dev, CI, or this environment). Not real container isolation,
    but exercises the exact same control flow — setup commands, timeout
    handling, exit-code capture — that the Modal path uses, so the workflow
    and verifier-scoring code above it is fully testable without a Modal
    account."""

    def run(self, setup_commands: list[str], check_command: str, timeout_seconds: int) -> SandboxResult:
        sandbox_id = f"local-{uuid.uuid4().hex[:8]}"
        with tempfile.TemporaryDirectory() as tmpdir:
            script = "\n".join([*setup_commands, check_command])
            try:
                result = subprocess.run(
                    script,
                    shell=True,
                    cwd=tmpdir,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                )
                return SandboxResult(
                    sandbox_id=sandbox_id,
                    exit_code=result.returncode,
                    stdout=result.stdout,
                    stderr=result.stderr,
                )
            except subprocess.TimeoutExpired as exc:
                return SandboxResult(
                    sandbox_id=sandbox_id,
                    exit_code=-1,
                    stdout=exc.stdout.decode() if exc.stdout else "",
                    stderr=f"timed out after {timeout_seconds}s",
                    timed_out=True,
                )


def get_sandbox_runner() -> SandboxRunner:
    if os.environ.get("MODAL_TOKEN_ID"):
        return ModalSandboxRunner()
    return LocalSandboxRunner()
