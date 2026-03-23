# Clawmson FTS5 + Session Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add FTS5 full-text search across all Hermes memory layers and restart-bounded session tracking with automatic resume context injection to Clawmson.

**Architecture:** Two new modules (`clawmson_fts.py`, `clawmson_sessions.py`) plus targeted changes to `clawmson_db.py`, `clawmson_memory.py`, and `telegram-dispatcher.py`. FTS5 and cosine similarity are complementary — FTS handles keyword/phrase search and degrades gracefully when Ollama is unavailable. Sessions are restart-bounded: one UUID session key per bot process run, one DB record per `(session_key, chat_id)`.

**Tech Stack:** Python 3, SQLite FTS5 (porter unicode61 tokenizer), threading.Lock for TOCTOU safety, ThreadPoolExecutor fire-and-forget for LLM summaries.

**Spec:** `docs/superpowers/specs/2026-03-23-clawmson-fts-sessions-design.md`

> **Note on spec ambiguity:** The spec's `end_all_sessions()` docstring says "Does NOT generate LLM summaries" but the spec's prose section (lines 181-192) explicitly requires fire-and-forget LLM summary tasks via `MemoryManager._executor`. This plan follows the prose — summary tasks are queued as fire-and-forget.

---

## File Map

| File | Action | Role |
|------|--------|------|
| `scripts/clawmson_fts.py` | **Create** | FTS5 index management — index, search, remove, format |
| `scripts/clawmson_sessions.py` | **Create** | Session lifecycle — start, ensure, end, resume context |
| `scripts/tests/test_clawmson_fts.py` | **Create** | 8 FTS tests |
| `scripts/tests/test_clawmson_sessions.py` | **Create** | 6 session tests |
| `scripts/clawmson_db.py` | **Modify** | Add `memory_fts` + `sessions` tables; add `fts_index()` helper; update `save_message()` and `save_reference()` to sync FTS |
| `scripts/clawmson_memory.py` | **Modify** | Add FTS results section to `retrieve()`; add FTS sync to EpisodicMemory.ingest(), SemanticMemory.ingest/ingest_explicit(), ShortTermMemory.check_and_summarize() |
| `scripts/telegram-dispatcher.py` | **Modify** | Session start on boot, SIGTERM handler, resume inject on first post-restart message per chat_id, new `/search` command |
| `scripts/clawmson_memory_migrate.py` | **Modify** | Update success message to include new tables |

---

## Task 1: DB Schema — memory_fts + sessions tables + fts_index()

**Files:**
- Modify: `scripts/clawmson_db.py`
- Test: `scripts/tests/test_clawmson_fts.py` (partial — schema only)

### Step 1.1: Write failing test for table existence

- [ ] Create `scripts/tests/test_clawmson_fts.py` with just the schema test:

```python
#!/usr/bin/env python3
"""Tests for FTS5 search module. All FTS tests require FTS5 support."""
from __future__ import annotations
import os
import sys
import unittest
from pathlib import Path

os.environ["CLAWMSON_DB_PATH"] = ":memory:"

_SCRIPTS = Path(__file__).parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import clawmson_db as db
db._init_db()

# Probe FTS5 availability at module level
FTS5_AVAILABLE = False
try:
    import sqlite3 as _sqlite3
    _conn = _sqlite3.connect(":memory:")
    _conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_check USING fts5(x)")
    _conn.close()
    FTS5_AVAILABLE = True
except Exception:
    pass

import clawmson_fts as fts  # noqa: E402 — imported after DB setup


class TestFTSSchema(unittest.TestCase):
    @unittest.skipUnless(FTS5_AVAILABLE, "FTS5 not supported")
    def test_fts_tables_exist(self):
        """memory_fts and sessions tables exist after _init_db()."""
        import importlib
        import clawmson_db
        importlib.reload(clawmson_db)
        with clawmson_db._get_conn() as conn:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' OR type='shadow'"
            ).fetchall()}
            # FTS5 creates shadow tables; check the main virtual table name
            all_names = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master"
            ).fetchall()}
        self.assertIn("memory_fts", all_names)
        self.assertIn("sessions", all_names)


if __name__ == "__main__":
    unittest.main()
```

- [ ] Run test to confirm it fails (ImportError on clawmson_fts):

```
cd ~/openclaw/scripts && python3 -m pytest tests/test_clawmson_fts.py::TestFTSSchema -v
```

Expected: `ModuleNotFoundError: No module named 'clawmson_fts'`

### Step 1.2: Add tables to clawmson_db._init_db()

- [ ] In `scripts/clawmson_db.py`, add to the `executescript` call inside `_init_db()`, **after** the `idx_digests_paper` index line and **before** the closing `"""`):

```sql
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                content,
                source    UNINDEXED,
                chat_id   UNINDEXED,
                source_id UNINDEXED,
                ts        UNINDEXED,
                tokenize = 'porter unicode61'
            );
            CREATE TABLE IF NOT EXISTS sessions (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                session_key   TEXT NOT NULL,
                chat_id       TEXT NOT NULL,
                started_at    TEXT NOT NULL,
                ended_at      TEXT,
                message_count INTEGER NOT NULL DEFAULT 0,
                summary       TEXT,
                UNIQUE(session_key, chat_id)
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_chat ON sessions(chat_id, started_at DESC);
```

**Note:** If the host SQLite was compiled without FTS5, the `CREATE VIRTUAL TABLE` will raise `OperationalError`. Wrap `_init_db()` to catch this case after adding the tables. The actual guard goes in `clawmson_fts.py` (Task 2). For the DB layer, the FTS table creation failure must be non-fatal — catch and log only.

Update `_init_db()` to split FTS creation into a separate try/except block:

```python
def _init_db():
    with _get_conn() as conn:
        conn.executescript("""
            ... (all existing tables and indexes unchanged) ...
            CREATE TABLE IF NOT EXISTS sessions (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                session_key   TEXT NOT NULL,
                chat_id       TEXT NOT NULL,
                started_at    TEXT NOT NULL,
                ended_at      TEXT,
                message_count INTEGER NOT NULL DEFAULT 0,
                summary       TEXT,
                UNIQUE(session_key, chat_id)
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_chat ON sessions(chat_id, started_at DESC);
        """)
    # FTS5 creation is separate — not all SQLite builds support it
    try:
        with _get_conn() as conn:
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                    content,
                    source    UNINDEXED,
                    chat_id   UNINDEXED,
                    source_id UNINDEXED,
                    ts        UNINDEXED,
                    tokenize = 'porter unicode61'
                )
            """)
    except Exception as e:
        print(f"[db] FTS5 not available: {e}")
```

### Step 1.3: Add fts_index() helper to clawmson_db

- [ ] Add after `save_reference()` in `scripts/clawmson_db.py`:

```python
def fts_index(chat_id: str, source: str, source_id: int,
              content: str, ts: str, conn=None):
    """Insert one item into memory_fts. No-op if FTS5 unavailable.

    When conn is provided, INSERT runs inside the caller's existing transaction.
    When conn=None, a new connection is opened.
    """
    # Lazy import avoids circular dependency — clawmson_fts imports clawmson_db
    try:
        import clawmson_fts as _fts
        if not _fts.FTS5_AVAILABLE:
            return
    except ImportError:
        return

    sql = ("INSERT INTO memory_fts (content, source, chat_id, source_id, ts)"
           " VALUES (?, ?, ?, ?, ?)")
    params = (content, source, chat_id, source_id, ts)
    if conn is not None:
        conn.execute(sql, params)
    else:
        with _get_conn() as c:
            c.execute(sql, params)
```

### Step 1.4: Create minimal clawmson_fts.py stub (so test can import)

- [ ] Create `scripts/clawmson_fts.py` with just the FTS5_AVAILABLE probe:

```python
#!/usr/bin/env python3
from __future__ import annotations
"""FTS5 full-text search across all Hermes memory layers."""

import sqlite3 as _sqlite3

# Probe FTS5 availability at module init
FTS5_AVAILABLE = False
try:
    _probe = _sqlite3.connect(":memory:")
    _probe.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_check USING fts5(x)")
    _probe.close()
    FTS5_AVAILABLE = True
except Exception:
    pass
```

### Step 1.5: Run schema test — must pass

- [ ] Run:
```
cd ~/openclaw/scripts && python3 -m pytest tests/test_clawmson_fts.py::TestFTSSchema -v
```
Expected: PASS (or SKIP if FTS5 unavailable on this machine)

### Step 1.6: Commit

```bash
git add scripts/clawmson_db.py scripts/clawmson_fts.py scripts/tests/test_clawmson_fts.py
git commit -m "feat: add memory_fts + sessions tables, fts_index() helper, FTS5 probe"
```

---

## Task 2: clawmson_fts.py — full module

**Files:**
- Modify: `scripts/clawmson_fts.py`
- Modify: `scripts/tests/test_clawmson_fts.py` (add 7 more tests)

### Step 2.1: Add remaining 7 FTS tests

- [ ] Append to `scripts/tests/test_clawmson_fts.py` after `TestFTSSchema`:

```python
class TestFTSIndexAndSearch(unittest.TestCase):
    def setUp(self):
        import importlib
        import clawmson_db
        importlib.reload(clawmson_db)
        import clawmson_fts
        importlib.reload(clawmson_fts)

    @unittest.skipUnless(FTS5_AVAILABLE, "FTS5 not supported")
    def test_fts_index_and_search(self):
        """Index one item; search returns it with rank field."""
        import clawmson_fts as fts
        import datetime
        ts = datetime.datetime.utcnow().isoformat()
        fts.index("chat1", "conversation", 1, "Jordan loves qwen3 model", ts)
        results = fts.search("chat1", "qwen3")
        self.assertEqual(len(results), 1)
        self.assertIn("rank", results[0])
        self.assertIn("snippet", results[0])
        self.assertEqual(results[0]["source"], "conversation")

    @unittest.skipUnless(FTS5_AVAILABLE, "FTS5 not supported")
    def test_fts_cross_layer(self):
        """Items from conversation, episodic, semantic all returned."""
        import clawmson_fts as fts
        import datetime
        ts = datetime.datetime.utcnow().isoformat()
        fts.index("chat2", "conversation", 1, "deploy the qwen3 model server", ts)
        fts.index("chat2", "episodic", 2, "we deployed qwen3 successfully", ts)
        fts.index("chat2", "semantic", 3, "model preference: qwen3", ts)
        results = fts.search("chat2", "qwen3", limit=10)
        sources = {r["source"] for r in results}
        self.assertIn("conversation", sources)
        self.assertIn("episodic", sources)
        self.assertIn("semantic", sources)

    @unittest.skipUnless(FTS5_AVAILABLE, "FTS5 not supported")
    def test_fts_chat_id_scoped(self):
        """chat_id A results do not include chat_id B items."""
        import clawmson_fts as fts
        import datetime
        ts = datetime.datetime.utcnow().isoformat()
        fts.index("chatA", "conversation", 1, "unique phrase alpha bravo", ts)
        fts.index("chatB", "conversation", 2, "unique phrase alpha bravo", ts)
        results = fts.search("chatA", "alpha bravo")
        # Exactly 1 result: the chatA item. chatB item must not leak through.
        # (memory_fts doesn't return chat_id in output columns; count is the isolation proof)
        self.assertEqual(len(results), 1)

    @unittest.skipUnless(FTS5_AVAILABLE, "FTS5 not supported")
    def test_fts_remove(self):
        """Removed item no longer appears in results."""
        import clawmson_fts as fts
        import datetime
        ts = datetime.datetime.utcnow().isoformat()
        fts.index("chat3", "episodic", 42, "unique removable phrase xyz", ts)
        before = fts.search("chat3", "removable phrase")
        self.assertEqual(len(before), 1)
        fts.remove("episodic", 42)
        after = fts.search("chat3", "removable phrase")
        self.assertEqual(len(after), 0)

    @unittest.skipUnless(FTS5_AVAILABLE, "FTS5 not supported")
    def test_fts_in_retrieve_fallback(self):
        """retrieve() returns FTS results when _embed() raises (Ollama down)."""
        import importlib
        import clawmson_db
        importlib.reload(clawmson_db)
        import clawmson_memory
        importlib.reload(clawmson_memory)
        import clawmson_fts as fts
        import datetime
        from unittest.mock import patch

        ts = datetime.datetime.utcnow().isoformat()
        fts.index("chat4", "semantic", 1, "Jordan uses qwen3 coder model", ts)

        from clawmson_memory import MemoryManager
        mm = MemoryManager()
        with patch("clawmson_memory._embed", side_effect=Exception("Ollama down")):
            result = mm.retrieve("chat4", "qwen3 model")
        self.assertIn("qwen3", result.lower())

    @unittest.skipUnless(FTS5_AVAILABLE, "FTS5 not supported")
    def test_search_command_formats_results(self):
        """format_results() returns string with source labels."""
        import clawmson_fts as fts
        import datetime
        ts = datetime.datetime.utcnow().isoformat()
        fts.index("chat5", "conversation", 1, "test format results content here", ts)
        results = fts.search("chat5", "format results")
        formatted = fts.format_results(results)
        self.assertIsInstance(formatted, str)
        self.assertIn("[conversation]", formatted)

    @unittest.skipUnless(FTS5_AVAILABLE, "FTS5 not supported")
    def test_fts_malformed_query_returns_empty(self):
        """Malformed FTS5 query returns [], no exception raised."""
        import clawmson_fts as fts
        result = fts.search("chat6", '"')  # unmatched quote — malformed FTS5 query
        self.assertEqual(result, [])


# Not guarded by @skipUnless — format_results() does not require FTS5
class TestFTSFormat(unittest.TestCase):
    def test_format_results_empty(self):
        """format_results([]) returns 'No results found.'"""
        import clawmson_fts as fts
        self.assertEqual(fts.format_results([]), "No results found.")
```

- [ ] Run tests — expect ImportError or failures (functions not yet implemented):

```
cd ~/openclaw/scripts && python3 -m pytest tests/test_clawmson_fts.py -v
```

### Step 2.2: Implement full clawmson_fts.py

- [ ] Replace `scripts/clawmson_fts.py` with the full implementation:

```python
#!/usr/bin/env python3
from __future__ import annotations
"""FTS5 full-text search across all Hermes memory layers."""
import os
import sqlite3 as _sqlite3
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

# Probe FTS5 availability at module init
FTS5_AVAILABLE = False
try:
    _probe = _sqlite3.connect(":memory:")
    _probe.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_check USING fts5(x)")
    _probe.close()
    FTS5_AVAILABLE = True
except Exception:
    pass

if not FTS5_AVAILABLE:
    import warnings
    warnings.warn("[clawmson_fts] FTS5 not available — search disabled", stacklevel=1)

import clawmson_db as db


def index(chat_id: str, source: str, source_id: int,
          content: str, ts: str, conn=None):
    """Insert one item into memory_fts. No-op if FTS5 unavailable."""
    if not FTS5_AVAILABLE:
        return
    sql = ("INSERT INTO memory_fts (content, source, chat_id, source_id, ts)"
           " VALUES (?, ?, ?, ?, ?)")
    params = (content, source, chat_id, source_id, ts)
    if conn is not None:
        conn.execute(sql, params)
    else:
        with db._get_conn() as c:
            c.execute(sql, params)


def remove(source: str, source_id: int):
    """Delete item from memory_fts by source + source_id. No-op if FTS5 unavailable."""
    if not FTS5_AVAILABLE:
        return
    with db._get_conn() as conn:
        conn.execute(
            "DELETE FROM memory_fts WHERE source=? AND source_id=?",
            (source, source_id)
        )


def search(chat_id: str, query: str, limit: int = 10) -> list[dict]:
    """
    BM25-ranked FTS5 search scoped to chat_id.
    Returns list of {source, content, snippet, ts, rank}.
    Returns [] if FTS5 unavailable or query is empty.

    Query is phrase-quoted before MATCH to handle multi-word queries.
    OperationalError (malformed FTS5 query) is caught and returns [].
    """
    if not FTS5_AVAILABLE or not query or not query.strip():
        return []

    # Phrase-quote for exact phrase matching; escape any embedded quotes
    safe_query = query.strip().replace('"', '""')
    fts_query = f'"{safe_query}"'

    try:
        with db._get_conn() as conn:
            rows = conn.execute(
                "SELECT source, content,"
                " snippet(memory_fts, 0, '>>', '<<', '...', 8) AS snippet,"
                " ts, rank"
                " FROM memory_fts"
                " WHERE memory_fts MATCH ? AND chat_id = ?"
                " ORDER BY rank LIMIT ?",
                (fts_query, chat_id, limit)
            ).fetchall()
        return [dict(r) for r in rows]
    except _sqlite3.OperationalError:
        return []


def format_results(results: list[dict]) -> str:
    """Format search results for Telegram /search reply.
    Each result: '[source] snippet (ts)'
    Returns 'No results found.' if list is empty.
    """
    if not results:
        return "No results found."
    lines = []
    for r in results:
        ts_short = r.get("ts", "")[:10]
        snippet = r.get("snippet") or r.get("content", "")[:100]
        lines.append(f"[{r['source']}] {snippet} ({ts_short})")
    return "\n".join(lines)
```

### Step 2.3: Run all FTS tests — must pass

- [ ] Run:
```
cd ~/openclaw/scripts && python3 -m pytest tests/test_clawmson_fts.py -v
```
Expected: All tests PASS (or SKIP for FTS5-guarded tests if FTS5 unavailable)

### Step 2.4: Commit

```bash
git add scripts/clawmson_fts.py scripts/tests/test_clawmson_fts.py
git commit -m "feat: clawmson_fts module — index/search/remove/format with FTS5 probe"
```

---

## Task 3: FTS sync at all 5 insert sites in clawmson_db + clawmson_memory

**Files:**
- Modify: `scripts/clawmson_db.py` (save_message, save_reference)
- Modify: `scripts/clawmson_memory.py` (EpisodicMemory.ingest, SemanticMemory.ingest, SemanticMemory.ingest_explicit, ShortTermMemory.check_and_summarize)

### Step 3.1: FTS sync in save_message()

`save_message()` is in `clawmson_db.py` at line 167. It must capture `lastrowid` and call `fts_index()` within the same connection context.

- [ ] Replace `save_message()` in `scripts/clawmson_db.py`:

```python
def save_message(chat_id: str, role: str, content: str,
                 message_id: int = None, media_type: str = None):
    ts = datetime.datetime.utcnow().isoformat()
    with _get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO conversations (chat_id, message_id, role, content, timestamp, media_type)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (chat_id, message_id, role, content, ts, media_type)
        )
        source_id = cur.lastrowid
        fts_index(chat_id, "conversation", source_id, content, ts, conn=conn)
```

### Step 3.2: FTS sync in save_reference()

`save_reference()` is at line 210. Index `title + " " + summary`.

- [ ] Replace `save_reference()` in `scripts/clawmson_db.py`:

```python
def save_reference(chat_id: str, url: str, title: str, summary: str, content: str):
    ts = datetime.datetime.utcnow().isoformat()
    with _get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO refs (chat_id, url, title, summary, content, timestamp)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (chat_id, url, title or url, summary, content, ts)
        )
        source_id = cur.lastrowid
        fts_content = f"{title or url} {summary or ''}".strip()
        fts_index(chat_id, "reference", source_id, fts_content, ts, conn=conn)
```

### Step 3.3: FTS sync in EpisodicMemory.ingest()

In `scripts/clawmson_memory.py`, `EpisodicMemory.ingest()` at line 259. After the INSERT into `episodic_memories`, capture `lastrowid` and call `db.fts_index()`.

- [ ] In `EpisodicMemory.ingest()`, replace the `with db._get_conn() as conn:` block (lines 289-295):

```python
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
```

### Step 3.4: FTS sync in SemanticMemory.ingest() and ingest_explicit()

Both methods use `ON CONFLICT ... DO UPDATE` (UPSERT), so `lastrowid` refers to the affected row's rowid — correct for both INSERT and UPDATE paths.

- [ ] In `SemanticMemory.ingest()`, replace the inner `with db._get_conn() as conn:` block (lines 373-382):

```python
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
```

- [ ] In `SemanticMemory.ingest_explicit()`, replace the `with db._get_conn() as conn:` block (lines 392-399):

```python
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
```

### Step 3.5: FTS sync in ShortTermMemory.check_and_summarize()

In `scripts/clawmson_memory.py`, `ShortTermMemory.check_and_summarize()` at line 182. After the INSERT into `stm_summaries`, capture `lastrowid` and call `db.fts_index()`.

- [ ] Replace the `with db._get_conn() as conn:` block that inserts the summary (lines 216-226):

```python
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
```

### Step 3.6: Run full test suite — must still pass

- [ ] Run:
```
cd ~/openclaw/scripts && python3 -m pytest tests/ -v
```
Expected: All 27 existing tests + 8 FTS tests PASS (some FTS tests may SKIP)

### Step 3.7: Commit

```bash
git add scripts/clawmson_db.py scripts/clawmson_memory.py
git commit -m "feat: FTS sync at all 5 memory insert sites"
```

---

## Task 4: FTS integration into retrieve() + fallback

**Files:**
- Modify: `scripts/clawmson_memory.py`

The `retrieve()` method in `MemoryManager` (line 575) assembles the context block. Add FTS results after the procedural section, with deduplication by `(source, source_id)`.

Also add config constant at top of file.

### Step 4.1: Add FTS_LIMIT config constant

- [ ] In `scripts/clawmson_memory.py`, after `PROC_THRESHOLD` line (line 54), add:

```python
CLAWMSON_FTS_LIMIT = int(os.environ.get("CLAWMSON_FTS_LIMIT", "5"))
```

### Step 4.2: Update retrieve() to include FTS results

- [ ] Replace `MemoryManager.retrieve()` (lines 575-616) with:

```python
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
        try:
            episodes = self._episodic.retrieve(chat_id, probe)
        except Exception:
            episodes = []
        if episodes:
            parts.append("**Past events:**")
            parts.extend(episodes)

        # Layer 4: Semantic
        try:
            facts = self._semantic.retrieve(chat_id, probe)
        except Exception:
            facts = []
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
```

**Known v1 spec deviation — deduplication scope:** The spec (line 125) requires FTS results to be deduplicated against episodic/semantic results already assembled, tracked as a `(source, source_id)` set during assembly. This is implemented here only between FTS results — `seen_ids` is never populated from the episodic/semantic layers because those layers return formatted strings, not `(source_id, text)` tuples. Full dedup would require changing those return types, which is a deeper refactor. This is a known out-of-spec v1 limitation: in the rare case a semantic or episodic fact also exists in `memory_fts`, the context block may contain it twice. Acceptable for v1; full dedup deferred to v2.

### Step 4.3: Run test_fts_in_retrieve_fallback

- [ ] Run:
```
cd ~/openclaw/scripts && python3 -m pytest tests/test_clawmson_fts.py::TestFTSIndexAndSearch::test_fts_in_retrieve_fallback -v
```
Expected: PASS (or SKIP if FTS5 unavailable)

### Step 4.4: Run full suite

- [ ] Run:
```
cd ~/openclaw/scripts && python3 -m pytest tests/ -v
```
Expected: All tests PASS

### Step 4.5: Commit

```bash
git add scripts/clawmson_memory.py
git commit -m "feat: FTS results in retrieve() with Ollama fallback and dedup"
```

---

## Task 5: clawmson_sessions.py module

**Files:**
- Modify: `scripts/clawmson_sessions.py` (full implementation)
- Create: `scripts/tests/test_clawmson_sessions.py`

### Step 5.1: Write failing session tests

- [ ] Create `scripts/tests/test_clawmson_sessions.py`:

```python
#!/usr/bin/env python3
"""Tests for session lifecycle module."""
from __future__ import annotations
import os
import sys
import datetime
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

os.environ["CLAWMSON_DB_PATH"] = ":memory:"
os.environ["CLAWMSON_SESSION_KEY_FILE"] = "/tmp/test-clawmson-session-key.txt"

_SCRIPTS = Path(__file__).parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import clawmson_db as db
db._init_db()


def _now_offset(hours: float) -> str:
    """Return UTC ISO timestamp offset by `hours` from now."""
    return (datetime.datetime.utcnow() +
            datetime.timedelta(hours=hours)).isoformat()


class TestSessions(unittest.TestCase):
    def setUp(self):
        import importlib
        import clawmson_db
        importlib.reload(clawmson_db)
        # Clean sessions table
        with clawmson_db._get_conn() as conn:
            conn.execute("DELETE FROM sessions")
        import clawmson_sessions
        importlib.reload(clawmson_sessions)
        # Remove stale key file
        key_file = Path(os.environ["CLAWMSON_SESSION_KEY_FILE"])
        if key_file.exists():
            key_file.unlink()

    def test_start_session_writes_key_file(self):
        """start_session() creates key file containing a valid UUID."""
        import uuid
        import clawmson_sessions as sessions
        key = sessions.start_session()
        key_file = Path(os.environ["CLAWMSON_SESSION_KEY_FILE"])
        self.assertTrue(key_file.exists())
        written = key_file.read_text().strip()
        self.assertEqual(written, key)
        # Validate UUID format
        uuid.UUID(key)  # raises if invalid

    def test_ensure_session_creates_record(self):
        """First ensure_session() call creates row; second increments message_count."""
        import clawmson_sessions as sessions
        import clawmson_db as db
        key = "test-key-001"
        sessions.ensure_session(key, "chat1")
        with db._get_conn() as conn:
            row = conn.execute(
                "SELECT message_count FROM sessions WHERE session_key=? AND chat_id=?",
                (key, "chat1")
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 1)

        sessions.ensure_session(key, "chat1")
        with db._get_conn() as conn:
            row2 = conn.execute(
                "SELECT message_count FROM sessions WHERE session_key=? AND chat_id=?",
                (key, "chat1")
            ).fetchone()
        self.assertEqual(row2[0], 2)

    def test_end_all_sessions_sets_ended_at(self):
        """end_all_sessions() sets ended_at for all open sessions."""
        import clawmson_sessions as sessions
        import clawmson_db as db
        key = "test-key-002"
        sessions.ensure_session(key, "chatA")
        sessions.ensure_session(key, "chatB")
        # Mock MemoryManager to avoid Ollama calls
        with patch("clawmson_sessions.MemoryManager") as MockMM:
            mock_mm = MagicMock()
            mock_mm._executor = MagicMock()
            MockMM.return_value = mock_mm
            sessions.end_all_sessions(key)
        with db._get_conn() as conn:
            rows = conn.execute(
                "SELECT ended_at FROM sessions WHERE session_key=?", (key,)
            ).fetchall()
        self.assertEqual(len(rows), 2)
        for r in rows:
            self.assertIsNotNone(r[0])

    def test_get_resume_context_recent(self):
        """Session ended <24h ago with summary returns ### Previous Session block."""
        import clawmson_sessions as sessions
        import clawmson_db as db
        old_key = "old-key-001"
        new_key = "new-key-001"
        ended = _now_offset(-1)  # 1 hour ago
        with db._get_conn() as conn:
            conn.execute(
                "INSERT INTO sessions (session_key, chat_id, started_at, ended_at,"
                " message_count, summary) VALUES (?,?,?,?,?,?)",
                (old_key, "chat1", _now_offset(-2), ended, 5,
                 "Jordan was debugging the FTS module.")
            )
        result = sessions.get_resume_context("chat1", new_key)
        self.assertIn("### Previous Session", result)
        self.assertIn("FTS module", result)

    def test_get_resume_context_stale(self):
        """Session ended >24h ago returns empty string."""
        import clawmson_sessions as sessions
        import clawmson_db as db
        old_key = "old-key-002"
        new_key = "new-key-002"
        ended = _now_offset(-25)  # 25 hours ago
        with db._get_conn() as conn:
            conn.execute(
                "INSERT INTO sessions (session_key, chat_id, started_at, ended_at,"
                " message_count, summary) VALUES (?,?,?,?,?,?)",
                (old_key, "chat2", _now_offset(-26), ended, 3, "Some old session.")
            )
        result = sessions.get_resume_context("chat2", new_key)
        self.assertEqual(result, "")

    def test_get_resume_context_null_ended_at(self):
        """Session with ended_at=NULL (kill -9 case) returns empty string."""
        import clawmson_sessions as sessions
        import clawmson_db as db
        old_key = "old-key-003"
        new_key = "new-key-003"
        with db._get_conn() as conn:
            conn.execute(
                "INSERT INTO sessions (session_key, chat_id, started_at,"
                " message_count, summary) VALUES (?,?,?,?,?)",
                (old_key, "chat3", _now_offset(-1), 5, "Killed without SIGTERM.")
            )
        result = sessions.get_resume_context("chat3", new_key)
        self.assertEqual(result, "")


if __name__ == "__main__":
    unittest.main()
```

- [ ] Run tests — expect ImportError:
```
cd ~/openclaw/scripts && python3 -m pytest tests/test_clawmson_sessions.py -v
```

### Step 5.2: Implement clawmson_sessions.py

- [ ] Create `scripts/clawmson_sessions.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations
"""
Session lifecycle for Clawmson.
Sessions are restart-bounded: one UUID session_key per bot process run.
One DB record per (session_key, chat_id), created lazily on first message.
"""
import os
import uuid
import datetime
from pathlib import Path

SESSION_KEY_FILE = Path(os.environ.get(
    "CLAWMSON_SESSION_KEY_FILE", "/tmp/clawmson-session-key.txt"
))
RESUME_WINDOW_HOURS = int(os.environ.get("CLAWMSON_RESUME_WINDOW_HOURS", "24"))


def _now() -> str:
    return datetime.datetime.utcnow().isoformat()


def start_session() -> str:
    """
    Generate UUID session_key, write to SESSION_KEY_FILE.
    Returns session_key. Called once on dispatcher boot.
    """
    key = str(uuid.uuid4())
    SESSION_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_KEY_FILE.write_text(key)
    return key


def ensure_session(session_key: str, chat_id: str):
    """
    INSERT OR IGNORE session record for (session_key, chat_id).
    Increments message_count on every call (including the INSERT).
    Called per-message from dispatcher.
    """
    import clawmson_db as db
    ts = _now()
    with db._get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO sessions"
            " (session_key, chat_id, started_at, message_count)"
            " VALUES (?, ?, ?, 0)",
            (session_key, chat_id, ts)
        )
        conn.execute(
            "UPDATE sessions SET message_count = message_count + 1"
            " WHERE session_key=? AND chat_id=?",
            (session_key, chat_id)
        )


def end_all_sessions(session_key: str):
    """
    Called on SIGTERM/SIGINT. Sets ended_at = utcnow() for all open sessions
    under session_key. Queues fire-and-forget LLM summary tasks via executor.
    """
    import clawmson_db as db
    ts = _now()
    with db._get_conn() as conn:
        rows = conn.execute(
            "SELECT id, chat_id FROM sessions"
            " WHERE session_key=? AND ended_at IS NULL",
            (session_key,)
        ).fetchall()
        if not rows:
            return
        conn.execute(
            "UPDATE sessions SET ended_at=? WHERE session_key=? AND ended_at IS NULL",
            (ts, session_key)
        )

    # Fire-and-forget LLM summaries via MemoryManager executor
    # Import here to avoid circular import at module level
    try:
        from clawmson_memory import MemoryManager
        _mm = MemoryManager()
        for row in rows:
            sid = row[0]
            cid = row[1]
            _mm._executor.submit(_generate_summary, sid, cid)
        _mm._executor.shutdown(wait=False)
    except Exception as e:
        print(f"[sessions] Could not queue summary tasks: {e}")


def _generate_summary(session_id: int, chat_id: str):
    """Background task: generate 3-sentence LLM summary for a session."""
    try:
        import clawmson_db as db
        from clawmson_memory import _llm_text

        with db._get_conn() as conn:
            msgs = conn.execute(
                "SELECT role, content FROM conversations"
                " WHERE chat_id=? ORDER BY id DESC LIMIT 20",
                (chat_id,)
            ).fetchall()

        if not msgs:
            return

        exchange = "\n".join(
            f"{r['role'].capitalize()}: {r['content'][:200]}"
            for r in reversed(msgs)
        )
        prompt = (
            f"Summarize the following conversation in exactly 3 sentences, "
            f"focusing on topics discussed, decisions made, and key information.\n\n"
            f"{exchange}"
        )
        summary = _llm_text(prompt)
        if not summary:
            return

        with db._get_conn() as conn:
            conn.execute(
                "UPDATE sessions SET summary=? WHERE id=?",
                (summary, session_id)
            )
    except Exception as e:
        print(f"[sessions] Summary generation failed for session {session_id}: {e}")


def get_resume_context(chat_id: str, current_session_key: str) -> str:
    """
    Find the most recent session for chat_id where session_key != current_session_key.

    Returns '### Previous Session\\n<summary>' if ALL of:
      - ended_at IS NOT NULL
      - ended_at is within RESUME_WINDOW_HOURS of utcnow()
      - summary IS NOT NULL and non-empty

    Returns "" in all other cases.
    """
    import clawmson_db as db
    with db._get_conn() as conn:
        row = conn.execute(
            "SELECT ended_at, summary FROM sessions"
            " WHERE chat_id=? AND session_key != ?"
            " ORDER BY started_at DESC LIMIT 1",
            (chat_id, current_session_key)
        ).fetchone()

    if not row:
        return ""

    ended_at = row["ended_at"] if hasattr(row, "keys") else row[0]
    summary = row["summary"] if hasattr(row, "keys") else row[1]

    if not ended_at:
        return ""
    if not summary:
        return ""

    try:
        ended_dt = datetime.datetime.fromisoformat(ended_at)
        now_dt = datetime.datetime.utcnow()
        age_hours = (now_dt - ended_dt).total_seconds() / 3600
        if age_hours > RESUME_WINDOW_HOURS:
            return ""
    except Exception:
        return ""

    return f"### Previous Session\n{summary}"
```

### Step 5.3: Run session tests — must all pass

- [ ] Run:
```
cd ~/openclaw/scripts && python3 -m pytest tests/test_clawmson_sessions.py -v
```
Expected: All 6 tests PASS

### Step 5.4: Run full suite

- [ ] Run:
```
cd ~/openclaw/scripts && python3 -m pytest tests/ -v
```
Expected: All tests PASS (≥33 tests)

### Step 5.5: Commit

```bash
git add scripts/clawmson_sessions.py scripts/tests/test_clawmson_sessions.py
git commit -m "feat: clawmson_sessions — start/ensure/end/resume lifecycle"
```

---

## Task 6: Wire into telegram-dispatcher.py

**Files:**
- Modify: `scripts/telegram-dispatcher.py`

Four changes:
1. Import sessions module + declare module-level state
2. Call `start_session()` on boot in `main()`
3. Register SIGTERM/SIGINT handlers in `main()`
4. Resume injection + `ensure_session()` in `_conversation_thread()`
5. Add `/search` command before `/memory-stats` routing block

### Step 6.1: Add imports and module-level state

- [ ] In `scripts/telegram-dispatcher.py`, after `import clawmson_memory as mem_module` (line 59), add:

```python
import clawmson_fts as fts
import clawmson_sessions as sessions
import signal

CLAWMSON_SEARCH_LIMIT = int(os.environ.get("CLAWMSON_SEARCH_LIMIT", "10"))

_SESSION_KEY: str = ""                     # set on boot by start_session()
_resumed: set[str] = set()                # chat_ids already resumed this process run
_resumed_lock = threading.Lock()           # guards check-then-add on _resumed
```

### Step 6.2: Add handle_search function

- [ ] After `handle_reject_proc()` (around line 390), add:

```python
def handle_search(chat_id: str, query: str):
    """FTS5 keyword search across all memory layers. Usage: /search <query>"""
    results = fts.search(chat_id, query, limit=CLAWMSON_SEARCH_LIMIT)
    send(chat_id, fts.format_results(results))
```

### Step 6.3: Add /search routing before /memory-stats

- [ ] In the `/slash commands` block, add `/search` routing **before** the `/memory-stats` block (currently around line 527):

```python
        if lower.startswith("/search"):
            query = text[len("/search"):].strip()
            if not query:
                send(chat_id, "Usage: /search <query>")
            else:
                handle_search(chat_id, query)
            return
```

### Step 6.4: Add resume injection + ensure_session in _conversation_thread()

- [ ] Replace `_conversation_thread()` (lines 416-435):

```python
def _conversation_thread(chat_id: str, effective_text: str,
                         has_image: bool, intent: str = None):
    """Called in a background thread. Fetches Ollama reply and sends it."""
    send_typing(chat_id)

    # Session tracking
    if _SESSION_KEY:
        sessions.ensure_session(_SESSION_KEY, chat_id)

    history        = _memory.sensory(chat_id)
    memory_context = _memory.retrieve(chat_id, effective_text)

    # Resume injection: first post-restart message per chat_id gets previous session context
    if _SESSION_KEY:
        with _resumed_lock:
            already_resumed = chat_id in _resumed
            if not already_resumed:
                _resumed.add(chat_id)
        if not already_resumed:
            resume = sessions.get_resume_context(chat_id, _SESSION_KEY)
            if resume:
                memory_context = resume + "\n\n" + memory_context

    model_name = router.route(effective_text, intent=intent, has_image=has_image)
    t0    = time.monotonic()
    reply = llm.chat(history, effective_text, has_image=has_image,
                     model=model_name, memory_context=memory_context)
    elapsed_ms = (time.monotonic() - t0) * 1000

    success = not any(reply.startswith(e) for e in _OLLAMA_ERROR_PREFIXES)
    task_type = "vision" if has_image else (
        router.INTENT_TO_TASK.get(intent, "chat") if intent else "chat"
    )
    router.record_result(model_name, task_type, elapsed_ms, success=success)

    send(chat_id, reply)
    _memory.ingest_async(chat_id, "assistant", reply)
```

### Step 6.5: Wire SIGTERM handler and session start in main()

- [ ] Add `_shutdown()` function before `main()` (around line 668):

```python
def _shutdown():
    """Clean shutdown: end all sessions, then exit."""
    if _SESSION_KEY:
        sessions.end_all_sessions(_SESSION_KEY)
    sys.exit(0)
```

- [ ] Modify `main()` to call `start_session()` and register signal handlers:

```python
def main():
    global _SESSION_KEY
    _SESSION_KEY = sessions.start_session()
    print(f"[dispatcher] Session key: {_SESSION_KEY}")

    signal.signal(signal.SIGTERM, lambda sig, frame: _shutdown())
    signal.signal(signal.SIGINT,  lambda sig, frame: _shutdown())

    print(f"[dispatcher] Starting Clawmson. Allowed users: {ALLOWED_USERS}")
    print(f"[dispatcher] Default repo: {DEFAULT_REPO} @ {DEFAULT_REPO_PATH}")
    print(f"[dispatcher] Ollama: {os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434')}"
          f" / model routing active")
    offset = load_offset()

    while True:
        updates = get_updates(offset)
        for update in updates:
            offset = update["update_id"] + 1
            save_offset(offset)
            msg = update.get("message", {})
            if msg:
                try:
                    handle_message(msg)
                except Exception as e:
                    print(f"[dispatcher] Unhandled error: {e}")
        time.sleep(POLL_INTERVAL)
```

### Step 6.6: Run full test suite

- [ ] Run:
```
cd ~/openclaw/scripts && python3 -m pytest tests/ -v
```
Expected: All tests PASS

### Step 6.7: Commit

```bash
git add scripts/telegram-dispatcher.py
git commit -m "feat: wire sessions + /search into dispatcher — SIGTERM handler, resume injection"
```

---

## Task 7: Migration update + final verification

**Files:**
- Modify: `scripts/clawmson_memory_migrate.py`

### Step 7.1: Update migration script success message

- [ ] In `scripts/clawmson_memory_migrate.py`, update the final print statement (line 51):

```python
    print(f"  New tables ready: stm_summaries, episodic_memories, semantic_facts,"
          f" procedures, procedure_candidates, memory_fts, sessions")
```

### Step 7.2: Run migration against live DB

- [ ] Run:
```
python3 ~/openclaw/scripts/clawmson_memory_migrate.py
```
Expected output includes: `memory_fts, sessions` in the new tables line

### Step 7.3: Final full test run — count must be ≥ 39

- [ ] Run:
```
cd ~/openclaw/scripts && python3 -m pytest tests/ -v --tb=short 2>&1 | tail -20
```
Expected: `40 passed` (or `40 passed, N skipped` if FTS5 unavailable — 8 guarded FTS tests skip, `test_format_results_empty` always runs)

### Step 7.4: Commit

```bash
git add scripts/clawmson_memory_migrate.py
git commit -m "feat: update migration script to report memory_fts and sessions tables"
```

---

## Final Checklist

- [ ] 15 new tests added (9 FTS + 6 sessions), total ≥ 40
  - **Note:** spec specifies 8 FTS tests and total 39; this plan adds 1 extra (`test_format_results_empty` in `TestFTSFormat`, which does not require FTS5 and is intentionally beyond the spec's test table)
- [ ] All tests pass (or skip with `@skipUnless` guard for FTS5-specific tests)
- [ ] `clawmson_fts.FTS5_AVAILABLE` probe at module init — no crash on systems without FTS5
- [ ] `fts_index()` called at all 5 insert sites with correct `source_id` from `lastrowid`
- [ ] `_resumed_lock` prevents TOCTOU race on resume injection
- [ ] SIGTERM handler calls `end_all_sessions()` before `sys.exit(0)`
- [ ] `/search` routing placed before `/memory-stats` in dispatcher
- [ ] Migration script updated and run against live DB
