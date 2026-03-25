"""Basic validation tests for the Instagram crawler."""
import sys
import json
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add parent dir to path so we can import modules
sys.path.insert(0, str(Path(__file__).parent.parent))

import signals as sig


class TestTickerExtraction(unittest.TestCase):
    """Test $CASHTAG extraction from Instagram captions."""

    def test_basic_tickers(self):
        text = "I'm buying $AAPL and $TSLA today #investing"
        result = sig.extract_tickers(text)
        self.assertIn("AAPL", result)
        self.assertIn("TSLA", result)

    def test_crypto_tickers(self):
        text = "$BTC.X to the moon! Also watching $ETH.X #crypto"
        result = sig.extract_tickers(text)
        self.assertIn("BTC.X", result)
        self.assertIn("ETH.X", result)

    def test_blacklisted_tickers_filtered(self):
        text = "$I think $CEO is doing $DD on this $IG post"
        result = sig.extract_tickers(text)
        self.assertNotIn("I", result)
        self.assertNotIn("CEO", result)
        self.assertNotIn("DD", result)
        self.assertNotIn("IG", result)

    def test_no_tickers(self):
        text = "Just a regular post with no ticker symbols #finance"
        result = sig.extract_tickers(text)
        self.assertEqual(result, [])

    def test_empty_text(self):
        self.assertEqual(sig.extract_tickers(""), [])
        self.assertEqual(sig.extract_tickers(None), [])

    def test_deduplication(self):
        text = "$AAPL is great, $AAPL all the way #stocks"
        result = sig.extract_tickers(text)
        self.assertEqual(result.count("AAPL"), 1)


class TestSentimentScoring(unittest.TestCase):
    """Test sentiment analysis with keyword scoring."""

    def test_keyword_bullish(self):
        text = "This is going to moon! Bullish, buying calls, rocket! #crypto"
        direction, conf = sig.score_sentiment(text)
        self.assertEqual(direction, "bullish")
        self.assertGreater(conf, 0.5)

    def test_keyword_bearish(self):
        text = "Crash incoming, dump it, this is a rug pull for sure #bitcoin"
        direction, conf = sig.score_sentiment(text)
        self.assertEqual(direction, "bearish")
        self.assertGreater(conf, 0.5)

    def test_neutral_text(self):
        text = "The market moved a bit today, not sure what to think"
        direction, conf = sig.score_sentiment(text)
        self.assertIn(direction, ["neutral", "unknown"])

    def test_empty_text(self):
        direction, conf = sig.score_sentiment("")
        self.assertEqual(direction, "unknown")
        self.assertEqual(conf, 0.0)

    def test_confidence_bounded(self):
        text = " ".join(["bullish moon rocket pump calls"] * 20)
        _, conf = sig.score_sentiment(text)
        self.assertLessEqual(conf, 1.0)
        self.assertGreaterEqual(conf, 0.0)


class TestContentClassification(unittest.TestCase):
    """Test content type classification."""

    def test_educational(self):
        text = "Learn how to read charts! This tutorial explains RSI strategy"
        result = sig.classify_content(text)
        self.assertEqual(result, "educational")

    def test_hype(self):
        text = "100x gem don't miss this rocket to the moon lambo incoming"
        result = sig.classify_content(text)
        self.assertEqual(result, "hype")

    def test_news(self):
        text = "Breaking: SEC just approved the new ETF listing announcement"
        result = sig.classify_content(text)
        self.assertEqual(result, "news")

    def test_analysis(self):
        text = "Chart shows strong support at resistance level RSI divergence MACD crossover"
        result = sig.classify_content(text)
        self.assertEqual(result, "analysis")

    def test_general_fallback(self):
        text = "Beautiful day to check the portfolio"
        result = sig.classify_content(text)
        self.assertEqual(result, "general")

    def test_empty_text(self):
        self.assertEqual(sig.classify_content(""), "unknown")
        self.assertEqual(sig.classify_content(None), "unknown")


class TestUrgencyDetection(unittest.TestCase):
    """Test urgency classification."""

    def test_realtime(self):
        self.assertEqual(sig.detect_urgency("breaking news just now"), "realtime")

    def test_hours(self):
        self.assertEqual(sig.detect_urgency("expiry today 0dte"), "hours")

    def test_default_days(self):
        self.assertEqual(sig.detect_urgency("looking at this stock"), "days")

    def test_empty(self):
        self.assertEqual(sig.detect_urgency(""), "days")


class TestSignalBuilding(unittest.TestCase):
    """Test full signal construction from Instagram post dicts."""

    def test_build_signal_structure(self):
        post = {
            "id": "CxYz12345",
            "caption": "$AAPL calls are printing, bullish AF #investing #stocks",
            "author": "finfluencer123",
            "likes": 1500,
            "comments": 200,
            "media_type": "carousel",
            "url": "https://www.instagram.com/p/CxYz12345/",
            "timestamp": "2026-03-24T12:00:00Z",
            "author_followers": 50000,
        }
        signal = sig.build_signal(post, hashtag="investing")
        # Check required fields exist
        self.assertIn("id", signal)
        self.assertIn("type", signal)
        self.assertIn("source_url", signal)
        self.assertIn("direction", signal)
        self.assertIn("confidence", signal)
        self.assertIn("urgency", signal)
        self.assertIn("engagement", signal)
        self.assertIn("tags", signal)
        self.assertIn("extracted_at", signal)
        # Check values
        self.assertEqual(signal["source_author"], "finfluencer123")
        self.assertEqual(signal["engagement"]["upvotes"], 1500)
        self.assertEqual(signal["engagement"]["comments"], 200)
        self.assertEqual(signal["direction"], "bullish")
        self.assertIn("AAPL", signal["ticker_or_market"])
        # Check raw_data has content_type
        self.assertIn("content_type", signal["raw_data"])

    def test_hashtag_as_ticker_fallback(self):
        """If no $CASHTAG, use the hashtag as ticker_or_market."""
        post = {
            "id": "abc999",
            "caption": "Great market moves today! #crypto",
            "author": "someone",
            "likes": 10,
            "comments": 2,
        }
        signal = sig.build_signal(post, hashtag="crypto")
        self.assertEqual(signal["ticker_or_market"], "crypto")

    def test_signal_id_deterministic(self):
        id1 = sig.make_signal_id("instagram", "CxYz12345")
        id2 = sig.make_signal_id("instagram", "CxYz12345")
        self.assertEqual(id1, id2)

    def test_signal_id_unique(self):
        id1 = sig.make_signal_id("instagram", "CxYz12345")
        id2 = sig.make_signal_id("instagram", "AbCd67890")
        self.assertNotEqual(id1, id2)

    def test_high_engagement_confidence_boost(self):
        post = {
            "id": "viral_post",
            "caption": "neutral message about the market",
            "author": "bigaccount",
            "likes": 5000,
            "comments": 500,
        }
        signal = sig.build_signal(post)
        # engagement >= 1000 should boost confidence by 0.1
        self.assertGreaterEqual(signal["confidence"], 0.2)

    def test_medium_engagement_confidence_boost(self):
        post = {
            "id": "mid_post",
            "caption": "bullish on the market, buying calls",
            "author": "midaccount",
            "likes": 80,
            "comments": 30,
        }
        signal = sig.build_signal(post)
        # engagement >= 100 should boost confidence by 0.05
        base_dir, base_conf = sig.score_sentiment(post["caption"])
        self.assertGreaterEqual(signal["confidence"], base_conf)


class TestAggregation(unittest.TestCase):
    """Test hashtag sentiment aggregation."""

    def test_aggregate_basic(self):
        signals_list = [
            {"ticker_or_market": "crypto", "direction": "bullish",
             "confidence": 0.8, "engagement": {"upvotes": 50, "comments": 10}},
            {"ticker_or_market": "crypto", "direction": "bearish",
             "confidence": 0.6, "engagement": {"upvotes": 20, "comments": 5}},
            {"ticker_or_market": "crypto", "direction": "bullish",
             "confidence": 0.7, "engagement": {"upvotes": 100, "comments": 20}},
        ]
        agg = sig.aggregate_hashtag_sentiment(signals_list)
        self.assertIn("crypto", agg)
        self.assertEqual(agg["crypto"]["bullish"], 2)
        self.assertEqual(agg["crypto"]["bearish"], 1)
        self.assertEqual(agg["crypto"]["total"], 3)
        self.assertEqual(agg["crypto"]["total_likes"], 170)
        self.assertEqual(agg["crypto"]["total_comments"], 35)
        self.assertEqual(agg["crypto"]["bull_bear_ratio"], 2.0)

    def test_aggregate_empty(self):
        self.assertEqual(sig.aggregate_hashtag_sentiment([]), {})

    def test_aggregate_no_tickers(self):
        signals_list = [{"ticker_or_market": "", "direction": "bullish"}]
        self.assertEqual(sig.aggregate_hashtag_sentiment(signals_list), {})


class TestVelocity(unittest.TestCase):
    """Test post velocity calculation."""

    def test_velocity_counts(self):
        signals_list = [
            {"ticker_or_market": "crypto"},
            {"ticker_or_market": "crypto"},
            {"ticker_or_market": "bitcoin"},
        ]
        counts = sig.compute_velocity(signals_list)
        self.assertEqual(counts["crypto"], 2)
        self.assertEqual(counts["bitcoin"], 1)

    def test_velocity_empty(self):
        self.assertEqual(sig.compute_velocity([]), {})


class TestTags(unittest.TestCase):
    """Test tag building."""

    def test_crypto_hashtag_tag(self):
        tags = sig._build_tags("crypto", ["BTC.X"], "hype")
        self.assertIn("instagram", tags)
        self.assertIn("#crypto", tags)
        self.assertIn("crypto", tags)
        self.assertIn("hype", tags)
        self.assertIn("$BTC.X", tags)

    def test_stock_tag(self):
        tags = sig._build_tags("investing", ["AAPL"], "analysis")
        self.assertIn("instagram", tags)
        self.assertIn("#investing", tags)
        self.assertIn("analysis", tags)
        self.assertIn("$AAPL", tags)
        self.assertNotIn("crypto", tags)

    def test_empty_hashtag(self):
        tags = sig._build_tags("", [], "general")
        self.assertIn("instagram", tags)
        self.assertNotIn("general", tags)  # "general" and "unknown" are filtered out


class TestConfigImport(unittest.TestCase):
    """Test that config module loads without error."""

    def test_import_config(self):
        import config
        self.assertEqual(config.PLATFORM, "instagram")
        self.assertIsInstance(config.HASHTAGS, list)
        self.assertGreater(len(config.HASHTAGS), 0)

    def test_intervals_positive(self):
        import config
        self.assertGreater(config.HASHTAG_INTERVAL_SEC, 0)
        self.assertGreater(config.PROFILE_INTERVAL_SEC, 0)

    def test_rate_limits(self):
        import config
        self.assertGreaterEqual(config.REQUEST_DELAY_MIN, 3.0)
        self.assertGreaterEqual(config.REQUEST_DELAY_MAX, config.REQUEST_DELAY_MIN)

    def test_influencers_list(self):
        import config
        self.assertIsInstance(config.INFLUENCERS, list)
        self.assertGreater(len(config.INFLUENCERS), 0)


class TestStorageInit(unittest.TestCase):
    """Test storage module initialization."""

    def test_import_storage(self):
        import storage
        self.assertTrue(hasattr(storage, "init"))
        self.assertTrue(hasattr(storage, "write_signals"))
        self.assertTrue(hasattr(storage, "cleanup"))


class TestHTMLParsing(unittest.TestCase):
    """Test HTML parsing with mock HTML structures."""

    def test_parse_empty_html(self):
        from crawler import _parse_hashtag_html
        result = _parse_hashtag_html("", hashtag="crypto")
        self.assertEqual(result, [])

    def test_parse_minimal_html(self):
        from crawler import _parse_hashtag_html
        html = "<html><body><p>No posts here</p></body></html>"
        result = _parse_hashtag_html(html, hashtag="crypto")
        self.assertIsInstance(result, list)

    def test_parse_shared_data(self):
        from crawler import _parse_hashtag_html
        shared_data = {
            "entry_data": {
                "TagPage": [{
                    "graphql": {
                        "hashtag": {
                            "edge_hashtag_to_media": {
                                "edges": [{
                                    "node": {
                                        "shortcode": "CxYz12345",
                                        "edge_media_to_caption": {
                                            "edges": [{"node": {"text": "$BTC to the moon!"}}]
                                        },
                                        "edge_liked_by": {"count": 500},
                                        "edge_media_to_comment": {"count": 50},
                                        "__typename": "GraphImage",
                                        "taken_at_timestamp": 1711288800,
                                        "owner": {"username": "cryptotrader"}
                                    }
                                }]
                            }
                        }
                    }
                }]
            }
        }
        html = f"""
        <html><body>
        <script>
            window._sharedData = {json.dumps(shared_data)};
        </script>
        </body></html>
        """
        result = _parse_hashtag_html(html, hashtag="crypto")
        self.assertGreater(len(result), 0)
        self.assertEqual(result[0]["id"], "CxYz12345")
        self.assertIn("BTC", result[0]["caption"])
        self.assertEqual(result[0]["likes"], 500)
        self.assertEqual(result[0]["comments"], 50)

    def test_parse_post_links(self):
        from crawler import _parse_hashtag_html
        html = """
        <html><body>
        <meta property="og:description" content="1.2M posts - Explore #crypto" />
        <a href="/p/AbCd67890/"><img alt="Great crypto content" /></a>
        <a href="/p/EfGh11111/"><img alt="More crypto" /></a>
        </body></html>
        """
        result = _parse_hashtag_html(html, hashtag="crypto")
        self.assertGreater(len(result), 0)
        ids = [p["id"] for p in result]
        self.assertIn("AbCd67890", ids)

    def test_parse_count_helper(self):
        from crawler import _parse_count
        self.assertEqual(_parse_count("1,234"), 1234)
        self.assertEqual(_parse_count("1.2K"), 1200)
        self.assertEqual(_parse_count("3.5M"), 3500000)
        self.assertEqual(_parse_count("45.3k"), 45300)
        self.assertEqual(_parse_count("invalid"), 0)

    def test_parse_profile_meta(self):
        from crawler import _parse_profile_html
        html = """
        <html><body>
        <meta property="og:description" content="50.2K Followers, 500 Posts - See Instagram photos" />
        <a href="/p/ProfilePost1/"></a>
        </body></html>
        """
        posts, info = _parse_profile_html(html, "testuser")
        self.assertEqual(info["username"], "testuser")
        self.assertEqual(info["followers"], 50200)


class TestGraphAPIHelpers(unittest.TestCase):
    """Test Graph API mode detection."""

    def test_has_api_token_false(self):
        from crawler import _has_api_token
        import config
        original = config.INSTAGRAM_ACCESS_TOKEN
        config.INSTAGRAM_ACCESS_TOKEN = ""
        self.assertFalse(_has_api_token())
        config.INSTAGRAM_ACCESS_TOKEN = original

    def test_has_api_token_true(self):
        from crawler import _has_api_token
        import config
        original = config.INSTAGRAM_ACCESS_TOKEN
        config.INSTAGRAM_ACCESS_TOKEN = "test_token_123"
        self.assertTrue(_has_api_token())
        config.INSTAGRAM_ACCESS_TOKEN = original


if __name__ == "__main__":
    unittest.main()
