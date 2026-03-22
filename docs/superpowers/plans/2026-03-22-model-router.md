# Model Router Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `scripts/model_router.py` — a VRAM-aware model routing layer that picks the optimal Ollama model per request type, with fallback chains and SQLite stats tracking, then wire it into `clawmson_chat.py` and `telegram-dispatcher.py`.

**Architecture:** `route(prompt, task_type, intent, has_image)` maps intent signals to task types, polls `GET /api/ps` (cached 10s, thread-safe) for VRAM state, walks a fallback chain (prefer loaded → fits in VRAM → unconditional last), logs to SQLite, and returns a model name string. `clawmson_chat.py` gains a `model=` parameter; the dispatcher passes intent and measures latency for `record_result()`.

**Tech Stack:** Python 3, `requests`, `sqlite3`, `threading`, `unittest.mock` for tests. No new dependencies.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `scripts/model_router.py` | All routing logic: constants, VRAM polling, chain selection, SQLite init + writes, public API |
| Create | `tests/test_model_router.py` | Unit tests for all public functions (mocked HTTP + SQLite) |
| Modify | `scripts/clawmson_chat.py` | Remove `CHAT_MODEL`/`VISION_MODEL` constants; add `model: str = None` param to `chat()` |
| Modify | `scripts/telegram-dispatcher.py` | Pass `intent` to `dispatch_conversation`; measure latency; call `record_result()` |

---

## Task 1: Scaffold model_router.py with constants and VRAM polling

**Files:**
- Create: `scripts/model_router.py`
- Create: `tests/test_model_router.py`

- [ ] **Step 1: Create the test file with a VRAM polling test**

```python
# tests/test_model_router.py
import sys, os
# Prevent model_router from creating ~/.openclaw/clawmson.db at import time
os.environ.setdefault("MODEL_ROUTER_SKIP_INIT", "1")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from unittest.mock import patch, MagicMock, patch
from pathlib import Path
import model_router as router

def test_get_loaded_models_parses_api_ps():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "models": [
            {"name": "qwen2.5:7b", "size": 5033164800, "size_vram": 4937433088},
            {"name": "qwen3:30b",  "size": 19000000000, "size_vram": 18500000000},
        ]
    }
    mock_resp.raise_for_status = MagicMock()
    with patch('model_router.requests.get', return_value=mock_resp):
        router._ps_cache = None  # bust cache
        models = router.get_loaded_models()
    assert "qwen2.5:7b" in models
    assert "qwen3:30b" in models

def test_get_loaded_models_returns_empty_on_error():
    with patch('model_router.requests.get', side_effect=Exception("down")):
        router._ps_cache = None
        models = router.get_loaded_models()
    assert models == []

def test_get_vram_used_gb_sums_size_vram_fields():
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "models": [
            {"name": "qwen2.5:7b",  "size_vram": 4937433088},
            {"name": "qwen3:30b",   "size_vram": 18500000000},
        ]
    }
    with patch('model_router.requests.get', return_value=mock_resp):
        router._ps_cache = None
        used = router._get_vram_used_gb()
    expected = (4937433088 + 18500000000) / 1e9
    assert abs(used - expected) < 0.001

def test_intent_to_task_covers_all_known_intents():
    known_intents = ["CONVERSATION", "UNCLEAR", "BUILD_TASK",
                     "REFERENCE_INGEST", "STATUS_QUERY", "DIRECT_COMMAND"]
    for intent in known_intents:
        result = router.INTENT_TO_TASK.get(intent)
        assert result is not None, f"{intent} has no entry in INTENT_TO_TASK"
        assert result in router.FALLBACK_CHAINS, \
            f"INTENT_TO_TASK[{intent}]={result!r} not in FALLBACK_CHAINS"
```

- [ ] **Step 2: Run test to verify it fails (module doesn't exist yet)**

```bash
cd ~/openclaw && python -m pytest .claude/worktrees/nervous-mclaren/tests/test_model_router.py -v 2>&1 | head -30
```
Expected: `ModuleNotFoundError: No module named 'model_router'`

- [ ] **Step 3: Create scripts/model_router.py with constants and VRAM polling**

```python
#!/usr/bin/env python3
from __future__ import annotations
"""
OpenClaw model router.
Routes requests to the optimal Ollama model based on task type,
current VRAM usage, and historical performance data.
"""

import os
import json
import time
import sqlite3
import threading
import datetime
import requests
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

OLLAMA_BASE_URL  = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
VRAM_CEILING_GB  = float(os.environ.get("OPENCLAW_VRAM_TOTAL_GB", "90.0"))
DB_PATH          = Path(os.environ.get("CLAWMSON_DB_PATH",
                        Path.home() / ".openclaw" / "clawmson.db"))
_PS_CACHE_TTL    = 10.0   # seconds

# ── Model sizes (GB, from bakeoff 2026-03-19) ────────────────────────────────

MODEL_SIZES_GB: dict[str, float] = {
    "qwen3:32b":           20.0,
    "qwen3:30b":           18.0,
    "qwen3-coder-next":    51.0,
    "devstral-small-2":    15.0,
    "deepseek-coder:33b":  18.0,
    "deepseek-coder:6.7b":  3.8,
    "llama3.1:70b":        42.0,
    "llama3.3:70b":        42.0,
    "qwen2.5:14b":          9.0,
    "qwen2.5:32b":         19.0,
    "qwen2.5:7b":           4.7,
    "llama3.2:3b":          2.0,
    "qwen3-vl:32b":        20.0,
    "nomic-embed-text":     0.3,
}

# ── Fallback chains per task type ────────────────────────────────────────────

FALLBACK_CHAINS: dict[str, list[str]] = {
    "chat":      ["qwen2.5:7b", "qwen2.5:14b", "qwen2.5:32b"],
    "code":      ["qwen3-coder-next", "devstral-small-2", "deepseek-coder:6.7b"],
    "research":  ["qwen3:30b", "qwen3:32b", "qwen2.5:32b"],
    "routing":   ["qwen2.5:7b", "llama3.2:3b"],
    "vision":    ["qwen3-vl:32b"],
    "embedding": ["nomic-embed-text"],
}

# ── Intent → task_type lookup ────────────────────────────────────────────────

INTENT_TO_TASK: dict[str, str] = {
    "CONVERSATION":     "chat",
    "UNCLEAR":          "chat",
    "BUILD_TASK":       "code",
    "REFERENCE_INGEST": "research",
    "STATUS_QUERY":     "routing",
    "DIRECT_COMMAND":   "routing",
}

# ── Env var overrides (backwards compat) ────────────────────────────────────

_ENV_OVERRIDES: dict[str, str] = {
    "chat":   "OLLAMA_CHAT_MODEL",
    "vision": "OLLAMA_VISION_MODEL",
}

# ── VRAM cache (thread-safe) ─────────────────────────────────────────────────

_ps_cache: dict | None = None          # {"models": [...], "fetched_at": float}
_ps_lock  = threading.Lock()


def _fetch_ps() -> dict:
    """Fetch /api/ps and return parsed JSON. Returns empty models list on error."""
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/ps", timeout=5)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[model_router] /api/ps error: {e}")
        return {"models": []}


def _get_ps() -> dict:
    """Return cached /api/ps result, refreshing if older than _PS_CACHE_TTL."""
    global _ps_cache
    with _ps_lock:
        now = time.monotonic()
        if _ps_cache is None or (now - _ps_cache["fetched_at"]) >= _PS_CACHE_TTL:
            data = _fetch_ps()
            _ps_cache = {"data": data, "fetched_at": now}
        return _ps_cache["data"]


def get_loaded_models() -> list[str]:
    """Return model names currently loaded in Ollama (from /api/ps cache)."""
    ps = _get_ps()
    return [m["name"] for m in ps.get("models", [])]


def _get_vram_used_gb() -> float:
    """Return total VRAM in use across all loaded models (GB)."""
    ps = _get_ps()
    total = sum(m.get("size_vram", 0) for m in ps.get("models", []))
    return total / 1e9
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd ~/openclaw && python -m pytest .claude/worktrees/nervous-mclaren/tests/test_model_router.py::test_get_loaded_models_parses_api_ps .claude/worktrees/nervous-mclaren/tests/test_model_router.py::test_get_loaded_models_returns_empty_on_error -v
```
Expected: both PASS

- [ ] **Step 5: Commit**

```bash
cd ~/openclaw/.claude/worktrees/nervous-mclaren
git add scripts/model_router.py tests/test_model_router.py
git commit -m "feat: model_router scaffold — constants, VRAM polling, get_loaded_models"
```

---

## Task 2: SQLite schema init

**Files:**
- Modify: `scripts/model_router.py`
- Modify: `tests/test_model_router.py`

- [ ] **Step 1: Write the failing test**

```python
# Add to tests/test_model_router.py
import sqlite3, tempfile, os

def test_init_db_creates_tables():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        tmp = f.name
    try:
        with patch.object(router, 'DB_PATH', Path(tmp)):
            router._init_db()
        conn = sqlite3.connect(tmp)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert "routing_log" in tables
        assert "model_stats" in tables
    finally:
        os.unlink(tmp)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/openclaw && python -m pytest .claude/worktrees/nervous-mclaren/tests/test_model_router.py::test_init_db_creates_tables -v
```
Expected: `AttributeError: module 'model_router' has no attribute '_init_db'`

- [ ] **Step 3: Add _init_db() to model_router.py (append after _get_vram_used_gb)**

```python
# ── SQLite init ───────────────────────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    with _get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS routing_log (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                task_type    TEXT    NOT NULL,
                model_chosen TEXT    NOT NULL,
                intent       TEXT,
                vram_used_gb REAL,
                timestamp    TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_routing_ts
                ON routing_log(timestamp);

            CREATE TABLE IF NOT EXISTS model_stats (
                model          TEXT    NOT NULL,
                task_type      TEXT    NOT NULL,
                call_count     INTEGER DEFAULT 0,
                success_count  INTEGER DEFAULT 0,
                avg_latency_ms REAL    DEFAULT 0.0,
                last_updated   TEXT,
                PRIMARY KEY (model, task_type)
            );
        """)


# Init on import (matches clawmson_db.py pattern)
# Guard allows tests to skip DB creation by setting MODEL_ROUTER_SKIP_INIT=1
if not os.environ.get("MODEL_ROUTER_SKIP_INIT"):
    _init_db()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd ~/openclaw && python -m pytest .claude/worktrees/nervous-mclaren/tests/test_model_router.py::test_init_db_creates_tables -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd ~/openclaw/.claude/worktrees/nervous-mclaren
git add scripts/model_router.py tests/test_model_router.py
git commit -m "feat: model_router SQLite init — routing_log + model_stats tables"
```

---

## Task 3: Chain selection logic

**Files:**
- Modify: `scripts/model_router.py`
- Modify: `tests/test_model_router.py`

- [ ] **Step 1: Write the failing tests**

```python
# Add to tests/test_model_router.py

def _mock_ps(loaded: list[str], vram_gb: float = 0.0):
    """Helper: patch _get_ps to return given loaded models at given VRAM usage."""
    size_vram = int(vram_gb * 1e9 / max(len(loaded), 1)) if loaded else 0
    return {
        "models": [
            {"name": n, "size": size_vram, "size_vram": size_vram}
            for n in loaded
        ]
    }

def test_select_prefers_loaded_model():
    with patch('model_router._get_ps', return_value=_mock_ps(["devstral-small-2"], 15.0)):
        model = router._select_from_chain(
            ["qwen3-coder-next", "devstral-small-2", "deepseek-coder:6.7b"],
            vram_used_gb=15.0
        )
    assert model == "devstral-small-2"

def test_select_falls_back_to_fits_in_vram():
    # Nothing loaded, but 10GB free — deepseek-coder:6.7b (3.8GB) fits
    with patch('model_router._get_ps', return_value=_mock_ps([], 80.0)):
        model = router._select_from_chain(
            ["qwen3-coder-next", "devstral-small-2", "deepseek-coder:6.7b"],
            vram_used_gb=80.0
        )
    assert model == "deepseek-coder:6.7b"

def test_select_unconditional_last_when_nothing_fits():
    # 89.5 GB used, nothing loaded, nothing fits
    with patch('model_router._get_ps', return_value=_mock_ps([], 89.5)):
        model = router._select_from_chain(
            ["qwen3-coder-next", "devstral-small-2", "deepseek-coder:6.7b"],
            vram_used_gb=89.5
        )
    assert model == "deepseek-coder:6.7b"  # last in chain

def test_select_single_model_chain():
    with patch('model_router._get_ps', return_value=_mock_ps([], 50.0)):
        model = router._select_from_chain(["qwen3-vl:32b"], vram_used_gb=50.0)
    assert model == "qwen3-vl:32b"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/openclaw && python -m pytest .claude/worktrees/nervous-mclaren/tests/test_model_router.py -k "test_select" -v
```
Expected: `AttributeError: module 'model_router' has no attribute '_select_from_chain'`

- [ ] **Step 3: Add _select_from_chain() to model_router.py**

```python
# ── Chain selection ───────────────────────────────────────────────────────────

def _select_from_chain(chain: list[str], vram_used_gb: float) -> str:
    """
    Pick the best model from a fallback chain:
    1. First model in chain that is currently loaded in Ollama
    2. First model in chain that fits in remaining VRAM
    3. Last model in chain unconditionally (Ollama handles load/evict)
    """
    loaded = set(get_loaded_models())
    remaining = VRAM_CEILING_GB - vram_used_gb

    # Pass 1: prefer already-loaded (no cold-load penalty)
    for model in chain:
        if model in loaded:
            return model

    # Pass 2: fits in remaining VRAM
    for model in chain:
        size = MODEL_SIZES_GB.get(model, 0.0)
        if size <= remaining:
            return model

    # Pass 3: unconditional last resort
    return chain[-1]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd ~/openclaw && python -m pytest .claude/worktrees/nervous-mclaren/tests/test_model_router.py -k "test_select" -v
```
Expected: all 4 PASS

- [ ] **Step 5: Commit**

```bash
cd ~/openclaw/.claude/worktrees/nervous-mclaren
git add scripts/model_router.py tests/test_model_router.py
git commit -m "feat: model_router chain selection — loaded > fits-in-vram > unconditional"
```

---

## Task 4: Public route() function

**Files:**
- Modify: `scripts/model_router.py`
- Modify: `tests/test_model_router.py`

- [ ] **Step 1: Write the failing tests**

```python
# Add to tests/test_model_router.py

def test_route_with_task_type_bypasses_classification():
    with patch('model_router._get_ps', return_value=_mock_ps(["qwen2.5:7b"], 4.7)):
        with patch('model_router._log_routing'):
            model = router.route("hello", task_type="chat")
    assert model == "qwen2.5:7b"

def test_route_intent_maps_to_task_type():
    with patch('model_router._get_ps', return_value=_mock_ps(["qwen3-coder-next"], 51.0)):
        with patch('model_router._log_routing'):
            model = router.route("build a login form", intent="BUILD_TASK")
    assert model == "qwen3-coder-next"

def test_route_has_image_forces_vision():
    with patch('model_router._get_ps', return_value=_mock_ps(["qwen3-vl:32b"], 20.0)):
        with patch('model_router._log_routing'):
            model = router.route("what's in this image?", has_image=True)
    assert model == "qwen3-vl:32b"

def test_route_env_override_bypasses_all_logic():
    with patch.dict(os.environ, {"OLLAMA_CHAT_MODEL": "my-custom-model"}):
        model = router.route("hello", task_type="chat")
    assert model == "my-custom-model"

def test_route_vision_env_override():
    with patch.dict(os.environ, {"OLLAMA_VISION_MODEL": "my-vision-model"}):
        model = router.route("what's in this?", has_image=True)
    assert model == "my-vision-model"

def test_route_unknown_intent_defaults_to_chat():
    with patch('model_router._get_ps', return_value=_mock_ps(["qwen2.5:7b"], 4.7)):
        with patch('model_router._log_routing'):
            model = router.route("yo", intent="UNKNOWN_THING")
    assert model == "qwen2.5:7b"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/openclaw && python -m pytest .claude/worktrees/nervous-mclaren/tests/test_model_router.py -k "test_route" -v
```
Expected: `AttributeError: module 'model_router' has no attribute 'route'`

- [ ] **Step 3: Add route() and _log_routing() to model_router.py**

```python
# ── Logging helper ────────────────────────────────────────────────────────────

def _log_routing(task_type: str, model: str, intent: str | None, vram_used_gb: float):
    ts = datetime.datetime.utcnow().isoformat()
    try:
        with _get_conn() as conn:
            conn.execute(
                "INSERT INTO routing_log (task_type, model_chosen, intent, vram_used_gb, timestamp)"
                " VALUES (?, ?, ?, ?, ?)",
                (task_type, model, intent, round(vram_used_gb, 3), ts)
            )
    except Exception as e:
        print(f"[model_router] routing_log write failed: {e}")


# ── Classification helper (non-Telegram callers only) ─────────────────────────

_CLASSIFY_PROMPT = """\
Classify this request into one word: chat, code, research, routing, vision, or embedding.
- code: writing/fixing/reviewing code or software
- research: reading, summarizing, studying URLs or documents
- routing: system status, queue checks, shell commands
- vision: analyzing an image
- embedding: generating embeddings
- chat: everything else (default)
Return ONLY the single word."""


def _classify_prompt(prompt: str) -> str:
    """Use qwen2.5:7b to classify prompt → task_type. Never calls route()."""
    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": "qwen2.5:7b",  # hardcoded — must not recurse via route()
                "messages": [
                    {"role": "system", "content": _CLASSIFY_PROMPT},
                    {"role": "user", "content": prompt[:500]},
                ],
                "stream": False,
            },
            timeout=15,
        )
        resp.raise_for_status()
        result = resp.json().get("message", {}).get("content", "").strip().lower()
        if result in FALLBACK_CHAINS:
            return result
    except Exception as e:
        print(f"[model_router] classification failed: {e}")
    return "chat"


# ── Public API ────────────────────────────────────────────────────────────────

def route(
    prompt: str,
    task_type: str = None,
    intent: str = None,
    has_image: bool = False,
) -> str:
    """
    Return the model name to use for this request.

    Priority:
    1. has_image=True → forces "vision" task_type
    2. task_type provided → use directly
    3. intent provided → map via INTENT_TO_TASK lookup
    4. neither → classify via qwen2.5:7b (non-Telegram path)

    Env var overrides (OLLAMA_CHAT_MODEL, OLLAMA_VISION_MODEL) bypass all logic.
    """
    # has_image overrides everything
    if has_image:
        task_type = "vision"

    # Resolve task_type
    if not task_type:
        if intent:
            task_type = INTENT_TO_TASK.get(intent.upper(), "chat")
        else:
            task_type = _classify_prompt(prompt)

    # Env var override (backwards compat)
    env_key = _ENV_OVERRIDES.get(task_type)
    if env_key:
        override = os.environ.get(env_key)
        if override:
            return override

    # Get VRAM state and pick from chain
    vram_used = _get_vram_used_gb()
    chain = FALLBACK_CHAINS.get(task_type, FALLBACK_CHAINS["chat"])
    model = _select_from_chain(chain, vram_used)

    _log_routing(task_type, model, intent, vram_used)
    return model
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd ~/openclaw && python -m pytest .claude/worktrees/nervous-mclaren/tests/test_model_router.py -k "test_route" -v
```
Expected: all 5 PASS

- [ ] **Step 5: Commit**

```bash
cd ~/openclaw/.claude/worktrees/nervous-mclaren
git add scripts/model_router.py tests/test_model_router.py
git commit -m "feat: model_router route() — intent mapping, VRAM selection, env overrides"
```

---

## Task 5: record_result() and get_stats()

**Files:**
- Modify: `scripts/model_router.py`
- Modify: `tests/test_model_router.py`

- [ ] **Step 1: Write the failing tests**

```python
# Add to tests/test_model_router.py

def test_record_result_updates_stats():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        tmp = f.name
    try:
        with patch.object(router, 'DB_PATH', Path(tmp)):
            router._init_db()
            router.record_result("qwen2.5:7b", "chat", 1000.0, success=True)
            router.record_result("qwen2.5:7b", "chat",  500.0, success=True)
            stats = router.get_stats()
        row = next(r for r in stats if r["model"] == "qwen2.5:7b" and r["task_type"] == "chat")
        assert row["call_count"] == 2
        assert row["success_count"] == 2
        # CMA: (0*0 + 1000) / 1 = 1000, then (1000*1 + 500) / 2 = 750
        assert abs(row["avg_latency_ms"] - 750.0) < 0.01
    finally:
        os.unlink(tmp)

def test_record_result_tracks_failures():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        tmp = f.name
    try:
        with patch.object(router, 'DB_PATH', Path(tmp)):
            router._init_db()
            router.record_result("qwen2.5:7b", "chat", 100.0, success=False)
            router.record_result("qwen2.5:7b", "chat", 200.0, success=True)
            stats = router.get_stats()
        row = next(r for r in stats if r["model"] == "qwen2.5:7b")
        assert row["call_count"] == 2
        assert row["success_count"] == 1
    finally:
        os.unlink(tmp)

def test_record_result_silently_survives_db_error():
    # Should not raise even if DB is broken
    with patch('model_router._get_conn', side_effect=Exception("db gone")):
        router.record_result("qwen2.5:7b", "chat", 100.0)  # must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/openclaw && python -m pytest .claude/worktrees/nervous-mclaren/tests/test_model_router.py -k "test_record" -v
```
Expected: `AttributeError: module 'model_router' has no attribute 'record_result'`

- [ ] **Step 3: Add record_result() and get_stats() to model_router.py**

```python
def record_result(
    model: str,
    task_type: str,
    latency_ms: float,
    success: bool = True,
) -> None:
    """
    Record inference outcome. Updates model_stats with cumulative moving average.
    Never raises — stats must not block inference.
    """
    ts = datetime.datetime.utcnow().isoformat()
    try:
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT call_count, avg_latency_ms FROM model_stats"
                " WHERE model = ? AND task_type = ?",
                (model, task_type)
            ).fetchone()
            if row:
                old_count = row["call_count"]
                old_avg   = row["avg_latency_ms"]
                new_count = old_count + 1
                new_avg   = (old_avg * old_count + latency_ms) / new_count
                conn.execute(
                    "UPDATE model_stats"
                    " SET call_count=?, success_count=success_count+?, avg_latency_ms=?, last_updated=?"
                    " WHERE model=? AND task_type=?",
                    (new_count, 1 if success else 0, new_avg, ts, model, task_type)
                )
            else:
                conn.execute(
                    "INSERT INTO model_stats"
                    " (model, task_type, call_count, success_count, avg_latency_ms, last_updated)"
                    " VALUES (?, ?, 1, ?, ?, ?)",
                    (model, task_type, 1 if success else 0, latency_ms, ts)
                )
    except Exception as e:
        print(f"[model_router] record_result failed: {e}")


def get_stats() -> list[dict]:
    """
    Return all rows from model_stats as list of dicts.
    Keys: model, task_type, call_count, success_count, avg_latency_ms, last_updated.
    """
    try:
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT model, task_type, call_count, success_count,"
                "       avg_latency_ms, last_updated FROM model_stats"
                " ORDER BY model, task_type"
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"[model_router] get_stats failed: {e}")
        return []
```

- [ ] **Step 4: Run all tests to verify they pass**

```bash
cd ~/openclaw && python -m pytest .claude/worktrees/nervous-mclaren/tests/test_model_router.py -v
```
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
cd ~/openclaw/.claude/worktrees/nervous-mclaren
git add scripts/model_router.py tests/test_model_router.py
git commit -m "feat: model_router record_result + get_stats — CMA latency tracking"
```

---

## Task 6: Update clawmson_chat.py

**Files:**
- Modify: `scripts/clawmson_chat.py`

- [ ] **Step 1: Write a failing test for the new chat() signature**

```python
# Add to tests/test_model_router.py
import clawmson_chat as chat_mod

def test_chat_accepts_model_parameter():
    """chat() must accept a model= kwarg and use it."""
    import inspect
    sig = inspect.signature(chat_mod.chat)
    assert "model" in sig.parameters, "chat() must have a model= parameter"

def test_chat_module_has_no_hardcoded_model_constants():
    """CHAT_MODEL and VISION_MODEL constants must be removed."""
    assert not hasattr(chat_mod, "CHAT_MODEL"), \
        "CHAT_MODEL constant must be removed (shadows router)"
    assert not hasattr(chat_mod, "VISION_MODEL"), \
        "VISION_MODEL constant must be removed (shadows router)"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/openclaw && python -m pytest .claude/worktrees/nervous-mclaren/tests/test_model_router.py -k "test_chat" -v
```
Expected: `FAIL — CHAT_MODEL found` (constants still present)

- [ ] **Step 3: Update clawmson_chat.py**

Make these targeted edits to `scripts/clawmson_chat.py`:

**Remove** lines 15-16 (the two constants):
```python
# DELETE these two lines:
CHAT_MODEL      = os.environ.get("OLLAMA_CHAT_MODEL",   "qwen2.5:7b")
VISION_MODEL    = os.environ.get("OLLAMA_VISION_MODEL", "qwen3-vl:32b")
```

**Replace** the `chat()` signature and model selection (lines 38-46):
```python
def chat(history: list, user_message: str, has_image: bool = False,
         model: str = None) -> str:
    """
    Send conversation history + new user message to Ollama.
    history: list of {"role": "user"|"assistant", "content": str}
    model: override model selection (if None, router decides)
    Returns the assistant's reply as a string.
    """
    if model is None:
        import model_router as router
        # Pass has_image so router applies the vision override internally
        model = router.route(user_message, has_image=has_image)
    system_prompt = _load_system_prompt()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd ~/openclaw && python -m pytest .claude/worktrees/nervous-mclaren/tests/test_model_router.py -k "test_chat" -v
```
Expected: both PASS

- [ ] **Step 5: Run full test suite**

```bash
cd ~/openclaw && python -m pytest .claude/worktrees/nervous-mclaren/tests/test_model_router.py -v
```
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
cd ~/openclaw/.claude/worktrees/nervous-mclaren
git add scripts/clawmson_chat.py
git commit -m "feat: clawmson_chat uses model_router — remove hardcoded constants, add model= param"
```

---

## Task 7: Wire latency tracking into telegram-dispatcher.py

**Files:**
- Modify: `scripts/telegram-dispatcher.py`

The dispatcher's `_conversation_thread` (line 341) calls `llm.chat()` but doesn't know which model was used or how long it took. We need to:
1. Pass `intent` into `dispatch_conversation` so the router can skip re-classification
2. Wrap the `llm.chat()` call with a timer
3. Call `router.record_result()` after inference

- [ ] **Step 1: Add model_router import and error-sentinel constant to telegram-dispatcher.py**

At the top of `telegram-dispatcher.py`, after the existing imports, add:
```python
import model_router as router

# Prefixes that indicate Ollama inference failed (from clawmson_chat.py error returns)
_OLLAMA_ERROR_PREFIXES = (
    "Ollama is not reachable",
    "Ollama timed out",
    "Ollama HTTP error",
    "Chat error",
)
```

- [ ] **Step 2: Update _conversation_thread to accept intent and track latency**

Replace `_conversation_thread` (lines 341-347):
```python
def _conversation_thread(chat_id: str, effective_text: str,
                         has_image: bool, intent: str = None):
    """Called in a background thread. Fetches Ollama reply and sends it."""
    send_typing(chat_id)
    history    = db.get_history(chat_id, limit=50)
    task_type  = "vision" if has_image else None
    model_name = router.route(effective_text, task_type=task_type, intent=intent,
                               has_image=has_image)
    t0    = time.monotonic()
    reply = llm.chat(history, effective_text, has_image=has_image, model=model_name)
    elapsed_ms = (time.monotonic() - t0) * 1000

    # Record result — check for Ollama error sentinels before marking success
    success = not any(reply.startswith(e) for e in _OLLAMA_ERROR_PREFIXES)
    router.record_result(model_name, task_type or "chat", elapsed_ms, success=success)

    db.save_message(chat_id, "assistant", reply)
    send(chat_id, reply)
```

- [ ] **Step 3: Update dispatch_conversation to pass intent**

Replace `dispatch_conversation` (lines 350-356):
```python
def dispatch_conversation(chat_id: str, effective_text: str,
                          has_image: bool = False, intent: str = None):
    t = threading.Thread(
        target=_conversation_thread,
        args=(chat_id, effective_text, has_image, intent),
        daemon=True
    )
    t.start()
```

- [ ] **Step 4: Pass intent at the two call sites that know it**

In `handle_message`, the `intent` variable is resolved at line 506. Update the final `dispatch_conversation` call (line 543) to pass it:
```python
# Default: CONVERSATION  (line ~543)
dispatch_conversation(chat_id, effective_text, has_image=has_image, intent=intent)
```

The early-exit call at line 487 (media without URL) doesn't have intent yet — leave that one as-is (intent=None, router will use task_type from has_image flag).

There is also a third call site in `_reference_thread` (line ~373) that does a conversational follow-up after URL ingestion:
```python
dispatch_conversation(chat_id, context_note)
```
Leave this unchanged — no intent is available here. The router will classify via qwen2.5:7b (the non-Telegram path). Latency tracking still fires from `_conversation_thread`.

- [ ] **Step 5: Remove the stale startup log line that references OLLAMA_CHAT_MODEL default**

In `main()` at line ~552, update the startup print to not reference the removed env var default:
```python
# Replace:
f" / {os.environ.get('OLLAMA_CHAT_MODEL', 'qwen2.5:7b')}")
# With:
f" / model routing active")
```

- [ ] **Step 6: Add a test that record_result fires from the dispatcher thread**

Add to `tests/test_model_router.py`:
```python
def test_conversation_thread_calls_record_result():
    """_conversation_thread must call router.record_result after inference."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
    import telegram_dispatcher as dispatcher  # noqa: rename if needed

    with patch('clawmson_db.get_history', return_value=[]), \
         patch('clawmson_chat.chat', return_value="hi"), \
         patch('model_router.route', return_value="qwen2.5:7b"), \
         patch('model_router.record_result') as mock_record, \
         patch('telegram_dispatcher.send'), \
         patch('clawmson_db.save_message'):
        dispatcher._conversation_thread("123", "hello", False, "CONVERSATION")

    mock_record.assert_called_once()
    args = mock_record.call_args[0]
    assert args[0] == "qwen2.5:7b"   # model
    assert args[1] == "chat"          # task_type
    assert isinstance(args[2], float) # latency_ms
```

- [ ] **Step 7: Run full test suite**

```bash
cd ~/openclaw && python -m pytest .claude/worktrees/nervous-mclaren/tests/test_model_router.py -v
```
Expected: all tests PASS

- [ ] **Step 8: Commit**

```bash
cd ~/openclaw/.claude/worktrees/nervous-mclaren
git add scripts/telegram-dispatcher.py
git commit -m "feat: dispatcher wires model_router — intent passthrough, latency tracking, record_result"
```

---

## Task 8: Smoke test

- [ ] **Step 1: Verify model_router imports cleanly**

```bash
cd ~/openclaw && python -c "
import sys; sys.path.insert(0, 'scripts')
import model_router as r
print('loaded_models:', r.get_loaded_models())
print('route(chat):', r.route('hello', task_type='chat'))
print('route(code):', r.route('fix my bug', intent='BUILD_TASK'))
print('stats:', r.get_stats())
print('OK')
"
```
Expected: prints loaded models (may be empty if Ollama has nothing loaded), model names for each route call, empty stats list, and "OK".

- [ ] **Step 2: Verify clawmson_chat imports cleanly**

```bash
cd ~/openclaw && python -c "
import sys; sys.path.insert(0, 'scripts')
import clawmson_chat
import inspect
sig = inspect.signature(clawmson_chat.chat)
print('chat signature:', sig)
assert 'model' in sig.parameters
assert not hasattr(clawmson_chat, 'CHAT_MODEL')
print('OK')
"
```
Expected: prints signature with `model` param, prints "OK".

- [ ] **Step 3: Final commit tag**

```bash
cd ~/openclaw/.claude/worktrees/nervous-mclaren
git add -p  # review any unstaged changes
git commit -m "feat: model router complete — smoke test OK" --allow-empty
```
