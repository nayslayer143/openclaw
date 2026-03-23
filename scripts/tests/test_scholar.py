#!/usr/bin/env python3
"""Tests for scripts/autoresearch/scholar.py"""
from __future__ import annotations
import os
import sys
import unittest
import requests
from pathlib import Path
from unittest.mock import patch, MagicMock

# Point DB to in-memory SQLite before any imports touch clawmson_db
os.environ["CLAWMSON_DB_PATH"] = ":memory:"

_SCRIPTS = Path(__file__).parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import clawmson_db as db
import json


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


class TestEmbedAndRank(unittest.TestCase):
    def setUp(self):
        from autoresearch import scholar
        scholar._GOAL_VECTOR = None  # reset cache before each test

    def _make_embed_response(self, vec: list) -> MagicMock:
        mock = MagicMock()
        mock.raise_for_status = MagicMock()
        mock.json.return_value = {"embedding": vec}
        return mock

    def test_embed_text_returns_list(self):
        from autoresearch import scholar
        with patch("requests.post", return_value=self._make_embed_response([0.1, 0.2, 0.3])):
            result = scholar.embed_text("hello world")
        self.assertIsInstance(result, list)
        self.assertEqual(result, [0.1, 0.2, 0.3])

    def test_rank_by_relevance_sorts_descending(self):
        from autoresearch import scholar
        goal_vec = [1.0, 0.0]
        paper_vecs = {
            "p1": [1.0, 0.0],   # cosine=1.0 (identical)
            "p2": [0.0, 1.0],   # cosine=0.0 (orthogonal)
            "p3": [0.7, 0.7],   # cosine~0.7
        }
        papers_list = ["p1", "p2", "p3"]
        call_order = [0]

        def ordered_embed(text):
            if call_order[0] == 0:
                call_order[0] += 1
                return goal_vec  # first call is for goal vector
            pid = papers_list[call_order[0] - 1]
            call_order[0] += 1
            return paper_vecs[pid]

        candidates = [
            {"paper_id": "p1", "abstract": "p1 abstract"},
            {"paper_id": "p2", "abstract": "p2 abstract"},
            {"paper_id": "p3", "abstract": "p3 abstract"},
        ]

        with patch.object(scholar, "embed_text", side_effect=ordered_embed), \
             patch.object(scholar, "_GOAL_VECTOR", None):
            ranked = scholar.rank_by_relevance(candidates)

        scores = [r["relevance_score"] for r in ranked]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(ranked[0]["paper_id"], "p1")

    def test_cosine_similarity(self):
        from autoresearch import scholar
        self.assertAlmostEqual(scholar._cosine([1, 0], [1, 0]), 1.0, places=5)
        self.assertAlmostEqual(scholar._cosine([1, 0], [0, 1]), 0.0, places=5)


class TestDiscovery(unittest.TestCase):
    def setUp(self):
        conn = db._get_conn()
        conn.execute("DELETE FROM paper_digests")
        conn.execute("DELETE FROM papers")
        conn.commit()

    def _hf_response(self, papers: list) -> MagicMock:
        mock = MagicMock()
        mock.raise_for_status = MagicMock()
        mock.json.return_value = papers
        return mock

    def test_search_papers_deduplicates(self):
        from autoresearch import scholar
        # Pre-seed one known paper
        scholar.save_paper("2401.00010", "Known", None, None, None, 0.8)

        hf_results = [
            {"id": "2401.00010", "title": "Known", "authors": [],
             "publishedAt": "2024-01-01", "summary": "abstract"},
            {"id": "2401.00011", "title": "New", "authors": [],
             "publishedAt": "2024-01-02", "summary": "new abstract"},
        ]
        with patch("requests.get", return_value=self._hf_response(hf_results)):
            results = scholar.search_papers("test query", limit=20)

        ids = [p["paper_id"] for p in results]
        self.assertNotIn("2401.00010", ids)  # already known — deduplicated
        self.assertIn("2401.00011", ids)

    def test_discover_saves_and_returns_ranked(self):
        from autoresearch import scholar
        hf_results = [
            {"id": "2401.00020", "title": "Paper X", "authors": [],
             "publishedAt": "2024-01-01", "summary": "agent orchestration paper"},
        ]

        def fake_embed(text):
            return [1.0, 0.0]  # trivial — all papers get same score

        with patch("requests.get", return_value=self._hf_response(hf_results)), \
             patch.object(scholar, "_get_goal_vector", return_value=[1.0, 0.0]), \
             patch.object(scholar, "embed_text", side_effect=fake_embed):
            results = scholar.discover(query="agents", limit=5)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["paper_id"], "2401.00020")
        # Verify saved to DB
        conn = db._get_conn()
        row = conn.execute("SELECT * FROM papers WHERE paper_id='2401.00020'").fetchone()
        self.assertIsNotNone(row)


class TestFetchMarkdown(unittest.TestCase):
    def setUp(self):
        conn = db._get_conn()
        conn.execute("DELETE FROM paper_digests")
        conn.execute("DELETE FROM papers")
        conn.commit()

    def test_fetch_returns_markdown(self):
        from autoresearch import scholar
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = "# My Paper\n\nThis is the content."
        with patch("requests.get", return_value=mock_resp):
            result = scholar.fetch_paper_markdown("2401.99001")
        self.assertEqual(result, "# My Paper\n\nThis is the content.")

    def test_fetch_fallback_to_abstract(self):
        from autoresearch import scholar
        # Paper exists in DB with an abstract
        scholar.save_paper("2401.99002", "Fallback Paper", None,
                           "This is the abstract.", None, 0.7)
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError("404")
        with patch("requests.get", return_value=mock_resp):
            result = scholar.fetch_paper_markdown("2401.99002")
        self.assertEqual(result, "This is the abstract.")

    def test_fetch_returns_empty_string_if_no_fallback(self):
        from autoresearch import scholar
        # Paper not in DB at all
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError("404")
        with patch("requests.get", return_value=mock_resp):
            result = scholar.fetch_paper_markdown("2401.99003")
        self.assertEqual(result, "")

    def test_fetch_empty_response_returns_empty_string(self):
        from autoresearch import scholar
        # HTTP 200 but empty body — no fallback, return empty string
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = ""
        with patch("requests.get", return_value=mock_resp):
            result = scholar.fetch_paper_markdown("2401.99004")
        self.assertEqual(result, "")

    def test_fetch_fallback_null_abstract_returns_empty_string(self):
        from autoresearch import scholar
        # Paper in DB but abstract is NULL
        scholar.save_paper("2401.99005", "No Abstract Paper", None, None, None, None)
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError("404")
        with patch("requests.get", return_value=mock_resp):
            result = scholar.fetch_paper_markdown("2401.99005")
        self.assertEqual(result, "")


class TestDigestPaper(unittest.TestCase):
    def setUp(self):
        conn = db._get_conn()
        conn.execute("DELETE FROM paper_digests")
        conn.execute("DELETE FROM papers")
        conn.commit()
        from autoresearch import scholar
        self.s = scholar

    def _mock_ollama(self, content: str) -> MagicMock:
        mock = MagicMock()
        mock.raise_for_status = MagicMock()
        mock.json.return_value = {"message": {"content": content}}
        return mock

    def _good_digest_json(self) -> str:
        return json.dumps({
            "KEY_FINDINGS": ["finding 1", "finding 2"],
            "IMPLEMENTABLE_TECHNIQUES": ["technique A"],
            "LINKED_MODELS": ["bert-base-uncased"],
            "RELEVANCE_TO_BUILDS": "Relevant to RAG pipeline",
            "PRIORITY": "P1",
        })

    def test_digest_saves_to_db(self):
        self.s.save_paper("2401.30001", "Digest Test", None,
                          "Abstract text.", None, 0.8)
        with patch("requests.get") as mock_get, \
             patch("requests.post", return_value=self._mock_ollama(self._good_digest_json())):
            mock_get.return_value = MagicMock(
                raise_for_status=MagicMock(), text="# Digest Test\n\nFull content."
            )
            result = self.s.digest_paper("2401.30001")

        self.assertNotIn("error", result)
        conn = db._get_conn()
        row = conn.execute("SELECT * FROM paper_digests WHERE paper_id='2401.30001'").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["priority"], "P1")
        # Paper should be marked digested
        p = conn.execute("SELECT digested FROM papers WHERE paper_id='2401.30001'").fetchone()
        self.assertEqual(p["digested"], 1)

    def test_digest_handles_json_parse_error(self):
        self.s.save_paper("2401.30002", "Parse Error Paper", None, "abs", None, 0.7)
        with patch("requests.get") as mock_get, \
             patch("requests.post", return_value=self._mock_ollama("not json at all")):
            mock_get.return_value = MagicMock(raise_for_status=MagicMock(), text="# Title\n")
            result = self.s.digest_paper("2401.30002")

        self.assertIn("error", result)
        self.assertEqual(result["error"], "parse_failed")
        # No digest row written
        conn = db._get_conn()
        row = conn.execute("SELECT * FROM paper_digests WHERE paper_id='2401.30002'").fetchone()
        self.assertIsNone(row)

    def test_digest_unknown_paper_extracts_title(self):
        # paper_id not in DB — fetch succeeds with title in markdown
        md = "# Discovered Paper Title\n\nContent here."
        with patch("requests.get") as mock_get, \
             patch("requests.post", return_value=self._mock_ollama(self._good_digest_json())):
            mock_get.return_value = MagicMock(raise_for_status=MagicMock(), text=md)
            result = self.s.digest_paper("2401.30003")

        self.assertNotIn("error", result)
        conn = db._get_conn()
        row = conn.execute("SELECT title FROM papers WHERE paper_id='2401.30003'").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["title"], "Discovered Paper Title")

    def test_digest_unknown_paper_no_markdown_returns_error(self):
        with patch.object(self.s, "fetch_paper_markdown", return_value=""):
            result = self.s.digest_paper("2401.30004")
        self.assertEqual(result.get("error"), "unknown_paper")

    def test_digest_handles_ollama_failure(self):
        self.s.save_paper("2401.30005", "Ollama Fail Paper", None, "abs", None, 0.7)
        with patch("requests.get") as mock_get, \
             patch("requests.post") as mock_post:
            mock_get.return_value = MagicMock(raise_for_status=MagicMock(), text="# Ollama Fail Paper\n")
            mock_post.side_effect = Exception("connection refused")
            result = self.s.digest_paper("2401.30005")

        self.assertEqual(result.get("error"), "ollama_failed")
        # No digest row written
        conn = db._get_conn()
        row = conn.execute("SELECT * FROM paper_digests WHERE paper_id='2401.30005'").fetchone()
        self.assertIsNone(row)


class TestActionRouting(unittest.TestCase):
    def setUp(self):
        conn = db._get_conn()
        conn.execute("DELETE FROM paper_digests")
        conn.execute("DELETE FROM papers")
        conn.commit()
        from autoresearch import scholar
        self.s = scholar
        # Use a temp dir for file outputs in tests
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        self._orig_root = self.s.OPENCLAW_ROOT
        self.s.OPENCLAW_ROOT = Path(self._tmpdir)
        (Path(self._tmpdir) / "improvements").mkdir()
        (Path(self._tmpdir) / "benchmark").mkdir()
        (Path(self._tmpdir) / "autoresearch" / "outputs" / "papers").mkdir(parents=True)

    def tearDown(self):
        self.s.OPENCLAW_ROOT = self._orig_root
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_p1_with_techniques_writes_improvement(self):
        self.s.save_paper("2401.40001", "Action Paper", None, None, None, 0.9)
        actions = self.s._route_paper_actions(
            "2401.40001", "P1", ["technique A"], [], "some relevance"
        )
        self.assertIn("improvement", actions)
        # Check file written
        improv_files = list((Path(self._tmpdir) / "improvements").glob("scholar-*.md"))
        self.assertEqual(len(improv_files), 1)

    def test_linked_models_appends_to_bakeoff_queue(self):
        self.s.save_paper("2401.40002", "Model Paper", None, None, None, 0.85)
        actions = self.s._route_paper_actions(
            "2401.40002", "P2", [], ["bert-base", "t5-small"], ""
        )
        self.assertIn("bakeoff", actions)
        bakeoff = Path(self._tmpdir) / "benchmark" / "bakeoff-queue.md"
        self.assertTrue(bakeoff.exists())
        content = bakeoff.read_text()
        self.assertIn("bert-base", content)
        self.assertIn("autoscholar", content)

    def test_p1_with_relevance_writes_build_note(self):
        self.s.save_paper("2401.40003", "Relevant Paper", None, None, None, 0.95)
        actions = self.s._route_paper_actions(
            "2401.40003", "P1", [], [], "Directly relevant to RAG pipeline"
        )
        self.assertIn("build_note", actions)

    def test_no_match_returns_none(self):
        self.s.save_paper("2401.40004", "P3 Paper", None, None, None, 0.6)
        actions = self.s._route_paper_actions(
            "2401.40004", "P3", [], [], ""
        )
        self.assertEqual(actions, [])

    def test_all_rules_can_fire(self):
        self.s.save_paper("2401.40005", "Full Paper", None, None, None, 0.99)
        actions = self.s._route_paper_actions(
            "2401.40005", "P1", ["technique X"], ["model-y"], "Very relevant"
        )
        self.assertIn("improvement", actions)
        self.assertIn("bakeoff", actions)
        self.assertIn("build_note", actions)


if __name__ == "__main__":
    unittest.main()
