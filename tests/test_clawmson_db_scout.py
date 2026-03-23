import os
import json
import tempfile
import pytest

# Point DB at a temp file so tests don't touch production DB
os.environ["CLAWMSON_DB_PATH"] = tempfile.mkstemp(suffix=".db")[1]

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


@pytest.fixture(autouse=True)
def clean_db():
    """Clear scout_links table before each test for isolation."""
    import sqlite3
    from pathlib import Path
    db_path = Path(os.environ["CLAWMSON_DB_PATH"])
    if db_path.exists():
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute("DELETE FROM scout_links")
    yield


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
