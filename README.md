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

Fully built, section by section — see commit history (10 commits, one per
architectural section). Per-component status: [docs/STATUS.md](./docs/STATUS.md).

## Proof numbers

- **58 tests passing** across the project: 53 passed + 1 documented skip in
  the Python/pytest suite (`cd backend && PYTHONPATH=. pytest ../tests -v`),
  plus 5/5 passing in the Django back-office suite
  (`cd backend/django_admin && python manage.py test tasks`).
- The 1 skip is `test_regression_run_workflow_against_live_temporal_server` —
  documented and intentional: this environment has no network route to
  Temporal's ephemeral-test-server download endpoint, so the activity under
  test (`run_trial_activity`) is instead verified directly with 6 passing
  tests, and the skip records the live-server integration shape that would
  run in CI with network access.
- A real bug was caught and fixed by the test suite along the way: a numpy
  `np.bool_` vs. Python `bool` identity mismatch in
  `app/stats/significance.py` (`tests/test_significance.py`), and a missing
  `n_pairs`/`n_concordant`/count breakdown in the `/runs/compare` HTTP
  response that the dashboard needed (`app/api/main.py`, found while wiring
  up `frontend/lib/api.ts`). Both are called out in their section's commit
  message rather than silently fixed.
- `~1,760` lines of backend Python (`app/`, excluding tests), `~840` lines of
  backend tests, `~830` lines of frontend TypeScript/TSX.
- 10 Kubernetes manifests (`k8s/`), structurally validated (`yaml.safe_load_all`
  over every file) — no live cluster available in this environment to apply
  them against, documented in `k8s/README.md` along with what's deliberately
  out of scope (external Temporal server, metrics pipeline, Ingress).
- The dashboard (`frontend/`) type-checks clean (`tsc --noEmit`), lints clean
  (`eslint .`), and builds a production bundle (`next build`) — both routes
  prerender statically against the demo-data fallback when no backend URL is
  configured, and switch to live data automatically once
  `NEXT_PUBLIC_FASTAPI_BASE`/`NEXT_PUBLIC_DJANGO_BASE` are set.

## Running it

```bash
# backend
cd backend
pip install -r requirements.txt
PYTHONPATH=. uvicorn app.api.main:app --reload --port 8000

# django back-office (separate terminal)
cd backend/django_admin
python manage.py migrate
python manage.py runserver 8001

# dashboard (separate terminal)
cd frontend
npm install
cp .env.example .env.local   # point at the two services above
npm run dev
```

Full test suite:

```bash
cd backend && pip install -r requirements.txt
PYTHONPATH=backend pytest tests/ -v          # from repo root
cd backend/django_admin && python manage.py test tasks -v 2
cd frontend && npm install && npx tsc --noEmit && npx eslint . && npm run build
```

## Stack

Backend: Python, FastAPI, Django, Pydantic
Frontend: Next.js, React, TypeScript, Tailwind
Data: PostgreSQL, Redis, Snowflake (ELT target), DuckDB (local analytics)
Orchestration/Infra: Kubernetes, Temporal, Modal
Agents/LLM: LangGraph, LangChain, FastMCP, Harbor-style task/trial model,
NeMo-Gym-shaped environment registry
Observability: Datadog, PostHog, LangSmith
