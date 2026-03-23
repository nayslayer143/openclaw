# Twitter Scout Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Twitter/X link scouting pipeline to Clawmson that extracts tweet content, categorizes it via local Ollama, stores results in SQLite, and returns immediate digests — all without blocking the Telegram dispatcher.

**Architecture:** Pre-route check in `telegram-dispatcher.py` intercepts Twitter/X status URLs before intent classification, spawns a daemon thread, and delegates entirely to `clawmson_scout.py`. Extraction uses a three-strategy fallback chain (nitter → fxtwitter → oembed) implemented in `clawmson_twitter.py`. Results are stored in a new `scout_links` table added additively to `clawmson_db.py`.

**Tech Stack:** Python 3, SQLite (via stdlib `sqlite3`), `requests`, `beautifulsoup4` (new), Ollama local inference (`qwen2.5:7b`), Telegram Bot API (polling, existing pattern)

**Spec:** `docs/superpowers/specs/2026-03-22-twitter-scout-pipeline-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `scripts/clawmson_twitter.py` | CREATE | Extraction fallback chain + Ollama categorization |
| `scripts/clawmson_scout.py` | CREATE | Telegram UX: handle links, digest, format report |
| `scripts/clawmson_db.py` | MODIFY | Add `scout_links` table + 3 new DB functions |
| `scripts/telegram-dispatcher.py` | MODIFY | Pre-route Twitter check + `/scout` command + import |
| `requirements.txt` | MODIFY | Add `beautifulsoup4` |
| `tests/test_clawmson_twitter.py` | CREATE | Unit tests for extraction + categorization |
| `tests/test_clawmson_scout.py` | CREATE | Unit tests for formatting + digest |
| `tests/test_clawmson_db_scout.py` | CREATE | Unit tests for new DB functions |

---

## Task 1: Add `beautifulsoup4` to requirements and `scout_links` table to DB

**Files:**
- Modify: `requirements.txt`
- Modify: `scripts/clawmson_db.py`
- Create: `tests/test_clawmson_db_scout.py`

- [ ] **Step 1.1: Write failing DB tests**

Create `tests/test_clawmson_db_scout.py`:

```python
import os
import json
import tempfile
import pytest

# Point DB at a temp file so tests don't touch production DB
os.environ["CLAWMSON_DB_PATH"] = tempfile.mktemp(suffix=".db")

import clawmson_db as db


CHAT = "test_chat_123"
URL  = "https://x.com/foo/status/123456"

EXTRACTION_OK = {
    "author": "testuser",
    "text": "This is a great new tool for AI agents",
    "media_urls": [],
    "linked_urls": ["https://github.com/example/tool"],
    "timestamp": "2026-03-22T10:00:00",
    "raw_html": "<div>tweet</div>",
    "method": "nitter",
}

EXTRACTION_FAILED = {
    "extraction_failed": True,
    "methods_tried": ["nitter", "fxtwitter", "oembed"],
    "url": URL,
}

CATEGORIZATION_OK = {
    "category": "tool",
    "relevance_score": 8,
    "summary": "A new tool for agentic AI workflows.",
    "action_items": ["Check the repo", "Try the demo"],
}

CATEGORIZATION_FAILED = {
    "category": "categorization_failed",
    "relevance_score": 0,
    "summary": "",
    "action_items": [],
}


def test_save_scout_link_success():
    db.save_scout_link(CHAT, URL, EXTRACTION_OK, CATEGORIZATION_OK)
    rows = db.get_scout_links(CHAT, since_hours=1)
    assert len(rows) == 1
    row = rows[0]
    assert row["url"] == URL
    assert row["author"] == "testuser"
    assert row["tweet_text"] == "This is a great new tool for AI agents"
    assert row["category"] == "tool"
    assert row["relevance_score"] == 8
    assert json.loads(row["action_items"]) == ["Check the repo", "Try the demo"]
    assert json.loads(row["github_repos"]) == ["https://github.com/example/tool"]
    assert row["processed_at"] is not None


def test_save_scout_link_extraction_failed():
    url2 = "https://x.com/bar/status/999"
    # When extraction fails, process_batch sets category="extraction_failed"
    extraction_failed_cat = {
        "category": "extraction_failed",
        "relevance_score": 0,
        "summary": "",
        "action_items": [],
    }
    db.save_scout_link(CHAT, url2, EXTRACTION_FAILED, extraction_failed_cat)
    rows = db.get_scout_links(CHAT, since_hours=1, category="extraction_failed")
    matching = [r for r in rows if r["url"] == url2]
    assert len(matching) == 1
    assert matching[0]["tweet_text"] is None      # extraction dict had no "text"
    assert matching[0]["category"] == "extraction_failed"
    raw = json.loads(matching[0]["raw_data"])
    assert raw["extraction_failed"] is True
    assert "methods_tried" in raw


def test_get_scout_links_category_filter():
    rows_tool = db.get_scout_links(CHAT, since_hours=1, category="tool")
    assert all(r["category"] == "tool" for r in rows_tool)


def test_get_scout_digest_structure():
    digest = db.get_scout_digest(CHAT, since_hours=1)
    assert "counts" in digest
    assert "top_items" in digest
    assert isinstance(digest["counts"], dict)
    assert isinstance(digest["top_items"], list)
    # top_items sorted by relevance_score descending
    scores = [item["relevance_score"] for item in digest["top_items"]]
    assert scores == sorted(scores, reverse=True)
    # top_items have required keys
    for item in digest["top_items"]:
        for key in ("url", "author", "summary", "category", "relevance_score"):
            assert key in item
```

- [ ] **Step 1.2: Run tests to verify they fail**

```bash
cd /Users/nayslayer/openclaw
python -m pytest .claude/worktrees/stupefied-hofstadter/tests/test_clawmson_db_scout.py -v 2>&1 | head -30
```

Expected: `ImportError` or `AttributeError: module 'clawmson_db' has no attribute 'save_scout_link'`

- [ ] **Step 1.3: Add `beautifulsoup4` to requirements**

In `requirements.txt`, add after the `requests` line:

```
# HTML parsing for nitter tweet extraction
beautifulsoup4
```

- [ ] **Step 1.4: Add `scout_links` table to `_init_db()` in `clawmson_db.py`**

In `scripts/clawmson_db.py`, find the `_init_db()` function. Inside the `conn.executescript("""...""")` block, append the new table DDL **before the closing `"""`**:

```sql
            CREATE TABLE IF NOT EXISTS scout_links (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id         TEXT NOT NULL,
                url             TEXT NOT NULL,
                author          TEXT,
                tweet_text      TEXT,
                category        TEXT,
                relevance_score INTEGER,
                summary         TEXT,
                action_items    TEXT,
                github_repos    TEXT,
                linked_urls     TEXT,
                processed_at    TEXT NOT NULL,
                raw_data        TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_scout_chat ON scout_links(chat_id);
            CREATE INDEX IF NOT EXISTS idx_scout_cat  ON scout_links(category);
```

- [ ] **Step 1.5: Add `save_scout_link()` to `clawmson_db.py`**

Append after `list_references()`, before `# Init on import`:

```python
def save_scout_link(chat_id: str, url: str, extraction: dict, categorization: dict):
    """Store one scouted tweet. Works for both success and extraction-failed dicts."""
    import json as _json
    ts = datetime.datetime.utcnow().isoformat()

    # For extraction-failed dicts, most fields will be None
    author      = extraction.get("author")
    tweet_text  = extraction.get("text")
    linked_urls = extraction.get("linked_urls", [])

    # GitHub repos: scan tweet text + linked_urls
    from clawmson_twitter import extract_github_repos
    all_text = (tweet_text or "") + " ".join(linked_urls)
    github_repos = extract_github_repos(all_text)

    category        = categorization.get("category")
    relevance_score = categorization.get("relevance_score")
    summary         = categorization.get("summary")
    action_items    = categorization.get("action_items", [])

    # raw_data: full extraction dict (includes methods_tried for failures)
    raw_data = _json.dumps(extraction)

    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO scout_links "
            "(chat_id, url, author, tweet_text, category, relevance_score, summary, "
            " action_items, github_repos, linked_urls, processed_at, raw_data) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                chat_id, url, author, tweet_text, category, relevance_score, summary,
                _json.dumps(action_items),
                _json.dumps(github_repos),
                _json.dumps(linked_urls),
                ts, raw_data,
            )
        )
```

- [ ] **Step 1.6: Add `get_scout_links()` to `clawmson_db.py`**

```python
def get_scout_links(chat_id: str, since_hours: int = 24, category: str = None) -> list:
    """Return scout_links rows for chat_id within since_hours, newest first."""
    import datetime as _dt
    cutoff = (_dt.datetime.utcnow() - _dt.timedelta(hours=since_hours)).isoformat()
    with _get_conn() as conn:
        if category:
            rows = conn.execute(
                "SELECT * FROM scout_links WHERE chat_id = ? AND processed_at >= ? "
                "AND category = ? ORDER BY processed_at DESC",
                (chat_id, cutoff, category)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM scout_links WHERE chat_id = ? AND processed_at >= ? "
                "ORDER BY processed_at DESC",
                (chat_id, cutoff)
            ).fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 1.7: Add `get_scout_digest()` to `clawmson_db.py`**

```python
def get_scout_digest(chat_id: str, since_hours: int = 24) -> dict:
    """Return category counts + top 5 items by relevance for the last N hours."""
    import datetime as _dt
    cutoff = (_dt.datetime.utcnow() - _dt.timedelta(hours=since_hours)).isoformat()
    with _get_conn() as conn:
        count_rows = conn.execute(
            "SELECT category, COUNT(*) as n FROM scout_links "
            "WHERE chat_id = ? AND processed_at >= ? GROUP BY category",
            (chat_id, cutoff)
        ).fetchall()
        top_rows = conn.execute(
            "SELECT url, author, summary, category, relevance_score FROM scout_links "
            "WHERE chat_id = ? AND processed_at >= ? "
            "ORDER BY relevance_score DESC LIMIT 5",
            (chat_id, cutoff)
        ).fetchall()
    return {
        "counts": {r["category"]: r["n"] for r in count_rows},
        "top_items": [dict(r) for r in top_rows],
    }
```

- [ ] **Step 1.8: Run tests**

```bash
cd /Users/nayslayer/openclaw/.claude/worktrees/stupefied-hofstadter/scripts
python -m pytest ../tests/test_clawmson_db_scout.py -v
```

Expected: All tests pass. If `clawmson_twitter` import in `save_scout_link` fails (module doesn't exist yet), temporarily stub `extract_github_repos` by replacing the import with a direct regex inline — then revert after Task 2.

- [ ] **Step 1.9: Commit**

```bash
cd /Users/nayslayer/openclaw/.claude/worktrees/stupefied-hofstadter
git add requirements.txt scripts/clawmson_db.py tests/test_clawmson_db_scout.py
git commit -m "feat: add scout_links table and DB functions to clawmson_db"
```

---

## Task 2: Create `clawmson_twitter.py` — extraction + categorization engine

**Files:**
- Create: `scripts/clawmson_twitter.py`
- Create: `tests/test_clawmson_twitter.py`

- [ ] **Step 2.1: Write failing tests**

Create `tests/test_clawmson_twitter.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from unittest.mock import patch, MagicMock
import clawmson_twitter as tw


TWEET_URL = "https://x.com/testuser/status/1234567890"


class TestExtractGithubRepos:
    def test_finds_github_url(self):
        text = "Check out https://github.com/owner/repo for more"
        assert tw.extract_github_repos(text) == ["https://github.com/owner/repo"]

    def test_deduplicates(self):
        text = "https://github.com/a/b https://github.com/a/b"
        assert tw.extract_github_repos(text) == ["https://github.com/a/b"]

    def test_returns_empty_for_no_match(self):
        assert tw.extract_github_repos("no links here") == []

    def test_ignores_non_repo_github_urls(self):
        # github.com/owner only (no repo) should not match
        result = tw.extract_github_repos("https://github.com/owner")
        assert result == []


class TestParseNitter:
    def test_extracts_tweet_text(self):
        html = """
        <div class="tweet-content media-body">Hello nitter world</div>
        <a class="username" href="/testuser">@testuser</a>
        """
        result = tw.parse_nitter(html)
        assert result["text"] == "Hello nitter world"
        assert result["author"] == "testuser"
        assert result["method"] == "nitter"

    def test_returns_none_on_empty_html(self):
        result = tw.parse_nitter("<html></html>")
        assert result is None


class TestExtractTweetFallbackChain:
    def test_methods_tried_recorded_on_failure(self):
        with patch("clawmson_twitter._try_nitter", return_value=None), \
             patch("clawmson_twitter._try_fxtwitter", return_value=None), \
             patch("clawmson_twitter._try_oembed", return_value=None):
            result = tw.extract_tweet(TWEET_URL)
        assert result["extraction_failed"] is True
        assert set(result["methods_tried"]) == {"nitter", "fxtwitter", "oembed"}

    def test_returns_nitter_result_when_successful(self):
        nitter_result = {
            "author": "foo", "text": "bar", "media_urls": [],
            "linked_urls": [], "timestamp": "", "raw_html": "", "method": "nitter"
        }
        with patch("clawmson_twitter._try_nitter", return_value=nitter_result):
            result = tw.extract_tweet(TWEET_URL)
        assert result["method"] == "nitter"
        assert result["author"] == "foo"

    def test_falls_through_to_fxtwitter(self):
        fx_result = {
            "author": "bar", "text": "baz", "media_urls": [],
            "linked_urls": [], "timestamp": "", "raw_html": "", "method": "fxtwitter"
        }
        with patch("clawmson_twitter._try_nitter", return_value=None), \
             patch("clawmson_twitter._try_fxtwitter", return_value=fx_result):
            result = tw.extract_tweet(TWEET_URL)
        assert result["method"] == "fxtwitter"


class TestCategorizeTweet:
    def test_returns_categorization_failed_on_ollama_error(self):
        with patch("clawmson_twitter.requests.post") as mock_post:
            mock_post.side_effect = Exception("connection refused")
            result = tw.categorize_tweet("some tweet text", [])
        assert result["category"] == "categorization_failed"
        assert result["relevance_score"] == 0

    def test_returns_parsed_result_on_success(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "message": {"content": '{"category":"tool","relevance_score":8,"summary":"A tool","action_items":["Try it"]}'}
        }
        with patch("clawmson_twitter.requests.post", return_value=mock_resp):
            result = tw.categorize_tweet("some tweet text", [])
        assert result["category"] == "tool"
        assert result["relevance_score"] == 8


class TestProcessBatch:
    def test_returns_stats(self):
        good = {
            "author": "a", "text": "t", "media_urls": [], "linked_urls": [],
            "timestamp": "", "raw_html": "", "method": "nitter"
        }
        cat = {"category": "tool", "relevance_score": 7, "summary": "s", "action_items": []}
        with patch("clawmson_twitter.extract_tweet", return_value=good), \
             patch("clawmson_twitter.categorize_tweet", return_value=cat), \
             patch("clawmson_twitter.time.sleep"):
            out = tw.process_batch(["https://x.com/a/status/1", "https://x.com/b/status/2"])
        assert out["stats"]["total"] == 2
        assert out["stats"]["succeeded"] == 2
        assert out["stats"]["failed"] == 0
        assert len(out["results"]) == 2
```

- [ ] **Step 2.2: Run tests to confirm they fail**

```bash
cd /Users/nayslayer/openclaw/.claude/worktrees/stupefied-hofstadter/scripts
python -m pytest ../tests/test_clawmson_twitter.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'clawmson_twitter'`

- [ ] **Step 2.3: Create `scripts/clawmson_twitter.py`**

```python
#!/usr/bin/env python3
from __future__ import annotations
"""
Twitter Scout — extraction + categorization engine.
Tries nitter → fxtwitter → oembed in order. Falls back gracefully on failure.
"""

import os
import re
import json
import time
import requests
from bs4 import BeautifulSoup

NITTER_INSTANCES = [
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
    "https://nitter.net",
]
RATE_LIMIT_DELAY = 0.5    # seconds between URLs (per-URL, not per-request)
REQUEST_TIMEOUT  = 15     # seconds per HTTP request
SCOUT_MODEL      = os.environ.get("OLLAMA_SCOUT_MODEL", "qwen2.5:7b")
OLLAMA_BASE_URL  = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

_GITHUB_RE = re.compile(r'https?://github\.com/[\w.-]+/[\w.-]+')
_TWITTER_STATUS_RE = re.compile(r'https?://(x\.com|twitter\.com)/(\w+)/status/(\d+)')

_CATEGORIZE_SYSTEM = """\
You are an AI research scout for OpenClaw, a multimodal AI workspace. \
Categorize this tweet and extract actionable intelligence.

Categories:
- tool: A new tool, library, framework, or software that could improve our AI/dev workflow
- technique: A prompting technique, coding pattern, or methodology worth trying
- business_intel: Business insights, market data, funding news, or competitive intelligence
- code_pattern: Specific code snippets, architectures, or implementations to study
- market_intel: Market trends, pricing strategies, user behavior data, or opportunity signals
- irrelevant: Not actionable for an AI agent automation setup

Return JSON: {"category": str, "relevance_score": int (1-10), \
"summary": str (1 sentence), "action_items": [str]}"""


def extract_github_repos(text: str) -> list:
    """Find github.com/owner/repo URLs in text. Returns deduplicated list."""
    return list(dict.fromkeys(_GITHUB_RE.findall(text)))


def parse_nitter(html: str) -> dict | None:
    """Parse nitter HTML page. Returns tweet dict or None if parse fails."""
    try:
        soup = BeautifulSoup(html, "html.parser")
        content = soup.find(class_="tweet-content")
        if not content:
            return None
        text = content.get_text(strip=True)
        if not text:
            return None

        author = ""
        username_tag = soup.find(class_="username")
        if username_tag:
            author = username_tag.get_text(strip=True).lstrip("@")

        timestamp = ""
        time_tag = soup.find("span", class_="tweet-date")
        if time_tag:
            a = time_tag.find("a")
            if a:
                timestamp = a.get("title", "")

        media_urls = [
            img["src"] for img in soup.find_all("img", class_="still-image")
            if img.get("src")
        ]

        linked_urls = [
            a["href"] for a in content.find_all("a")
            if a.get("href") and a["href"].startswith("http")
        ]

        return {
            "author": author,
            "text": text,
            "media_urls": media_urls,
            "linked_urls": linked_urls,
            "timestamp": timestamp,
            "raw_html": html[:4000],
            "method": "nitter",
        }
    except Exception:
        return None


def _nitter_url(tweet_url: str, instance: str) -> str:
    """Convert a twitter/x URL to a nitter instance URL."""
    m = _TWITTER_STATUS_RE.search(tweet_url)
    if not m:
        return tweet_url
    username, status_id = m.group(2), m.group(3)
    return f"{instance}/{username}/status/{status_id}"


def _try_nitter(tweet_url: str) -> dict | None:
    """Try all nitter instances. Returns parsed dict or None."""
    for instance in NITTER_INSTANCES:
        url = _nitter_url(tweet_url, instance)
        try:
            r = requests.get(
                url, timeout=REQUEST_TIMEOUT,
                headers={"User-Agent": "Mozilla/5.0 (compatible; Clawmson/1.0)"},
                allow_redirects=True,
            )
            if r.status_code == 200:
                result = parse_nitter(r.text)
                if result:
                    print(f"[twitter] nitter success via {instance}")
                    return result
        except Exception as e:
            print(f"[twitter] nitter {instance} failed: {e}")
    return None


def parse_fxtwitter(url: str) -> dict | None:
    """Fetch fxtwitter version and parse Open Graph tags."""
    try:
        fx_url = _TWITTER_STATUS_RE.sub(
            lambda m: f"https://fxtwitter.com/{m.group(2)}/status/{m.group(3)}",
            url
        )
        r = requests.get(
            fx_url, timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 (compatible; Clawmson/1.0)"},
        )
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        desc = soup.find("meta", {"property": "og:description"})
        author_tag = soup.find("meta", {"property": "og:title"})
        text = desc["content"] if desc and desc.get("content") else ""
        author = author_tag["content"].split(" on ")[0] if author_tag and author_tag.get("content") else ""
        if not text:
            return None
        return {
            "author": author,
            "text": text,
            "media_urls": [],
            "linked_urls": [],
            "timestamp": "",
            "raw_html": r.text[:4000],
            "method": "fxtwitter",
        }
    except Exception as e:
        print(f"[twitter] fxtwitter failed: {e}")
        return None


def _try_fxtwitter(tweet_url: str) -> dict | None:
    return parse_fxtwitter(tweet_url)


def parse_oembed(url: str) -> dict | None:
    """Use Twitter OEmbed API. Strips HTML tags from returned html field."""
    try:
        r = requests.get(
            "https://publish.twitter.com/oembed",
            params={"url": url},
            timeout=REQUEST_TIMEOUT,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        html = data.get("html", "")
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()
        author = data.get("author_name", "")
        if not text:
            return None
        return {
            "author": author,
            "text": text,
            "media_urls": [],
            "linked_urls": [],
            "timestamp": "",
            "raw_html": html[:4000],
            "method": "oembed",
        }
    except Exception as e:
        print(f"[twitter] oembed failed: {e}")
        return None


def _try_oembed(tweet_url: str) -> dict | None:
    return parse_oembed(tweet_url)


def extract_tweet(url: str) -> dict:
    """
    Try nitter → fxtwitter → oembed. Returns tweet dict on success,
    or {"extraction_failed": True, "methods_tried": [...], "url": url} on total failure.
    """
    methods_tried = []

    result = _try_nitter(url)
    if result:
        return result
    methods_tried.append("nitter")

    result = _try_fxtwitter(url)
    if result:
        return result
    methods_tried.append("fxtwitter")

    result = _try_oembed(url)
    if result:
        return result
    methods_tried.append("oembed")

    print(f"[twitter] all extraction methods failed for {url}")
    return {"extraction_failed": True, "methods_tried": methods_tried, "url": url}


def categorize_tweet(tweet_text: str, linked_urls: list) -> dict:
    """
    Send tweet text to Ollama for categorization.
    Returns {category, relevance_score, summary, action_items}.
    Falls back to categorization_failed if Ollama is unreachable.
    """
    user_msg = f"Tweet: {tweet_text}"
    if linked_urls:
        user_msg += f"\nLinked URLs: {', '.join(linked_urls)}"

    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": SCOUT_MODEL,
                "messages": [
                    {"role": "system", "content": _CATEGORIZE_SYSTEM},
                    {"role": "user", "content": user_msg},
                ],
                "stream": False,
                "format": "json",
            },
            timeout=60,
        )
        resp.raise_for_status()
        raw = resp.json().get("message", {}).get("content", "")
        result = json.loads(raw)
        result.setdefault("category", "irrelevant")
        result.setdefault("relevance_score", 5)
        result.setdefault("summary", "")
        result.setdefault("action_items", [])
        return result
    except Exception as e:
        print(f"[twitter] categorize_tweet failed: {e}")
        return {
            "category": "categorization_failed",
            "relevance_score": 0,
            "summary": "",
            "action_items": [],
        }


def process_batch(urls: list) -> dict:
    """
    Process a list of Twitter URLs. Rate-limited per URL (not per HTTP request).
    Returns {results: [...], stats: {total, succeeded, failed, by_category: {}}}
    """
    results = []
    by_category: dict = {}

    for i, url in enumerate(urls):
        extraction = extract_tweet(url)
        if extraction.get("extraction_failed"):
            cat_result = {
                "category": "extraction_failed",
                "relevance_score": 0,
                "summary": "",
                "action_items": [],
            }
        else:
            cat_result = categorize_tweet(
                extraction.get("text", ""),
                extraction.get("linked_urls", []),
            )

        record = {
            "url": url,
            "extraction": extraction,
            "categorization": cat_result,
        }
        results.append(record)
        cat = cat_result.get("category", "unknown")
        by_category[cat] = by_category.get(cat, 0) + 1

        # Rate limit: sleep after each URL except the last
        if i < len(urls) - 1:
            time.sleep(RATE_LIMIT_DELAY)

    succeeded = sum(1 for r in results if not r["extraction"].get("extraction_failed"))
    return {
        "results": results,
        "stats": {
            "total": len(urls),
            "succeeded": succeeded,
            "failed": len(urls) - succeeded,
            "by_category": by_category,
        },
    }
```

- [ ] **Step 2.4: Run tests**

```bash
cd /Users/nayslayer/openclaw/.claude/worktrees/stupefied-hofstadter/scripts
python -m pytest ../tests/test_clawmson_twitter.py -v
```

Expected: All tests pass. If any `parse_nitter` test fails due to CSS class changes, inspect the HTML fixture and adjust the class name in the test, not in the implementation.

- [ ] **Step 2.5: Re-run DB tests to confirm `save_scout_link` import now resolves**

```bash
python -m pytest ../tests/test_clawmson_db_scout.py -v
```

Expected: All pass (the `from clawmson_twitter import extract_github_repos` in `clawmson_db.py` now resolves).

- [ ] **Step 2.6: Commit**

```bash
cd /Users/nayslayer/openclaw/.claude/worktrees/stupefied-hofstadter
git add scripts/clawmson_twitter.py tests/test_clawmson_twitter.py
git commit -m "feat: add clawmson_twitter extraction and categorization engine"
```

---

## Task 3: Create `clawmson_scout.py` — Telegram UX layer

**Files:**
- Create: `scripts/clawmson_scout.py`
- Create: `tests/test_clawmson_scout.py`

- [ ] **Step 3.1: Write failing tests**

Create `tests/test_clawmson_scout.py`:

```python
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, call

os.environ["CLAWMSON_DB_PATH"] = tempfile.mktemp(suffix=".db")
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import clawmson_scout as scout


CHAT = "chat_456"


class TestFormatScoutReport:
    def test_single_tool(self):
        results = [{
            "url": "https://x.com/a/status/1",
            "extraction": {"author": "alice", "text": "check this out"},
            "categorization": {"category": "tool", "relevance_score": 9,
                               "summary": "Great tool for AI.", "action_items": []},
        }]
        report = scout.format_scout_report(results)
        assert "Scout Report" in report
        assert "1 link" in report
        assert "9/10" in report
        assert "Great tool for AI." in report
        assert "🔧" in report

    def test_mixed_categories(self):
        results = [
            {"url": "u1", "extraction": {}, "categorization": {"category": "tool", "relevance_score": 8, "summary": "s1", "action_items": []}},
            {"url": "u2", "extraction": {}, "categorization": {"category": "technique", "relevance_score": 6, "summary": "s2", "action_items": []}},
            {"url": "u3", "extraction": {}, "categorization": {"category": "irrelevant", "relevance_score": 1, "summary": "s3", "action_items": []}},
        ]
        report = scout.format_scout_report(results)
        assert "🔧" in report
        assert "💡" in report
        assert "🗑" in report
        assert "3 links" in report

    def test_top_find_is_highest_relevance(self):
        results = [
            {"url": "u1", "extraction": {}, "categorization": {"category": "tool", "relevance_score": 3, "summary": "low", "action_items": []}},
            {"url": "u2", "extraction": {}, "categorization": {"category": "technique", "relevance_score": 9, "summary": "TOP FIND", "action_items": []}},
        ]
        report = scout.format_scout_report(results)
        assert "TOP FIND" in report

    def test_extraction_failed_shown_with_x_emoji(self):
        results = [{"url": "u1", "extraction": {"extraction_failed": True}, "categorization": {"category": "extraction_failed", "relevance_score": 0, "summary": "", "action_items": []}}]
        report = scout.format_scout_report(results)
        assert "❌" in report


class TestGenerateDigest:
    def test_empty_digest(self):
        with patch("clawmson_scout.db.get_scout_digest", return_value={"counts": {}, "top_items": []}):
            result = scout.generate_digest(CHAT)
        assert "No scouted links" in result or "digest" in result.lower()

    def test_digest_with_items(self):
        digest_data = {
            "counts": {"tool": 3, "technique": 1},
            "top_items": [
                {"url": "https://x.com/a/status/1", "author": "alice",
                 "summary": "Great tool", "category": "tool", "relevance_score": 9},
            ]
        }
        with patch("clawmson_scout.db.get_scout_digest", return_value=digest_data):
            result = scout.generate_digest(CHAT)
        assert "tool" in result.lower() or "🔧" in result
        assert "Great tool" in result


class TestHandleScoutLinks:
    def test_sends_acknowledgement_then_report(self):
        send_calls = []
        send_fn = lambda chat_id, msg: send_calls.append((chat_id, msg))

        batch_result = {
            "results": [{
                "url": "https://x.com/a/status/1",
                "extraction": {"author": "a", "text": "hello", "media_urls": [],
                               "linked_urls": [], "timestamp": "", "raw_html": "", "method": "nitter"},
                "categorization": {"category": "tool", "relevance_score": 7,
                                   "summary": "A nice tool", "action_items": []},
            }],
            "stats": {"total": 1, "succeeded": 1, "failed": 0, "by_category": {"tool": 1}},
        }

        with patch("clawmson_scout.tw.process_batch", return_value=batch_result), \
             patch("clawmson_scout.db.save_scout_link"):
            scout.handle_scout_links(
                CHAT,
                "check this https://x.com/a/status/1",
                send_fn,
            )

        assert len(send_calls) == 2
        # First call: acknowledgement
        assert "Scouting" in send_calls[0][1]
        # Second call: report
        assert "Scout Report" in send_calls[1][1]

    def test_saves_each_result_to_db(self):
        send_fn = lambda *a: None
        batch_result = {
            "results": [
                {"url": "u1", "extraction": {"author": "a", "text": "t1", "media_urls": [],
                  "linked_urls": [], "timestamp": "", "raw_html": "", "method": "nitter"},
                 "categorization": {"category": "tool", "relevance_score": 5, "summary": "", "action_items": []}},
                {"url": "u2", "extraction": {"author": "b", "text": "t2", "media_urls": [],
                  "linked_urls": [], "timestamp": "", "raw_html": "", "method": "fxtwitter"},
                 "categorization": {"category": "technique", "relevance_score": 6, "summary": "", "action_items": []}},
            ],
            "stats": {"total": 2, "succeeded": 2, "failed": 0, "by_category": {}},
        }
        with patch("clawmson_scout.tw.process_batch", return_value=batch_result) as _pb, \
             patch("clawmson_scout.db.save_scout_link") as mock_save:
            scout.handle_scout_links(CHAT, "https://x.com/a/status/1 https://x.com/b/status/2", send_fn)
        assert mock_save.call_count == 2
```

- [ ] **Step 3.2: Run tests to confirm they fail**

```bash
cd /Users/nayslayer/openclaw/.claude/worktrees/stupefied-hofstadter/scripts
python -m pytest ../tests/test_clawmson_scout.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'clawmson_scout'`

- [ ] **Step 3.3: Create `scripts/clawmson_scout.py`**

```python
#!/usr/bin/env python3
from __future__ import annotations
"""
Clawmson Scout — Telegram UX layer for the Twitter Scout pipeline.
Handles link processing, digest generation, and report formatting.
clawmson_scout never imports telegram-dispatcher; send_fn is injected.
"""

import re
import clawmson_db as db
import clawmson_twitter as tw

_TWITTER_RE = re.compile(r'https?://(x\.com|twitter\.com)/\w+/status/\d+')

_EMOJI = {
    "tool":                 "🔧",
    "technique":            "💡",
    "business_intel":       "📈",
    "code_pattern":         "🧩",
    "market_intel":         "📊",
    "irrelevant":           "🗑",
    "extraction_failed":    "❌",
    "categorization_failed":"⚠️",
}


def format_scout_report(results: list) -> str:
    """Compact summary sent immediately after batch processing completes."""
    total = len(results)
    link_word = "link" if total == 1 else "links"

    # Count by category
    counts: dict = {}
    for r in results:
        cat = r["categorization"].get("category", "unknown")
        counts[cat] = counts.get(cat, 0) + 1

    # Category summary line (skip irrelevant/failed from headline if others present)
    cat_parts = []
    priority_cats = ["tool", "technique", "business_intel", "code_pattern", "market_intel"]
    other_cats    = ["irrelevant", "extraction_failed", "categorization_failed"]
    for cat in priority_cats:
        if cat in counts:
            emoji = _EMOJI.get(cat, "•")
            n = counts[cat]
            label = cat.replace("_", " ")
            cat_parts.append(f"{emoji} {n} {label}")
    for cat in other_cats:
        if cat in counts:
            emoji = _EMOJI.get(cat, "•")
            n = counts[cat]
            label = cat.replace("_", " ")
            cat_parts.append(f"{emoji} {n} {label}")

    # Top find: highest relevance_score
    scored = sorted(
        results,
        key=lambda r: r["categorization"].get("relevance_score", 0),
        reverse=True
    )
    top = scored[0]["categorization"] if scored else {}
    top_score   = top.get("relevance_score", 0)
    top_summary = top.get("summary", "")

    lines = [f"📊 Scout Report ({total} {link_word})"]
    if cat_parts:
        lines.append(" · ".join(cat_parts))
    if top_score and top_summary:
        lines.append(f"\nTop find ({top_score}/10): {top_summary}")
    lines.append("\nSend /scout for full digest.")
    return "\n".join(lines)


def generate_digest(chat_id: str, since_hours: int = 24) -> str:
    """Full categorized digest for /scout command."""
    digest = db.get_scout_digest(chat_id, since_hours=since_hours)
    counts    = digest.get("counts", {})
    top_items = digest.get("top_items", [])

    if not counts:
        return f"No scouted links in the last {since_hours}h. Paste some Twitter/X links to get started."

    lines = [f"📋 Scout Digest (last {since_hours}h)\n"]

    # Category breakdown
    for cat, n in sorted(counts.items(), key=lambda x: -x[1]):
        emoji = _EMOJI.get(cat, "•")
        label = cat.replace("_", " ")
        lines.append(f"{emoji} {label}: {n}")

    # Top items
    if top_items:
        lines.append("\n🏆 Top finds:")
        for item in top_items:
            score   = item.get("relevance_score", 0)
            summary = item.get("summary") or "(no summary)"
            author  = item.get("author") or "unknown"
            cat     = item.get("category", "")
            emoji   = _EMOJI.get(cat, "•")
            url     = item.get("url", "")
            lines.append(f"{emoji} [{score}/10] @{author}: {summary}")
            lines.append(f"   {url}")

    return "\n".join(lines)


def handle_scout_links(chat_id: str, message_text: str, send_fn) -> None:
    """
    Main entry point, called from _scout_thread in telegram-dispatcher.
    send_fn is the dispatcher's send() — injected to avoid circular import.
    """
    full_urls = [m.group(0) for m in _TWITTER_RE.finditer(message_text)]

    n = len(full_urls)
    link_word = "link" if n == 1 else "links"
    send_fn(chat_id, f"🔍 Scouting {n} {link_word}...")

    batch = tw.process_batch(full_urls)

    for record in batch["results"]:
        db.save_scout_link(
            chat_id,
            record["url"],
            record["extraction"],
            record["categorization"],
        )

    send_fn(chat_id, format_scout_report(batch["results"]))
```

- [ ] **Step 3.4: Run tests**

```bash
cd /Users/nayslayer/openclaw/.claude/worktrees/stupefied-hofstadter/scripts
python -m pytest ../tests/test_clawmson_scout.py -v
```

Expected: All pass. If `handle_scout_links` URL extraction test fails because `_TWITTER_RE.findall` returns tuples (due to capture groups), fix by using `_TWITTER_RE.finditer` consistently (already done in the implementation above).

- [ ] **Step 3.5: Run all tests to confirm nothing broken**

```bash
python -m pytest ../tests/ -v
```

Expected: All pass.

- [ ] **Step 3.6: Commit**

```bash
cd /Users/nayslayer/openclaw/.claude/worktrees/stupefied-hofstadter
git add scripts/clawmson_scout.py tests/test_clawmson_scout.py
git commit -m "feat: add clawmson_scout Telegram UX layer"
```

---

## Task 4: Wire into `telegram-dispatcher.py`

**Files:**
- Modify: `scripts/telegram-dispatcher.py`

No new test file needed — the dispatcher integration is covered by manual smoke test (bot must be running). The unit-testable logic is already tested in Task 3.

- [ ] **Step 4.1: Add import at top of dispatcher imports block**

In `scripts/telegram-dispatcher.py`, find the existing import block (around line 44-48):

```python
import clawmson_db as db
import clawmson_chat as llm
import clawmson_intents as intents
import clawmson_media as media
import clawmson_references as refs
```

Add one line:

```python
import clawmson_scout as scout
```

- [ ] **Step 4.2: Add module-level `_TWITTER_RE` constant**

After the existing `POLL_INTERVAL = 5` line, add:

```python
_TWITTER_RE = re.compile(r'https?://(x\.com|twitter\.com)/\w+/status/\d+')
```

- [ ] **Step 4.3: Add `_scout_thread` function**

After the existing `dispatch_reference_ingest` function (around line 376), add:

```python
def _scout_thread(chat_id: str, text: str):
    """Background thread for Twitter scout pipeline."""
    scout.handle_scout_links(chat_id, text, send)
```

- [ ] **Step 4.4: Add pre-route Twitter check in `handle_message()`**

In `handle_message()`, locate the auth check block (the `if user_id not in ALLOWED_USERS:` block). Immediately after it (before the existing `if text:` shortcut block at line ~414), insert:

```python
    # ── 0. Twitter/X scout pre-route (runs before all other routing) ─────────
    if text and _TWITTER_RE.search(text):
        db.save_message(chat_id, "user", text, message_id=msg_id)
        t = threading.Thread(target=_scout_thread, args=(chat_id, text), daemon=True)
        t.start()
        return
```

- [ ] **Step 4.5: Add `/scout` commands to the slash-commands block**

In `handle_message()`, find the slash-commands block. Locate the `/references` handler:

```python
        if lower == "/references":
            handle_references(chat_id)
            return
```

Immediately after it (before the `/approve` check), insert:

```python
        if lower == "/scout":
            send(chat_id, scout.generate_digest(chat_id))
            return
        if lower == "/scout clear":
            send(chat_id, "Scout queue clear is not yet implemented.")
            return
```

Note: `/scout clear` is a stub requested in the original feature spec. It is intentional — the command is discoverable and fails gracefully now, ready to be wired up later.

- [ ] **Step 4.6: Update `/help` text to mention scout**

In `handle_help()`, find the `/references` line in the help text and add after it:

```python
        "/scout              — digest of recently scouted Twitter links\n"
```

- [ ] **Step 4.7: Smoke test — verify dispatcher starts without errors**

```bash
cd /Users/nayslayer/openclaw/.claude/worktrees/stupefied-hofstadter/scripts
python -c "import telegram-dispatcher" 2>&1 || python -c "
import sys
sys.path.insert(0, '.')
# Just check all imports resolve
import clawmson_db, clawmson_chat, clawmson_intents, clawmson_media, clawmson_references, clawmson_scout, clawmson_twitter
print('All imports OK')
"
```

Expected: `All imports OK`

- [ ] **Step 4.8: Run full test suite**

```bash
cd /Users/nayslayer/openclaw/.claude/worktrees/stupefied-hofstadter/scripts
python -m pytest ../tests/ -v
```

Expected: All pass.

- [ ] **Step 4.9: Commit**

```bash
cd /Users/nayslayer/openclaw/.claude/worktrees/stupefied-hofstadter
git add scripts/telegram-dispatcher.py
git commit -m "feat: wire Twitter scout pre-route and /scout command into dispatcher"
```

---

## Task 5: Final integration check + PR

- [ ] **Step 5.1: Confirm `beautifulsoup4` is installable**

```bash
pip install beautifulsoup4 --dry-run 2>&1 | tail -5
```

Expected: No errors. If already installed, that's fine.

- [ ] **Step 5.2: Run full test suite one final time**

```bash
cd /Users/nayslayer/openclaw/.claude/worktrees/stupefied-hofstadter/scripts
python -m pytest ../tests/ -v --tb=short
```

Expected: All pass, no warnings.

- [ ] **Step 5.3: Verify no existing tests were broken**

Confirm the existing test files (if any) in `tests/` still pass. If there are no pre-existing tests, skip.

- [ ] **Step 5.4: Final commit (if any uncommitted changes)**

```bash
cd /Users/nayslayer/openclaw/.claude/worktrees/stupefied-hofstadter
git status
# If clean, nothing to do. If any files changed, commit them.
```

- [ ] **Step 5.5: Push branch and open PR**

```bash
git push origin claude/stupefied-hofstadter
gh pr create \
  --title "feat: Twitter Scout pipeline for Clawmson" \
  --body "$(cat <<'EOF'
## Summary
- Adds Twitter/X link scouting pipeline to Clawmson
- Extracts tweet content via nitter → fxtwitter → oembed fallback chain
- Categorizes tweets using local qwen2.5:7b via Ollama
- Stores results in new scout_links SQLite table
- Sends immediate 📊 Scout Report after each batch
- Adds /scout command for 24h digest

## Files
- NEW: scripts/clawmson_twitter.py — extraction + categorization engine
- NEW: scripts/clawmson_scout.py — Telegram UX layer
- MOD: scripts/clawmson_db.py — scout_links table + 3 new functions
- MOD: scripts/telegram-dispatcher.py — pre-route + /scout command
- MOD: requirements.txt — adds beautifulsoup4

## Test plan
- [ ] All unit tests pass: pytest tests/ -v
- [ ] Dispatcher starts without import errors
- [ ] Send a real Twitter/X URL in Telegram — confirm scouting acknowledgement and report
- [ ] Send /scout — confirm digest renders with categories and top finds
EOF
)"
```
