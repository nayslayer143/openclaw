#!/usr/bin/env python3
"""
OpenClaw model router.
Routes requests to the optimal Ollama model based on task type,
current VRAM usage, and historical performance data.
"""
from __future__ import annotations

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
                        str(Path.home() / ".openclaw" / "clawmson.db")))
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

_ps_cache: dict | None = None          # {"data": {...}, "fetched_at": float}
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
