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
