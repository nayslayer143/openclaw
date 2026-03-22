# Clawmson Hermes 5-Layer Memory System — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add persistent 5-layer memory (sensory, short-term, episodic, semantic, procedural) to the Clawmson Telegram bot so it remembers conversations, facts, and workflows across sessions.

**Architecture:** Each layer is a discrete Python class in `clawmson_memory.py`. A `MemoryManager` coordinator owns all five and exposes `sensory()`, `retrieve()`, and `ingest_async()` to the dispatcher. All memory persists in SQLite via five new tables. Embeddings use `nomic-embed-text` via Ollama with in-memory cosine similarity (numpy). Async ingest is serialized through a single `ThreadPoolExecutor(max_workers=1)` to prevent race conditions.

**Tech Stack:** Python 3.10+, SQLite (existing `~/.openclaw/clawmson.db`), Ollama HTTP API (`http://localhost:11434`), numpy, threading.ThreadPoolExecutor.

**Spec:** `docs/superpowers/specs/2026-03-22-clawmson-hermes-memory-design.md`

---

## File Map

| Action | Path | Responsibility |
|--------|------|---------------|
| Create | `scripts/clawmson_memory.py` | All 5 layer classes + MemoryManager coordinator |
| Create | `scripts/clawmson_memory_migrate.py` | One-shot DB migration (safe to re-run) |
| Create | `scripts/tests/__init__.py` | Empty — makes tests/ a package |
| Create | `scripts/tests/test_clawmson_memory.py` | 17 unit tests, offline (in-memory DB, mocked Ollama) |
| Create | `agents/configs/clawmson-memory.md` | Agent config documenting the system |
| Modify | `scripts/clawmson_db.py` | Add 5 new tables + `archived` column + filter `get_history()` |
| Modify | `scripts/clawmson_chat.py` | Add `memory_context: str = ""` param to `chat()` |
| Modify | `scripts/telegram-dispatcher.py` | Wire memory into `_conversation_thread()` + 6 new command handlers |

---

## Task 1: DB Schema — Add `archived` column and 5 new tables

**Files:**
- Modify: `scripts/clawmson_db.py`
- Create: `scripts/clawmson_memory_migrate.py`

### Step 1.1 — Write the failing migration test
Create `scripts/tests/test_clawmson_memory.py` with just the schema test first.

```python
#!/usr/bin/env python3
"""
Clawmson memory system tests.
All tests use in-memory SQLite and mocked Ollama — no running services needed.
"""
from __future__ import annotations
import os
import sys
import json
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Point DB at in-memory SQLite before any imports
os.environ["CLAWMSON_DB_PATH"] = ":memory:"

# Add scripts dir to path
_SCRIPTS = Path(__file__).parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import clawmson_db as db


class TestSchema(unittest.TestCase):
    def test_new_tables_exist(self):
        """All 5 new tables must exist after _init_db()."""
        with db._get_conn() as conn:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
        expected = {"stm_summaries", "episodic_memories",
                    "semantic_facts", "procedures", "procedure_candidates"}
        self.assertTrue(expected.issubset(tables), f"Missing tables: {expected - tables}")

    def test_conversations_has_archived_column(self):
        """conversations table must have archived column defaulting to 0."""
        with db._get_conn() as conn:
            cols = {r[1] for r in conn.execute(
                "PRAGMA table_info(conversations)"
            ).fetchall()}
        self.assertIn("archived", cols)

    def test_get_history_excludes_archived(self):
        """get_history() must not return archived rows."""
        db.save_message("chat1", "user", "hello")
        with db._get_conn() as conn:
            conn.execute("UPDATE conversations SET archived=1 WHERE chat_id='chat1'")
        result = db.get_history("chat1", limit=50)
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] Create `scripts/tests/__init__.py` (empty file)
- [ ] Write the test file above to `scripts/tests/test_clawmson_memory.py`

### Step 1.2 — Run schema tests to verify they fail
```bash
cd ~/openclaw && python3 -m pytest scripts/tests/test_clawmson_memory.py::TestSchema -v
```
Expected: 3 FAIL — `archived` column doesn't exist yet, new tables don't exist yet.

### Step 1.3 — Modify `clawmson_db.py` to add new schema

Open `scripts/clawmson_db.py`. Modify `_init_db()` to add the `archived` column and 5 new tables. Also update `get_history()` to filter `archived=0`.

Replace the entire `_init_db()` function:
```python
def _init_db():
    with _get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id     TEXT    NOT NULL,
                message_id  INTEGER,
                role        TEXT    NOT NULL,
                content     TEXT    NOT NULL,
                timestamp   TEXT    NOT NULL,
                media_type  TEXT,
                archived    INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS context (
                chat_id TEXT NOT NULL,
                key     TEXT NOT NULL,
                value   TEXT NOT NULL,
                PRIMARY KEY (chat_id, key)
            );
            CREATE TABLE IF NOT EXISTS refs (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id   TEXT NOT NULL,
                url       TEXT NOT NULL,
                title     TEXT,
                summary   TEXT,
                content   TEXT,
                timestamp TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS stm_summaries (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id   TEXT    NOT NULL,
                summary   TEXT    NOT NULL,
                from_ts   TEXT    NOT NULL,
                to_ts     TEXT    NOT NULL,
                timestamp TEXT    NOT NULL
            );
            CREATE TABLE IF NOT EXISTS episodic_memories (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id   TEXT    NOT NULL,
                content   TEXT    NOT NULL,
                summary   TEXT    NOT NULL,
                timestamp TEXT    NOT NULL,
                valence   TEXT    NOT NULL DEFAULT 'neutral',
                embedding BLOB
            );
            CREATE TABLE IF NOT EXISTS semantic_facts (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id    TEXT    NOT NULL,
                key        TEXT    NOT NULL,
                value      TEXT    NOT NULL,
                confidence REAL    NOT NULL DEFAULT 0.8,
                source     TEXT    NOT NULL DEFAULT 'inferred',
                timestamp  TEXT    NOT NULL,
                embedding  BLOB,
                UNIQUE(chat_id, key)
            );
            CREATE TABLE IF NOT EXISTS procedures (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id            TEXT    NOT NULL,
                trigger_pattern    TEXT    NOT NULL,
                action_description TEXT    NOT NULL,
                created_by         TEXT    NOT NULL DEFAULT 'explicit',
                status             TEXT    NOT NULL DEFAULT 'active',
                occurrence_count   INTEGER NOT NULL DEFAULT 1,
                last_triggered     TEXT,
                timestamp          TEXT    NOT NULL
            );
            CREATE TABLE IF NOT EXISTS procedure_candidates (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id        TEXT    NOT NULL,
                intent         TEXT    NOT NULL,
                action         TEXT    NOT NULL,
                trigger_phrase TEXT    NOT NULL,
                count          INTEGER NOT NULL DEFAULT 1,
                last_seen      TEXT    NOT NULL,
                UNIQUE(chat_id, intent, action)
            );
            CREATE INDEX IF NOT EXISTS idx_conv_chat     ON conversations(chat_id);
            CREATE INDEX IF NOT EXISTS idx_conv_archived ON conversations(chat_id, archived);
            CREATE INDEX IF NOT EXISTS idx_ref_chat      ON refs(chat_id);
            CREATE INDEX IF NOT EXISTS idx_stm_chat      ON stm_summaries(chat_id);
            CREATE INDEX IF NOT EXISTS idx_episodic_chat ON episodic_memories(chat_id);
            CREATE INDEX IF NOT EXISTS idx_semantic_chat ON semantic_facts(chat_id);
            CREATE INDEX IF NOT EXISTS idx_procedures_chat ON procedures(chat_id, status);
            CREATE INDEX IF NOT EXISTS idx_candidates_chat ON procedure_candidates(chat_id);
        """)
```

Replace `get_history()` to filter archived rows:
```python
def get_history(chat_id: str, limit: int = 50) -> list:
    """Return last `limit` non-archived messages as list of dicts, oldest first."""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT role, content, media_type FROM conversations"
            " WHERE chat_id = ? AND archived = 0 ORDER BY id DESC LIMIT ?",
            (chat_id, limit)
        ).fetchall()
    return [dict(r) for r in reversed(rows)]
```

### Step 1.4 — Run schema tests
```bash
cd ~/openclaw && python3 -m pytest scripts/tests/test_clawmson_memory.py::TestSchema -v
```
Expected: 3 PASS.

### Step 1.5 — Write migration script

Create `scripts/clawmson_memory_migrate.py`:
```python
#!/usr/bin/env python3
"""
Clawmson memory system DB migration.
Safe to run multiple times — all operations are idempotent.
Run: python3 ~/openclaw/scripts/clawmson_memory_migrate.py
"""
from __future__ import annotations
import os
import sys
import sqlite3
from pathlib import Path

DB_PATH = Path(os.environ.get("CLAWMSON_DB_PATH",
               Path.home() / ".openclaw" / "clawmson.db"))


def migrate():
    if str(DB_PATH) == ":memory:":
        print("In-memory DB — skipping migration")
        return

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Add archived column to conversations if missing
    cols = {r[1] for r in conn.execute("PRAGMA table_info(conversations)").fetchall()}
    if "archived" not in cols:
        conn.execute("ALTER TABLE conversations ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
        conn.commit()
        print("  + Added archived column to conversations")
    else:
        print("  ✓ archived column already exists")

    # Force re-init (creates new tables if missing)
    # Import after potential DB path set
    sys.path.insert(0, str(Path(__file__).parent))
    import clawmson_db as db
    db._init_db()

    # Count existing data
    with db._get_conn() as c:
        conv_count = c.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        ctx_count  = c.execute("SELECT COUNT(*) FROM context").fetchone()[0]
        ref_count  = c.execute("SELECT COUNT(*) FROM refs").fetchone()[0]

    conn.close()
    print(f"\nMigration complete.")
    print(f"  Existing rows: conversations={conv_count}, context={ctx_count}, refs={ref_count}")
    print(f"  New tables ready: stm_summaries, episodic_memories, semantic_facts, procedures, procedure_candidates")


if __name__ == "__main__":
    print(f"Migrating {DB_PATH} ...")
    migrate()
```

### Step 1.6 — Commit
```bash
git add scripts/clawmson_db.py scripts/clawmson_memory_migrate.py \
        scripts/tests/__init__.py scripts/tests/test_clawmson_memory.py
git commit -m "feat: add Hermes memory schema to clawmson_db + migration script"
```

---

## Task 2: SensoryBuffer

**Files:**
- Create: `scripts/clawmson_memory.py` (start file here)
- Modify: `scripts/tests/test_clawmson_memory.py` (add TestSensoryBuffer class)

### Step 2.1 — Write SensoryBuffer tests

Append to `scripts/tests/test_clawmson_memory.py`:

```python
# ── Helper: mock embed + LLM ────────────────────────────────────────────────

def _fake_embed(text: str) -> bytes:
    """Return a deterministic fake embedding (all zeros, 768-dim)."""
    import numpy as np
    return np.zeros(768, dtype=np.float32).tobytes()


def _fake_llm_json(payload: dict) -> dict:
    """Return a fake Ollama /api/chat JSON response."""
    return {"message": {"content": json.dumps(payload)}}


# ── SensoryBuffer tests ─────────────────────────────────────────────────────

class TestSensoryBuffer(unittest.TestCase):
    def setUp(self):
        # Fresh in-memory DB for each test
        os.environ["CLAWMSON_DB_PATH"] = ":memory:"
        import importlib
        import clawmson_db
        importlib.reload(clawmson_db)
        import clawmson_memory
        importlib.reload(clawmson_memory)
        from clawmson_memory import SensoryBuffer
        self.buf = SensoryBuffer(window=10)

    def test_sensory_buffer_limit(self):
        """Buffer caps at window size; oldest message evicted."""
        for i in range(15):
            self.buf.push("c1", "user", f"msg {i}")
        result = self.buf.get("c1")
        self.assertEqual(len(result), 10)
        self.assertEqual(result[0]["content"], "msg 5")  # oldest kept
        self.assertEqual(result[-1]["content"], "msg 14")

    def test_sensory_cold_start(self):
        """Seeds from DB (archived=0 only) on first get()."""
        import clawmson_db as db
        db.save_message("c2", "user", "old msg")
        # Mark it archived
        with db._get_conn() as conn:
            conn.execute("UPDATE conversations SET archived=1 WHERE chat_id='c2'")
        db.save_message("c2", "user", "live msg")
        result = self.buf.get("c2")
        contents = [m["content"] for m in result]
        self.assertIn("live msg", contents)
        self.assertNotIn("old msg", contents)

    def test_sensory_push_role_preserved(self):
        """role field is stored and returned correctly."""
        self.buf.push("c3", "assistant", "hello there")
        msgs = self.buf.get("c3")
        self.assertEqual(msgs[0]["role"], "assistant")
```

- [ ] Append the test code above to `scripts/tests/test_clawmson_memory.py`

### Step 2.2 — Run to verify tests fail
```bash
cd ~/openclaw && python3 -m pytest scripts/tests/test_clawmson_memory.py::TestSensoryBuffer -v
```
Expected: ImportError or AttributeError — `clawmson_memory` doesn't exist yet.

### Step 2.3 — Create `scripts/clawmson_memory.py` with SensoryBuffer

```python
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
import numpy as np
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys

_SCRIPTS = Path(__file__).parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import clawmson_db as db

# ── Config ───────────────────────────────────────────────────────────────────

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

# ── Utility: Ollama calls ────────────────────────────────────────────────────

def _embed(text: str) -> bytes:
    """Embed text via nomic-embed-text. Returns numpy float32 bytes."""
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
```

- [ ] Create `scripts/clawmson_memory.py` with the content above.

### Step 2.4 — Run SensoryBuffer tests
```bash
cd ~/openclaw && python3 -m pytest scripts/tests/test_clawmson_memory.py::TestSensoryBuffer -v
```
Expected: 3 PASS.

### Step 2.5 — Commit
```bash
git add scripts/clawmson_memory.py scripts/tests/test_clawmson_memory.py
git commit -m "feat: SensoryBuffer — layer 1 of Hermes memory"
```

---

## Task 3: ShortTermMemory

**Files:**
- Modify: `scripts/clawmson_memory.py` (append ShortTermMemory class)
- Modify: `scripts/tests/test_clawmson_memory.py` (append TestShortTermMemory)

### Step 3.1 — Write STM tests

Append to test file:
```python
class TestShortTermMemory(unittest.TestCase):
    def setUp(self):
        os.environ["CLAWMSON_DB_PATH"] = ":memory:"
        import importlib, clawmson_db, clawmson_memory
        importlib.reload(clawmson_db)
        importlib.reload(clawmson_memory)
        from clawmson_memory import ShortTermMemory
        self.stm = ShortTermMemory(max_rows=10, batch=5)

    def _fill(self, chat_id, n):
        import clawmson_db as db
        for i in range(n):
            db.save_message(chat_id, "user" if i % 2 == 0 else "assistant", f"msg {i}")

    def test_stm_retrieve_empty(self):
        """Returns empty string when no summaries exist."""
        result = self.stm.retrieve("c1")
        self.assertEqual(result, "")

    def test_stm_summarize_triggers(self):
        """Summarization fires and stores summary when active rows > max_rows."""
        self._fill("c2", 12)  # > max_rows of 10
        summary_text = "Test summary of conversation."
        with patch("clawmson_memory._llm_text", return_value=summary_text):
            self.stm.check_and_summarize("c2")
        import clawmson_db as db
        with db._get_conn() as conn:
            rows = conn.execute(
                "SELECT summary FROM stm_summaries WHERE chat_id='c2'"
            ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], summary_text)

    def test_stm_archives_correct_rows(self):
        """Archives exactly batch-size oldest rows. Other chat_ids untouched. Archived rows preserved."""
        import clawmson_db as db
        self._fill("c3", 12)
        self._fill("other", 3)  # different chat_id — must not be touched
        with patch("clawmson_memory._llm_text", return_value="summary"):
            self.stm.check_and_summarize("c3")
        with db._get_conn() as conn:
            archived_c3 = conn.execute(
                "SELECT COUNT(*) FROM conversations WHERE chat_id='c3' AND archived=1"
            ).fetchone()[0]
            active_c3 = conn.execute(
                "SELECT COUNT(*) FROM conversations WHERE chat_id='c3' AND archived=0"
            ).fetchone()[0]
            total_c3 = conn.execute(
                "SELECT COUNT(*) FROM conversations WHERE chat_id='c3'"
            ).fetchone()[0]
            other_archived = conn.execute(
                "SELECT COUNT(*) FROM conversations WHERE chat_id='other' AND archived=1"
            ).fetchone()[0]
        self.assertEqual(archived_c3, 5)     # batch size
        self.assertEqual(active_c3, 7)       # 12 - 5
        self.assertEqual(total_c3, 12)       # no hard deletes
        self.assertEqual(other_archived, 0)  # other chat_id untouched
```

### Step 3.2 — Run to verify tests fail
```bash
cd ~/openclaw && python3 -m pytest scripts/tests/test_clawmson_memory.py::TestShortTermMemory -v
```
Expected: FAIL — `ShortTermMemory` not defined yet.

### Step 3.3 — Append ShortTermMemory to `clawmson_memory.py`

```python
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
```

### Step 3.4 — Run STM tests
```bash
cd ~/openclaw && python3 -m pytest scripts/tests/test_clawmson_memory.py::TestShortTermMemory -v
```
Expected: 3 PASS.

### Step 3.5 — Commit
```bash
git add scripts/clawmson_memory.py scripts/tests/test_clawmson_memory.py
git commit -m "feat: ShortTermMemory — layer 2 of Hermes memory"
```

---

## Task 4: EpisodicMemory

**Files:**
- Modify: `scripts/clawmson_memory.py`
- Modify: `scripts/tests/test_clawmson_memory.py`

### Step 4.1 — Write episodic tests

Append to test file:
```python
class TestEpisodicMemory(unittest.TestCase):
    def setUp(self):
        os.environ["CLAWMSON_DB_PATH"] = ":memory:"
        import importlib, clawmson_db, clawmson_memory
        importlib.reload(clawmson_db)
        importlib.reload(clawmson_memory)
        from clawmson_memory import EpisodicMemory
        self.ep = EpisodicMemory()

    def test_episodic_rule_pass(self):
        """Trigger keyword in message pair passes rule check."""
        self.assertTrue(self.ep._rule_pass("we deployed the fix"))
        self.assertTrue(self.ep._rule_pass("it broke prod"))

    def test_episodic_rule_no_match(self):
        """Neutral message skips LLM call and stores nothing."""
        with patch("clawmson_memory._llm_json") as mock_llm, \
             patch("clawmson_memory._embed", return_value=_fake_embed("")):
            self.ep.ingest("c1", "hey how are you", "doing well thanks")
            mock_llm.assert_not_called()
        import clawmson_db as db
        with db._get_conn() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM episodic_memories WHERE chat_id='c1'"
            ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_episodic_store_retrieve(self):
        """Stores a significant episode; cosine search returns it."""
        fake_emb = _fake_embed("")
        llm_resp = {"significant": True, "summary": "Deployed fix, prod broke.",
                    "valence": "critical"}
        with patch("clawmson_memory._llm_json", return_value=llm_resp), \
             patch("clawmson_memory._embed", return_value=fake_emb):
            self.ep.ingest("c2", "we deployed the fix", "it broke prod login")
        results = self.ep.retrieve("c2", "deployment", embed_fn=lambda t: fake_emb,
                                   min_sim=0.0)
        self.assertEqual(len(results), 1)
        self.assertIn("critical", results[0])
        self.assertIn("Deployed fix", results[0])
```

### Step 4.2 — Run to verify fail
```bash
cd ~/openclaw && python3 -m pytest scripts/tests/test_clawmson_memory.py::TestEpisodicMemory -v
```
Expected: FAIL.

### Step 4.3 — Append EpisodicMemory to `clawmson_memory.py`

```python
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
```

### Step 4.4 — Run episodic tests
```bash
cd ~/openclaw && python3 -m pytest scripts/tests/test_clawmson_memory.py::TestEpisodicMemory -v
```
Expected: 3 PASS.

### Step 4.5 — Commit
```bash
git add scripts/clawmson_memory.py scripts/tests/test_clawmson_memory.py
git commit -m "feat: EpisodicMemory — layer 3 of Hermes memory"
```

---

## Task 5: SemanticMemory

**Files:**
- Modify: `scripts/clawmson_memory.py`
- Modify: `scripts/tests/test_clawmson_memory.py`

### Step 5.1 — Write semantic tests

Append to test file:
```python
class TestSemanticMemory(unittest.TestCase):
    def setUp(self):
        os.environ["CLAWMSON_DB_PATH"] = ":memory:"
        import importlib, clawmson_db, clawmson_memory
        importlib.reload(clawmson_db)
        importlib.reload(clawmson_memory)
        from clawmson_memory import SemanticMemory
        self.sem = SemanticMemory()

    def test_semantic_upsert(self):
        """Same key updates value — no duplicate row created."""
        fake_emb = _fake_embed("")
        facts_v1 = [{"key": "preferred model", "value": "qwen3:32b", "confidence": 0.8}]
        facts_v2 = [{"key": "preferred model", "value": "qwen3-coder", "confidence": 0.9}]
        with patch("clawmson_memory._llm_json", return_value={"facts": facts_v1}), \
             patch("clawmson_memory._embed", return_value=fake_emb):
            self.sem.ingest("c1", "I prefer qwen3:32b", "got it")
        with patch("clawmson_memory._llm_json", return_value={"facts": facts_v2}), \
             patch("clawmson_memory._embed", return_value=fake_emb):
            self.sem.ingest("c1", "actually I prefer qwen3-coder", "updated")
        import clawmson_db as db
        with db._get_conn() as conn:
            rows = conn.execute(
                "SELECT value FROM semantic_facts WHERE chat_id='c1' AND key='preferred model'"
            ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "qwen3-coder")

    def test_semantic_retrieve_topk(self):
        """Returns ≤ SEMANTIC_TOP_K facts above similarity threshold."""
        fake_emb = _fake_embed("")
        for i in range(8):
            with db._get_conn() as conn:
                conn.execute(
                    "INSERT INTO semantic_facts"
                    " (chat_id, key, value, confidence, source, timestamp, embedding)"
                    " VALUES (?,?,?,?,?,?,?)",
                    ("c2", f"key{i}", f"fact {i}", 0.9, "explicit", _now(), fake_emb)
                )
        results = self.sem.retrieve("c2", "anything",
                                    embed_fn=lambda t: fake_emb, min_sim=0.0)
        self.assertLessEqual(len(results), 5)
```

### Step 5.2 — Run to verify fail
```bash
cd ~/openclaw && python3 -m pytest scripts/tests/test_clawmson_memory.py::TestSemanticMemory -v
```
Expected: FAIL.

### Step 5.3 — Append SemanticMemory to `clawmson_memory.py`

```python
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
```

### Step 5.4 — Run semantic tests
```bash
cd ~/openclaw && python3 -m pytest scripts/tests/test_clawmson_memory.py::TestSemanticMemory -v
```
Expected: 2 PASS.

### Step 5.5 — Commit
```bash
git add scripts/clawmson_memory.py scripts/tests/test_clawmson_memory.py
git commit -m "feat: SemanticMemory — layer 4 of Hermes memory"
```

---

## Task 6: ProceduralMemory

**Files:**
- Modify: `scripts/clawmson_memory.py`
- Modify: `scripts/tests/test_clawmson_memory.py`

### Step 6.1 — Write procedural tests

Append to test file:
```python
class TestProceduralMemory(unittest.TestCase):
    def setUp(self):
        os.environ["CLAWMSON_DB_PATH"] = ":memory:"
        import importlib, clawmson_db, clawmson_memory
        importlib.reload(clawmson_db)
        importlib.reload(clawmson_memory)
        from clawmson_memory import ProceduralMemory
        self.proc = ProceduralMemory(threshold=3)
        self._notifications = []

    def _notify(self, chat_id, msg):
        self._notifications.append((chat_id, msg))

    def test_procedural_explicit(self):
        """add_procedure() creates an active procedure immediately."""
        pid = self.proc.add_procedure("c1", "scout X", "run research pipeline on X")
        import clawmson_db as db
        with db._get_conn() as conn:
            row = conn.execute(
                "SELECT status, created_by FROM procedures WHERE id=?", (pid,)
            ).fetchone()
        self.assertEqual(row["status"], "active")
        self.assertEqual(row["created_by"], "explicit")

    def test_procedural_candidate_tracking(self):
        """3 occurrences of same pattern creates pending_approval procedure."""
        for _ in range(3):
            self.proc.track_candidate("c2", "BUILD_TASK", "build",
                                      "build the contact form",
                                      notify_fn=self._notify)
        import clawmson_db as db
        with db._get_conn() as conn:
            pending = conn.execute(
                "SELECT id FROM procedures WHERE chat_id='c2' AND status='pending_approval'"
            ).fetchall()
            candidates = conn.execute(
                "SELECT count FROM procedure_candidates WHERE chat_id='c2'"
            ).fetchall()
        self.assertEqual(len(pending), 1)
        self.assertEqual(len(candidates), 0)  # moved to procedures, removed from candidates
        self.assertEqual(len(self._notifications), 1)

    def test_procedural_approve_reject(self):
        """Approve → active. Reject → tombstone (status=rejected, row kept)."""
        pid = self.proc.add_procedure("c3", "trigger", "action")
        with db._get_conn() as conn:
            conn.execute("UPDATE procedures SET status='pending_approval' WHERE id=?", (pid,))
        self.proc.approve_procedure("c3", pid)
        with db._get_conn() as conn:
            row = conn.execute("SELECT status FROM procedures WHERE id=?", (pid,)).fetchone()
        self.assertEqual(row["status"], "active")

        pid2 = self.proc.add_procedure("c3", "trigger2", "action2")
        with db._get_conn() as conn:
            conn.execute("UPDATE procedures SET status='pending_approval' WHERE id=?", (pid2,))
        self.proc.reject_procedure("c3", pid2)
        with db._get_conn() as conn:
            row2 = conn.execute("SELECT status FROM procedures WHERE id=?", (pid2,)).fetchone()
        self.assertIsNotNone(row2)  # row kept
        self.assertEqual(row2["status"], "rejected")

    def test_procedural_no_reproposal_after_reject(self):
        """Rejected (intent, action) pair is not proposed again."""
        # Create and reject a procedure for "BUILD_TASK/build"
        pid = self.proc.add_procedure("c4", "build", "build thing")
        with db._get_conn() as conn:
            conn.execute(
                "UPDATE procedures SET status='rejected', created_by='proposed'"
                " WHERE id=?", (pid,))
            # Also set intent/action in a way the tracker can find it
            conn.execute(
                "UPDATE procedures SET trigger_pattern='build' WHERE id=?", (pid,))
        # Now fire 3 candidate occurrences
        for _ in range(3):
            self.proc.track_candidate("c4", "BUILD_TASK", "build",
                                      "build it", notify_fn=self._notify)
        self.assertEqual(len(self._notifications), 0)  # no re-proposal
```

### Step 6.2 — Run to verify fail
```bash
cd ~/openclaw && python3 -m pytest scripts/tests/test_clawmson_memory.py::TestProceduralMemory -v
```
Expected: FAIL.

### Step 6.3 — Append ProceduralMemory to `clawmson_memory.py`

```python
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
                " AND trigger_pattern LIKE ?",
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
                    f" → {r['action_description']}"
                )
        return results
```

### Step 6.4 — Run procedural tests
```bash
cd ~/openclaw && python3 -m pytest scripts/tests/test_clawmson_memory.py::TestProceduralMemory -v
```
Expected: 4 PASS.

### Step 6.5 — Commit
```bash
git add scripts/clawmson_memory.py scripts/tests/test_clawmson_memory.py
git commit -m "feat: ProceduralMemory — layer 5 of Hermes memory"
```

---

## Task 7: MemoryManager coordinator + integration tests

**Files:**
- Modify: `scripts/clawmson_memory.py`
- Modify: `scripts/tests/test_clawmson_memory.py`

### Step 7.1 — Write integration tests

Append to test file:
```python
class TestMemoryManager(unittest.TestCase):
    def setUp(self):
        os.environ["CLAWMSON_DB_PATH"] = ":memory:"
        import importlib, clawmson_db, clawmson_memory
        importlib.reload(clawmson_db)
        importlib.reload(clawmson_memory)
        from clawmson_memory import MemoryManager
        self.mm = MemoryManager()

    def test_retrieve_assembles_context(self):
        """Full retrieve() output must be under 500 tokens (~2000 chars)."""
        import clawmson_db as db
        db.save_message("c1", "user", "we deployed the fix")
        db.save_message("c1", "assistant", "it broke prod")
        with db._get_conn() as conn:
            conn.execute(
                "INSERT INTO episodic_memories"
                " (chat_id, content, summary, timestamp, valence, embedding)"
                " VALUES ('c1','x','Deployed fix broke prod','2026-01-01','critical',?)",
                (_fake_embed(""),)
            )
            conn.execute(
                "INSERT INTO semantic_facts"
                " (chat_id, key, value, confidence, source, timestamp, embedding)"
                " VALUES ('c1','model','Jordan prefers qwen3:32b',0.9,'explicit','2026-01-01',?)",
                (_fake_embed(""),)
            )
        result = self.mm.retrieve("c1", "test query",
                                  _ep_embed=lambda t: _fake_embed(""),
                                  _sem_embed=lambda t: _fake_embed(""))
        self.assertLess(len(result), 2000)

    def test_retrieve_empty_query_uses_probe(self):
        """retrieve() with empty query must not raise and returns a string."""
        result = self.mm.retrieve("c1", "")
        self.assertIsInstance(result, str)

    def test_ingest_async_nonblocking(self):
        """ingest_async() returns in < 0.5s even if layers 3-5 are slow."""
        import time
        def slow_embed(t): time.sleep(2); return _fake_embed("")
        with patch("clawmson_memory._embed", side_effect=slow_embed):
            start = time.time()
            self.mm.ingest_async("c1", "user", "we deployed")
            elapsed = time.time() - start
        self.assertLess(elapsed, 0.5)

    def test_ingest_async_concurrent_no_duplicate_summaries(self):
        """Two rapid ingest_async() calls produce at most 1 STM summary."""
        import clawmson_db as db
        # Pre-fill 12 active rows (> STM default 10 for test MemoryManager)
        for i in range(12):
            db.save_message("c2", "user" if i%2==0 else "assistant", f"m{i}")
        with patch("clawmson_memory._llm_text", return_value="summary"), \
             patch("clawmson_memory._llm_json", return_value={"significant": False}), \
             patch("clawmson_memory._embed", return_value=_fake_embed("")):
            self.mm.ingest_async("c2", "user", "msg A")
            self.mm.ingest_async("c2", "assistant", "msg B")
            self.mm._executor.shutdown(wait=True)
        with db._get_conn() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM stm_summaries WHERE chat_id='c2'"
            ).fetchone()[0]
        self.assertLessEqual(count, 1)

    def test_clear_layer(self):
        """clear(episodic) deletes only episodic rows, leaves others intact."""
        import clawmson_db as db
        with db._get_conn() as conn:
            conn.execute(
                "INSERT INTO episodic_memories"
                " (chat_id,content,summary,timestamp,valence)"
                " VALUES ('c3','x','y','2026-01-01','neutral')"
            )
            conn.execute(
                "INSERT INTO semantic_facts"
                " (chat_id,key,value,confidence,source,timestamp)"
                " VALUES ('c3','k','v',0.9,'explicit','2026-01-01')"
            )
        self.mm.clear("c3", "episodic")
        with db._get_conn() as conn:
            ep  = conn.execute("SELECT COUNT(*) FROM episodic_memories WHERE chat_id='c3'").fetchone()[0]
            sem = conn.execute("SELECT COUNT(*) FROM semantic_facts WHERE chat_id='c3'").fetchone()[0]
        self.assertEqual(ep, 0)
        self.assertEqual(sem, 1)
```

### Step 7.2 — Run to verify fail
```bash
cd ~/openclaw && python3 -m pytest scripts/tests/test_clawmson_memory.py::TestMemoryManager -v
```
Expected: FAIL.

### Step 7.3 — Append MemoryManager to `clawmson_memory.py`

```python
# ════════════════════════════════════════════════════════════════════════════
# MemoryManager — Public Coordinator
# ════════════════════════════════════════════════════════════════════════════

class MemoryManager:
    """
    Coordinator for all 5 memory layers.
    All async ingest work is serialized through a single ThreadPoolExecutor(max_workers=1)
    to prevent concurrent STM summarization passes producing duplicate entries.
    """

    def __init__(self):
        self._sensory   = SensoryBuffer()
        self._stm       = ShortTermMemory()
        self._episodic  = EpisodicMemory()
        self._semantic  = SemanticMemory()
        self._procedural= ProceduralMemory()
        self._executor  = ThreadPoolExecutor(max_workers=1, thread_name_prefix="clawmson-memory")
        self._notify_fn = None  # set by dispatcher: notify_fn(chat_id, msg)

    def set_notify_fn(self, fn):
        """Register function for procedural proposal notifications. fn(chat_id, msg)."""
        self._notify_fn = fn

    def sensory(self, chat_id: str) -> list:
        """Return last N messages for Ollama history. Seeds from DB on cold start."""
        return self._sensory.get(chat_id)

    def retrieve(self, chat_id: str, query: str = "",
                 _ep_embed=None, _sem_embed=None) -> str:
        """
        Query layers 2-5 and assemble a memory context block.
        Returns "" if nothing relevant. Output kept under ~500 tokens.
        _ep_embed/_sem_embed: override embed function (for testing).
        """
        probe = query.strip() or _DEFAULT_PROBE
        parts = []

        stm = self._stm.retrieve(chat_id)
        if stm:
            parts.append(f"[Short-term] {stm}")

        ep_kw = {"embed_fn": _ep_embed} if _ep_embed else {}
        for line in self._episodic.retrieve(chat_id, probe, **ep_kw):
            parts.append(line)

        sem_kw = {"embed_fn": _sem_embed} if _sem_embed else {}
        for line in self._semantic.retrieve(chat_id, probe, **sem_kw):
            parts.append(line)

        for line in self._procedural.retrieve(chat_id, probe):
            parts.append(line)

        if not parts:
            return ""

        context = "### Memory Context\n" + "\n".join(parts)
        # Hard cap at ~2000 chars (~500 tokens) to protect context window
        if len(context) > 2000:
            context = context[:1997] + "..."
        return context

    def ingest_async(self, chat_id: str, role: str, content: str):
        """
        Non-blocking. Submits full ingest work to serial background executor.
        Call AFTER send() to only record delivered messages.
        """
        self._executor.submit(self._full_ingest, chat_id, role, content)

    def _full_ingest(self, chat_id: str, role: str, content: str):
        """Runs in background executor thread. Serialized — no race conditions."""
        try:
            self._sensory.push(chat_id, role, content)
            self._stm.check_and_summarize(chat_id)

            # Layers 3-5 only fire when we have a complete exchange (assistant reply)
            if role == "assistant":
                history = self._sensory.get(chat_id)
                # Find most recent user message
                user_msg = ""
                for msg in reversed(history[:-1]):  # exclude the just-pushed assistant msg
                    if msg["role"] == "user":
                        user_msg = msg["content"]
                        break
                if user_msg:
                    self._episodic.ingest(chat_id, user_msg, content)
                    self._semantic.ingest(chat_id, user_msg, content)
        except Exception as e:
            print(f"[memory] ingest error for {chat_id}: {e}")

    def track_procedure_candidate(self, chat_id: str, intent: str, action: str,
                                  trigger_phrase: str):
        """Called by dispatcher after classification. Tracks procedural patterns."""
        if action:
            self._executor.submit(
                self._procedural.track_candidate,
                chat_id, intent, action, trigger_phrase, self._notify_fn
            )

    def add_procedure(self, chat_id: str, trigger: str, action: str) -> int:
        return self._procedural.add_procedure(chat_id, trigger, action)

    def approve_procedure(self, chat_id: str, proc_id: int):
        self._procedural.approve_procedure(chat_id, proc_id)

    def reject_procedure(self, chat_id: str, proc_id: int):
        self._procedural.reject_procedure(chat_id, proc_id)

    def stats(self, chat_id: str) -> dict:
        buf = self._sensory.get(chat_id)
        with db._get_conn() as conn:
            stm_n  = conn.execute("SELECT COUNT(*) FROM stm_summaries WHERE chat_id=?",
                                  (chat_id,)).fetchone()[0]
            ep_n   = conn.execute("SELECT COUNT(*) FROM episodic_memories WHERE chat_id=?",
                                  (chat_id,)).fetchone()[0]
            sem_n  = conn.execute("SELECT COUNT(*) FROM semantic_facts WHERE chat_id=?",
                                  (chat_id,)).fetchone()[0]
            proc_a = conn.execute(
                "SELECT COUNT(*) FROM procedures WHERE chat_id=? AND status='active'",
                (chat_id,)).fetchone()[0]
            proc_p = conn.execute(
                "SELECT COUNT(*) FROM procedures WHERE chat_id=? AND status='pending_approval'",
                (chat_id,)).fetchone()[0]
            cand_n = conn.execute(
                "SELECT COUNT(*) FROM procedure_candidates WHERE chat_id=?",
                (chat_id,)).fetchone()[0]
        return {
            "sensory": len(buf),
            "stm_summaries": stm_n,
            "episodic": ep_n,
            "semantic": sem_n,
            "procedural_active": proc_a,
            "procedural_pending": proc_p,
            "candidates": cand_n,
        }

    def clear(self, chat_id: str, layer: str = "all"):
        """Delete memory for one layer or all. Keeps rejected procedure tombstones."""
        with db._get_conn() as conn:
            if layer in ("all", "stm"):
                conn.execute("DELETE FROM stm_summaries WHERE chat_id=?", (chat_id,))
            if layer in ("all", "episodic"):
                conn.execute("DELETE FROM episodic_memories WHERE chat_id=?", (chat_id,))
            if layer in ("all", "semantic"):
                conn.execute("DELETE FROM semantic_facts WHERE chat_id=?", (chat_id,))
            if layer in ("all", "procedural"):
                conn.execute(
                    "DELETE FROM procedures WHERE chat_id=? AND status != 'rejected'",
                    (chat_id,))
                conn.execute("DELETE FROM procedure_candidates WHERE chat_id=?", (chat_id,))
        if layer in ("all", "sensory"):
            self._sensory._buffers.pop(chat_id, None)
            self._sensory._seeded.discard(chat_id)


# ── Module-level singleton ───────────────────────────────────────────────────
memory = MemoryManager()
```

### Step 7.4 — Run all integration tests
```bash
cd ~/openclaw && python3 -m pytest scripts/tests/test_clawmson_memory.py::TestMemoryManager -v
```
Expected: 5 PASS.

### Step 7.5 — Run full test suite
```bash
cd ~/openclaw && python3 -m pytest scripts/tests/test_clawmson_memory.py -v
```
Expected: 20 PASS (3 schema + 3 sensory + 3 stm + 3 episodic + 2 semantic + 4 procedural + 5 manager). Note: the spec listed 17 — the plan adds 3 additional coverage tests (`test_sensory_push_role_preserved`, `test_ingest_async_nonblocking` counted in manager, `test_clear_layer`). All 20 are in the test file.

### Step 7.6 — Commit
```bash
git add scripts/clawmson_memory.py scripts/tests/test_clawmson_memory.py
git commit -m "feat: MemoryManager coordinator — all 5 layers wired, 17 tests pass"
```

---

## Task 8: Modify `clawmson_chat.py`

**Files:**
- Modify: `scripts/clawmson_chat.py`

### Step 8.1 — Add `memory_context` parameter to `chat()`

Open `scripts/clawmson_chat.py`. Find the `chat()` function signature and add the `memory_context` parameter. Then inject it into the system prompt before the Ollama call.

Change the function signature from:
```python
def chat(history: list, user_message: str, has_image: bool = False) -> str:
```
To:
```python
def chat(history: list, user_message: str, has_image: bool = False,
         memory_context: str = "") -> str:
```

Add memory context injection right after `system_prompt = _load_system_prompt()`:
```python
    system_prompt = _load_system_prompt()
    if memory_context:
        system_prompt = system_prompt + "\n\n" + memory_context
```

### Step 8.2 — Verify the change works
```bash
cd ~/openclaw && python3 -c "
import sys; sys.path.insert(0, 'scripts')
import os; os.environ['CLAWMSON_DB_PATH'] = ':memory:'
import clawmson_chat
import inspect
sig = inspect.signature(clawmson_chat.chat)
assert 'memory_context' in sig.parameters, 'memory_context param missing'
print('OK — memory_context param present')
"
```
Expected: `OK — memory_context param present`

### Step 8.3 — Run full test suite to confirm no regression
```bash
cd ~/openclaw && python3 -m pytest scripts/tests/test_clawmson_memory.py -v
```
Expected: 17 PASS.

### Step 8.4 — Commit
```bash
git add scripts/clawmson_chat.py
git commit -m "feat: add memory_context param to clawmson_chat.chat()"
```

---

## Task 9: Wire memory into `telegram-dispatcher.py`

**Files:**
- Modify: `scripts/telegram-dispatcher.py`

### Step 9.1 — Import clawmson_memory and initialize

At the top of `telegram-dispatcher.py`, after the existing imports block (after `import clawmson_references as refs`), add:
```python
import clawmson_memory as mem_module

# Module-level memory singleton
memory = mem_module.memory
```

After `media.init(BOT_TOKEN)`, add:
```python
# Wire memory notification function (for procedure proposals)
memory.set_notify_fn(send)
```

### Step 9.2 — Update `_conversation_thread()`

Replace the existing `_conversation_thread()` function:
```python
def _conversation_thread(chat_id: str, effective_text: str, has_image: bool):
    """Called in a background thread. Fetches Ollama reply and sends it."""
    send_typing(chat_id)
    history        = memory.sensory(chat_id)
    memory_context = memory.retrieve(chat_id, effective_text)
    reply          = llm.chat(history, effective_text, has_image=has_image,
                              memory_context=memory_context)
    db.save_message(chat_id, "assistant", reply)
    send(chat_id, reply)
    # Ingest AFTER send() — only record delivered messages
    memory.ingest_async(chat_id, "user", effective_text)
    memory.ingest_async(chat_id, "assistant", reply)
```

### Step 9.3 — Add procedure candidate tracking

In `handle_message()`, the existing code sets `intent = result["intent"]` immediately after classification. Find the block that reads:
```python
    intent = result["intent"]
    print(f"[dispatcher] intent={intent} ...")
```

Add the following immediately after that `print(...)` line:
```python
    # Track procedural patterns for auto-proposal
    if result.get("action") and intent not in (intents.STATUS_QUERY,
                                                intents.DIRECT_COMMAND):
        memory.track_procedure_candidate(
            chat_id, intent,
            result.get("action", ""),
            effective_text[:100]
        )
```
`result` is the full dict from `intents.classify()` (contains `intent`, `action`, `project`, etc.).
`intent`, `chat_id`, and `effective_text` are all already in scope at this point in `handle_message()`.

### Step 9.4 — Add 6 new command handlers

Add these handler functions before `handle_message()`:

```python
def handle_memory(chat_id: str):
    context = memory.retrieve(chat_id, "")
    send(chat_id, context if context else "No memory context yet.")


def handle_memory_stats(chat_id: str):
    stats = memory.stats(chat_id)
    lines = ["Memory stats:"]
    lines.append(f"  Sensory buffer:      {stats['sensory']} msgs")
    lines.append(f"  Short-term summaries:{stats['stm_summaries']}")
    lines.append(f"  Episodic events:     {stats['episodic']}")
    lines.append(f"  Semantic facts:      {stats['semantic']}")
    lines.append(f"  Procedures (active): {stats['procedural_active']}")
    lines.append(f"  Procedures (pending):{stats['procedural_pending']}")
    lines.append(f"  Candidates:          {stats['candidates']}")
    send(chat_id, "\n".join(lines))


def handle_forget_memory(chat_id: str, layer: str = "all"):
    valid = {"all", "sensory", "stm", "episodic", "semantic", "procedural"}
    if layer not in valid:
        send(chat_id, f"Unknown layer '{layer}'. Valid: {', '.join(sorted(valid))}")
        return
    memory.clear(chat_id, layer)
    send(chat_id, f"Memory cleared: {layer}")


def handle_remember_procedure(chat_id: str, raw: str):
    """Parse '/remember <trigger> → <action>' and add procedure."""
    sep = "→" if "→" in raw else "->"
    parts = raw.split(sep, 1)
    if len(parts) != 2:
        send(chat_id, "Format: /remember <trigger> → <action>")
        return
    trigger = parts[0].strip().strip('"').strip("'")
    action  = parts[1].strip()
    if not trigger or not action:
        send(chat_id, "Both trigger and action are required.")
        return
    pid = memory.add_procedure(chat_id, trigger, action)
    send(chat_id, f"Procedure saved (id: {pid}): when '{trigger}' → {action}")


def handle_approve_proc(chat_id: str, proc_id_str: str):
    try:
        pid = int(proc_id_str.strip())
    except ValueError:
        send(chat_id, "Usage: /approve-proc <id>")
        return
    memory.approve_procedure(chat_id, pid)
    send(chat_id, f"Procedure {pid} approved and active.")


def handle_reject_proc(chat_id: str, proc_id_str: str):
    try:
        pid = int(proc_id_str.strip())
    except ValueError:
        send(chat_id, "Usage: /reject-proc <id>")
        return
    memory.reject_procedure(chat_id, pid)
    send(chat_id, f"Procedure {pid} rejected.")
```

### Step 9.5 — Wire new commands into `handle_message()`

In `handle_message()`, in the `/slash commands` section (after the existing `/approve` handler), add:

```python
        if lower == "/memory":
            handle_memory(chat_id)
            return
        if lower == "/memory-stats":
            handle_memory_stats(chat_id)
            return
        if lower.startswith("/forget-memory"):
            parts = text.split(None, 1)
            layer = parts[1].strip() if len(parts) > 1 else "all"
            handle_forget_memory(chat_id, layer)
            return
        if lower.startswith("/remember "):
            raw = text[len("/remember "):].strip()
            handle_remember_procedure(chat_id, raw)
            return
        if lower.startswith("/approve-proc"):
            parts = text.split(None, 1)
            proc_id_str = parts[1] if len(parts) > 1 else ""
            handle_approve_proc(chat_id, proc_id_str)
            return
        if lower.startswith("/reject-proc"):
            parts = text.split(None, 1)
            proc_id_str = parts[1] if len(parts) > 1 else ""
            handle_reject_proc(chat_id, proc_id_str)
            return
```

### Step 9.6 — Smoke test the dispatcher imports cleanly
```bash
cd ~/openclaw && python3 -c "
import sys, os
sys.path.insert(0, 'scripts')
os.environ['CLAWMSON_DB_PATH'] = ':memory:'
os.environ['TELEGRAM_BOT_TOKEN'] = 'test'
os.environ['TELEGRAM_ALLOWED_USERS'] = '\"123\"'
# Don't actually start the bot — just verify imports
print('Checking imports...')
import clawmson_memory
print(f'  clawmson_memory: OK ({len(dir(clawmson_memory))} attrs)')
import clawmson_chat
import inspect
assert 'memory_context' in inspect.signature(clawmson_chat.chat).parameters
print('  clawmson_chat.chat() memory_context param: OK')
print('All checks passed.')
"
```
Expected: `All checks passed.`

### Step 9.7 — Run full test suite
```bash
cd ~/openclaw && python3 -m pytest scripts/tests/test_clawmson_memory.py -v
```
Expected: 17 PASS.

### Step 9.8 — Commit
```bash
git add scripts/telegram-dispatcher.py
git commit -m "feat: wire Hermes memory into telegram-dispatcher + 6 new commands"
```

---

## Task 10: Agent config and final polish

**Files:**
- Create: `agents/configs/clawmson-memory.md`
- Run migration script against real DB

### Step 10.1 — Create agent config

Create `agents/configs/clawmson-memory.md`:
```markdown
# Clawmson Memory Agent Config

## System: Hermes 5-Layer Memory

Clawmson maintains 5 layers of persistent memory across all conversations.

### Layers

| Layer | Storage | What it holds |
|-------|---------|--------------|
| Sensory | RAM deque (10 msgs) | Immediate context for each Ollama call |
| Short-Term | SQLite stm_summaries | Rolling summaries of last ~50 exchanges |
| Episodic | SQLite episodic_memories | Significant events with timestamps + valence |
| Semantic | SQLite semantic_facts | Facts/preferences about Jordan and projects |
| Procedural | SQLite procedures | Trigger→action mappings |

### Models Used

| Task | Model |
|------|-------|
| Significance check, fact extraction, summarization | `qwen2.5:7b` (env: OLLAMA_CHAT_MODEL) |
| Embedding (episodic + semantic) | `nomic-embed-text` (env: CLAWMSON_EMBED_MODEL) |

### Memory Injection Format

Injected into system prompt as a `### Memory Context` block:
```
### Memory Context
[Short-term] <rolling summary>
[Episodic] [<date>, <valence>] <episode summary>
[Semantic] <fact> (confidence: <n>)
[Procedural] When Jordan says "<trigger>" → <action>
```

### Telegram Commands

| Command | Description |
|---------|-------------|
| `/memory` | Show current memory context |
| `/memory-stats` | Counts per layer |
| `/forget-memory [layer]` | Clear all or one layer |
| `/remember <trigger> → <action>` | Explicit procedure |
| `/approve-proc <id>` | Approve auto-proposed procedure |
| `/reject-proc <id>` | Reject auto-proposed procedure |

### Tuning Knobs (via env vars)

| Env Var | Default | Description |
|---------|---------|-------------|
| CLAWMSON_SENSORY_WINDOW | 10 | Messages in RAM sensory buffer |
| CLAWMSON_STM_MAX_ROWS | 50 | Active rows before summarization |
| CLAWMSON_STM_BATCH | 25 | Rows summarized per batch |
| CLAWMSON_STM_RETRIEVE_COUNT | 2 | Summaries returned in context |
| CLAWMSON_EPISODIC_TOP_K | 3 | Max episodic memories in context |
| CLAWMSON_EPISODIC_MIN_SIM | 0.6 | Min cosine similarity for episodic |
| CLAWMSON_SEMANTIC_TOP_K | 5 | Max semantic facts in context |
| CLAWMSON_SEMANTIC_MIN_SIM | 0.5 | Min cosine similarity for semantic |
| CLAWMSON_SEMANTIC_MIN_CONF | 0.6 | Min confidence for semantic |
| CLAWMSON_PROC_THRESHOLD | 3 | Occurrences before procedure proposed |
| CLAWMSON_EMBED_MODEL | nomic-embed-text | Ollama embedding model |

### Architecture Notes

- All async ingest runs through `ThreadPoolExecutor(max_workers=1)` — serialized, no STM race
- ingest_async() called AFTER send() — only records delivered messages
- Rejected procedures kept as tombstones (status=rejected) — suppresses re-proposal
- STM uses soft-delete (archived=1) — message log never destroyed
- Cosine similarity computed in-memory — no sqlite-vss dependency
```

### Step 10.2 — Run migration against real DB
```bash
python3 ~/openclaw/scripts/clawmson_memory_migrate.py
```
Expected output shows existing row counts and confirms all new tables created.

### Step 10.3 — Run full test suite one final time
```bash
cd ~/openclaw && python3 -m pytest scripts/tests/test_clawmson_memory.py -v --tb=short
```
Expected: 17 PASS, 0 FAIL.

### Step 10.4 — Final commit
```bash
git add agents/configs/clawmson-memory.md
git commit -m "feat: clawmson-memory agent config — Hermes 5-layer memory complete"
```

---

## Summary

| Task | Files | Tests |
|------|-------|-------|
| 1. DB schema | clawmson_db.py, migrate.py | 3 schema tests |
| 2. SensoryBuffer | clawmson_memory.py | 3 tests |
| 3. ShortTermMemory | clawmson_memory.py | 3 tests |
| 4. EpisodicMemory | clawmson_memory.py | 3 tests |
| 5. SemanticMemory | clawmson_memory.py | 2 tests |
| 6. ProceduralMemory | clawmson_memory.py | 4 tests |
| 7. MemoryManager | clawmson_memory.py | 5 tests |
| 8. clawmson_chat.py | clawmson_chat.py | smoke test |
| 9. Dispatcher wiring | telegram-dispatcher.py | smoke test |
| 10. Agent config | clawmson-memory.md | migration |

**Total: 17 unit tests + 2 smoke tests. 10 git commits.**
