# Plan: build-ewa-request-logging-20260320

## Goal
Add HTTP request logging middleware to `backend/server.py`. Each request logs:
- Timestamp (ISO 8601 UTC, e.g. `2026-03-20T00:00:00Z`)
- HTTP method
- Path
- Status code
- Response time in milliseconds

Format: `[2026-03-20T00:00:00Z] GET /health 200 12ms`

## Branch
`feat/build-ewa-request-logging-20260320`

## Files to Change

| File | Change |
|------|--------|
| `backend/server.py` | Add `import time`, add `@app.middleware("http")` logging function |
| `tests/test_logging.py` | New file: pytest test using `caplog` to verify log output |

## Implementation Steps

### Step 1 — Add `import time` to server.py
Insert `import time` after the existing `import asyncio` on line ~17.

### Step 2 — Add middleware to server.py
After the logging setup (line 109), add:

```python
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    logger.info("[%s] %s %s %d %dms", timestamp, request.method, request.url.path, response.status_code, elapsed_ms)
    return response
```

Placement: after `logger = logging.getLogger(__name__)` and before `# ============== MODELS ==============`.

### Step 3 — Add test file
Create `tests/test_logging.py`:
- Import and set MONGO_URL env var
- Use `TestClient(app)` and pytest `caplog` fixture
- Make a GET `/health` request with `caplog.at_level(logging.INFO)`
- Assert a log record contains `GET`, `/health`, `200`, and `ms` in the message

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| `time` not imported | Certain (it's missing) | Add import explicitly |
| Middleware sees response before body is fully sent (streaming) | Low — these routes return JSON | Acceptable for this API |
| `test_intentional_failure` in `test_health.py` pre-exists | Pre-existing | Note in output contract; not our bug |
| Log capture in TestClient may not propagate correctly | Low | Use `caplog.at_level` with exact logger name `backend.server` |
| Middleware placement relative to CORS | No issue — our middleware logs regardless of CORS outcome | No change needed |

## Rollback
```bash
git checkout main
git branch -D feat/build-ewa-request-logging-20260320
```

## Acceptance Criteria Check
- [ ] Every request produces a log line in the specified format
- [ ] Log includes method, path, status code, and response time
- [ ] New pytest test passes
- [ ] All existing tests still pass (excluding pre-existing `test_intentional_failure`)
