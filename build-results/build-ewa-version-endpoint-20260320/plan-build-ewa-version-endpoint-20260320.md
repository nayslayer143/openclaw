# Plan: build-ewa-version-endpoint-20260320

## Goal
Add `GET /version` endpoint to `backend/server.py` returning `{"version": "1.0.0", "service": "EmergentWebActions", "env": "development"}`, with no auth required. Add a pytest test in `tests/`.

## Explore Findings

| Item | Detail |
|------|--------|
| Route pattern | Direct `@app.get(...)` on the `app` object (not `api_router`) for top-level paths |
| Existing analogue | `@app.get("/health")` at line 1304, returns a plain dict |
| Test pattern | `tests/test_health.py`: sets `MONGO_URL` env var before importing app, uses `TestClient(app)` |
| Intentional failure | `test_intentional_failure` in test_health.py always fails — pre-existing, not our concern |
| Router prefix | `api_router` has prefix `/api` — `/version` must be on `app` directly |

## Implementation Steps (TDD)

### 1. Create feature branch
```
git checkout -b feat/build-ewa-version-endpoint-20260320
```

### 2. RED — Write failing test first
File: `tests/test_version.py`
```python
import os
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")

from fastapi.testclient import TestClient
from backend.server import app

client = TestClient(app)


def test_version_status_200():
    response = client.get("/version")
    assert response.status_code == 200


def test_version_field_version():
    response = client.get("/version")
    assert response.json()["version"] == "1.0.0"


def test_version_field_service():
    response = client.get("/version")
    assert response.json()["service"] == "EmergentWebActions"


def test_version_field_env():
    response = client.get("/version")
    assert response.json()["env"] == "development"
```

Run and confirm all 4 tests fail with 404 (feature missing).

### 3. GREEN — Add endpoint
In `backend/server.py`, after line 1306 (after the `/health` route), add:
```python
@app.get("/version")
async def version():
    return {"version": "1.0.0", "service": "EmergentWebActions", "env": "development"}
```

Run and confirm all 4 new tests pass.

### 4. Verify all existing tests still pass
Run `./scripts/test.sh` (or `pytest tests/`).
Note: `test_intentional_failure` is a pre-existing deliberate failure (DR drill); it is not a regression.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| `test_intentional_failure` shows as failure | Low | Pre-existing; not a regression introduced by this change |
| MongoDB not running locally | Low | TestClient + `setdefault` MONGO_URL pattern already established |
| `env` field hardcoded to `"development"` | Low | Task spec explicitly says `"development"` — acceptable for now |
| Route collision with `api_router` | Low | `api_router` has `/api` prefix; `/version` on `app` is unambiguous |

## Rollback
```
git checkout main
git branch -D feat/build-ewa-version-endpoint-20260320
```

## Changed Files
- `tests/test_version.py` (new)
- `backend/server.py` (add 3 lines after `/health` route)
