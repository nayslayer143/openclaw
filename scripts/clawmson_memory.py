#!/usr/bin/env python3
from __future__ import annotations
"""
Clawmson Hermes 5-Layer Memory System.

Layers:
  1. SensoryBuffer     — last N messages in RAM, passed directly as Ollama history
  2. ShortTermMemory   — rolling SQLite window, auto-summarized when full
  3. EpisodicMemory    — significant events with valence tags + nomic embeddings
  4. SemanticMemory    — extracted facts/preferences + nomic embeddings
  5. ProceduralMemory  — trigger→action mappings, explicit + auto-proposed

Public API (via MemoryManager):
  memory.sensory(chat_id)              → list of {role, content} dicts
  memory.retrieve(chat_id, query="")   → formatted context string for system prompt
  memory.ingest_async(chat_id, role, content)  — call AFTER send()
  memory.add_procedure(chat_id, trigger, action) → int id
  memory.approve_procedure(chat_id, proc_id)
  memory.reject_procedure(chat_id, proc_id)
  memory.stats(chat_id)               → dict of counts per layer
  memory.clear(chat_id, layer="all")
"""

import os
import json
import datetime
import threading
import requests
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys

_SCRIPTS = Path(__file__).parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import clawmson_db as db

# ── Config ────────────────────────────────────────────────────────────────────

OLLAMA_BASE_URL  = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
MEMORY_MODEL     = os.environ.get("OLLAMA_CHAT_MODEL", "qwen2.5:7b")
EMBED_MODEL      = os.environ.get("CLAWMSON_EMBED_MODEL", "nomic-embed-text")
SENSORY_WINDOW   = int(os.environ.get("CLAWMSON_SENSORY_WINDOW", "10"))
STM_MAX_ROWS     = int(os.environ.get("CLAWMSON_STM_MAX_ROWS", "50"))
STM_BATCH        = int(os.environ.get("CLAWMSON_STM_BATCH", "25"))
STM_RETRIEVE_N   = int(os.environ.get("CLAWMSON_STM_RETRIEVE_COUNT", "2"))
EPISODIC_TOP_K   = int(os.environ.get("CLAWMSON_EPISODIC_TOP_K", "3"))
EPISODIC_MIN_SIM = float(os.environ.get("CLAWMSON_EPISODIC_MIN_SIM", "0.6"))
SEMANTIC_TOP_K   = int(os.environ.get("CLAWMSON_SEMANTIC_TOP_K", "5"))
SEMANTIC_MIN_SIM = float(os.environ.get("CLAWMSON_SEMANTIC_MIN_SIM", "0.5"))
SEMANTIC_MIN_CONF= float(os.environ.get("CLAWMSON_SEMANTIC_MIN_CONF", "0.6"))
PROC_THRESHOLD   = int(os.environ.get("CLAWMSON_PROC_THRESHOLD", "3"))

_DEFAULT_PROBE   = "what do you know about Jordan and the current projects?"

# ── Utility: Ollama calls ─────────────────────────────────────────────────────

def _embed(text: str) -> bytes:
    """Embed text via nomic-embed-text. Returns numpy float32 bytes."""
    import numpy as np
    resp = requests.post(
        f"{OLLAMA_BASE_URL}/api/embed",
        json={"model": EMBED_MODEL, "input": text},
        timeout=30
    )
    resp.raise_for_status()
    vector = resp.json()["embeddings"][0]
    return np.array(vector, dtype=np.float32).tobytes()


def _cosine(a: bytes, b: bytes) -> float:
    """Cosine similarity between two serialized numpy float32 vectors."""
    import numpy as np
    va = np.frombuffer(a, dtype=np.float32)
    vb = np.frombuffer(b, dtype=np.float32)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    if denom == 0:
        return 0.0
    return float(np.dot(va, vb) / denom)


def _llm_json(prompt: str, system: str = "") -> dict:
    """Call Ollama with JSON format. Returns parsed dict or {} on failure."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={"model": MEMORY_MODEL, "messages": messages,
                  "stream": False, "format": "json"},
            timeout=60
        )
        resp.raise_for_status()
        raw = resp.json().get("message", {}).get("content", "{}")
        return json.loads(raw)
    except Exception as e:
        print(f"[memory] LLM JSON call failed: {e}")
        return {}


def _llm_text(prompt: str) -> str:
    """Call Ollama for plain text. Returns string."""
    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={"model": MEMORY_MODEL,
                  "messages": [{"role": "user", "content": prompt}],
                  "stream": False},
            timeout=60
        )
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "").strip()
    except Exception as e:
        print(f"[memory] LLM text call failed: {e}")
        return ""


def _now() -> str:
    return datetime.datetime.utcnow().isoformat()


# ════════════════════════════════════════════════════════════════════════════
# Layer 1 — SensoryBuffer
# ════════════════════════════════════════════════════════════════════════════

class SensoryBuffer:
    """RAM-backed deque of last N messages per chat_id. No DB reads after warm-up."""

    def __init__(self, window: int = SENSORY_WINDOW):
        self._window  = window
        self._buffers: dict[str, deque] = {}
        self._seeded:  set[str]         = set()
        self._lock = threading.Lock()

    def get(self, chat_id: str) -> list:
        """Return messages oldest-first as list of {role, content} dicts."""
        with self._lock:
            if chat_id not in self._seeded:
                self._seed(chat_id)
            return list(self._buffers.get(chat_id, deque()))

    def push(self, chat_id: str, role: str, content: str):
        with self._lock:
            if chat_id not in self._seeded:
                self._seed(chat_id)
            if chat_id not in self._buffers:
                self._buffers[chat_id] = deque(maxlen=self._window)
            self._buffers[chat_id].append({"role": role, "content": content})

    def _seed(self, chat_id: str):
        rows = db.get_history(chat_id, limit=self._window)
        buf  = deque(maxlen=self._window)
        for r in rows:
            buf.append({"role": r["role"], "content": r["content"]})
        self._buffers[chat_id] = buf
        self._seeded.add(chat_id)
