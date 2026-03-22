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
