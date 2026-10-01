# Kubernetes manifests

Applies in numeric prefix order (`kubectl apply -f k8s/`, or pipe through
`kustomize` — no kustomization.yaml is included since this is a from-scratch
set of plain manifests, not a templated chart).

| File | What it deploys | Why it's separate |
|---|---|---|
| `00-namespace.yaml` | `agent-regression-flywheel` namespace | isolation |
| `01-config-secrets.yaml` | shared ConfigMap + Secret template | config split from code, per 12-factor |
| `10-agent-runner.yaml` | FastAPI `/agent/run`, HPA on request rate | latency-sensitive, request-driven — see ARCHITECTURE.md "Why Kubernetes" |
| `11-mining-service.yaml` | `app.mining.worker`, HPA on Redis queue depth | bursty, batch-driven — different scaling signal than the agent runner |
| `12-fastapi-dashboard-api.yaml` | FastAPI `/tasks`, `/runs/compare` | dashboard read traffic, scaled independently of agent-run traffic |
| `13-django-backoffice.yaml` | Django/DRF task-approval API + admin | low-QPS CRUD, fixed replica count |
| `14-dashboard-frontend.yaml` | Next.js dashboard | stateless, points at the two API deployments over in-cluster DNS |
| `20-postgres.yaml` | Postgres StatefulSet + PVC | durable state (tasks, trials, runs) — needs to survive a pod reschedule |
| `21-redis.yaml` | Redis Deployment, no PVC | ephemeral trace queue + rate limiter — disposable by design |
| `22-temporal-worker.yaml` | `app.workflows.worker`, HPA on Temporal backlog | regression-run fan-out; assumes an external/managed Temporal server |

A real cluster would also need a Temporal server deployment (or point
`TEMPORAL_ADDRESS` at Temporal Cloud), a metrics-server + Prometheus adapter
for the two custom-metric HPAs (`http_requests_per_second`,
`redis_trace_queue_depth`, `temporal_task_queue_backlog`), and Ingress/TLS
termination in front of `dashboard-frontend` — all left out here since they're
cluster/provider-specific rather than part of this project's own code.
