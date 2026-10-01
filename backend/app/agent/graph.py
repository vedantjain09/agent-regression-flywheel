"""The production agent, as an explicit LangGraph state graph.

plan -> act -> observe -> (retry up to max_steps) -> finish

This is deliberately not a single opaque "agent.run()" call: each node is a
real graph node with its own state transition, which is what makes the
LangSmith trace downstream mineable at step granularity (the failure-mining
service in mining/cluster.py clusters on these per-step traces, not just a
final pass/fail).
"""
from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, StateGraph

from app.agent.llm_client import LLMClient
from app.tools.local_tools import TOOL_REGISTRY


class AgentState(TypedDict):
    instruction: str
    observations: Annotated[list[str], operator.add]
    steps_taken: int
    max_steps: int
    status: str  # "running" | "finished" | "errored"
    tool_calls_made: Annotated[list[dict], operator.add]


def plan_node(state: AgentState, llm: LLMClient) -> dict:
    tool_names = list(TOOL_REGISTRY.keys())
    response = llm.invoke(state["instruction"], tool_names, state["observations"])
    if not response.tool_calls or response.tool_calls[0]["name"] == "finish":
        return {"status": "finished"}
    return {"tool_calls_made": [response.tool_calls[0]], "status": "running"}


def act_node(state: AgentState) -> dict:
    if not state["tool_calls_made"]:
        return {}
    call = state["tool_calls_made"][-1]
    tool_fn = TOOL_REGISTRY.get(call["name"])
    if tool_fn is None:
        return {"observations": [f"ERROR: unknown tool {call['name']}"], "steps_taken": state["steps_taken"] + 1}
    try:
        result = tool_fn(**call["args"])
        return {"observations": [str(result)], "steps_taken": state["steps_taken"] + 1}
    except Exception as exc:  # noqa: BLE001 — agent tool failures are data, not crashes
        return {"observations": [f"ERROR: {exc}"], "steps_taken": state["steps_taken"] + 1}


def should_continue(state: AgentState) -> str:
    if state["status"] == "finished":
        return "end"
    if state["steps_taken"] >= state["max_steps"]:
        return "end"
    return "continue"


def build_agent_graph(llm: LLMClient | None = None):
    llm = llm or LLMClient()
    graph = StateGraph(AgentState)
    graph.add_node("plan", lambda s: plan_node(s, llm))
    graph.add_node("act", act_node)
    graph.set_entry_point("plan")
    graph.add_conditional_edges("plan", should_continue, {"continue": "act", "end": END})
    graph.add_edge("act", "plan")
    return graph.compile()


def run_agent(instruction: str, max_steps: int = 10, llm: LLMClient | None = None) -> AgentState:
    app = build_agent_graph(llm)
    initial: AgentState = {
        "instruction": instruction,
        "observations": [],
        "steps_taken": 0,
        "max_steps": max_steps,
        "status": "running",
        "tool_calls_made": [],
    }
    return app.invoke(initial)
