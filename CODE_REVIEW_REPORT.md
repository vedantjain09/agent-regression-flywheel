# Code Review Report: Bugs, Fixes, and Improvements

**Date**: 2026-03-18  
**Scope**: Full codebase review  
**Files Reviewed**: 30+ Python/TypeScript files across backend, frontend, and infrastructure

---

## Critical Bugs (Must Fix)

### 1. **Type Mismatch in Frontend Types** 
**Location**: `frontend/lib/types.ts` vs `backend/app/api/main.py`

**Issue**: 
- Frontend `CompareResponse` includes `summary` field (line 38)
- Backend `CompareResponse` includes `summary` field (line 128)
- But backend returns the result from `SignificanceResult.summary()` which returns a string
- This is correct, but the frontend `CompareResponse` type should match exactly

**Severity**: Low (types match, but inconsistent naming)

**Fix**: None needed - types are actually consistent

---

### 2. **Hardcoded Username in Frontend**
**Location**: `frontend/components/ReviewQueue.tsx:60`

**Issue**:
```typescript
const updated = await fn(id, "vedant", `${decision}d from the dashboard review queue`);
```
Username is hardcoded to "vedant" instead of being passed from auth/session.

**Severity**: Medium (functional in dev, but not production-ready)

**Fix**:
```typescript
// Add user context (passed from auth or prompt for demo)
const [currentUser, setCurrentUser] = useState("anonymous");

// In handleDecision:
const updated = await fn(id, currentUser, `${decision}d from the dashboard review queue`);
```

---

### 3. **Missing Error Handling in Mining Worker**
**Location**: `backend/app/mining/worker.py:90-96`

**Issue**:
```python
return [
    TraceSummary(trace_id=tid, summary=by_id[tid].summary, agent_version=by_id[tid].agent_version)
    for tid in trace_ids
    if tid in by_id
]
```
If a trace_id is not found in `by_id`, it's silently skipped. This could lead to:
- Clusters with fewer traces than expected
- Confusion about why trace count doesn't match input

**Severity**: Medium

**Fix**:
```python
# Add logging for skipped traces
missing_ids = set(trace_ids) - set(by_id.keys())
if missing_ids:
    logger.warning(f"Skipping {len(missing_ids)} trace IDs not found in trace store")

return [
    TraceSummary(trace_id=tid, summary=by_id[tid].summary, agent_version=by_id[tid].agent_version)
    for tid in trace_ids
    if tid in by_id
]
```

---

### 4. **No Timeout on Regression Run Workflow**
**Location**: `backend/app/workflows/regression_run.py:98`

**Issue**:
```python
start_to_close_timeout=timedelta(minutes=5),
```
5-minute timeout for individual trials is hardcoded. For complex tasks or slow sandboxes, this could be too short.

**Severity**: Medium

**Fix**:
```python
# Make timeout configurable per task
task = Task.model_validate(task_dict)
timeout = task.environment.max_runtime_seconds + 60  # task timeout + buffer
start_to_close_timeout=timedelta(seconds=timeout),
```

---

### 5. **Path Traversal Vulnerability in Local Tools**
**Location**: `backend/app/tools/local_tools.py:21-25`

**Issue**:
```python
def _resolve(path: str) -> pathlib.Path:
    resolved = (_SANDBOX_ROOT / path).resolve()
    if _SANDBOX_ROOT.resolve() not in resolved.parents and resolved != _SANDBOX_ROOT.resolve():
        raise ValueError(f"path escapes sandbox root: {path}")
    return resolved
```
The check `if _SANDBOX_ROOT.resolve() not in resolved.parents` is vulnerable to symlink attacks or race conditions.

**Severity**: High (security issue in production)

**Fix**:
```python
def _resolve(path: str) -> pathlib.Path:
    # Normalize and resolve relative to sandbox root
    target = (_SANDBOX_ROOT / path).resolve()
    sandbox = _SANDBOX_ROOT.resolve()
    
    # Check if resolved path is within sandbox using commonpath
    try:
        target.relative_to(sandbox)
    except ValueError:
        raise ValueError(f"path escapes sandbox root: {path}")
    return target
```

---

## Potential Bugs (Should Fix)

### 6. **Race Condition in Task Approval**
**Location**: `backend/django_admin/tasks/api.py:34-42`

**Issue**:
```python
def approve(self, request, pk=None):
    task = self.get_object()
    task.status = PendingTask.ReviewStatus.APPROVED
    task.reviewed_by = request.data.get("reviewed_by", "unknown")
    task.review_notes = request.data.get("notes", "")
    task.reviewed_at = timezone.now()
    task.save()
```
No check if task is already approved. Two concurrent requests could approve the same task twice.

**Severity**: Low (unlikely in practice, but possible)

**Fix**:
```python
def approve(self, request, pk=None):
    task = self.get_object()
    if task.status != PendingTask.ReviewStatus.PENDING:
        return Response(
            {"error": f"Task already {task.status}"},
            status=400
        )
    task.status = PendingTask.ReviewStatus.APPROVED
    # ... rest of the code
```

---

### 7. **Memory Leak in Sandbox Output Truncation**
**Location**: `backend/app/workflows/sandbox_runner.py:60` and `backend/app/workflows/regression_run.py:60`

**Issue**:
```python
trial.verifier_output = {"exit_code": result.exit_code, "stdout": result.stdout[-2000:], "stderr": result.stderr[-2000:]}
```
Negative indexing works, but if output is less than 2000 chars, it returns the whole string. If output is massive (GB), this could still cause memory issues.

**Severity**: Low (unlikely in practice)

**Fix**:
```python
# Add max length cap
MAX_OUTPUT = 10000  # 10KB max
stdout = result.stdout[-MAX_OUTPUT:] if len(result.stdout) > MAX_OUTPUT else result.stdout
stderr = result.stderr[-MAX_OUTPUT:] if len(result.stderr) > MAX_OUTPUT else result.stderr
```

---

### 8. **Missing Validation on Compare Request**
**Location**: `backend/app/api/main.py:112-116`

**Issue**:
```python
class CompareRequest(BaseModel):
    baseline_version: str
    candidate_version: str
    pairs: list[dict]  # [{task_id, seed, baseline_passed, candidate_passed}, ...]
```
No validation that:
- `seed` is non-negative
- `task_id` is valid UUID format
- `baseline_passed` and `candidate_passed` are actually booleans

**Severity**: Low (Pydantic provides some validation, but not explicit)

**Fix**:
```python
from pydantic import BaseModel, Field, field_validator
from uuid import UUID

class PairedOutcomeInput(BaseModel):
    task_id: str
    seed: int = Field(ge=0)  # non-negative
    baseline_passed: bool
    candidate_passed: bool

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, v: str) -> str:
        try:
            UUID(v)
        except ValueError:
            raise ValueError("task_id must be a valid UUID")
        return v

class CompareRequest(BaseModel):
    baseline_version: str
    candidate_version: str
    pairs: list[PairedOutcomeInput]
```

---

### 9. **Cluster Size Threshold Magic Number**
**Location**: `backend/app/mining/worker.py:40` and `backend/app/registry/environment_registry.py:81`

**Issue**:
```python
promote_threshold: int = 5,  # in worker
size_threshold: int,  # in registry
```
Default threshold of 5 is hardcoded in worker but not validated in registry call. Could lead to inconsistent behavior.

**Severity**: Low

**Fix**:
```python
# Use consistent default
DEFAULT_PROMOTE_THRESHOLD = 5

# In registry:
def promote_clusters(
    self,
    clusters: list[FailureCluster],
    size_threshold: int = DEFAULT_PROMOTE_THRESHOLD,  # use constant
    default_check_command: str = "true",
) -> list[Task]:
```

---

### 10. **Missing Environment Variable Validation**
**Location**: `backend/app/observability/metrics.py:38`

**Issue**:
```python
initialize(api_key=os.environ["DATADOG_API_KEY"], app_key=os.environ.get("DATADOG_APP_KEY"))
```
If `DATADOG_API_KEY` is set but invalid, this will fail silently or throw an exception that crashes the import.

**Severity**: Medium

**Fix**:
```python
def _build_statsd():
    api_key = os.environ.get("DATADOG_API_KEY")
    if not api_key:
        return _NoOpStatsd()
    try:
        from datadog import initialize, statsd

        initialize(api_key=api_key, app_key=os.environ.get("DATADOG_APP_KEY"))
        return statsd
    except ImportError:
        return _NoOpStatsd()
    except Exception as e:
        logger.warning(f"Failed to initialize Datadog: {e}")
        return _NoOpStatsd()
```

---

## Improvements (Should Consider)

### 11. **Add Retry Configuration to Temporal**
**Location**: `backend/app/workflows/regression_run.py:84-88`

**Issue**: Retry policy is hardcoded:
```python
retry_policy = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,
    maximum_attempts=3,
)
```

**Improvement**: Make configurable via environment variables:
```python
RETRY_INITIAL_INTERVAL = int(os.environ.get("RETRY_INITIAL_INTERVAL", 2))
RETRY_BACKOFF_COEFFICIENT = float(os.environ.get("RETRY_BACKOFF_COEFFICIENT", 2.0))
RETRY_MAX_ATTEMPTS = int(os.environ.get("RETRY_MAX_ATTEMPTS", 3))

retry_policy = RetryPolicy(
    initial_interval=timedelta(seconds=RETRY_INITIAL_INTERVAL),
    backoff_coefficient=RETRY_BACKOFF_COEFFICIENT,
    maximum_attempts=RETRY_MAX_ATTEMPTS,
)
```

---

### 12. **Add Health Check Dependencies**
**Location**: `backend/app/api/main.py:164-166`

**Issue**: Health check only returns static status, doesn't check if dependencies (Postgres, Redis, etc.) are actually reachable.

**Improvement**:
```python
@app.get("/health")
def health() -> dict:
    health_status = {"status": "ok"}
    
    # Check database if configured
    if os.environ.get("DATABASE_URL"):
        try:
            # Try a simple query
            health_status["database"] = "ok"
        except Exception as e:
            health_status["status"] = "degraded"
            health_status["database"] = f"error: {str(e)}"
    
    return health_status
```

---

### 13. **Add Rate Limiting to Agent Run Endpoint**
**Location**: `backend/app/api/main.py:78-93`

**Issue**: No rate limiting on `/agent/run` endpoint. Could be abused to exhaust resources.

**Improvement**:
```python
from slowapi import Limiter, _rate_limit
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.post("/agent/run", response_model=AgentRunResponse)
@limiter.limit("10/minute")  # 10 agent runs per minute per IP
def agent_run(req: AgentRunRequest) -> AgentRunResponse:
    # ... existing code
```

---

### 14. **Add Request ID for Tracing**
**Location**: `backend/app/api/main.py`

**Issue**: No request ID tracking. Hard to correlate logs across services.

**Improvement**:
```python
import uuid

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response
```

---

### 15. **Add Graceful Shutdown**
**Location**: `backend/app/api/main.py`

**Issue**: No graceful shutdown handling. In-flight requests could be dropped during deploy.

**Improvement**:
```python
import signal
import asyncio

@app.on_event("startup")
async def startup():
    # Startup logic
    pass

@app.on_event("shutdown")
async def shutdown():
    # Graceful shutdown logic
    logger.info("Shutting down gracefully...")
    # Wait for in-flight requests to complete
    await asyncio.sleep(2)
```

---

### 16. **Frontend: Add Error Boundaries**
**Location**: `frontend/app/layout.tsx`

**Issue**: No error boundary. Any React error will crash the entire app.

**Improvement**:
```typescript
'use client';

import { Component, ReactNode } from 'react';

class ErrorBoundary extends Component<{children: ReactNode}, {hasError: boolean, error: Error | null}> {
  state = {hasError: false, error: null};

  static getDerivedStateFromError(error: Error) {
    return {hasError: true, error};
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="p-4 bg-red-950 text-red-200">
          <h2>Something went wrong</h2>
          <p>{this.state.error?.message}</p>
        </div>
      );
    }
    return this.props.children;
  }
}

// Wrap your root component
export default function RootLayout({children}: {children: ReactNode}) {
  return (
    <ErrorBoundary>
      {/* existing layout code */}
    </ErrorBoundary>
  );
}
```

---

### 17. **Frontend: Add Loading States**
**Location**: `frontend/components/ReviewQueue.tsx`

**Issue**: No loading state while fetching data from backend. Users see empty state briefly.

**Improvement**:
```typescript
const [isLoading, setIsLoading] = useState(true);

useEffect(() => {
  const loadTasks = async () => {
    setIsLoading(true);
    const { tasks } = await getPendingReview();
    setTasks(tasks);
    setIsLoading(false);
  };
  loadTasks();
}, []);

// In render:
{isLoading ? (
  <p className="text-sm text-neutral-500">Loading review queue...</p>
) : (
  // existing task list
)}
```

---

### 18. **Kubernetes: Missing Resource Limits on Some Deployments**
**Location**: `k8s/10-agent-runner.yaml`, `k8s/11-mining-service.yaml`

**Issue**: Only dashboard-api has resource limits defined. Agent runner and mining service could consume unlimited resources.

**Improvement**: Add limits to all deployments:
```yaml
resources:
  requests:
    cpu: "200m"
    memory: "512Mi"
  limits:
    cpu: "1000m"
    memory: "2Gi"
```

---

### 19. **Add Database Migration Rollback Strategy**
**Location**: `backend/django_admin/`

**Issue**: No documented rollback strategy for Django migrations.

**Improvement**: Add to RUNBOOK.md:
```bash
# Rollback migration
python manage.py migrate <app> <previous_migration_number>

# Or use django-migrations:
pip install django-migrations
python manage.py showmigrations
python manage.py migrate <app> <target_migration>
```

---

### 20. **Add Configuration Validation at Startup**
**Location**: `backend/app/api/main.py`

**Issue**: No validation that required environment variables are set at startup.

**Improvement**:
```python
@app.on_event("startup")
async def validate_config():
    required_vars = ["DATABASE_URL"]  # or whatever is required
    missing = [var for var in required_vars if not os.environ.get(var)]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")
```

---

## Code Quality Issues

### 21. **Inconsistent Error Handling Patterns**
**Location**: Multiple files

**Issue**: Some functions raise exceptions, some return error tuples, some return None on error.

**Improvement**: Standardize on one pattern:
- For API: raise HTTPException
- For internal: raise custom exception classes
- For workflows: return error status codes

---

### 22. **Missing Docstring Examples**
**Location**: `backend/app/stats/significance.py`, `backend/app/mining/cluster.py`

**Issue**: Docstrings explain what functions do but don't show examples.

**Improvement**: Add example usage in docstrings:
```python
def mcnemar_exact(outcomes: list[PairedOutcome], alpha: float = 0.05) -> SignificanceResult:
    """Exact McNemar's test on paired binary outcomes.
    
    Example:
        >>> outcomes = [
        ...     PairedOutcome(task_id="t1", seed=1, baseline_passed=True, candidate_passed=False),
        ...     PairedOutcome(task_id="t2", seed=2, baseline_passed=False, candidate_passed=True),
        ... ]
        >>> result = mcnemar_exact(outcomes)
        >>> result.significant
        False
    """
```

---

### 23. **Magic Numbers Without Constants**
**Location**: Multiple files

**Issue**: Numbers like `2000`, `200`, `512`, `5` scattered throughout code without explanation.

**Improvement**: Extract to named constants:
```python
MAX_OUTPUT_TRUNCATION = 2000
MAX_SUMMARY_LENGTH = 512
DEFAULT_POLL_INTERVAL_SECONDS = 5.0
DEFAULT_PROMOTE_THRESHOLD = 5
```

---

## Security Issues

### 24. **No Input Sanitization on Shell Commands**
**Location**: `backend/app/tools/local_tools.py:49-56`

**Issue**:
```python
result = subprocess.run(
    command, shell=True, cwd=_SANDBOX_ROOT, capture_output=True, text=True, timeout=timeout_seconds
)
```
Even with sandbox protection, if `command` contains shell metacharacters like `;`, `&&`, `|`, it could execute unintended commands.

**Severity**: Medium (mitigated by sandbox, but still risky)

**Fix**:
```python
def run_shell(command: str, timeout_seconds: int = 30) -> dict:
    # Sanitize command to prevent shell injection
    forbidden_chars = [';', '&', '|', '`', '$', '(', ')', '<', '>']
    if any(char in command for char in forbidden_chars):
        raise ValueError(f"Shell command contains forbidden characters: {command}")
    
    try:
        result = subprocess.run(
            command, shell=True, cwd=_SANDBOX_ROOT, capture_output=True, text=True, timeout=timeout_seconds
        )
        return {"exit_code": result.returncode, "stdout": result.stdout[-4000:], "stderr": result.stderr[-4000:]}
    except subprocess.TimeoutExpired:
        return {"exit_code": -1, "stdout": "", "stderr": f"timed out after {timeout_seconds}s"}
```

---

### 25. **No Authentication on API Endpoints**
**Location**: `backend/app/api/main.py`

**Issue**: All endpoints are publicly accessible. No authentication middleware.

**Severity**: High (for production deployment)

**Improvement**: Add authentication:
```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if credentials.credentials != os.environ.get("API_TOKEN"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )
    return credentials.credentials

# Protect endpoints:
@app.get("/tasks", dependencies=[Depends(verify_token)])
def list_tasks() -> list[Task]:
    return _task_repo.list_approved()
```

---

## Performance Issues

### 26. **N+1 Query Problem in Django**
**Location**: `backend/django_admin/tasks/api.py:23`

**Issue**:
```python
queryset = PendingTask.objects.all().order_by("-origin_cluster_size", "-created_at")
```
This loads all tasks into memory. For large datasets, this is inefficient.

**Improvement**: Add pagination:
```python
from rest_framework.pagination import PageNumberPagination

class PendingTaskPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 100

class PendingTaskViewSet(viewsets.ModelViewSet):
    pagination_class = PendingTaskPagination
    # ... rest of code
```

---

### 27. **No Caching on Task List**
**Location**: `backend/app/api/main.py:99-101`

**Issue**: Every request to `/tasks` queries the database. Tasks don't change frequently.

**Improvement**: Add caching:
```python
from fastapi_cache2 import FastAPICache
from fastapi_cache.backends.redis import FastAPIRedisBackend

cache = FastAPICache()
cache.set_backend(FastAPIRedisBackend("redis://localhost"))

@app.get("/tasks", response_model=list[Task])
@cache(expire=60)  # Cache for 60 seconds
def list_tasks() -> list[Task]:
    return _task_repo.list_approved()
```

---

### 28. **Synchronous Database Calls in Async Context**
**Location**: `backend/django_admin/tasks/api.py`

**Issue**: Django ORM is synchronous. In an async context (if the API were async), this would block.

**Improvement**: Use async Django ORM or ensure Django endpoints run in thread pool.

---

## Testing Issues

### 29. **Missing Integration Tests**
**Location**: No integration tests for full workflow

**Issue**: Unit tests exist for individual components, but no end-to-end tests for:
- Mining → clustering → task creation flow
- Regression run → significance test → promotion flow

**Improvement**: Add integration tests in `tests/`:
```python
def test_mining_to_approval_flow():
    # Simulate traces → cluster → task → approve
    pass

def test_regression_to_promotion_flow():
    # Simulate regression run → significance → promote
    pass
```

---

### 30. **Frontend Tests Missing**
**Location**: `frontend/`

**Issue**: No frontend tests at all (no Jest, no Cypress, no Playwright).

**Improvement**: Add basic tests:
```typescript
// components/ReviewQueue.test.tsx
import { render, screen } from '@testing-library/react';
import ReviewQueue from './ReviewQueue';

describe('ReviewQueue', () => {
  it('renders tasks correctly', () => {
    const tasks = [
      {id: 1, name: 'task1', status: 'pending', instruction: 'test', ...}
    ];
    render(<ReviewQueue initialTasks={tasks} live={false} />);
    expect(screen.getByText('task1')).toBeInTheDocument();
  });
});
```

---

## Documentation Issues

### 31. **RUNBOOK.md: Missing Troubleshooting for Common Errors**
**Issue**: RUNBOOK.md is good but missing common error scenarios.

**Improvement**: Add section:
```markdown
## Common Errors

### "Port already in use"
Solution: ...

### "Module not found"
Solution: ...

### "Connection refused"
Solution: ...
```

---

### 32. **Missing API Documentation**
**Location**: No OpenAPI/Swagger documentation for FastAPI

**Improvement**: Enable Swagger UI:
```python
from fastapi.openapi.docs import get_swagger_ui_html

app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(openapi_url=app.openapi_url)
```

---

## Summary

### Critical Issues: 2
1. Path traversal vulnerability in local tools
2. No authentication on API endpoints

### High Priority: 5
3. Missing error handling in mining worker
4. No timeout configuration in regression runs
5. Shell command injection risk
6. Missing request ID for tracing
7. Missing health check dependencies

### Medium Priority: 10
8. Hardcoded username in frontend
9. Race condition in task approval
10. Missing environment variable validation
11. No rate limiting on agent run
12. Missing graceful shutdown
13. Missing frontend error boundaries
14. Missing K8s resource limits
15. No input sanitization on shell commands

### Low Priority: 10
16. Type naming consistency
17. Memory leak in output truncation
18. Missing validation on compare request
19. Cluster size threshold consistency
20. Retry configuration hardcoded
21. No request ID tracing
22. Missing docstring examples
23. Magic numbers without constants

### Improvements: 8
24. Add configuration validation
25. Standardize error handling
26. Add database pagination
27. Add caching
28. Add integration tests
29. Add frontend tests
30. Improve documentation
31. Add API documentation
32. Add monitoring/alerting

### Security: 2
33. Path traversal vulnerability
34. No authentication

### Performance: 3
35. N+1 query problem
36. No caching
37. Synchronous DB in async context

---

## Recommended Fix Priority

**Immediate (Before Production)**:
1. Fix path traversal vulnerability (#5)
2. Add authentication to API (#25)
3. Add rate limiting to agent run (#13)
4. Fix shell command sanitization (#24)

**Short-term (Next Sprint)**:
5. Add error handling in mining worker (#3)
6. Add graceful shutdown (#15)
7. Add health check dependencies (#12)
8. Add configuration validation (#20)

**Medium-term (Next Quarter)**:
9. Add integration tests (#29)
10. Add frontend tests (#30)
11. Add caching (#27)
12. Add pagination (#26)
13. Improve documentation (#31-32)

**Long-term (As Needed)**:
14. Standardize error handling (#21)
15. Add docstring examples (#22)
16. Extract magic numbers (#23)
17. Add request ID tracing (#14)
