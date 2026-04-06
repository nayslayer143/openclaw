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
CLAWMSON_FTS_LIMIT = int(os.environ.get("CLAWMSON_FTS_LIMIT", "5"))

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
                  "stream": False, "format": "json",
                  "options": {"num_ctx": int(os.environ.get("OPENCLAW_NUM_CTX", "16384"))}},
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
                  "stream": False,
                  "options": {"num_ctx": int(os.environ.get("OPENCLAW_NUM_CTX", "16384"))}},
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

    def clear(self, chat_id: str):
        """Remove chat_id from RAM buffer and seed set."""
        with self._lock:
            self._buffers.pop(chat_id, None)
            self._seeded.discard(chat_id)


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
            cur = conn.execute(
                "INSERT INTO stm_summaries (chat_id, summary, from_ts, to_ts, timestamp)"
                " VALUES (?, ?, ?, ?, ?)",
                (chat_id, summary, from_ts, to_ts, ts)
            )
            source_id = cur.lastrowid
            db.fts_index(chat_id, "stm", source_id, summary, ts, conn=conn)
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
            cur = conn.execute(
                "INSERT INTO episodic_memories"
                " (chat_id, content, summary, timestamp, valence, embedding)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (chat_id, combined[:1000], summary, ts, valence, embedding)
            )
            source_id = cur.lastrowid
            db.fts_index(chat_id, "episodic", source_id, summary, ts, conn=conn)

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
                cur = conn.execute(
                    "INSERT INTO semantic_facts"
                    " (chat_id, key, value, confidence, source, timestamp, embedding)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)"
                    " ON CONFLICT(chat_id, key) DO UPDATE SET"
                    " value=excluded.value, confidence=excluded.confidence,"
                    " timestamp=excluded.timestamp, embedding=excluded.embedding",
                    (chat_id, key, value, conf, source, ts, embedding)
                )
                source_id = cur.lastrowid
                fts_content = f"{key}: {value}"
                db.fts_index(chat_id, "semantic", source_id, fts_content, ts, conn=conn)

    def ingest_explicit(self, chat_id: str, key: str, value: str):
        """Store a fact explicitly (/remember fact: key = value)."""
        try:
            embedding = _embed(value)
        except Exception:
            embedding = None
        ts = _now()
        with db._get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO semantic_facts"
                " (chat_id, key, value, confidence, source, timestamp, embedding)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(chat_id, key) DO UPDATE SET"
                " value=excluded.value, confidence=1.0,"
                " timestamp=excluded.timestamp, embedding=excluded.embedding",
                (chat_id, key[:100], value[:500], 1.0, "explicit", ts, embedding)
            )
            source_id = cur.lastrowid
            db.fts_index(chat_id, "semantic", source_id, f"{key}: {value}", ts, conn=conn)

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


# ════════════════════════════════════════════════════════════════════════════
# Layer 5 — ProceduralMemory
# ════════════════════════════════════════════════════════════════════════════

class ProceduralMemory:
    """Trigger→action mappings. Explicit creation + auto-proposed from patterns."""

    def __init__(self, threshold: int = PROC_THRESHOLD):
        self._threshold = threshold

    def add_procedure(self, chat_id: str, trigger: str, action: str) -> int:
        """Explicit /remember command. Inserts active procedure. Returns id."""
        ts = _now()
        with db._get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO procedures"
                " (chat_id, trigger_pattern, action_description, created_by, status,"
                " occurrence_count, timestamp)"
                " VALUES (?, ?, ?, 'explicit', 'active', 1, ?)",
                (chat_id, trigger, action, ts)
            )
            return cur.lastrowid

    def track_candidate(self, chat_id: str, intent: str, action: str,
                        trigger_phrase: str, notify_fn=None):
        """
        Increment occurrence count for (intent, action) pair.
        When threshold reached and no rejected tombstone exists: propose to user.
        notify_fn(chat_id, message) is called to send the proposal notification.
        """
        # Check for existing rejected tombstone — suppress re-proposal
        with db._get_conn() as conn:
            tombstone = conn.execute(
                "SELECT id FROM procedures"
                " WHERE chat_id=? AND status='rejected' AND created_by='proposed'"
                " AND action_description LIKE ?",
                (chat_id, f"%{action}%")
            ).fetchone()
        if tombstone:
            return

        ts = _now()
        with db._get_conn() as conn:
            conn.execute(
                "INSERT INTO procedure_candidates"
                " (chat_id, intent, action, trigger_phrase, count, last_seen)"
                " VALUES (?, ?, ?, ?, 1, ?)"
                " ON CONFLICT(chat_id, intent, action) DO UPDATE SET"
                " count=count+1, last_seen=excluded.last_seen",
                (chat_id, intent, action, trigger_phrase, ts)
            )
            row = conn.execute(
                "SELECT id, count, trigger_phrase FROM procedure_candidates"
                " WHERE chat_id=? AND intent=? AND action=?",
                (chat_id, intent, action)
            ).fetchone()

        if not row or row["count"] < self._threshold:
            return

        # Threshold reached — promote to pending_approval
        with db._get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO procedures"
                " (chat_id, trigger_pattern, action_description, created_by, status,"
                " occurrence_count, timestamp)"
                " VALUES (?, ?, ?, 'proposed', 'pending_approval', ?, ?)",
                (chat_id, row["trigger_phrase"], action, row["count"], ts)
            )
            proc_id = cur.lastrowid
            conn.execute(
                "DELETE FROM procedure_candidates"
                " WHERE chat_id=? AND intent=? AND action=?",
                (chat_id, intent, action)
            )

        if notify_fn:
            msg = (
                f"I've noticed you keep asking me to '{action}' when you mention "
                f"'{row['trigger_phrase']}'. Want me to remember that?\n"
                f"/approve-proc {proc_id} or /reject-proc {proc_id}"
            )
            notify_fn(chat_id, msg)

    def approve_procedure(self, chat_id: str, proc_id: int):
        with db._get_conn() as conn:
            conn.execute(
                "UPDATE procedures SET status='active' WHERE id=? AND chat_id=?",
                (proc_id, chat_id)
            )

    def reject_procedure(self, chat_id: str, proc_id: int):
        """Tombstone — sets status=rejected, keeps row to suppress re-proposal."""
        with db._get_conn() as conn:
            conn.execute(
                "UPDATE procedures SET status='rejected' WHERE id=? AND chat_id=?",
                (proc_id, chat_id)
            )

    def retrieve(self, chat_id: str, query: str) -> list:
        """Keyword match against active trigger_patterns. Returns formatted strings."""
        lower = query.lower()
        with db._get_conn() as conn:
            rows = conn.execute(
                "SELECT trigger_pattern, action_description FROM procedures"
                " WHERE chat_id=? AND status='active'",
                (chat_id,)
            ).fetchall()
        results = []
        for r in rows:
            if r["trigger_pattern"].lower() in lower:
                results.append(
                    f"[Procedural] When Jordan says \"{r['trigger_pattern']}\""
                    f" \u2192 {r['action_description']}"
                )
        return results


# ════════════════════════════════════════════════════════════════════════════
# MemoryManager — coordinator
# ════════════════════════════════════════════════════════════════════════════

class MemoryManager:
    """
    Coordinator for all 5 memory layers.
    Single ThreadPoolExecutor(max_workers=1) serializes background ingest.
    """

    def __init__(self):
        self._sensory   = SensoryBuffer()
        self._stm       = ShortTermMemory()
        self._episodic  = EpisodicMemory()
        self._semantic  = SemanticMemory()
        self._procedural = ProceduralMemory()
        self._executor  = ThreadPoolExecutor(max_workers=1)
        self._notify_fn = None  # set externally if desired

    # ── Public layer accessors ─────────────────────────────────────────────

    def sensory(self, chat_id: str) -> list:
        """Return last N messages as list of {role, content} dicts."""
        return self._sensory.get(chat_id)

    def retrieve(self, chat_id: str, query: str = "") -> str:
        """
        Assemble a ### Memory Context block from all layers.
        If query is empty, use the default probe string.
        Cap total output at ~2000 chars.
        Returns "" if all layers empty.
        """
        probe = query.strip() or _DEFAULT_PROBE

        parts = []
        # Track (source, source_id) to deduplicate FTS results
        seen_ids: set[tuple] = set()

        # Layer 2: STM summaries
        stm = self._stm.retrieve(chat_id)
        if stm:
            parts.append(f"**Recent summary:** {stm}")

        # Layer 3: Episodic
        episodes = self._episodic.retrieve(chat_id, probe)
        if episodes:
            parts.append("**Past events:**")
            parts.extend(episodes)

        # Layer 4: Semantic
        facts = self._semantic.retrieve(chat_id, probe)
        if facts:
            parts.append("**Known facts:**")
            parts.extend(facts)

        # Layer 5: Procedural
        procs = self._procedural.retrieve(chat_id, probe)
        if procs:
            parts.append("**Procedures:**")
            parts.extend(procs)

        # FTS search — complementary to cosine, works even when Ollama is down
        try:
            import clawmson_fts as fts
            fts_results = fts.search(chat_id, probe, limit=CLAWMSON_FTS_LIMIT)
            fts_parts = []
            for r in fts_results:
                key = (r.get("source"), r.get("source_id"))
                if key in seen_ids:
                    continue
                seen_ids.add(key)
                snippet = r.get("snippet") or r.get("content", "")[:100]
                ts_short = (r.get("ts") or "")[:10]
                fts_parts.append(f"[Search] {snippet} ({ts_short})")
            if fts_parts:
                parts.append("**Search matches:**")
                parts.extend(fts_parts)
        except Exception:
            pass

        if not parts:
            return ""

        body = "\n".join(parts)
        if len(body) > 2000:
            body = body[:1997] + "..."
        return f"### Memory Context\n{body}"

    def ingest_async(self, chat_id: str, role: str, content: str):
        """
        Push message to sensory buffer synchronously, then submit full ingest
        to the background serial executor. Call AFTER send().
        """
        self._sensory.push(chat_id, role, content)
        fut = self._executor.submit(self._full_ingest_wrapper, chat_id, role, content)
        fut.add_done_callback(
            lambda f: f.exception() and print(f"[memory/ingest] background error: {f.exception()}")
        )

    def _full_ingest_wrapper(self, chat_id: str, role: str, content: str):
        """
        Background task: save to DB, run STM check, trigger episodic+semantic ingest.
        Only runs full ingest when we have a user+assistant pair (role==assistant).
        """
        db.save_message(chat_id, role, content)

        if role != "assistant":
            return

        # Get last user message from sensory buffer
        msgs = self._sensory.get(chat_id)
        user_msg = ""
        for m in reversed(msgs):
            if m["role"] == "user":
                user_msg = m["content"]
                break

        self._stm.check_and_summarize(chat_id)
        self._episodic.ingest(chat_id, user_msg, content)
        self._semantic.ingest(chat_id, user_msg, content)

    # ── Procedural memory passthrough ──────────────────────────────────────

    def track_procedure_candidate(self, chat_id: str, intent: str, action: str,
                                   trigger_phrase: str):
        self._procedural.track_candidate(
            chat_id, intent, action, trigger_phrase,
            notify_fn=self._notify_fn
        )

    def add_procedure(self, chat_id: str, trigger: str, action: str) -> int:
        return self._procedural.add_procedure(chat_id, trigger, action)

    def approve_procedure(self, chat_id: str, proc_id: int):
        self._procedural.approve_procedure(chat_id, proc_id)

    def reject_procedure(self, chat_id: str, proc_id: int):
        self._procedural.reject_procedure(chat_id, proc_id)

    # ── Stats and management ───────────────────────────────────────────────

    def stats(self, chat_id: str) -> dict:
        """Return dict of counts per layer for the given chat_id."""
        with db._get_conn() as conn:
            stm_count = conn.execute(
                "SELECT COUNT(*) FROM stm_summaries WHERE chat_id=?", (chat_id,)
            ).fetchone()[0]
            ep_count = conn.execute(
                "SELECT COUNT(*) FROM episodic_memories WHERE chat_id=?", (chat_id,)
            ).fetchone()[0]
            sem_count = conn.execute(
                "SELECT COUNT(*) FROM semantic_facts WHERE chat_id=?", (chat_id,)
            ).fetchone()[0]
            proc_count = conn.execute(
                "SELECT COUNT(*) FROM procedures WHERE chat_id=? AND status='active'",
                (chat_id,)
            ).fetchone()[0]
        return {
            "sensory":   len(self._sensory.get(chat_id)),
            "stm":       stm_count,
            "episodic":  ep_count,
            "semantic":  sem_count,
            "procedural": proc_count,
        }

    def clear(self, chat_id: str, layer: str = "all"):
        """Clear one or all layers for chat_id. layer: 'stm'|'episodic'|'semantic'|'procedural'|'all'"""
        # Drain the executor queue to prevent in-flight tasks from re-writing after clear
        try:
            self._executor.submit(lambda: None).result(timeout=5)
        except Exception:
            pass
        tables = {
            "stm":        "stm_summaries",
            "episodic":   "episodic_memories",
            "semantic":   "semantic_facts",
            "procedural": "procedures",
        }
        to_clear = list(tables.items()) if layer == "all" else [(layer, tables[layer])]
        with db._get_conn() as conn:
            for _, tbl in to_clear:
                conn.execute(f"DELETE FROM {tbl} WHERE chat_id=?", (chat_id,))
        # Also clear sensory buffer in RAM
        if layer == "all":
            self._sensory.clear(chat_id)


# ── Module-level singleton ─────────────────────────────────────────────────

memory = MemoryManager()
