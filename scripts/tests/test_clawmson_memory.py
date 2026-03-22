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


# ── EpisodicMemory tests ─────────────────────────────────────────────────────

class TestEpisodicMemory(unittest.TestCase):
    def setUp(self):
        import importlib
        import clawmson_db
        importlib.reload(clawmson_db)
        import clawmson_memory
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
        results = self.ep.retrieve("c2", "deployment",
                                   embed_fn=lambda t: fake_emb,
                                   min_sim=0.0)
        self.assertEqual(len(results), 1)
        self.assertIn("critical", results[0])
        self.assertIn("Deployed fix", results[0])


class TestSemanticMemory(unittest.TestCase):
    def setUp(self):
        import importlib
        import clawmson_db
        importlib.reload(clawmson_db)
        import clawmson_memory
        importlib.reload(clawmson_memory)
        from clawmson_memory import SemanticMemory
        self.sem = SemanticMemory()

    def test_semantic_upsert(self):
        """Same key updates value — no duplicate row created."""
        import clawmson_db as db
        fake_emb = _fake_embed("")
        facts_v1 = {"facts": [{"key": "preferred model", "value": "qwen3:32b", "confidence": 0.8}]}
        facts_v2 = {"facts": [{"key": "preferred model", "value": "qwen3-coder", "confidence": 0.9}]}
        with patch("clawmson_memory._llm_json", return_value=facts_v1), \
             patch("clawmson_memory._embed", return_value=fake_emb):
            self.sem.ingest("c1", "I prefer qwen3:32b", "got it")
        with patch("clawmson_memory._llm_json", return_value=facts_v2), \
             patch("clawmson_memory._embed", return_value=fake_emb):
            self.sem.ingest("c1", "actually I prefer qwen3-coder", "updated")
        with db._get_conn() as conn:
            rows = conn.execute(
                "SELECT value FROM semantic_facts WHERE chat_id='c1' AND key='preferred model'"
            ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "qwen3-coder")

    def test_semantic_retrieve_topk(self):
        """Returns at most SEMANTIC_TOP_K facts."""
        import clawmson_db as db
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


if __name__ == "__main__":
    unittest.main()
