from __future__ import annotations

import sqlite3
import datetime
from unittest.mock import patch, MagicMock
import pytest


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    db = str(tmp_path / "test.db")
    monkeypatch.setenv("CLAWMSON_DB_PATH", db)
    monkeypatch.setenv("KALSHI_API_KEY_ID", "test-key-id")
    monkeypatch.setenv("KALSHI_PRIVATE_KEY_PATH", "")  # will mock auth
    monkeypatch.setenv("KALSHI_API_ENV", "demo")
    # Clear cached modules so env vars take effect
    import sys
    for mod in list(sys.modules.keys()):
        if "mirofish" in mod:
            del sys.modules[mod]
    # Create the table
    conn = sqlite3.connect(db)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS kalshi_markets (
            ticker        TEXT NOT NULL,
            event_ticker  TEXT,
            title         TEXT,
            category      TEXT,
            yes_bid       REAL,
            yes_ask       REAL,
            no_bid        REAL,
            no_ask        REAL,
            last_price    REAL,
            volume        REAL,
            volume_24h    REAL,
            open_interest REAL,
            status        TEXT,
            close_time    TEXT,
            rules_primary TEXT,
            strike_type   TEXT,
            cap_strike    REAL,
            floor_strike  REAL,
            fetched_at    TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    yield db


def _feed():
    import sys
    for mod in list(sys.modules.keys()):
        if "kalshi_feed" in mod:
            del sys.modules[mod]
    import scripts.mirofish.kalshi_feed as feed
    return feed


def _make_kalshi_market(
    ticker="KXBTC-26JUN30-T149999",
    event_ticker="KXBTC-26JUN30",
    title="Bitcoin above $150,000?",
    yes_bid=42,
    yes_ask=44,
    no_bid=56,
    no_ask=58,
    last_price=43,
    volume=12345,
    volume_24h=567,
    open_interest=8901,
    category="Crypto",
    status="open",
    strike_type="greater",
    cap_strike=150000,
):
    return {
        "ticker": ticker,
        "event_ticker": event_ticker,
        "title": title,
        "yes_bid": yes_bid,
        "yes_ask": yes_ask,
        "no_bid": no_bid,
        "no_ask": no_ask,
        "last_price": last_price,
        "volume": volume,
        "volume_24h": volume_24h,
        "open_interest": open_interest,
        "status": status,
        "category": category,
        "close_time": "2026-06-30T00:00:00Z",
        "rules_primary": "Resolves Yes if BTC > $150k",
        "rules_secondary": "",
        "strike_type": strike_type,
        "cap_strike": cap_strike,
        "floor_strike": None,
        "result": "",
    }


def _mock_api_response(markets, cursor=None):
    return {"markets": markets, "cursor": cursor or ""}


def _mock_auth_headers(method, path):
    """Bypass RSA auth for tests."""
    return {
        "KALSHI-ACCESS-KEY": "test-key",
        "KALSHI-ACCESS-TIMESTAMP": "1234567890000",
        "KALSHI-ACCESS-SIGNATURE": "dGVzdA==",
        "Content-Type": "application/json",
    }


def _mock_requests_get(*args, **kwargs):
    mock = MagicMock()
    mock.status_code = 200
    mock.raise_for_status.return_value = None
    mock.json.return_value = _mock_api_response([_make_kalshi_market()])
    return mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_fetch_parses_markets(temp_db):
    feed = _feed()
    with patch.object(feed, "_auth_headers", side_effect=_mock_auth_headers):
        with patch.object(feed, "_is_cache_fresh", return_value=False):
            with patch("requests.request", side_effect=_mock_requests_get):
                markets = feed.fetch()

    assert len(markets) == 1
    m = markets[0]
    assert m["market_id"] == "KXBTC-26JUN30-T149999"
    assert m["venue"] == "kalshi"
    assert m["yes_bid"] == pytest.approx(0.42)
    assert m["yes_ask"] == pytest.approx(0.44)
    assert m["no_bid"] == pytest.approx(0.56)
    assert m["volume_24h"] == 567


def test_fetch_caches_to_db(temp_db):
    feed = _feed()
    with patch.object(feed, "_auth_headers", side_effect=_mock_auth_headers):
        with patch.object(feed, "_is_cache_fresh", return_value=False):
            with patch("requests.request", side_effect=_mock_requests_get):
                feed.fetch()

    conn = sqlite3.connect(temp_db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM kalshi_markets").fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0]["ticker"] == "KXBTC-26JUN30-T149999"


def test_fresh_cache_skips_api(temp_db):
    feed = _feed()
    # Seed cache
    conn = sqlite3.connect(temp_db)
    recent = datetime.datetime.utcnow().isoformat()
    conn.execute("""
        INSERT INTO kalshi_markets
        (ticker, event_ticker, title, category, yes_bid, yes_ask, no_bid, no_ask,
         last_price, volume, volume_24h, open_interest, status, close_time,
         rules_primary, strike_type, cap_strike, floor_strike, fetched_at)
        VALUES ('CACHED-MKT', 'CACHED', 'Cached market', 'crypto', 0.50, 0.52,
                0.48, 0.50, 0.51, 1000, 100, 500, 'open', '', '', '', NULL, NULL, ?)
    """, (recent,))
    conn.commit()
    conn.close()

    with patch.object(feed, "_auth_headers", side_effect=_mock_auth_headers):
        # Don't mock _is_cache_fresh — let it check real DB
        markets = feed.fetch()

    assert len(markets) >= 1
    ids = [m["market_id"] for m in markets]
    assert "CACHED-MKT" in ids


def test_no_credentials_returns_empty(temp_db, monkeypatch):
    monkeypatch.setenv("KALSHI_API_KEY_ID", "")
    feed = _feed()
    markets = feed.fetch()
    assert markets == []


def test_api_error_falls_back_to_cache(temp_db):
    feed = _feed()
    # Seed cache
    conn = sqlite3.connect(temp_db)
    recent = datetime.datetime.utcnow().isoformat()
    conn.execute("""
        INSERT INTO kalshi_markets
        (ticker, event_ticker, title, category, yes_bid, yes_ask, no_bid, no_ask,
         last_price, volume, volume_24h, open_interest, status, close_time,
         rules_primary, strike_type, cap_strike, floor_strike, fetched_at)
        VALUES ('FALLBACK', 'FB', 'Fallback market', 'crypto', 0.60, 0.62,
                0.38, 0.40, 0.61, 2000, 200, 1000, 'open', '', '', '', NULL, NULL, ?)
    """, (recent,))
    conn.commit()
    conn.close()

    def _failing_request(*args, **kwargs):
        raise ConnectionError("API down")

    with patch.object(feed, "_auth_headers", side_effect=_mock_auth_headers):
        with patch.object(feed, "_is_cache_fresh", return_value=False):
            with patch("requests.request", side_effect=_failing_request):
                markets = feed.fetch()

    ids = [m["market_id"] for m in markets]
    assert "FALLBACK" in ids


def test_cents_to_float():
    feed = _feed()
    assert feed._cents_to_float(42) == pytest.approx(0.42)
    assert feed._cents_to_float(99) == pytest.approx(0.99)
    assert feed._cents_to_float(0) == pytest.approx(0.0)
    assert feed._cents_to_float(None) is None


def test_category_filter(temp_db):
    feed = _feed()
    crypto = _make_kalshi_market(ticker="CRYPTO-1", category="Crypto")
    politics = _make_kalshi_market(ticker="POL-1", category="Politics")

    def _multi_market_response(*args, **kwargs):
        mock = MagicMock()
        mock.status_code = 200
        mock.raise_for_status.return_value = None
        mock.json.return_value = _mock_api_response([crypto, politics])
        return mock

    with patch.object(feed, "_auth_headers", side_effect=_mock_auth_headers):
        with patch.object(feed, "_is_cache_fresh", return_value=False):
            with patch("requests.request", side_effect=_multi_market_response):
                markets = feed.fetch(categories=["crypto"])

    assert all(m["category"] == "crypto" for m in markets)


def test_get_latest_prices(temp_db):
    feed = _feed()
    conn = sqlite3.connect(temp_db)
    recent = datetime.datetime.utcnow().isoformat()
    conn.execute("""
        INSERT INTO kalshi_markets
        (ticker, event_ticker, title, category, yes_bid, yes_ask, no_bid, no_ask,
         last_price, volume, volume_24h, open_interest, status, close_time,
         rules_primary, strike_type, cap_strike, floor_strike, fetched_at)
        VALUES ('PRICE-MKT', 'PM', 'Price market', 'crypto', 0.55, 0.57,
                0.43, 0.45, 0.56, 3000, 300, 1500, 'open', '', '', '', NULL, NULL, ?)
    """, (recent,))
    conn.commit()
    conn.close()

    prices = feed.get_latest_prices()
    assert "PRICE-MKT" in prices
    assert prices["PRICE-MKT"]["yes_bid"] == pytest.approx(0.55)


def test_market_event_normalization():
    """Test that Kalshi raw data normalizes to a valid MarketEvent."""
    from scripts.mirofish.market_event import MarketEventNormalizer, MarketEvent

    raw = _make_kalshi_market()
    event = MarketEventNormalizer.normalize_kalshi(raw)

    assert isinstance(event, MarketEvent)
    assert event.venue == "kalshi"
    assert event.market_id == "KXBTC-26JUN30-T149999"
    assert event.status == "open"
    assert event.contract.contract_type == "threshold"
    assert event.contract.upper_bound == 150000
    assert len(event.outcomes) == 2
    assert event.outcomes[0].outcome == "YES"
    assert event.outcomes[0].bid == pytest.approx(0.42)

    # Round-trip
    d = event.to_dict()
    event2 = MarketEvent.from_dict(d)
    assert event.market_id == event2.market_id
    assert event.outcomes[0].bid == event2.outcomes[0].bid


def test_resolved_market_status():
    """Markets with a result field should have status 'resolved'."""
    from scripts.mirofish.market_event import MarketEventNormalizer

    raw = _make_kalshi_market(status="closed")
    raw["result"] = "yes"
    event = MarketEventNormalizer.normalize_kalshi(raw)
    assert event.status == "resolved"


def test_bracket_contract_type():
    """Markets with strike_type='between' should be 'bracket' contracts."""
    from scripts.mirofish.market_event import MarketEventNormalizer

    raw = _make_kalshi_market(strike_type="between", cap_strike=160000)
    raw["floor_strike"] = 140000
    event = MarketEventNormalizer.normalize_kalshi(raw)
    assert event.contract.contract_type == "bracket"
    assert event.contract.lower_bound == 140000
    assert event.contract.upper_bound == 160000
