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


if __name__ == "__main__":
    unittest.main()
