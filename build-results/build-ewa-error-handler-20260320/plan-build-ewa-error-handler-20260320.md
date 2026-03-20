# Global Error Handler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add global 500 and 404 JSON error handlers to `backend/server.py` and test both.

**Architecture:** FastAPI supports `@app.exception_handler(status_code_or_exception_class)` decorators. We add two handlers — one for generic `Exception` (unhandled 500s) and one for HTTP 404 (unknown routes). Both return a `JSONResponse` with the required schema. `JSONResponse` must be imported from `fastapi.responses`.

**Tech Stack:** Python 3.11, FastAPI, pytest, starlette TestClient

---

## File Map

| File | Action | What changes |
|------|--------|-------------|
| `backend/server.py` | Modify | Add `JSONResponse` to imports; add two exception handler functions at end of file |
| `tests/test_error_handlers.py` | Create | Pytest tests for 500 and 404 handlers |

---

## Pre-existing Known Issue

`tests/test_health.py::test_intentional_failure` contains `assert False` — this is a pre-existing failure used as a DR drill marker. It is NOT introduced by this task and will remain failing. All other existing tests must continue to pass.

---

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Generic `Exception` handler intercepts `HTTPException` raised in routes | Low | FastAPI routes HTTPException through its own handler first; only truly unhandled exceptions reach `Exception` handler |
| 404 handler swallows intentional `raise HTTPException(status_code=404)` route responses | Low | Acceptable — they'll still return JSON 404, which is correct behavior |
| `JSONResponse` import conflict | None | Not currently imported; add to fastapi import line |

## Rollback

```bash
git checkout main
git branch -D feat/build-ewa-error-handler-20260320
```

---

## Task 1: Create feature branch

**Files:** none

- [ ] **Step 1: Create and switch to feature branch**

```bash
cd /Users/nayslayer/projects/EmergentWebActions
git checkout -b feat/build-ewa-error-handler-20260320
```

Expected: `Switched to a new branch 'feat/build-ewa-error-handler-20260320'`

---

## Task 2: Add exception handlers to server.py

**Files:**
- Modify: `backend/server.py:1` (import line) and `backend/server.py:1312` (before shutdown event)

- [ ] **Step 1: Add `JSONResponse` to the fastapi import on line 1**

Current line 1:
```python
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Header, BackgroundTasks, Request, WebSocket, WebSocketDisconnect
```

Add `responses` import below it (new line after imports block):
```python
from fastapi.responses import JSONResponse
```

- [ ] **Step 2: Add the two exception handlers before the shutdown event (after line 1311)**

```python
@app.exception_handler(404)
async def not_found_handler(request: Request, exc: Exception):
    return JSONResponse({"error": "Not found", "status": 404}, status_code=404)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse({"error": "Internal server error", "status": 500}, status_code=500)
```

---

## Task 3: Write tests for both handlers

**Files:**
- Create: `tests/test_error_handlers.py`

- [ ] **Step 1: Write the test file**

```python
import os
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")

from fastapi.testclient import TestClient
from fastapi import Request
from fastapi.responses import JSONResponse
from backend.server import app

client = TestClient(app, raise_server_exceptions=False)


# --- 404 handler tests ---

def test_404_unknown_route_status():
    response = client.get("/this-route-does-not-exist-xyz")
    assert response.status_code == 404


def test_404_unknown_route_body():
    response = client.get("/this-route-does-not-exist-xyz")
    assert response.json() == {"error": "Not found", "status": 404}


def test_404_content_type_is_json():
    response = client.get("/this-route-does-not-exist-xyz")
    assert "application/json" in response.headers["content-type"]


# --- 500 handler tests ---

def test_500_unhandled_exception_status():
    # Temporarily add a route that raises an unhandled exception
    @app.get("/test-trigger-500-status")
    async def _raise():
        raise RuntimeError("boom")

    response = client.get("/test-trigger-500-status")
    assert response.status_code == 500


def test_500_unhandled_exception_body():
    @app.get("/test-trigger-500-body")
    async def _raise():
        raise RuntimeError("boom")

    response = client.get("/test-trigger-500-body")
    assert response.json() == {"error": "Internal server error", "status": 500}


def test_500_content_type_is_json():
    @app.get("/test-trigger-500-ct")
    async def _raise():
        raise RuntimeError("boom")

    response = client.get("/test-trigger-500-ct")
    assert "application/json" in response.headers["content-type"]
```

- [ ] **Step 2: Run failing tests first (TDD verify)**

```bash
cd /Users/nayslayer/projects/EmergentWebActions
python -m pytest tests/test_error_handlers.py -v 2>&1 | head -40
```

Expected: tests fail (handlers not yet added) OR file doesn't exist yet (this step comes after Task 2 in execution).

---

## Task 4: Run full test suite

- [ ] **Step 1: Run all tests**

```bash
cd /Users/nayslayer/projects/EmergentWebActions
./scripts/test.sh 2>&1 | tail -30
```

Expected: `test_error_handlers.py` all pass; `test_health.py` and `test_version.py` all pass except pre-existing `test_intentional_failure`.

---

## Task 5: Commit

- [ ] **Step 1: Commit changes**

```bash
cd /Users/nayslayer/projects/EmergentWebActions
git add backend/server.py tests/test_error_handlers.py
git commit -m "feat: add global 500 and 404 JSON error handlers"
```
