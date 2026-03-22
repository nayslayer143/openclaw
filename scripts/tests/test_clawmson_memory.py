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


class TestProceduralMemory(unittest.TestCase):
    def setUp(self):
        import importlib
        import clawmson_db
        importlib.reload(clawmson_db)
        import clawmson_memory
        importlib.reload(clawmson_memory)
        from clawmson_memory import ProceduralMemory
        self.proc = ProceduralMemory(threshold=3)
        self._notifications = []

    def _notify(self, chat_id, msg):
        self._notifications.append((chat_id, msg))

    def test_procedural_explicit(self):
        """add_procedure() creates an active procedure immediately."""
        import clawmson_db as db
        pid = self.proc.add_procedure("c1", "scout X", "run research pipeline on X")
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
        import clawmson_db as db
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
        self.assertIsNotNone(row2)  # row kept (tombstone)
        self.assertEqual(row2["status"], "rejected")

    def test_procedural_no_reproposal_after_reject(self):
        """Rejected (intent, action) pair is not proposed again."""
        import clawmson_db as db
        # Insert a rejected tombstone procedure for "build" action
        ts = _now()
        with db._get_conn() as conn:
            conn.execute(
                "INSERT INTO procedures"
                " (chat_id, trigger_pattern, action_description, created_by, status,"
                "  occurrence_count, timestamp)"
                " VALUES ('c4','build','build thing','proposed','rejected',3,?)",
                (ts,)
            )
        # Now fire 3 candidate occurrences for the same (intent, action)
        for _ in range(3):
            self.proc.track_candidate("c4", "BUILD_TASK", "build",
                                      "build it", notify_fn=self._notify)
        self.assertEqual(len(self._notifications), 0)  # no re-proposal


class TestMemoryManager(unittest.TestCase):
    def setUp(self):
        import importlib
        import clawmson_db
        importlib.reload(clawmson_db)
        import clawmson_memory
        importlib.reload(clawmson_memory)
        from clawmson_memory import MemoryManager
        self.mm = MemoryManager()

    def _fake_embed(self, text: str) -> bytes:
        import numpy as np
        return np.zeros(768, dtype=np.float32).tobytes()

    def _nonzero_embed(self) -> bytes:
        """Return a non-zero embedding so cosine similarity is 1.0 between identical vectors."""
        import numpy as np
        v = np.ones(768, dtype=np.float32)
        return v.tobytes()

    def test_retrieve_assembles_context(self):
        """retrieve() returns a ### Memory Context block when data exists."""
        import clawmson_db as db
        from unittest.mock import patch
        # Use non-zero embedding so cosine similarity passes MIN_SIM threshold
        nonzero_emb = self._nonzero_embed()
        with db._get_conn() as conn:
            conn.execute(
                "INSERT INTO semantic_facts"
                " (chat_id, key, value, confidence, source, timestamp, embedding)"
                " VALUES (?,?,?,?,?,?,?)",
                ("c1", "model_pref", "Jordan prefers qwen3:32b", 0.9, "explicit", _now(), nonzero_emb)
            )
        # Patch _embed to return the same non-zero vector so cosine similarity == 1.0
        with patch("clawmson_memory._embed", return_value=nonzero_emb):
            result = self.mm.retrieve("c1", "model preference")
        self.assertIn("### Memory Context", result)
        self.assertIn("Jordan prefers qwen3:32b", result)

    def test_retrieve_empty_query_uses_probe(self):
        """retrieve() with empty query falls back to default probe and still returns string."""
        import clawmson_db as db
        from unittest.mock import patch
        nonzero_emb = self._nonzero_embed()
        with db._get_conn() as conn:
            conn.execute(
                "INSERT INTO semantic_facts"
                " (chat_id, key, value, confidence, source, timestamp, embedding)"
                " VALUES (?,?,?,?,?,?,?)",
                ("c2", "info", "Jordan runs openclaw", 0.9, "explicit", _now(), nonzero_emb)
            )
        with patch("clawmson_memory._embed", return_value=nonzero_emb):
            result = self.mm.retrieve("c2", "")  # empty query
        self.assertIsInstance(result, str)
        self.assertIn("Jordan runs openclaw", result)

    def test_ingest_async_nonblocking(self):
        """ingest_async() returns quickly (doesn't block the caller)."""
        import clawmson_db as db
        from unittest.mock import patch
        import time
        slow_called = []

        def slow_llm(prompt):
            time.sleep(0.3)
            slow_called.append(True)
            return ""

        with patch("clawmson_memory._llm_text", side_effect=slow_llm), \
             patch("clawmson_memory._embed", return_value=self._fake_embed("")), \
             patch("clawmson_memory._llm_json", return_value={}):
            # Seed a user message in sensory so assistant ingest has something to work with
            self.mm._sensory.push("c3", "user", "we deployed the fix")
            t0 = time.time()
            self.mm.ingest_async("c3", "assistant", "it broke prod login")
            elapsed = time.time() - t0
        # Should return in well under 0.2s even though LLM sleeps 0.3s
        self.assertLess(elapsed, 0.2)

    def test_ingest_async_concurrent_no_duplicate_summaries(self):
        """Serial executor (max_workers=1) prevents duplicate STM summaries."""
        import clawmson_db as db
        from unittest.mock import patch
        import time

        # Pre-fill 12 messages to trigger STM summarization
        for i in range(12):
            db.save_message("c4", "user" if i % 2 == 0 else "assistant", f"msg {i}")

        calls = []

        def counting_llm(prompt):
            calls.append(1)
            time.sleep(0.05)
            return "test summary"

        with patch("clawmson_memory._llm_text", side_effect=counting_llm), \
             patch("clawmson_memory._llm_json", return_value={}), \
             patch("clawmson_memory._embed", return_value=self._fake_embed("")):
            # Seed user message in sensory buffer so _full_ingest_wrapper finds it
            self.mm._sensory.push("c4", "user", "we deployed the fix")
            # Fire two concurrent ingests
            self.mm.ingest_async("c4", "assistant", "msg A")
            self.mm.ingest_async("c4", "assistant", "msg B")
            # Wait for executor to finish
            self.mm._executor.shutdown(wait=True)

        with db._get_conn() as conn:
            summaries = conn.execute(
                "SELECT COUNT(*) FROM stm_summaries WHERE chat_id='c4'"
            ).fetchone()[0]
        # Serial executor means at most 1 summary per trigger
        self.assertLessEqual(summaries, 1)

    def test_clear_layer(self):
        """clear() removes data from the specified layer only."""
        import clawmson_db as db
        from unittest.mock import patch
        fake_emb = self._fake_embed("")
        # Insert one semantic fact and one episodic memory
        with db._get_conn() as conn:
            conn.execute(
                "INSERT INTO semantic_facts"
                " (chat_id, key, value, confidence, source, timestamp, embedding)"
                " VALUES (?,?,?,?,?,?,?)",
                ("c5", "k1", "some fact", 0.9, "explicit", _now(), fake_emb)
            )
            conn.execute(
                "INSERT INTO episodic_memories"
                " (chat_id, content, summary, timestamp, valence, embedding)"
                " VALUES (?,?,?,?,?,?)",
                ("c5", "content", "episode", _now(), "neutral", fake_emb)
            )
        # Clear only semantic
        self.mm.clear("c5", layer="semantic")
        with db._get_conn() as conn:
            sem_count = conn.execute(
                "SELECT COUNT(*) FROM semantic_facts WHERE chat_id='c5'"
            ).fetchone()[0]
            ep_count = conn.execute(
                "SELECT COUNT(*) FROM episodic_memories WHERE chat_id='c5'"
            ).fetchone()[0]
        self.assertEqual(sem_count, 0)   # cleared
        self.assertEqual(ep_count, 1)    # untouched


if __name__ == "__main__":
    unittest.main()
