#!/usr/bin/env python3
"""Tests for scripts/autoresearch/scholar.py"""
from __future__ import annotations
import os
import sys
import unittest
from pathlib import Path

# Point DB to in-memory SQLite before any imports touch clawmson_db
os.environ["CLAWMSON_DB_PATH"] = ":memory:"

_SCRIPTS = Path(__file__).parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import clawmson_db as db


class TestDBSchema(unittest.TestCase):
    def test_papers_table_exists(self):
        conn = db._get_conn()
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='papers'"
        ).fetchone()
        self.assertIsNotNone(row, "papers table should exist")

    def test_paper_digests_table_exists(self):
        conn = db._get_conn()
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='paper_digests'"
        ).fetchone()
        self.assertIsNotNone(row, "paper_digests table should exist")

    def test_papers_columns(self):
        conn = db._get_conn()
        cols = {r[1] for r in conn.execute("PRAGMA table_info(papers)").fetchall()}
        expected = {"paper_id", "title", "authors", "abstract", "url",
                    "relevance_score", "discovered_at", "digested"}
        self.assertTrue(expected.issubset(cols))

    def test_paper_digests_columns(self):
        conn = db._get_conn()
        cols = {r[1] for r in conn.execute("PRAGMA table_info(paper_digests)").fetchall()}
        expected = {"id", "paper_id", "key_findings", "implementable_techniques",
                    "linked_models", "relevance_to_builds", "priority",
                    "action_taken", "digested_at"}
        self.assertTrue(expected.issubset(cols))


class TestModuleConstants(unittest.TestCase):
    def test_import(self):
        """scholar module imports without error."""
        from autoresearch import scholar
        self.assertIsNotNone(scholar)

    def test_hf_request_timeout(self):
        from autoresearch import scholar
        self.assertEqual(scholar.HF_REQUEST_TIMEOUT, 30)

    def test_default_threshold(self):
        from autoresearch import scholar
        # Default is 0.75; env var SCHOLAR_RELEVANCE_THRESHOLD can override
        self.assertGreater(scholar.RELEVANCE_THRESHOLD, 0)
        self.assertLessEqual(scholar.RELEVANCE_THRESHOLD, 1.0)


class TestDBHelpers(unittest.TestCase):
    def setUp(self):
        # Wipe papers tables between tests
        conn = db._get_conn()
        conn.execute("DELETE FROM paper_digests")
        conn.execute("DELETE FROM papers")
        conn.commit()
        from autoresearch import scholar
        self.s = scholar

    def test_save_paper_inserts(self):
        self.s.save_paper("2401.00001", "Test Paper", '["Alice"]',
                          "An abstract.", "https://hf.co/papers/2401.00001", 0.82)
        conn = db._get_conn()
        row = conn.execute("SELECT * FROM papers WHERE paper_id=?",
                           ("2401.00001",)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["title"], "Test Paper")
        self.assertEqual(row["digested"], 0)
        self.assertIsNotNone(row["discovered_at"])

    def test_save_paper_insert_or_ignore(self):
        self.s.save_paper("2401.00002", "Paper A", None, None, None, 0.9)
        self.s.save_paper("2401.00002", "Paper B", None, None, None, 0.5)
        conn = db._get_conn()
        rows = conn.execute("SELECT title FROM papers WHERE paper_id=?",
                            ("2401.00002",)).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Paper A")  # first write wins

    def test_mark_digested(self):
        self.s.save_paper("2401.00003", "Paper C", None, None, None, 0.7)
        self.s.mark_digested("2401.00003")
        conn = db._get_conn()
        row = conn.execute("SELECT digested FROM papers WHERE paper_id=?",
                           ("2401.00003",)).fetchone()
        self.assertEqual(row["digested"], 1)

    def test_save_digest_inserts(self):
        import json
        self.s.save_paper("2401.00004", "Paper D", None, None, None, 0.8)
        self.s.save_digest(
            paper_id="2401.00004",
            findings=json.dumps(["finding 1", "finding 2"]),
            techniques=json.dumps(["technique A"]),
            models=json.dumps(["bert-base"]),
            relevance="Relevant to RAG",
            priority="P1",
            action="improvement,bakeoff",
        )
        conn = db._get_conn()
        row = conn.execute("SELECT * FROM paper_digests WHERE paper_id=?",
                           ("2401.00004",)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["priority"], "P1")
        self.assertEqual(row["action_taken"], "improvement,bakeoff")
        self.assertIsNotNone(row["digested_at"])

    def test_get_undigested(self):
        self.s.save_paper("2401.00005", "Undigested", None, None, None, 0.9)
        self.s.save_paper("2401.00006", "Digested", None, None, None, 0.8)
        self.s.mark_digested("2401.00006")
        results = self.s.get_undigested(limit=10)
        ids = [r["paper_id"] for r in results]
        self.assertIn("2401.00005", ids)
        self.assertNotIn("2401.00006", ids)

    def test_get_recent_papers_structure(self):
        self.s.save_paper("2401.00007", "Recent Paper", None, None, None, 0.85)
        self.s.mark_digested("2401.00007")
        result = self.s.get_recent_papers(days=7)
        self.assertIn("total", result)
        self.assertIn("digested", result)
        self.assertIn("top_titles", result)
        self.assertIsInstance(result["top_titles"], list)
        self.assertGreaterEqual(result["total"], 1)


if __name__ == "__main__":
    unittest.main()
