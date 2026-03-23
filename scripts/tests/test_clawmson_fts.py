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

from clawmson_fts import FTS5_AVAILABLE
import clawmson_fts as fts


class TestFTSSchema(unittest.TestCase):
    @unittest.skipUnless(FTS5_AVAILABLE, "FTS5 not supported")
    def test_fts_tables_exist(self):
        """memory_fts and sessions tables exist after _init_db()."""
        with db._get_conn() as conn:
            all_names = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master"
            ).fetchall()}
        self.assertIn("memory_fts", all_names)
        self.assertIn("sessions", all_names)


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
            result = mm.retrieve("chat4", "qwen3")
        self.assertIn("qwen3", result.lower())
        self.assertIn("[Search]", result)

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


if __name__ == "__main__":
    unittest.main()
