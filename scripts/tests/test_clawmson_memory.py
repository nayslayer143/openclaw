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

# Force re-initialization with in-memory DB
db._init_db()


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


# ── Helper: fake embedding (no Ollama needed) ────────────────────────────────

def _fake_embed(text: str) -> bytes:
    """Return a deterministic fake embedding (all zeros, 768-dim)."""
    import numpy as np
    return np.zeros(768, dtype=np.float32).tobytes()


def _now():
    import datetime
    return datetime.datetime.utcnow().isoformat()


# ── SensoryBuffer tests ──────────────────────────────────────────────────────

class TestSensoryBuffer(unittest.TestCase):
    def setUp(self):
        """Fresh in-memory DB for each test class."""
        import importlib
        # Reload db module to get a fresh in-memory connection
        import clawmson_db
        importlib.reload(clawmson_db)
        # Clear any existing test data
        with clawmson_db._get_conn() as conn:
            conn.execute("DELETE FROM conversations")
            conn.execute("DELETE FROM context")

    def _get_sensory(self):
        import importlib
        import clawmson_memory
        importlib.reload(clawmson_memory)
        from clawmson_memory import SensoryBuffer
        return SensoryBuffer(window=10)

    def test_sensory_buffer_limit(self):
        """Buffer caps at window size; oldest message evicted."""
        buf = self._get_sensory()
        for i in range(15):
            buf.push("c1", "user", f"msg {i}")
        result = buf.get("c1")
        self.assertEqual(len(result), 10)
        self.assertEqual(result[0]["content"], "msg 5")  # oldest kept
        self.assertEqual(result[-1]["content"], "msg 14")

    def test_sensory_cold_start(self):
        """Seeds from DB (archived=0 only) on first get()."""
        import clawmson_db as db
        db.save_message("c2", "user", "old msg")
        with db._get_conn() as conn:
            conn.execute("UPDATE conversations SET archived=1 WHERE chat_id='c2'")
        db.save_message("c2", "user", "live msg")

        buf = self._get_sensory()
        result = buf.get("c2")
        contents = [m["content"] for m in result]
        self.assertIn("live msg", contents)
        self.assertNotIn("old msg", contents)

    def test_sensory_push_role_preserved(self):
        """role field is stored and returned correctly."""
        buf = self._get_sensory()
        buf.push("c3", "assistant", "hello there")
        msgs = buf.get("c3")
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["role"], "assistant")
        self.assertEqual(msgs[0]["content"], "hello there")


# ── ShortTermMemory tests ────────────────────────────────────────────────────

class TestShortTermMemory(unittest.TestCase):
    def setUp(self):
        """Fresh in-memory DB for each test."""
        import importlib
        import clawmson_db
        importlib.reload(clawmson_db)
        import clawmson_memory
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


if __name__ == "__main__":
    unittest.main()
