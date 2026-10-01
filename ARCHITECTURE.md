# Architecture — Agent Regression Flywheel

## Problem

Most agent-evaluation projects run a fixed, hand-written benchmark against a model and
call it done. That tells you how an agent does on problems someone already thought of.
It says nothing about the failure modes actually happening in production, and it treats
every pass/fail result as ground truth even though LLM agents are stochastic — the same
task can pass on one rollout and fail on the next.

This project closes two gaps at once:

1. **The benchmark is generated from live failures, not hand-curated.** Production
   traces are mined for *novel* failure clusters (unsupervised, not keyword-matched
   against a list of known bugs), and each cluster becomes a regression task
   automatically.
2. **Promoting a new agent version requires statistical proof, not a percentage diff.**
   Because trials are stochastic, a naive "72% -> 76% pass rate, ship it" comparison is
   frequently noise. Version comparisons run paired trials and gate promotion behind a
   significance test (McNemar's test on paired pass/fail outcomes).

## System overview

```
                 ┌─────────────────────────────────────────────────────────┐
                 │                     PRODUCTION AGENT                     │
                 │   LangGraph state graph (plan -> act -> observe -> retry) │
                 │   LangChain LLM/tool abstraction                          │
                 │   Tools exposed as real MCP servers (FastMCP)             │
                 └───────────────────────┬────────────────────────────────┘
                                          │ every run traced
                                          ▼
                 ┌─────────────────────────────────────────────────────────┐
                 │                    LangSmith (traces)                    │
                 └───────────────────────┬────────────────────────────────┘
                                          ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                           FAILURE MINING SERVICE                           │
│  Embed traces -> HDBSCAN cluster -> surface *new* failure modes            │
│  (unsupervised: discovers failure classes nobody pre-defined)              │
└───────────────────────────────┬────────────────────────────────────────────┘
                                 ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                 ENVIRONMENT REGISTRY (NeMo-Gym-shaped)                      │
│  dataset (task) / harness (how agent acts) / verifier (scoring) / state     │
│  Each cluster -> a Harbor-style task: instruction + env spec + verifier     │
│  (deterministic checks + LLM-as-judge w/ calibration set)                   │
└───────────────────────────────┬────────────────────────────────────────────┘
                                 ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                    TEMPORAL-ORCHESTRATED REGRESSION RUN                     │
│  Durable fan-out across trials -> Modal sandboxes (isolated per trial)      │
│  Retries on sandbox timeout, resumable if a worker dies mid-run             │
└───────────────────────────────┬────────────────────────────────────────────┘
                                 ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                      STATISTICAL SIGNIFICANCE GATE                          │
│  Paired trials, old vs. candidate agent version, same seeds                 │
│  McNemar's test -> only promote if improvement is significant (p < 0.05)    │
└───────────────────────────────┬────────────────────────────────────────────┘
                                 ▼
          ┌──────────────────────────────────┬──────────────────────────────┐
          │         FastAPI (hot path)         │     Django (back office)     │
          │  agent-facing API, dashboard API   │  task approval queue,        │
          │                                    │  verifier override, users    │
          └──────────────────┬─────────────────┴──────────────┬───────────────┘
                              ▼                                ▼
                    Next.js / React dashboard        Postgres (canonical state)
                    mining funnel, version compare    Redis (queue, rate limit)
                                                       Snowflake (trace warehouse)
                                                       DuckDB (ad-hoc local analytics)

                    Datadog (infra health) · PostHog (product analytics)
```

## Why each data store exists

- **Postgres** — canonical state: tasks, trials, runs, agent versions, promotion
  decisions. Needs transactions and foreign-key integrity.
- **Redis** — the mining job queue and LLM-call rate limiting. Needs to be fast and
  ephemeral, not durable.
- **Snowflake** — the durable warehouse that all historical production traces land in
  via batch ELT from LangSmith exports. This is the cold path: mining runs against
  windows of this data, not against a live production table.
- **DuckDB** — fast local/ad-hoc analysis when iterating on the clustering algorithm
  itself, before a change is promoted into the Snowflake batch pipeline. Lets you
  prototype against a Parquet export in seconds instead of waiting on a warehouse query.

## Why FastAPI *and* Django

FastAPI serves the agent-facing API and the dashboard's read API — both
latency-sensitive, both benefit from async. Django serves the back-office: task
approval queue, verifier override, user/permission management — CRUD-heavy,
benefits from Django admin instead of hand-building forms. Running both lets each
framework do the part it's actually good at instead of forcing one tool to do
everything adequately.

## Why Kubernetes

The agent runner (latency-sensitive, scales on request rate) and the mining service
(bursty, batch-driven, scales on queue depth) have different scaling signals, so they
run as separate deployments with separate HPA policies rather than one monolithic
service.

## The statistical layer in detail

See `backend/app/stats/significance.py`. Given paired pass/fail outcomes from the
baseline and candidate agent on the *same* tasks with the *same* sampling seeds,
McNemar's test is used instead of a simple proportion diff, because:

- It only looks at *discordant* pairs (tasks where the two versions disagree), which is
  exactly the signal that matters for "did this change something."
- A simple pass-rate diff is vulnerable to the stochasticity of LLM sampling producing
  an apparent improvement that's actually noise at typical eval sample sizes (dozens to
  low hundreds of trials).

Promotion is gated on p < 0.05 by default (configurable), and the system refuses to
mark a version as "ready to promote" without it, surfacing "not statistically
significant — need more trials" instead of a false green light.
