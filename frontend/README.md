# Dashboard

Next.js 16 (App Router) + TypeScript + Tailwind dashboard for the Agent
Regression Flywheel. Two views:

- **Mining Funnel** (`/`) — production failure clusters discovered by
  `backend/app/mining/cluster.py`, flowing through the Django review queue
  (`backend/django_admin`), down to the approved tasks actually replayed in
  every regression run. Approve/reject actions write back to the Django
  API in real time.
- **Version Comparison** (`/compare`) — runs `backend/app/stats/significance.py`'s
  McNemar's exact test (via `FastAPI /runs/compare`) over a paired-trial
  outcome set and shows the promote/block decision, not just a pass-rate
  number. Three preset scenarios (clear improvement, clear regression,
  small noisy gain) make the point: a raw pass-rate diff can't distinguish
  "candidate fixed real failures" from "one flaky trial flipped."

## Live data vs. demo data

Every data-fetching function in `lib/api.ts` calls the real backend when
`NEXT_PUBLIC_FASTAPI_BASE` / `NEXT_PUBLIC_DJANGO_BASE` are set (see
`.env.example`), and falls back to the fixtures in `lib/demo-data.ts` —
in the exact same response shape — when the backend isn't configured or
isn't reachable. A `live` / `demo data` badge in the UI always says which
one is on screen. This mirrors the live/fallback split used throughout
the Python backend (`LLMClient`, `SnowflakeTraceStore`,
`get_sandbox_runner`).

## Run locally

```bash
npm install
npm run dev
```

Point it at a running backend:

```bash
# in backend/app, with `uvicorn app.api.main:app --port 8000` running
# in backend/django_admin, with `python manage.py runserver 8001` running
cp .env.example .env.local
npm run dev
```

## Build

```bash
npm run build
```
