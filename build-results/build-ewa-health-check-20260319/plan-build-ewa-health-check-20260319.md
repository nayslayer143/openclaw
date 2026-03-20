# Plan — build-ewa-health-check-20260319

## Goal
Add `GET /health` to `backend/server.py` returning `{"status": "ok", "version": "1.0.0"}` with no auth requirement. Add a pytest test in `tests/test_health.py`.

## Explore Findings

| Finding | Detail |
|---------|--------|
| Existing `/api/health` | Line 580, `api_router`, returns `{"status": "healthy", "timestamp": ...}` — wrong path and body |
| Route prefix | `api_router` has prefix `/api`; new endpoint must be on `app` directly for path `/health` |
| Auth pattern | Authenticated routes use `Depends(verify_api_key)` — new endpoint omits this |
| Module-level DB init | `AsyncIOMotorClient(mongo_url)` at import; motor only connects on first query — safe for TestClient with dummy URL |
| Required env vars | Only `MONGO_URL` is required (KeyError); others have defaults |
| Test runner | `./scripts/test.sh` runs `pytest backend_test.py tests/ -v --tb=short` |
| httpx available | Yes — in requirements.txt |

## Implementation Steps

### Step 1 — Feature branch
```
git checkout -b feature/health-endpoint
```

### Step 2 — Add endpoint to backend/server.py
Insert after line 1302 (before `@app.on_event("shutdown")`):
```python
@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
```
Mount on `app` (not `api_router`) so the path resolves to `/health`, not `/api/health`.

### Step 3 — Create tests/test_health.py
```python
import os
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")

from fastapi.testclient import TestClient
from backend.server import app

client = TestClient(app)

def test_health_status_200():
    response = client.get("/health")
    assert response.status_code == 200

def test_health_body_status_ok():
    response = client.get("/health")
    assert response.json()["status"] == "ok"
```

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| `MONGO_URL` KeyError on import | Medium | Set via `os.environ.setdefault` before import |
| Port conflict with existing `/api/health` | None | Different path entirely |
| Auth accidentally applied | Low | No `Depends()` added |
| `version` value mismatch | Low | Task specifies `"1.0.0"` literally |

## Rollback
```
git checkout main && git branch -D feature/health-endpoint
```
Or if committed:
```
git revert HEAD
```

## Acceptance Criteria Mapping
- `GET /health` returns HTTP 200 → `test_health_status_200`
- Response body contains `{"status": "ok"}` → `test_health_body_status_ok`
- New test passes via pytest → both tests in `tests/test_health.py`
