# Plan: build-ewa-readiness-probe-20260320

## Goal
Add `GET /ready` endpoint to `backend/server.py` that verifies the service is ready to accept traffic.

## Explore Summary

| File | Relevance |
|------|-----------|
| `backend/server.py:1349` | Existing `/health` endpoint — model for `/ready` placement |
| `backend/server.py:28` | `MONGO_URL` is the only `os.environ[...]` required var |
| `tests/test_health.py` | Where new `/ready` tests will be added |

## Design

### Endpoint
```python
@app.get("/ready")
async def ready():
    checks = {}
    checks["app"] = "ok"
    checks["env_mongo_url"] = "ok" if os.environ.get("MONGO_URL") else "missing"

    all_ok = all(v == "ok" for v in checks.values())
    if all_ok:
        return JSONResponse({"ready": True, "checks": checks}, status_code=200)
    return JSONResponse({"ready": False, "checks": checks}, status_code=503)
```

Placement: immediately after the `/health` endpoint (line 1351), before `/version`.

### Tests (added to `tests/test_health.py`)
1. `test_ready_returns_200` — happy path, assert status 200
2. `test_ready_body_ready_true` — assert `ready == True`
3. `test_ready_checks_object_present` — assert "checks" key in response
4. `test_ready_not_ready_returns_503` — patch `os.environ` to remove MONGO_URL, assert 503 and `ready == False`

## Risks

| Risk | Mitigation |
|------|-----------|
| `MONGO_URL` already consumed at import; patching at request time diverges from startup behavior | Document in code comment; the check is still meaningful for catch-all env-var patterns |
| `test_intentional_failure` already causes one test to fail | Pre-existing; not introduced by this change |
| Adding new `os.environ.get` call in hot path | Negligible overhead for a readiness endpoint |

## Rollback
```bash
git checkout main
git branch -D feat/build-ewa-readiness-probe-20260320
```

## Branch
`feat/build-ewa-readiness-probe-20260320`

## Changed Files
- `backend/server.py` — add `/ready` endpoint
- `tests/test_health.py` — add 4 new test cases
