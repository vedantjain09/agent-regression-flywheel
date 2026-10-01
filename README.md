# Agent Regression Flywheel

A closed-loop system that turns live agent failures into tomorrow's regression
suite, and gates every version promotion behind a statistical significance test
instead of a raw pass-rate diff.

Most eval harnesses run a fixed benchmark. This one asks a different question:
**what should be in the benchmark**, based on what's actually breaking in
production — and whether a "fix" is real or just sampling noise.

Full design rationale: [ARCHITECTURE.md](./ARCHITECTURE.md)

## Pipeline

1. Production agent (LangGraph + LangChain, tools exposed via FastMCP) runs live,
   traced end-to-end in LangSmith.
2. Failure-mining service embeds traces and clusters them (HDBSCAN) to surface
   *new* failure modes — not matched against a predefined list of known bugs.
3. Each cluster is converted into a Harbor-style task (instruction + sandboxed
   env spec + verifier) and filed into a NeMo-Gym-shaped environment registry.
4. Temporal durably orchestrates fan-out of regression trials into isolated
   Modal sandboxes, with retries and resumability on worker/sandbox failure.
5. Comparing a candidate agent version against the baseline runs paired trials
   and requires a McNemar's-test-significant improvement before promotion.
6. FastAPI serves the agent and dashboard APIs; Django serves the back-office
   task-approval queue. Postgres holds canonical state, Redis the job queue,
   Snowflake the trace warehouse, DuckDB local ad-hoc analytics.
7. Next.js/React dashboard: mining funnel, version-comparison view with the
   significance result front and center.

## Status

Actively built section by section — see commit history. Status of each
component is tracked in [docs/STATUS.md](./docs/STATUS.md).

## Stack

Backend: Python, FastAPI, Django, Pydantic
Frontend: Next.js, React, TypeScript, Tailwind
Data: PostgreSQL, Redis, Snowflake (ELT target), DuckDB (local analytics)
Orchestration/Infra: Kubernetes, Temporal, Modal
Agents/LLM: LangGraph, LangChain, FastMCP, Harbor-style task/trial model,
NeMo-Gym-shaped environment registry
Observability: Datadog, PostHog, LangSmith
