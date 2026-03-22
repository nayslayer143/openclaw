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


# ════════════════════════════════════════════════════════════════════════════
# Layer 2 — ShortTermMemory
# ════════════════════════════════════════════════════════════════════════════

class ShortTermMemory:
    """Rolling window of conversations in SQLite. Auto-summarizes when full."""

    def __init__(self, max_rows: int = STM_MAX_ROWS, batch: int = STM_BATCH,
                 retrieve_n: int = STM_RETRIEVE_N):
        self._max_rows   = max_rows
        self._batch      = batch
        self._retrieve_n = retrieve_n

    def check_and_summarize(self, chat_id: str):
        """Called after each ingest. Archives oldest batch if active count > max_rows."""
        with db._get_conn() as conn:
            active = conn.execute(
                "SELECT COUNT(*) FROM conversations WHERE chat_id=? AND archived=0",
                (chat_id,)
            ).fetchone()[0]
            if active <= self._max_rows:
                return
            rows = conn.execute(
                "SELECT id, content, role, timestamp FROM conversations"
                " WHERE chat_id=? AND archived=0 ORDER BY id ASC LIMIT ?",
                (chat_id, self._batch)
            ).fetchall()

        if not rows:
            return

        from_ts = rows[0]["timestamp"]
        to_ts   = rows[-1]["timestamp"]
        exchange_text = "\n".join(
            f"{r['role'].capitalize()}: {r['content'][:200]}" for r in rows
        )
        prompt = (
            f"Summarize these {len(rows)} conversation exchanges in 3-5 concise sentences. "
            f"Focus on topics discussed, decisions made, and key information exchanged.\n\n"
            f"{exchange_text}"
        )
        summary = _llm_text(prompt)
        if not summary:
            summary = f"(Summary unavailable for {len(rows)} messages from {from_ts[:10]})"

        ids = [r["id"] for r in rows]
        ts  = _now()
        with db._get_conn() as conn:
            conn.execute(
                "INSERT INTO stm_summaries (chat_id, summary, from_ts, to_ts, timestamp)"
                " VALUES (?, ?, ?, ?, ?)",
                (chat_id, summary, from_ts, to_ts, ts)
            )
            conn.execute(
                f"UPDATE conversations SET archived=1"
                f" WHERE id IN ({','.join('?' * len(ids))})",
                ids
            )

    def retrieve(self, chat_id: str) -> str:
        """Return last N summaries as a single string, or '' if none."""
        with db._get_conn() as conn:
            rows = conn.execute(
                "SELECT summary FROM stm_summaries WHERE chat_id=?"
                " ORDER BY id DESC LIMIT ?",
                (chat_id, self._retrieve_n)
            ).fetchall()
        if not rows:
            return ""
        return " ".join(r["summary"] for r in reversed(rows))


# ════════════════════════════════════════════════════════════════════════════
# Layer 3 — EpisodicMemory
# ════════════════════════════════════════════════════════════════════════════

class EpisodicMemory:
    """Significant events stored with valence tags and nomic embeddings."""

    _RULE_KEYWORDS = {
        "deploy", "deployed", "broke", "broken", "failed", "failure",
        "fixed", "shipped", "decided", "decision", "remember", "never again",
        "that worked", "rollback", "rolled back", "merged", "approved",
        "launched", "crashed", "error", "reverted"
    }

    def _rule_pass(self, text: str) -> bool:
        lower = text.lower()
        return any(kw in lower for kw in self._RULE_KEYWORDS)

    def ingest(self, chat_id: str, user_msg: str, assistant_msg: str):
        """Check significance and store if episodic. Called from background thread."""
        combined = f"{user_msg}\n{assistant_msg}"
        if not self._rule_pass(combined):
            return

        prompt = (
            f"User said: {user_msg[:500]}\n"
            f"Assistant replied: {assistant_msg[:500]}\n\n"
            f"Is this exchange episodically significant — a notable event, decision, "
            f"outcome, or failure worth remembering? "
            f"Return JSON: {{\"significant\": bool, \"summary\": \"1-sentence description\", "
            f"\"valence\": \"positive|negative|neutral|critical\"}}"
        )
        result = _llm_json(prompt)
        if not result.get("significant"):
            return

        summary = result.get("summary", combined[:200])
        valence = result.get("valence", "neutral")
        if valence not in ("positive", "negative", "neutral", "critical"):
            valence = "neutral"

        try:
            embedding = _embed(summary)
        except Exception as e:
            print(f"[memory/episodic] embed failed: {e}")
            embedding = None

        ts = _now()
        with db._get_conn() as conn:
            conn.execute(
                "INSERT INTO episodic_memories"
                " (chat_id, content, summary, timestamp, valence, embedding)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (chat_id, combined[:1000], summary, ts, valence, embedding)
            )

    def retrieve(self, chat_id: str, query: str,
                 embed_fn=None, min_sim: float = EPISODIC_MIN_SIM) -> list:
        """Return top-K formatted episode strings by cosine similarity."""
        embed_fn = embed_fn or _embed
        try:
            q_emb = embed_fn(query)
        except Exception:
            return []

        with db._get_conn() as conn:
            rows = conn.execute(
                "SELECT summary, timestamp, valence, embedding"
                " FROM episodic_memories WHERE chat_id=? AND embedding IS NOT NULL",
                (chat_id,)
            ).fetchall()

        if not rows:
            return []

        scored = []
        for r in rows:
            sim = _cosine(q_emb, r["embedding"])
            if sim >= min_sim:
                date = r["timestamp"][:10]
                scored.append((sim, f"[Episodic] [{date}, {r['valence']}] {r['summary']}"))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [text for _, text in scored[:EPISODIC_TOP_K]]


# ════════════════════════════════════════════════════════════════════════════
# Layer 4 — SemanticMemory
# ════════════════════════════════════════════════════════════════════════════

class SemanticMemory:
    """Extracted facts and preferences stored with nomic embeddings."""

    _RULE_PATTERNS = (
        "i prefer", "i always", "i hate", "i love", "i never", "i use",
        "we use", "we always", "we never", "the model is", "jordan likes",
        "jordan prefers", "jordan hates", "never use", "always use",
    )

    def _rule_pass(self, text: str) -> bool:
        lower = text.lower()
        return any(p in lower for p in self._RULE_PATTERNS)

    def ingest(self, chat_id: str, user_msg: str, assistant_msg: str,
               source: str = "inferred"):
        """Extract facts/preferences and upsert into semantic_facts."""
        combined = f"{user_msg}\n{assistant_msg}"
        if not self._rule_pass(combined):
            return

        prompt = (
            f"Message: {combined[:800]}\n\n"
            f"Extract any stated facts, preferences, or habits as a JSON list. "
            f"Each item: {{\"key\": \"short label\", \"value\": \"full fact sentence\", "
            f"\"confidence\": 0.0-1.0}}. Return {{\"facts\": []}} if nothing notable."
        )
        result = _llm_json(prompt)
        facts  = result.get("facts", [])
        if not facts:
            return

        ts = _now()
        for fact in facts:
            key   = str(fact.get("key", ""))[:100]
            value = str(fact.get("value", ""))[:500]
            conf  = float(fact.get("confidence", 0.7))
            if not key or not value:
                continue
            try:
                embedding = _embed(value)
            except Exception:
                embedding = None
            with db._get_conn() as conn:
                conn.execute(
                    "INSERT INTO semantic_facts"
                    " (chat_id, key, value, confidence, source, timestamp, embedding)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)"
                    " ON CONFLICT(chat_id, key) DO UPDATE SET"
                    " value=excluded.value, confidence=excluded.confidence,"
                    " timestamp=excluded.timestamp, embedding=excluded.embedding",
                    (chat_id, key, value, conf, source, ts, embedding)
                )

    def ingest_explicit(self, chat_id: str, key: str, value: str):
        """Store a fact explicitly (/remember fact: key = value)."""
        try:
            embedding = _embed(value)
        except Exception:
            embedding = None
        ts = _now()
        with db._get_conn() as conn:
            conn.execute(
                "INSERT INTO semantic_facts"
                " (chat_id, key, value, confidence, source, timestamp, embedding)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(chat_id, key) DO UPDATE SET"
                " value=excluded.value, confidence=1.0,"
                " timestamp=excluded.timestamp, embedding=excluded.embedding",
                (chat_id, key[:100], value[:500], 1.0, "explicit", ts, embedding)
            )

    def retrieve(self, chat_id: str, query: str,
                 embed_fn=None, min_sim: float = SEMANTIC_MIN_SIM) -> list:
        """Return top-K formatted fact strings by cosine similarity."""
        embed_fn = embed_fn or _embed
        try:
            q_emb = embed_fn(query)
        except Exception:
            return []

        with db._get_conn() as conn:
            rows = conn.execute(
                "SELECT key, value, confidence, embedding FROM semantic_facts"
                " WHERE chat_id=? AND embedding IS NOT NULL AND confidence >= ?",
                (chat_id, SEMANTIC_MIN_CONF)
            ).fetchall()

        if not rows:
            return []

        scored = []
        for r in rows:
            sim = _cosine(q_emb, r["embedding"])
            if sim >= min_sim:
                scored.append((sim,
                    f"[Semantic] {r['value']} (confidence: {r['confidence']:.1f})"))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [text for _, text in scored[:SEMANTIC_TOP_K]]
