import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, call

os.environ.setdefault("CLAWMSON_DB_PATH", tempfile.mkstemp(suffix=".db")[1])
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
