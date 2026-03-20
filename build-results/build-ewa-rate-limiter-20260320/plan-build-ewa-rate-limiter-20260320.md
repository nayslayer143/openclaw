# Plan: build-ewa-rate-limiter-20260320

## Goal
Add in-memory rate limiter to `backend/server.py` — 60 requests per minute per IP.
Over-limit requests return HTTP 429 `{"error": "Rate limit exceeded", "status": 429}`.

---

## Files to Change

| File | Change |
|------|--------|
| `backend/server.py` | Add `collections.defaultdict` import, module-level store + constant, new rate-limit middleware |
| `tests/test_rate_limiter.py` | New test file — 429 on excess, 200 within limit, body shape |

---

## Implementation Details

### 1. Import addition (server.py line ~7)
```python
from collections import defaultdict
```

### 2. Module-level state (after existing constants, ~line 55)
```python
RATE_LIMIT_REQUESTS = 60
RATE_LIMIT_WINDOW = 60  # seconds
_rate_limit_store: dict = defaultdict(list)
```

### 3. Middleware (after `log_requests`, ~line 122)
Define AFTER `log_requests` so it becomes the outermost layer and runs first:
```python
@app.middleware("http")
async def rate_limit(request: Request, call_next):
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        ip = forwarded_for.split(",")[0].strip()
    elif request.client:
        ip = request.client.host
    else:
        ip = "unknown"

    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW
    timestamps = _rate_limit_store[ip]

    # Purge expired timestamps
    while timestamps and timestamps[0] < window_start:
        timestamps.pop(0)

    if len(timestamps) >= RATE_LIMIT_REQUESTS:
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded", "status": 429},
        )

    timestamps.append(now)
    return await call_next(request)
```

### 4. Tests (`tests/test_rate_limiter.py`)
Use unique `X-Forwarded-For` IPs per test for isolation (TestClient always reports
`testclient` as host, so forwarded header is necessary).

```
test_rate_limit_429_after_exceeding_limit   — 61 requests, last is 429
test_rate_limit_200_within_limit            — 60 requests, all non-429
test_rate_limit_429_body_shape              — body has error + status fields
```

---

## Middleware Ordering Note
Starlette applies middlewares as a stack (LIFO). Defining `rate_limit` AFTER
`log_requests` in source means `rate_limit` wraps `log_requests` and runs first.
This is correct: rate-limited requests are rejected immediately; logging still
captures the 429 via `log_requests`.

---

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| IP spoofing via X-Forwarded-For | Low (internal use, AI agents) | Acceptable for this tier; noted in review |
| Memory growth if many unique IPs | Low (cleanup per request) | Old timestamps pruned each request |
| Test flakiness if real time.time() races across minute boundary | Very low | Each test uses isolated unique IP, all 61 requests fire in <1s |
| Middleware ordering breaks existing tests | Low | Existing tests are IP-agnostic and don't exceed 60 req/min |

---

## Rollback
```
git checkout main
git branch -D feat/build-ewa-rate-limiter-20260320
```
No database changes. No config changes. Pure in-memory, no persistence.

---

## Branch
`feat/build-ewa-rate-limiter-20260320`
