# Plan: build-ewa-env-config-20260320

## Goal
Refactor `backend/server.py` to load PORT, HOST, DEBUG, APP_ENV from environment variables with sensible defaults. Add a `/config` endpoint returning non-sensitive config as JSON. Add tests.

## Explore Summary

| File | Role |
|------|------|
| `backend/server.py` | Main FastAPI app — all routes live here |
| `tests/test_health.py` | Health endpoint tests (pattern to follow) |
| `tests/test_version.py` | Version endpoint tests (closest pattern to /config) |

**Key observations:**
- `load_dotenv` is called at line 25; `os.environ.get()` is already the pattern throughout
- `/health` and `/version` are at lines 1349-1355 — `/config` goes here
- `mongo_url = os.environ['MONGO_URL']` (required, raises if missing) — PORT/HOST/DEBUG/APP_ENV use `get()` with defaults
- Tests use `os.environ.setdefault("MONGO_URL", ...)` at top, then `TestClient(app)`

## Implementation Plan

### Step 1 — Add config vars to server.py (after `load_dotenv`, ~line 25)
```python
# Server configuration
PORT = int(os.environ.get('PORT', '8000'))
HOST = os.environ.get('HOST', '0.0.0.0')
DEBUG = os.environ.get('DEBUG', 'false').lower() == 'true'
APP_ENV = os.environ.get('APP_ENV', 'development')
```

### Step 2 — Add `/config` endpoint (after `/health` at line ~1351)
```python
@app.get("/config")
async def config():
    return {"port": PORT, "host": HOST, "debug": DEBUG, "env": APP_ENV}
```

### Step 3 — Add `tests/test_config.py`
Tests:
- `test_config_status_200` — GET /config returns 200
- `test_config_has_port` — response has "port" key, is int
- `test_config_has_host` — response has "host" key, is str
- `test_config_has_debug` — response has "debug" key, is bool
- `test_config_has_env` — response has "env" key, is str
- `test_config_default_port` — default port is 8000 when PORT not set
- `test_config_default_env` — default env is "development" when APP_ENV not set
- `test_config_env_override` — APP_ENV override works via env var

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| `int(os.environ.get('PORT', '8000'))` raises ValueError if PORT="abc" | Low | Default is '8000' (valid); validation on bad input is acceptable behavior |
| Exposing HOST in /config could reveal internal network binding | Low | HOST is non-sensitive config; IP binding is visible from connection anyway |
| DEBUG flag accidentally set to true in production | Low | Default is false; deployment env sets it explicitly |
| Existing `/version` hardcodes `"env": "development"` — inconsistency with APP_ENV | Low | Out of scope for this task; noted for follow-up |

## Rollback

```bash
git checkout main
git branch -D feat/build-ewa-env-config-20260320
```

## Files Changed
- `backend/server.py` — add 4 config vars + 1 endpoint
- `tests/test_config.py` — new file with 8 tests
