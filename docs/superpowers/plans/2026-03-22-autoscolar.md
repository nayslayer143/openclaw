# AutoScholar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `scripts/autoresearch/scholar.py` — a HuggingFace paper discovery, digestion, and routing module integrated into Clawmson's Telegram bot and overnight research pipeline.

**Architecture:** Single Python module under `scripts/autoresearch/` with four layers (DB helpers, discovery, digestion, action routing), wired into the existing `telegram-dispatcher.py` slash command handler and a new `cron-scholar.sh` nightly script. All AI inference via local Ollama. All data in `~/.openclaw/clawmson.db`.

**Tech Stack:** Python 3, SQLite (via `clawmson_db._get_conn()`), `requests`, `unittest` + `unittest.mock`, Ollama (`qwen3:30b` for digestion, `nomic-embed-text` for embeddings), HuggingFace Papers API, bash.

---

## File Map

| File | Status | Responsibility |
|------|--------|----------------|
| `scripts/autoresearch/__init__.py` | Create | Package marker (empty) |
| `scripts/autoresearch/scholar.py` | Create | All scholar logic: constants, DB helpers, discovery, digestion, action routing, auto_mode, ClawTeam shim |
| `scripts/tests/test_scholar.py` | Create | All tests for scholar.py |
| `scripts/clawmson_db.py` | Modify | Add `papers` + `paper_digests` tables + indexes to `_init_db()` |
| `scripts/telegram-dispatcher.py` | Modify | Add `from autoresearch import scholar` import + `/papers`, `/digest`, `/scholar` command handlers |
| `scripts/cron-scholar.sh` | Create | Nightly 2am cron — calls `scholar.auto_mode()`, logs, sends Telegram summary |
| `agents/configs/autoresearch-scholar.md` | Create | System documentation for the AutoScholar agent |

---

## Task 1: Add DB Schema

**Files:**
- Modify: `scripts/clawmson_db.py` (in `_init_db()`)

- [ ] **Step 1: Write failing test**

  Open `scripts/tests/test_scholar.py` and create it with this content:

  ```python
  #!/usr/bin/env python3
  """Tests for scripts/autoresearch/scholar.py"""
  from __future__ import annotations
  import os
  import sys
  import json
  import datetime
  import unittest
  from unittest.mock import patch, MagicMock
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
  ```

- [ ] **Step 2: Run test — verify it fails**

  ```bash
  cd ~/openclaw/scripts
  python -m pytest tests/test_scholar.py::TestDBSchema -v
  ```

  Expected: FAIL — `papers` and `paper_digests` tables don't exist yet.

- [ ] **Step 3: Add tables to `clawmson_db.py` `_init_db()`**

  In `scripts/clawmson_db.py`, find the end of the `executescript` block inside `_init_db()` (just before the closing `"""`). Add after the existing `procedure_candidates` table and its indexes:

  ```sql
          CREATE TABLE IF NOT EXISTS papers (
              paper_id        TEXT PRIMARY KEY,
              title           TEXT NOT NULL,
              authors         TEXT,
              abstract        TEXT,
              url             TEXT,
              relevance_score REAL,
              discovered_at   TEXT NOT NULL,
              digested        INTEGER DEFAULT 0
          );
          CREATE TABLE IF NOT EXISTS paper_digests (
              id                       INTEGER PRIMARY KEY AUTOINCREMENT,
              paper_id                 TEXT NOT NULL,
              key_findings             TEXT,
              implementable_techniques TEXT,
              linked_models            TEXT,
              relevance_to_builds      TEXT,
              priority                 TEXT,
              action_taken             TEXT,
              digested_at              TEXT NOT NULL
          );
          CREATE INDEX IF NOT EXISTS idx_papers_digested ON papers(digested);
          CREATE INDEX IF NOT EXISTS idx_papers_score ON papers(relevance_score);
          CREATE INDEX IF NOT EXISTS idx_digests_paper ON paper_digests(paper_id);
  ```

- [ ] **Step 4: Run test — verify it passes**

  ```bash
  cd ~/openclaw/scripts
  python -m pytest tests/test_scholar.py::TestDBSchema -v
  ```

  Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

  ```bash
  cd ~/openclaw
  git add scripts/clawmson_db.py scripts/tests/test_scholar.py
  git commit -m "feat(autoscolar): add papers + paper_digests tables to clawmson_db"
  ```

---

## Task 2: Package Scaffold + Module Constants

**Files:**
- Create: `scripts/autoresearch/__init__.py`
- Create: `scripts/autoresearch/scholar.py` (skeleton only)

- [ ] **Step 1: Create package marker**

  ```bash
  mkdir -p ~/openclaw/scripts/autoresearch
  touch ~/openclaw/scripts/autoresearch/__init__.py
  ```

- [ ] **Step 2: Write failing test**

  Add this class to `scripts/tests/test_scholar.py` (after the existing `TestDBSchema` class):

  ```python
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
  ```

- [ ] **Step 3: Run test — verify it fails**

  ```bash
  cd ~/openclaw/scripts
  python -m pytest tests/test_scholar.py::TestModuleConstants -v
  ```

  Expected: FAIL — module doesn't exist yet.

- [ ] **Step 4: Create `scripts/autoresearch/scholar.py` skeleton**

  ```python
  #!/usr/bin/env python3
  from __future__ import annotations
  """
  AutoScholar — HuggingFace paper discovery, digestion, and routing.
  Part of OpenClaw's research pipeline.

  Layers:
    1. DB helpers      — save/retrieve papers and digests from clawmson.db
    2. Discovery       — search HF, embed + rank by relevance
    3. Digestion       — fetch paper markdown, extract insights via qwen3:30b
    4. Action routing  — write improvements, bakeoff flags, build notes
    5. Auto mode       — overnight cron entry point
    6. ClawTeam shim   — get_paper_for_debate()
  """

  import os
  import sys
  import json
  import re
  import time
  import datetime
  import math
  import requests
  from pathlib import Path

  # Add scripts/ to path so clawmson_db is importable when this module
  # is run directly (e.g. from cron). When imported by telegram-dispatcher,
  # scripts/ is already on sys.path.
  _SCRIPTS_DIR = Path(__file__).parent.parent
  if str(_SCRIPTS_DIR) not in sys.path:
      sys.path.insert(0, str(_SCRIPTS_DIR))

  import clawmson_db as db

  # ── Constants ─────────────────────────────────────────────────────────────────

  OLLAMA_BASE_URL       = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
  DIGEST_MODEL          = os.environ.get("SCHOLAR_DIGEST_MODEL", "qwen3:30b")
  EMBED_MODEL           = os.environ.get("SCHOLAR_EMBED_MODEL", "nomic-embed-text")
  RELEVANCE_THRESHOLD   = float(os.environ.get("SCHOLAR_RELEVANCE_THRESHOLD", "0.75"))
  HF_REQUEST_TIMEOUT    = 30  # seconds for all HuggingFace HTTP calls

  OPENCLAW_ROOT = Path.home() / "openclaw"

  # ── Directory creation ────────────────────────────────────────────────────────
  # Ensure output directories exist at import time.

  for _d in [
      OPENCLAW_ROOT / "autoresearch" / "outputs" / "papers",
      OPENCLAW_ROOT / "improvements",
      OPENCLAW_ROOT / "benchmark",
  ]:
      _d.mkdir(parents=True, exist_ok=True)

  # ── Project goal vector (embedded once, cached) ───────────────────────────────

  _GOAL_TEXT = (
      "agent orchestration, prediction markets, memory architectures, "
      "local LLM optimization, multi-agent systems, RAG, tool use, "
      "web business automation, NFC cards, information products"
  )
  _GOAL_VECTOR: list[float] | None = None  # populated lazily on first embed call

  # ── Default domain keywords for auto_mode ────────────────────────────────────

  DEFAULT_DOMAINS = [
      "agent orchestration",
      "prediction markets",
      "memory architectures",
      "local LLM optimization",
      "multi-agent systems",
      "RAG retrieval augmented",
      "tool use LLM",
      "agentic systems",
  ]
  ```

- [ ] **Step 5: Run test — verify it passes**

  ```bash
  cd ~/openclaw/scripts
  python -m pytest tests/test_scholar.py::TestModuleConstants -v
  ```

  Expected: 3 tests PASS.

- [ ] **Step 6: Commit**

  ```bash
  cd ~/openclaw
  git add scripts/autoresearch/__init__.py scripts/autoresearch/scholar.py scripts/tests/test_scholar.py
  git commit -m "feat(autoscolar): scaffold package, constants, directory creation"
  ```

---

## Task 3: DB Helper Functions

**Files:**
- Modify: `scripts/autoresearch/scholar.py`
- Modify: `scripts/tests/test_scholar.py`

- [ ] **Step 1: Write failing tests**

  Add to `scripts/tests/test_scholar.py`:

  ```python
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
  ```

- [ ] **Step 2: Run test — verify it fails**

  ```bash
  cd ~/openclaw/scripts
  python -m pytest tests/test_scholar.py::TestDBHelpers -v
  ```

  Expected: FAIL — functions don't exist yet.

- [ ] **Step 3: Implement DB helpers in `scholar.py`**

  Append to `scripts/autoresearch/scholar.py`:

  ```python
  # ── DB helpers ────────────────────────────────────────────────────────────────

  def save_paper(paper_id: str, title: str, authors, abstract, url,
                 relevance_score) -> None:
      """INSERT OR IGNORE a paper row. discovered_at set to UTC now."""
      ts = datetime.datetime.utcnow().isoformat()
      with db._get_conn() as conn:
          conn.execute(
              "INSERT OR IGNORE INTO papers "
              "(paper_id, title, authors, abstract, url, relevance_score, discovered_at)"
              " VALUES (?, ?, ?, ?, ?, ?, ?)",
              (paper_id, title, authors, abstract, url, relevance_score, ts)
          )


  def mark_digested(paper_id: str) -> None:
      with db._get_conn() as conn:
          conn.execute("UPDATE papers SET digested=1 WHERE paper_id=?", (paper_id,))


  def save_digest(paper_id: str, findings: str, techniques: str, models: str,
                  relevance: str, priority: str, action: str) -> None:
      """Insert a paper_digests row. digested_at set to UTC now."""
      ts = datetime.datetime.utcnow().isoformat()
      with db._get_conn() as conn:
          conn.execute(
              "INSERT INTO paper_digests "
              "(paper_id, key_findings, implementable_techniques, linked_models, "
              " relevance_to_builds, priority, action_taken, digested_at)"
              " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
              (paper_id, findings, techniques, models, relevance, priority, action, ts)
          )


  def get_undigested(limit: int = 20) -> list[dict]:
      """Return papers not yet digested, ordered by relevance_score DESC."""
      with db._get_conn() as conn:
          rows = conn.execute(
              "SELECT * FROM papers WHERE digested=0 ORDER BY relevance_score DESC LIMIT ?",
              (limit,)
          ).fetchall()
      return [dict(r) for r in rows]


  def get_recent_papers(days: int = 7) -> dict:
      """
      Return summary of papers discovered in the last N days.
      Returns {"total": int, "digested": int, "top_titles": list[str]}
      """
      cutoff = (datetime.datetime.utcnow() - datetime.timedelta(days=days)).isoformat()
      with db._get_conn() as conn:
          total = conn.execute(
              "SELECT COUNT(*) FROM papers WHERE discovered_at >= ?", (cutoff,)
          ).fetchone()[0]
          digested = conn.execute(
              "SELECT COUNT(*) FROM papers WHERE discovered_at >= ? AND digested=1",
              (cutoff,)
          ).fetchone()[0]
          top_rows = conn.execute(
              "SELECT title FROM papers WHERE discovered_at >= ? AND digested=1"
              " ORDER BY relevance_score DESC LIMIT 5",
              (cutoff,)
          ).fetchall()
      return {
          "total": total,
          "digested": digested,
          "top_titles": [r["title"] for r in top_rows],
      }
  ```

- [ ] **Step 4: Run test — verify it passes**

  ```bash
  cd ~/openclaw/scripts
  python -m pytest tests/test_scholar.py::TestDBHelpers -v
  ```

  Expected: 6 tests PASS.

- [ ] **Step 5: Commit**

  ```bash
  cd ~/openclaw
  git add scripts/autoresearch/scholar.py scripts/tests/test_scholar.py
  git commit -m "feat(autoscolar): DB helper functions (save_paper, save_digest, get_recent_papers)"
  ```

---

## Task 4: Embedding + Relevance Ranking

**Files:**
- Modify: `scripts/autoresearch/scholar.py`
- Modify: `scripts/tests/test_scholar.py`

- [ ] **Step 1: Write failing tests**

  Add to `scripts/tests/test_scholar.py`:

  ```python
  class TestEmbedAndRank(unittest.TestCase):
      def _make_embed_response(self, vec: list[float]) -> MagicMock:
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
          # Three papers with different similarity to goal
          # We control embed_text: goal vector is [1,0], papers are [1,0], [0,1], [0.7,0.7]
          goal_vec = [1.0, 0.0]
          paper_vecs = {
              "p1": [1.0, 0.0],   # cosine=1.0 (identical)
              "p2": [0.0, 1.0],   # cosine=0.0 (orthogonal)
              "p3": [0.7, 0.7],   # cosine~0.7
          }
          call_count = [0]
          def fake_embed(text):
              if "goal" in text or call_count[0] == 0:
                  call_count[0] += 1
                  return goal_vec
              return [0.0, 0.0]

          candidates = [
              {"paper_id": "p1", "abstract": "p1 abstract"},
              {"paper_id": "p2", "abstract": "p2 abstract"},
              {"paper_id": "p3", "abstract": "p3 abstract"},
          ]

          # Inject known embed responses per paper_id
          embed_map = {"p1": [1.0, 0.0], "p2": [0.0, 1.0], "p3": [0.7, 0.7]}
          call_order = [0]
          papers_list = ["p1", "p2", "p3"]

          def ordered_embed(text):
              if call_order[0] == 0:
                  call_order[0] += 1
                  return goal_vec  # first call is for goal vector
              pid = papers_list[call_order[0] - 1]
              call_order[0] += 1
              return embed_map[pid]

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
  ```

- [ ] **Step 2: Run test — verify it fails**

  ```bash
  cd ~/openclaw/scripts
  python -m pytest tests/test_scholar.py::TestEmbedAndRank -v
  ```

  Expected: FAIL.

- [ ] **Step 3: Implement embedding functions in `scholar.py`**

  Append to `scripts/autoresearch/scholar.py`:

  ```python
  # ── Embedding + relevance ranking ─────────────────────────────────────────────

  def _cosine(a: list[float], b: list[float]) -> float:
      """Cosine similarity between two vectors."""
      dot = sum(x * y for x, y in zip(a, b))
      norm_a = math.sqrt(sum(x * x for x in a))
      norm_b = math.sqrt(sum(x * x for x in b))
      if norm_a == 0 or norm_b == 0:
          return 0.0
      return dot / (norm_a * norm_b)


  def embed_text(text: str) -> list[float]:
      """Embed text using nomic-embed-text via Ollama."""
      resp = requests.post(
          f"{OLLAMA_BASE_URL}/api/embeddings",
          json={"model": EMBED_MODEL, "prompt": text},
          timeout=30,
      )
      resp.raise_for_status()
      return resp.json()["embedding"]


  def _get_goal_vector() -> list[float]:
      """Return cached goal vector, embedding once on first call."""
      global _GOAL_VECTOR
      if _GOAL_VECTOR is None:
          _GOAL_VECTOR = embed_text(_GOAL_TEXT)
      return _GOAL_VECTOR


  def rank_by_relevance(candidates: list[dict]) -> list[dict]:
      """
      Embed each candidate's abstract and rank by cosine similarity
      against the project goal vector. Attaches relevance_score to each dict.
      Returns sorted list (highest score first).
      """
      goal = _get_goal_vector()
      for candidate in candidates:
          abstract = candidate.get("abstract") or candidate.get("title") or ""
          try:
              vec = embed_text(abstract)
              candidate["relevance_score"] = round(_cosine(goal, vec), 4)
          except Exception as e:
              print(f"[scholar] embed failed for {candidate.get('paper_id')}: {e}")
              candidate["relevance_score"] = 0.0
      return sorted(candidates, key=lambda c: c["relevance_score"], reverse=True)
  ```

- [ ] **Step 4: Run test — verify it passes**

  ```bash
  cd ~/openclaw/scripts
  python -m pytest tests/test_scholar.py::TestEmbedAndRank -v
  ```

  Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

  ```bash
  cd ~/openclaw
  git add scripts/autoresearch/scholar.py scripts/tests/test_scholar.py
  git commit -m "feat(autoscolar): embed_text, cosine similarity, rank_by_relevance"
  ```

---

## Task 5: HuggingFace Search + Discover

**Files:**
- Modify: `scripts/autoresearch/scholar.py`
- Modify: `scripts/tests/test_scholar.py`

- [ ] **Step 1: Write failing tests**

  Add to `scripts/tests/test_scholar.py`:

  ```python
  class TestDiscovery(unittest.TestCase):
      def setUp(self):
          conn = db._get_conn()
          conn.execute("DELETE FROM paper_digests")
          conn.execute("DELETE FROM papers")
          conn.commit()

      def _hf_response(self, papers: list[dict]) -> MagicMock:
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
               patch.object(scholar, "embed_text", side_effect=fake_embed), \
               patch.object(scholar, "_GOAL_VECTOR", None):
              results = scholar.discover(query="agents", limit=5)

          self.assertEqual(len(results), 1)
          self.assertEqual(results[0]["paper_id"], "2401.00020")
          # Verify saved to DB
          conn = db._get_conn()
          row = conn.execute("SELECT * FROM papers WHERE paper_id='2401.00020'").fetchone()
          self.assertIsNotNone(row)
  ```

- [ ] **Step 2: Run test — verify it fails**

  ```bash
  cd ~/openclaw/scripts
  python -m pytest tests/test_scholar.py::TestDiscovery -v
  ```

  Expected: FAIL.

- [ ] **Step 3: Implement search_papers + discover in `scholar.py`**

  Append to `scripts/autoresearch/scholar.py`:

  ```python
  # ── Discovery ─────────────────────────────────────────────────────────────────

  def _known_paper_ids() -> set[str]:
      """Return set of paper_ids already in DB."""
      with db._get_conn() as conn:
          rows = conn.execute("SELECT paper_id FROM papers").fetchall()
      return {r["paper_id"] for r in rows}


  def search_papers(query: str | None = None, limit: int = 20) -> list[dict]:
      """
      Fetch papers from HuggingFace API. Deduplicates against known DB papers.
      If query is None, fetches trending papers.
      Returns list of candidate dicts with paper_id, title, abstract, authors, url.
      """
      if query:
          url = f"https://huggingface.co/api/papers?search={requests.utils.quote(query)}"
      else:
          url = "https://huggingface.co/api/papers"

      resp = requests.get(url, timeout=HF_REQUEST_TIMEOUT)
      resp.raise_for_status()
      raw = resp.json()

      known = _known_paper_ids()
      candidates = []
      for item in raw[:limit * 2]:  # fetch extra to account for dedup
          pid = item.get("id") or item.get("paper_id", "")
          if not pid or pid in known:
              continue
          candidates.append({
              "paper_id": pid,
              "title":    item.get("title", ""),
              "authors":  json.dumps([a.get("name", a) if isinstance(a, dict) else a
                                      for a in item.get("authors", [])]),
              "abstract": item.get("summary") or item.get("abstract", ""),
              "url":      f"https://huggingface.co/papers/{pid}",
          })
          if len(candidates) >= limit:
              break
      return candidates


  def discover(query: str | None = None, limit: int = 10) -> list[dict]:
      """
      Full discovery pipeline:
      1. Search HF (or trending if no query)
      2. Rank by relevance against goal vector
      3. Save all candidates to DB
      4. Return ranked list
      """
      candidates = search_papers(query=query, limit=limit * 2)
      if not candidates:
          return []
      ranked = rank_by_relevance(candidates)
      for paper in ranked:
          save_paper(
              paper_id=paper["paper_id"],
              title=paper["title"],
              authors=paper.get("authors"),
              abstract=paper.get("abstract"),
              url=paper.get("url"),
              relevance_score=paper.get("relevance_score"),
          )
      return ranked[:limit]
  ```

- [ ] **Step 4: Run test — verify it passes**

  ```bash
  cd ~/openclaw/scripts
  python -m pytest tests/test_scholar.py::TestDiscovery -v
  ```

  Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

  ```bash
  cd ~/openclaw
  git add scripts/autoresearch/scholar.py scripts/tests/test_scholar.py
  git commit -m "feat(autoscolar): search_papers, discover with HF API + dedup"
  ```

---

## Task 6: Fetch Paper Markdown

**Files:**
- Modify: `scripts/autoresearch/scholar.py`
- Modify: `scripts/tests/test_scholar.py`

- [ ] **Step 1: Write failing tests**

  Add to `scripts/tests/test_scholar.py`:

  ```python
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
  ```

- [ ] **Step 2: Run test — verify it fails**

  ```bash
  cd ~/openclaw/scripts
  python -m pytest tests/test_scholar.py::TestFetchMarkdown -v
  ```

  Expected: FAIL.

- [ ] **Step 3: Implement `fetch_paper_markdown` in `scholar.py`**

  Append to `scripts/autoresearch/scholar.py`:

  ```python
  # ── Digestion ─────────────────────────────────────────────────────────────────

  def fetch_paper_markdown(paper_id: str) -> str:
      """
      Fetch full paper markdown from HuggingFace.
      On HTTP error: fall back to abstract from DB.
      If paper not in DB either: return empty string.
      """
      try:
          resp = requests.get(
              f"https://huggingface.co/papers/{paper_id}.md",
              timeout=HF_REQUEST_TIMEOUT,
          )
          resp.raise_for_status()
          return resp.text
      except Exception:
          # Fallback: abstract from DB
          with db._get_conn() as conn:
              row = conn.execute(
                  "SELECT abstract FROM papers WHERE paper_id=?", (paper_id,)
              ).fetchone()
          if row and row["abstract"]:
              return row["abstract"]
          return ""
  ```

- [ ] **Step 4: Run test — verify it passes**

  ```bash
  cd ~/openclaw/scripts
  python -m pytest tests/test_scholar.py::TestFetchMarkdown -v
  ```

  Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

  ```bash
  cd ~/openclaw
  git add scripts/autoresearch/scholar.py scripts/tests/test_scholar.py
  git commit -m "feat(autoscolar): fetch_paper_markdown with abstract fallback"
  ```

---

## Task 7: Paper Digestion

**Files:**
- Modify: `scripts/autoresearch/scholar.py`
- Modify: `scripts/tests/test_scholar.py`

- [ ] **Step 1: Write failing tests**

  Add to `scripts/tests/test_scholar.py`:

  ```python
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
  ```

- [ ] **Step 2: Run test — verify it fails**

  ```bash
  cd ~/openclaw/scripts
  python -m pytest tests/test_scholar.py::TestDigestPaper -v
  ```

  Expected: FAIL.

- [ ] **Step 3: Implement `digest_paper` in `scholar.py`**

  Append to `scripts/autoresearch/scholar.py`:

  ```python
  _DIGEST_PROMPT = """\
  Given this research paper, extract:
  1. KEY_FINDINGS: 3-7 bullet points of the most important findings
  2. IMPLEMENTABLE_TECHNIQUES: specific techniques we could build right now, \
  in the context of: agent orchestration, prediction markets, memory architectures, \
  local LLM optimization, multi-agent systems, RAG, tool use, web business automation
  3. LINKED_MODELS: any HuggingFace model/dataset IDs mentioned
  4. RELEVANCE_TO_BUILDS: how this relates to the above domains
  5. PRIORITY: P1 (use now) / P2 (useful soon) / P3 (interesting later)

  Return JSON only.\
  """


  def _extract_title_from_markdown(md: str) -> str | None:
      """Extract first # Heading from markdown. Returns None if not found."""
      for line in md.splitlines():
          line = line.strip()
          if line.startswith("# "):
              return line[2:].strip()
      return None


  def _strip_json_fences(raw: str) -> str:
      """Remove markdown code fences from LLM response."""
      raw = raw.strip()
      if raw.startswith("```"):
          raw = re.sub(r"^```(?:json)?\s*", "", raw)
          raw = re.sub(r"\s*```$", "", raw)
      return raw.strip()


  def digest_paper(paper_id: str) -> dict:
      """
      Fetch and digest a paper. Saves digest to DB and runs action routing.

      Returns the parsed digest dict on success, or {"error": "...", ...} on failure.
      Never raises.
      """
      # Check if paper is in DB
      with db._get_conn() as conn:
          row = conn.execute("SELECT * FROM papers WHERE paper_id=?",
                             (paper_id,)).fetchone()
      in_db = row is not None

      # Fetch content
      content = fetch_paper_markdown(paper_id)
      if not content:
          return {"error": "unknown_paper", "paper_id": paper_id}

      # If paper wasn't in DB, save a placeholder row with extracted title
      if not in_db:
          title = _extract_title_from_markdown(content) or paper_id
          save_paper(
              paper_id=paper_id,
              title=title,
              authors=None,
              abstract=None,
              url=f"https://huggingface.co/papers/{paper_id}",
              relevance_score=None,
          )

      # Build prompt — truncate content to avoid overwhelming the model
      prompt_content = content[:8000] if len(content) > 8000 else content
      prompt = f"{_DIGEST_PROMPT}\n\n---\n\n{prompt_content}"

      # Call qwen3:30b
      try:
          resp = requests.post(
              f"{OLLAMA_BASE_URL}/api/chat",
              json={
                  "model": DIGEST_MODEL,
                  "messages": [{"role": "user", "content": prompt}],
                  "stream": False,
              },
              timeout=120,
          )
          resp.raise_for_status()
          raw = resp.json().get("message", {}).get("content", "")
      except Exception as e:
          print(f"[scholar] Ollama call failed for {paper_id}: {e}")
          return {"error": "ollama_failed", "paper_id": paper_id}

      # Defensive JSON parsing
      try:
          parsed = json.loads(_strip_json_fences(raw))
      except json.JSONDecodeError:
          print(f"[scholar] JSON parse failed for {paper_id}. Raw: {raw[:200]}")
          return {"error": "parse_failed", "raw": raw[:200]}

      findings     = parsed.get("KEY_FINDINGS", [])
      techniques   = parsed.get("IMPLEMENTABLE_TECHNIQUES", [])
      models       = parsed.get("LINKED_MODELS", [])
      relevance    = parsed.get("RELEVANCE_TO_BUILDS", "")
      priority     = parsed.get("PRIORITY", "P3")

      # Persist
      actions = _route_paper_actions(paper_id, priority, techniques, models, relevance)
      save_digest(
          paper_id=paper_id,
          findings=json.dumps(findings),
          techniques=json.dumps(techniques),
          models=json.dumps(models),
          relevance=relevance,
          priority=priority,
          action=",".join(actions) if actions else "none",
      )
      mark_digested(paper_id)

      return {
          "paper_id": paper_id,
          "key_findings": findings,
          "implementable_techniques": techniques,
          "linked_models": models,
          "relevance_to_builds": relevance,
          "priority": priority,
          "actions": actions,
      }
  ```

- [ ] **Step 4: Add stub for `_route_paper_actions` so module loads**

  Append to `scripts/autoresearch/scholar.py` (temporary stub — will be replaced in Task 8):

  ```python
  def _route_paper_actions(paper_id, priority, techniques, models, relevance) -> list[str]:
      """Stub — implemented in Task 8."""
      return []
  ```

- [ ] **Step 5: Run test — verify it passes**

  ```bash
  cd ~/openclaw/scripts
  python -m pytest tests/test_scholar.py::TestDigestPaper -v
  ```

  Expected: 4 tests PASS.

- [ ] **Step 6: Commit**

  ```bash
  cd ~/openclaw
  git add scripts/autoresearch/scholar.py scripts/tests/test_scholar.py
  git commit -m "feat(autoscolar): digest_paper with defensive JSON parsing, unknown-paper handling"
  ```

---

## Task 8: Action Routing

**Files:**
- Modify: `scripts/autoresearch/scholar.py` (replace stub)
- Modify: `scripts/tests/test_scholar.py`

- [ ] **Step 1: Write failing tests**

  Add to `scripts/tests/test_scholar.py`:

  ```python
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
  ```

- [ ] **Step 2: Run test — verify it fails**

  ```bash
  cd ~/openclaw/scripts
  python -m pytest tests/test_scholar.py::TestActionRouting -v
  ```

  Expected: FAIL (stub returns `[]` — improvement/bakeoff/build_note files not written).

- [ ] **Step 3: Replace stub with full implementation in `scholar.py`**

  Find and replace the stub `_route_paper_actions` function:

  ```python
  def _route_paper_actions(paper_id: str, priority: str, techniques: list,
                            models: list, relevance: str) -> list[str]:
      """
      Route paper to downstream outputs. All matching rules fire.
      Returns list of action strings taken (may be empty).
      """
      actions = []
      today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
      slug = re.sub(r"[^a-z0-9]+", "-", paper_id.lower())[:30].strip("-")

      # Fetch paper title for output files
      with db._get_conn() as conn:
          row = conn.execute("SELECT title FROM papers WHERE paper_id=?",
                             (paper_id,)).fetchone()
      title = row["title"] if row else paper_id

      # Rule 1: P1 + implementable techniques → improvement proposal
      if priority == "P1" and isinstance(techniques, list) and len(techniques) > 0:
          path = OPENCLAW_ROOT / "improvements" / f"scholar-{slug}-{today}.md"
          path.write_text(
              f"# Scholar Improvement: {title}\n\n"
              f"**Paper:** https://huggingface.co/papers/{paper_id}\n"
              f"**Priority:** {priority}\n\n"
              f"## Implementable Techniques\n\n"
              + "\n".join(f"- {t}" for t in techniques) + "\n\n"
              f"## Relevance\n\n{relevance}\n"
          )
          actions.append("improvement")

      # Rule 2: Linked models → bakeoff queue
      if isinstance(models, list) and len(models) > 0:
          bakeoff = OPENCLAW_ROOT / "benchmark" / "bakeoff-queue.md"
          entry = (
              f"\n## {today} — {paper_id}\n"
              f"- Title: {title}\n"
              f"- Models: {', '.join(models)}\n"
              f"- Source: autoscholar\n"
          )
          with open(bakeoff, "a") as f:
              f.write(entry)
          actions.append("bakeoff")

      # Rule 3: P1 + non-empty relevance → build context note
      if priority == "P1" and relevance and relevance.strip():
          path = OPENCLAW_ROOT / "autoresearch" / "outputs" / "papers" / \
                 f"academic-{slug}-{today}.md"
          path.write_text(
              f"# Academic Note: {title}\n\n"
              f"**Paper:** https://huggingface.co/papers/{paper_id}\n"
              f"**Priority:** {priority}\n\n"
              f"## Relevance to Active Builds\n\n{relevance}\n"
          )
          actions.append("build_note")

      return actions
  ```

- [ ] **Step 4: Run test — verify it passes**

  ```bash
  cd ~/openclaw/scripts
  python -m pytest tests/test_scholar.py::TestActionRouting -v
  ```

  Expected: 5 tests PASS.

- [ ] **Step 5: Run all tests so far**

  ```bash
  cd ~/openclaw/scripts
  python -m pytest tests/test_scholar.py -v
  ```

  Expected: All tests PASS.

- [ ] **Step 6: Commit**

  ```bash
  cd ~/openclaw
  git add scripts/autoresearch/scholar.py scripts/tests/test_scholar.py
  git commit -m "feat(autoscolar): action routing — improvements, bakeoff queue, build notes"
  ```

---

## Task 9: digest_batch + get_paper_for_debate

**Files:**
- Modify: `scripts/autoresearch/scholar.py`
- Modify: `scripts/tests/test_scholar.py`

- [ ] **Step 1: Write failing tests**

  Add to `scripts/tests/test_scholar.py`:

  ```python
  class TestDigestBatchAndDebate(unittest.TestCase):
      def setUp(self):
          conn = db._get_conn()
          conn.execute("DELETE FROM paper_digests")
          conn.execute("DELETE FROM papers")
          conn.commit()
          from autoresearch import scholar
          self.s = scholar

      def test_digest_batch_calls_digest_paper(self):
          results_log = []
          def fake_digest(pid, **_):
              results_log.append(pid)
              return {"paper_id": pid, "key_findings": [], "priority": "P2"}

          with patch.object(self.s, "digest_paper", side_effect=fake_digest):
              results = self.s.digest_batch(["p1", "p2", "p3"], delay=0)

          self.assertEqual(results_log, ["p1", "p2", "p3"])
          self.assertEqual(len(results), 3)

      def test_get_paper_for_debate_full_data(self):
          self.s.save_paper("2401.50001", "Debate Paper", '["Author A"]',
                            "The abstract.", "http://hf.co/papers/2401.50001", 0.9)
          self.s.save_digest(
              "2401.50001",
              json.dumps(["finding 1"]),
              json.dumps(["technique A"]),
              json.dumps([]),
              "Relevant to agents",
              "P1",
              "improvement",
          )
          self.s.mark_digested("2401.50001")

          result = self.s.get_paper_for_debate("2401.50001")
          self.assertEqual(result["title"], "Debate Paper")
          self.assertEqual(result["abstract"], "The abstract.")
          self.assertEqual(result["key_findings"], ["finding 1"])
          self.assertIsNone(result.get("full_markdown"))

      def test_get_paper_for_debate_with_full_markdown(self):
          self.s.save_paper("2401.50002", "Full Paper", None, "abs", None, 0.8)
          md = "# Full Paper\n\nContent."
          with patch.object(self.s, "fetch_paper_markdown", return_value=md):
              result = self.s.get_paper_for_debate("2401.50002", full=True)
          self.assertEqual(result["full_markdown"], md)

      def test_get_paper_for_debate_undigested(self):
          self.s.save_paper("2401.50003", "Undigested", None, "abstract", None, 0.7)
          result = self.s.get_paper_for_debate("2401.50003")
          self.assertEqual(result["title"], "Undigested")
          self.assertIsNone(result["key_findings"])

      def test_get_paper_for_debate_not_found(self):
          from autoresearch import scholar
          result = scholar.get_paper_for_debate("9999.99999")
          self.assertEqual(result.get("error"), "not_found")
  ```

- [ ] **Step 2: Run test — verify it fails**

  ```bash
  cd ~/openclaw/scripts
  python -m pytest tests/test_scholar.py::TestDigestBatchAndDebate -v
  ```

  Expected: FAIL.

- [ ] **Step 3: Implement `digest_batch` and `get_paper_for_debate` in `scholar.py`**

  Append to `scripts/autoresearch/scholar.py`:

  ```python
  # ── Batch digestion ───────────────────────────────────────────────────────────

  def digest_batch(paper_ids: list[str], delay: int = 5) -> list[dict]:
      """
      Digest multiple papers with a delay between calls.
      Use delay=0 in tests to avoid real sleep.
      """
      results = []
      for i, pid in enumerate(paper_ids):
          result = digest_paper(pid)
          results.append(result)
          if delay > 0 and i < len(paper_ids) - 1:
              time.sleep(delay)
      return results


  # ── ClawTeam shim ─────────────────────────────────────────────────────────────

  def get_paper_for_debate(paper_id: str, full: bool = False) -> dict:
      """
      Return structured paper data for ClawTeam debate pattern.

      - Full data returned when paper has been digested.
      - Partial data (title/abstract/url, digest fields None) if not yet digested.
      - {"error": "not_found"} if paper_id is unknown.
      - full=True triggers a live fetch of paper markdown (slow, may fail).
      """
      with db._get_conn() as conn:
          paper = conn.execute(
              "SELECT * FROM papers WHERE paper_id=?", (paper_id,)
          ).fetchone()
          if not paper:
              return {"error": "not_found"}
          digest = conn.execute(
              "SELECT * FROM paper_digests WHERE paper_id=?", (paper_id,)
          ).fetchone()

      result = {
          "title":                  paper["title"],
          "abstract":               paper["abstract"],
          "url":                    paper["url"],
          "key_findings":           json.loads(digest["key_findings"]) if digest and digest["key_findings"] else None,
          "implementable_techniques": json.loads(digest["implementable_techniques"]) if digest and digest["implementable_techniques"] else None,
          "relevance_to_builds":    digest["relevance_to_builds"] if digest else None,
          "full_markdown":          None,
      }
      if full:
          result["full_markdown"] = fetch_paper_markdown(paper_id) or None
      return result
  ```

- [ ] **Step 4: Run test — verify it passes**

  ```bash
  cd ~/openclaw/scripts
  python -m pytest tests/test_scholar.py::TestDigestBatchAndDebate -v
  ```

  Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

  ```bash
  cd ~/openclaw
  git add scripts/autoresearch/scholar.py scripts/tests/test_scholar.py
  git commit -m "feat(autoscolar): digest_batch, get_paper_for_debate ClawTeam shim"
  ```

---

## Task 10: auto_mode

**Files:**
- Modify: `scripts/autoresearch/scholar.py`
- Modify: `scripts/tests/test_scholar.py`

- [ ] **Step 1: Write failing test**

  Add to `scripts/tests/test_scholar.py`:

  ```python
  class TestAutoMode(unittest.TestCase):
      def setUp(self):
          conn = db._get_conn()
          conn.execute("DELETE FROM paper_digests")
          conn.execute("DELETE FROM papers")
          conn.commit()

      def test_auto_mode_threshold_filters(self):
          from autoresearch import scholar

          # discover() returns two papers: one above threshold, one below
          above = {"paper_id": "2401.60001", "title": "High Score",
                   "abstract": "abc", "relevance_score": 0.9, "authors": None, "url": None}
          below = {"paper_id": "2401.60002", "title": "Low Score",
                   "abstract": "xyz", "relevance_score": 0.5, "authors": None, "url": None}

          digested_ids = []

          def fake_discover(query=None, limit=10):
              return [above, below]

          def fake_digest_batch(ids, delay=0):
              digested_ids.extend(ids)
              return [{"paper_id": pid} for pid in ids]

          with patch.object(scholar, "discover", side_effect=fake_discover), \
               patch.object(scholar, "digest_batch", side_effect=fake_digest_batch), \
               patch.object(scholar, "RELEVANCE_THRESHOLD", 0.75):
              # Save papers so get_recent_papers works
              scholar.save_paper("2401.60001", "High Score", None, None, None, 0.9)
              scholar.mark_digested("2401.60001")
              result = scholar.auto_mode(domains=["test domain"])

          self.assertIn("2401.60001", digested_ids)
          self.assertNotIn("2401.60002", digested_ids)
          self.assertIn("discovered", result)
          self.assertIn("digested", result)
          self.assertIn("top_titles", result)

      def test_auto_mode_returns_correct_structure(self):
          from autoresearch import scholar
          with patch.object(scholar, "discover", return_value=[]), \
               patch.object(scholar, "digest_batch", return_value=[]):
              result = scholar.auto_mode(domains=["agents"])

          self.assertIn("discovered", result)
          self.assertIn("digested", result)
          self.assertIn("actions_taken", result)
          self.assertIn("top_titles", result)
          self.assertIsInstance(result["actions_taken"], list)
  ```

- [ ] **Step 2: Run test — verify it fails**

  ```bash
  cd ~/openclaw/scripts
  python -m pytest tests/test_scholar.py::TestAutoMode -v
  ```

  Expected: FAIL.

- [ ] **Step 3: Implement `auto_mode` in `scholar.py`**

  Append to `scripts/autoresearch/scholar.py`:

  ```python
  # ── Auto mode ─────────────────────────────────────────────────────────────────

  def auto_mode(domains: list[str] | None = None) -> dict:
      """
      Overnight cron entry point.
      Discovers papers across configured domains, digests qualifying papers,
      writes daily digest report, returns summary dict.
      """
      if domains is None:
          domains = DEFAULT_DOMAINS

      today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
      all_candidates: list[dict] = []

      for keyword in domains:
          try:
              candidates = discover(query=keyword, limit=20)
              all_candidates.extend(candidates)
          except Exception as e:
              print(f"[scholar] discover failed for '{keyword}': {e}")

      # Deduplicate across domains
      seen: set[str] = set()
      unique = []
      for p in all_candidates:
          if p["paper_id"] not in seen:
              seen.add(p["paper_id"])
              unique.append(p)

      # Filter by relevance threshold
      to_digest = [p for p in unique if (p.get("relevance_score") or 0) >= RELEVANCE_THRESHOLD]

      # Digest qualifying papers
      digest_results = digest_batch([p["paper_id"] for p in to_digest], delay=5)

      # Collect actions taken
      actions_taken: list[str] = []
      for r in digest_results:
          for a in r.get("actions", []):
              if a not in actions_taken:
                  actions_taken.append(a)

      # Write daily digest report
      summary = get_recent_papers(days=1)
      report_path = (OPENCLAW_ROOT / "autoresearch" / "outputs" / "papers" /
                     f"academic-scholar-digest-{today}.md")
      digested_count = len([r for r in digest_results if "error" not in r])
      top_titles = summary.get("top_titles", [])

      report_lines = [
          f"# AutoScholar Daily Digest — {today}\n",
          f"**Discovered:** {len(unique)} papers\n",
          f"**Digested:** {digested_count} papers\n",
          f"**Actions:** {', '.join(actions_taken) or 'none'}\n\n",
          "## Top Papers\n",
      ]
      for title in top_titles:
          report_lines.append(f"- {title}\n")
      report_path.write_text("".join(report_lines))

      return {
          "discovered": len(unique),
          "digested": digested_count,
          "actions_taken": actions_taken,
          "top_titles": top_titles,
      }
  ```

- [ ] **Step 4: Run test — verify it passes**

  ```bash
  cd ~/openclaw/scripts
  python -m pytest tests/test_scholar.py::TestAutoMode -v
  ```

  Expected: 2 tests PASS.

- [ ] **Step 5: Run the full test suite**

  ```bash
  cd ~/openclaw/scripts
  python -m pytest tests/test_scholar.py -v
  ```

  Expected: All tests PASS.

- [ ] **Step 6: Commit**

  ```bash
  cd ~/openclaw
  git add scripts/autoresearch/scholar.py scripts/tests/test_scholar.py
  git commit -m "feat(autoscolar): auto_mode with daily digest report and threshold filtering"
  ```

---

## Task 11: Telegram Command Handlers

**Files:**
- Modify: `scripts/telegram-dispatcher.py`

- [ ] **Step 1: Add scholar import**

  In `scripts/telegram-dispatcher.py`, find the block of module imports near the top (around line 44-50):

  ```python
  import clawmson_db as db
  import clawmson_chat as llm
  import clawmson_intents as intents
  import clawmson_media as media
  import clawmson_references as refs
  import model_router as router
  ```

  Add after that block:

  ```python
  from autoresearch import scholar
  ```

- [ ] **Step 2: Add handler functions**

  In `scripts/telegram-dispatcher.py`, after `handle_references()` and before the direct command section, add:

  ```python
  def handle_papers(chat_id: str, topic: str):
      """Discover and summarize top 5 papers on a topic."""
      send_typing(chat_id)
      try:
          results = scholar.discover(query=topic or None, limit=5)
      except Exception as e:
          send(chat_id, f"Paper search failed: {e}")
          return
      if not results:
          send(chat_id, f"No papers found for '{topic}'." if topic else "No trending papers found.")
          return
      lines = [f"Top papers{' on ' + topic if topic else ' (trending)'}:\n"]
      for i, p in enumerate(results, 1):
          score = p.get("relevance_score", 0)
          lines.append(f"{i}. {p['title']} (relevance: {score:.2f})\n"
                       f"   {p.get('url', '')}\n")
      send(chat_id, "".join(lines))


  def handle_digest(chat_id: str, paper_id: str):
      """Deep-dive digest a specific paper."""
      if not paper_id:
          send(chat_id, "Usage: /digest <paper_id>")
          return
      send_typing(chat_id)
      result = scholar.digest_paper(paper_id)
      if "error" in result:
          if result["error"] == "unknown_paper":
              send(chat_id, f"Paper {paper_id} not found. Try /papers [topic] to discover it first.")
          else:
              send(chat_id, f"Digest failed: {result['error']}")
          return
      lines = [
          f"Digest: {paper_id}\n",
          f"Priority: {result.get('priority', '?')}\n\n",
          "Key Findings:\n",
      ]
      for f in result.get("key_findings", []):
          lines.append(f"• {f}\n")
      techniques = result.get("implementable_techniques", [])
      if techniques:
          lines.append("\nImplementable:\n")
          for t in techniques:
              lines.append(f"• {t}\n")
      relevance = result.get("relevance_to_builds", "")
      if relevance:
          lines.append(f"\nRelevance: {relevance}\n")
      actions = result.get("actions", [])
      if actions:
          lines.append(f"\nActions taken: {', '.join(actions)}\n")
      send(chat_id, "".join(lines))


  def handle_scholar(chat_id: str, subcommand: str):
      """Handle /scholar [subcommand]."""
      sub = subcommand.strip().lower()
      if sub == "status" or sub == "":
          summary = scholar.get_recent_papers(days=7)
          lines = [
              f"AutoScholar — last 7 days\n",
              f"Discovered: {summary['total']} papers\n",
              f"Digested: {summary['digested']} papers\n",
          ]
          if summary["top_titles"]:
              lines.append("\nTop digested:\n")
              for t in summary["top_titles"]:
                  lines.append(f"• {t}\n")
          send(chat_id, "".join(lines))
      else:
          send(chat_id, "Usage:\n/scholar status — recent activity\n"
                        "/papers [topic] — search papers\n"
                        "/digest [paper_id] — deep dive a paper")
  ```

- [ ] **Step 3: Wire handlers into `handle_message()`**

  In `handle_message()`, inside the `/slash commands` block (after the `/approve` handler, before the media check), add:

  ```python
      if text:
          lower = text.lower()
          # ... existing handlers above ...
          if lower.startswith("/papers"):
              topic = text[len("/papers"):].strip()
              handle_papers(chat_id, topic)
              return
          if lower.startswith("/digest ") or lower == "/digest":
              paper_id = text[len("/digest"):].strip()
              handle_digest(chat_id, paper_id)
              return
          if lower.startswith("/scholar"):
              subcommand = text[len("/scholar"):].strip()
              handle_scholar(chat_id, subcommand)
              return
  ```

  Place these before the `# ── 3. Process media if present` comment.

- [ ] **Step 4: Verify import works**

  ```bash
  cd ~/openclaw/scripts
  python3 -c "import sys; sys.path.insert(0, '.'); from autoresearch import scholar; print('OK')"
  ```

  Expected: `OK`

- [ ] **Step 5: Commit**

  ```bash
  cd ~/openclaw
  git add scripts/telegram-dispatcher.py
  git commit -m "feat(autoscolar): wire /papers /digest /scholar commands into Clawmson"
  ```

---

## Task 12: Cron Script

**Files:**
- Create: `scripts/cron-scholar.sh`

- [ ] **Step 1: Create the cron script**

  ```bash
  cat > ~/openclaw/scripts/cron-scholar.sh << 'CRONEOF'
  #!/bin/bash
  # =============================================================================
  # cron-scholar.sh — AutoScholar Nightly Discovery + Digestion
  # Schedule: nightly at 2am (0 2 * * *)
  # Phase 4 — AutoScholar · IDLE_PROTOCOL Advanced Tier
  #
  # Pipeline:
  #   1. Run auto_mode() — discover + rank + digest new papers
  #   2. Log results to logs/cron-scholar.log
  #   3. Send Telegram summary via notify-telegram.sh
  # =============================================================================

  OPENCLAW_ROOT="${HOME}/openclaw"
  TODAY=$(date +%Y-%m-%d)
  TIMESTAMP=$(date +%H:%M)
  LOG_FILE="${OPENCLAW_ROOT}/logs/cron-scholar.log"

  mkdir -p "${OPENCLAW_ROOT}/logs"

  echo "[$(date)] cron-scholar start" >> "$LOG_FILE"

  # Load .env
  set -a
  source "${OPENCLAW_ROOT}/.env" 2>/dev/null || true
  set +a

  # Run auto_mode and capture JSON result
  RESULT=$(python3 -c "
  import json, sys
  sys.path.insert(0, '${OPENCLAW_ROOT}/scripts')
  from autoresearch import scholar
  print(json.dumps(scholar.auto_mode()))
  " 2>> "$LOG_FILE")

  if [[ -z "$RESULT" ]]; then
    echo "[$(date)] auto_mode returned no output — check errors above" >> "$LOG_FILE"
    bash "${OPENCLAW_ROOT}/scripts/notify-telegram.sh" \
      "AutoScholar Nightly ${TODAY}: Failed to run. Check ~/openclaw/logs/cron-scholar.log" 2>/dev/null || true
    exit 1
  fi

  DISCOVERED=$(echo "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('discovered', 0))" 2>/dev/null || echo "?")
  DIGESTED=$(echo "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('digested', 0))" 2>/dev/null || echo "?")
  ACTIONS=$(echo "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); acts=d.get('actions_taken',[]); print(','.join(acts) if acts else 'none')" 2>/dev/null || echo "?")
  TOP_TITLES=$(echo "$RESULT" | python3 -c "
  import json,sys
  d=json.load(sys.stdin)
  titles=d.get('top_titles',[])
  print('\n'.join('• ' + t for t in titles[:5]) if titles else '(none)')
  " 2>/dev/null || echo "(none)")

  echo "[$(date)] discovered=${DISCOVERED} digested=${DIGESTED} actions=${ACTIONS}" >> "$LOG_FILE"

  bash "${OPENCLAW_ROOT}/scripts/notify-telegram.sh" \
  "AutoScholar Nightly — ${TODAY}

  Discovered: ${DISCOVERED} papers
  Digested: ${DIGESTED} papers
  Actions taken: ${ACTIONS}

  Top papers:
  ${TOP_TITLES}

  Review at: ~/openclaw/autoresearch/outputs/papers/" 2>/dev/null || true

  echo "[$(date)] cron-scholar complete" >> "$LOG_FILE"
  CRONEOF

  chmod +x ~/openclaw/scripts/cron-scholar.sh
  ```

- [ ] **Step 2: Smoke-test the script syntax**

  ```bash
  bash -n ~/openclaw/scripts/cron-scholar.sh && echo "Syntax OK"
  ```

  Expected: `Syntax OK`

- [ ] **Step 3: Commit**

  ```bash
  cd ~/openclaw
  git add scripts/cron-scholar.sh
  git commit -m "feat(autoscolar): nightly cron-scholar.sh with Telegram summary"
  ```

---

## Task 13: Agent Config Doc

**Files:**
- Create: `agents/configs/autoresearch-scholar.md`

- [ ] **Step 1: Create the agent config doc**

  ```bash
  cat > ~/openclaw/agents/configs/autoresearch-scholar.md << 'DOCEOF'
  # AutoScholar — Agent Config

  ## Role
  Paper discovery, digestion, and routing agent. Monitors HuggingFace for papers
  relevant to active OpenClaw domains and surfaces actionable research to the build
  pipeline, bakeoff queue, and Clawmson.

  ## Entry Points

  | Trigger | Function | When |
  |---------|----------|------|
  | Cron (nightly 2am) | `auto_mode()` | Automated overnight sweep |
  | Telegram `/papers [topic]` | `discover()` | On-demand search |
  | Telegram `/digest [paper_id]` | `digest_paper()` | On-demand deep dive |
  | Telegram `/scholar status` | `get_recent_papers()` | Status check |
  | ClawTeam debate | `get_paper_for_debate()` | Debate pattern input |

  ## Models Used

  | Model | Purpose |
  |-------|---------|
  | `qwen3:30b` | Paper digestion and insight extraction |
  | `nomic-embed-text` | Semantic relevance ranking |

  ## Configuration

  | Env var | Default | Purpose |
  |---------|---------|---------|
  | `SCHOLAR_RELEVANCE_THRESHOLD` | `0.75` | Auto-digest minimum score |
  | `SCHOLAR_DIGEST_MODEL` | `qwen3:30b` | Digestion model |
  | `SCHOLAR_EMBED_MODEL` | `nomic-embed-text` | Embedding model |

  ## Output Locations

  | Output | Path |
  |--------|------|
  | Daily digest | `autoresearch/outputs/papers/academic-scholar-digest-[date].md` |
  | Improvement proposals | `improvements/scholar-[slug]-[date].md` |
  | Bakeoff flags | `benchmark/bakeoff-queue.md` |
  | Build context notes | `autoresearch/outputs/papers/academic-[slug]-[date].md` |

  ## Data

  - SQLite: `~/.openclaw/clawmson.db` — tables `papers`, `paper_digests`
  - Logs: `logs/cron-scholar.log`

  ## Cron Schedule

  ```
  0 2 * * *  bash ~/openclaw/scripts/cron-scholar.sh
  ```

  Add to crontab with: `crontab -e`

  ## Action Routing Rules

  | Condition | Output |
  |-----------|--------|
  | P1 + implementable techniques | `improvements/scholar-*.md` |
  | Linked HF models found | `benchmark/bakeoff-queue.md` (append) |
  | P1 + non-empty relevance | `autoresearch/outputs/papers/academic-*.md` |

  ## Domains Monitored (default)

  - agent orchestration
  - prediction markets
  - memory architectures
  - local LLM optimization
  - multi-agent systems
  - RAG retrieval augmented
  - tool use LLM
  - agentic systems

  ## Source

  `scripts/autoresearch/scholar.py`
  DOCEOF
  ```

- [ ] **Step 2: Commit**

  ```bash
  cd ~/openclaw
  git add agents/configs/autoresearch-scholar.md
  git commit -m "docs(autoscolar): agent config doc for AutoScholar"
  ```

---

## Task 14: Final Verification

- [ ] **Step 1: Run the complete test suite**

  ```bash
  cd ~/openclaw/scripts
  python -m pytest tests/test_scholar.py -v
  ```

  Expected: All tests PASS. Count should be 22+ tests across 8 test classes.

- [ ] **Step 2: Verify existing tests still pass**

  ```bash
  cd ~/openclaw/scripts
  python -m pytest tests/ -v
  ```

  Expected: All tests PASS — no regressions.

- [ ] **Step 3: Verify module imports cleanly from scripts/**

  ```bash
  cd ~/openclaw/scripts
  python3 -c "
  from autoresearch import scholar
  print('HF_REQUEST_TIMEOUT:', scholar.HF_REQUEST_TIMEOUT)
  print('RELEVANCE_THRESHOLD:', scholar.RELEVANCE_THRESHOLD)
  print('DIGEST_MODEL:', scholar.DIGEST_MODEL)
  print('Import OK')
  "
  ```

  Expected: Constants printed, `Import OK`.

- [ ] **Step 4: Verify cron script is registered (optional)**

  To add to crontab for nightly 2am runs:
  ```bash
  (crontab -l 2>/dev/null; echo "0 2 * * * bash ~/openclaw/scripts/cron-scholar.sh") | crontab -
  crontab -l | grep scholar
  ```

- [ ] **Step 5: Final commit**

  ```bash
  cd ~/openclaw
  git add -A
  git status
  # Verify nothing unintended is staged, then:
  git commit -m "feat(autoscolar): AutoScholar complete — discovery, digestion, routing, Telegram, cron"
  ```
