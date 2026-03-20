# Plan: build-ewa-cors-headers-20260320

## Goal
Update CORS configuration in `backend/server.py` and add a test file verifying CORS headers.

## Current State (EXPLORE findings)
- `CORSMiddleware` already imported (line 4) and added to app (lines 1219-1225)
- Current config: `allow_credentials=True`, `allow_origins=["*"]`, `allow_methods=["*"]`, `allow_headers=["*"]`
- **Security issue**: `allow_credentials=True` + `allow_origins=["*"]` is invalid per CORS spec — browsers reject it; newer Starlette raises `ValueError`
- No existing CORS test file

## Changes Required

### 1. `backend/server.py` — lines 1219-1225
Update `add_middleware` call to:
- `allow_origins=["*"]`
- `allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"]`
- `allow_headers=["Content-Type", "Authorization"]`
- Remove `allow_credentials=True` (incompatible with wildcard origin)

Starlette `CORSMiddleware` handles OPTIONS preflight automatically when configured,
returning 200 with the correct `Access-Control-Allow-*` headers.

### 2. `tests/test_cors.py` — new file
Tests (following existing pattern: `os.environ.setdefault`, `TestClient(app)`):
- `test_cors_allow_origin_header` — GET /health with Origin header → `Access-Control-Allow-Origin: *`
- `test_cors_options_preflight_status` — OPTIONS /health with Origin + Access-Control-Request-Method → 200
- `test_cors_options_preflight_allow_methods` — OPTIONS preflight response includes allowed methods
- `test_cors_options_preflight_allow_headers` — OPTIONS preflight response includes allowed headers

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Starlette TestClient doesn't propagate CORS headers without Origin header | Medium | Always pass `headers={"Origin": "http://example.com"}` in test requests |
| Removing `allow_credentials=True` is a breaking change for any clients relying on cookies | Low | No known cookie-based auth in this API; API key auth via Authorization header |
| Tests in `test_health.py` include `test_intentional_failure` (always fails) | Known | Skip it; `./scripts/test.sh` may already account for this |

## Rollback
```
git checkout main
git branch -D feat/build-ewa-cors-headers-20260320
```
Or if already merged:
```
git revert <merge-commit>
```

## Branch
`feat/build-ewa-cors-headers-20260320`

## Files to Change
1. `backend/server.py` (edit lines 1219-1225)
2. `tests/test_cors.py` (new file)
