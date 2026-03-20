# Plan: build-ewa-request-id-20260320

## Goal
Add request ID middleware to `backend/server.py`. Each request gets a unique UUID as `X-Request-ID`. Client-provided values are echoed; server-generated values are UUID4. The ID appears in response headers and log output. New pytest tests verify this behavior.

---

## Explore Summary

**Relevant files:**
- `backend/server.py` — all API code; has two `@app.middleware("http")` decorators:
  - `log_requests` (line 126): logs `[ts] METHOD path status ms`
  - `rate_limit` (line 136): IP-based rate limiting
  - `app.add_middleware(CORSMiddleware, ...)` at line 1258 (end of file)
- `tests/test_logging.py` — tests log output from requests
- `tests/test_cors.py` — tests CORS headers (pattern reference)
- `tests/test_health.py` — tests health/ready endpoints

**Key facts:**
- `uuid` is already imported at line 13
- FastAPI/Starlette middleware order: last `@app.middleware("http")` registered = outermost = runs FIRST on incoming requests
- `request.state` is a safe place to carry per-request data between middlewares
- Existing test pattern: `os.environ.setdefault("MONGO_URL", ...)` + `TestClient(app)`

---

## Implementation Plan

### Step 1: Create feature branch
```
git checkout main
git checkout -b feat/build-ewa-request-id-20260320
```

### Step 2: Add `request_id` middleware to `backend/server.py`

Add AFTER the existing `rate_limit` middleware (so it is outermost and runs first):

```python
@app.middleware("http")
async def request_id(request: Request, call_next):
    rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = rid
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response
```

### Step 3: Update `log_requests` to include request ID

Modify the log line to include `request.state.request_id`:

```python
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    rid = getattr(request.state, "request_id", "-")
    logger.info("[%s] %s %s %d %dms rid=%s", timestamp, request.method, request.url.path, response.status_code, elapsed_ms, rid)
    return response
```

**Ordering note:** Since `request_id` middleware is defined AFTER `log_requests`, it wraps `log_requests` and runs FIRST. By the time `log_requests` runs, `request.state.request_id` is already set.

### Step 4: Create `tests/test_request_id.py`

Tests:
1. `test_request_id_header_present` — response always has `X-Request-ID`
2. `test_server_generated_request_id_is_valid_uuid` — auto-generated ID is valid UUID4
3. `test_client_provided_request_id_is_echoed` — client value is echoed back
4. `test_request_id_appears_in_log` — ID appears in log output

### Step 5: Run full test suite
```
cd /Users/nayslayer/projects/EmergentWebActions && ./scripts/test.sh
```

---

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Middleware ordering breaks log capture | Low | `request_id` defined last = outermost = sets state before `log_requests` runs |
| `request.state.request_id` not set when `log_requests` runs | Low | `getattr(request.state, "request_id", "-")` fallback avoids AttributeError |
| Client injects arbitrary string as request ID | Medium/Acceptable | No validation needed per spec; value is logged but not stored/executed |
| CORS doesn't expose `X-Request-ID` to browser clients | Low | Not a test requirement; can add `expose_headers` later if needed |
| Existing log test breaks due to changed log format | Low | Test checks for GET/path/status/ms — `rid=` suffix won't break it |

---

## Rollback Approach

```bash
git checkout main
git branch -D feat/build-ewa-request-id-20260320
```

All changes are isolated to the feature branch. No migrations, no data changes.

---

## Changed Files (expected)
- `backend/server.py` — add middleware, update log line
- `tests/test_request_id.py` — new test file (created)
