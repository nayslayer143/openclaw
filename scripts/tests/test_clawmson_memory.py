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


if __name__ == "__main__":
    unittest.main()
