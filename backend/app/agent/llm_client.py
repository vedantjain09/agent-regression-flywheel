"""LLM abstraction: real provider call when an API key is configured, a
deterministic rule-based fallback otherwise. This keeps the agent graph and
its tests runnable offline/in CI without live credentials, while the
production code path is a real LangChain chat model call.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[dict]


class LLMClient:
    """Wraps a LangChain chat model when OPENAI_API_KEY is set; otherwise
    falls back to a small rule-based planner so the graph is deterministic
    and testable without network access."""

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        self._model_name = model
        self._chat_model = None
        if os.environ.get("OPENAI_API_KEY"):
            try:
                from langchain_openai import ChatOpenAI  # type: ignore

                self._chat_model = ChatOpenAI(model=model, temperature=0)
            except ImportError:
                self._chat_model = None

    @property
    def is_live(self) -> bool:
        return self._chat_model is not None

    def invoke(self, instruction: str, tool_names: list[str], observations: list[str]) -> LLMResponse:
        if self._chat_model is not None:
            prompt = self._build_prompt(instruction, tool_names, observations)
            result = self._chat_model.invoke(prompt)
            return LLMResponse(content=result.content, tool_calls=[])
        return self._rule_based_plan(instruction, tool_names, observations)

    @staticmethod
    def _build_prompt(instruction: str, tool_names: list[str], observations: list[str]) -> str:
        obs_block = "\n".join(observations) or "(no observations yet)"
        return (
            f"Task: {instruction}\nAvailable tools: {', '.join(tool_names)}\n"
            f"Observations so far:\n{obs_block}\nWhat is the next action?"
        )

    @staticmethod
    def _rule_based_plan(instruction: str, tool_names: list[str], observations: list[str]) -> LLMResponse:
        """Deterministic fallback planner: pattern-matches the instruction
        against simple intents (write a file, read a file, run a command,
        finish). Covers enough ground that the agent graph's control flow
        (plan -> act -> observe -> retry -> finish) is fully exercised by
        tests without needing a live model."""
        lowered = instruction.lower()

        if observations and "ERROR" not in observations[-1] and len(observations) >= 1:
            return LLMResponse(content="finish", tool_calls=[{"name": "finish", "args": {}}])

        write_match = re.search(r"write ['\"]?([\w./-]+)['\"]? ?(?:to|containing)? ?['\"]?([^'\"]*)['\"]?", lowered)
        if "write" in lowered and "write_file" in tool_names:
            path_match = re.search(r"to ([\w./-]+\.\w+)", instruction) or re.search(r"([\w./-]+\.\w+)", instruction)
            path = path_match.group(1) if path_match else "out.txt"
            content_match = re.search(r"['\"]([^'\"]+)['\"]", instruction)
            content = content_match.group(1) if content_match else "hello"
            return LLMResponse(
                content=f"calling write_file({path!r})",
                tool_calls=[{"name": "write_file", "args": {"path": path, "content": content}}],
            )

        if "read" in lowered and "read_file" in tool_names:
            path_match = re.search(r"([\w./-]+\.\w+)", instruction)
            path = path_match.group(1) if path_match else "out.txt"
            return LLMResponse(
                content=f"calling read_file({path!r})",
                tool_calls=[{"name": "read_file", "args": {"path": path}}],
            )

        if "run" in lowered and "run_shell" in tool_names:
            cmd_match = re.search(r"`([^`]+)`", instruction)
            command = cmd_match.group(1) if cmd_match else "true"
            return LLMResponse(
                content=f"calling run_shell({command!r})",
                tool_calls=[{"name": "run_shell", "args": {"command": command}}],
            )

        return LLMResponse(content="finish", tool_calls=[{"name": "finish", "args": {}}])
