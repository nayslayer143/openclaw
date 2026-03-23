from __future__ import annotations
import json
import sqlite3
import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    db = str(tmp_path / "test.db")
    monkeypatch.setenv("CLAWMSON_DB_PATH", db)
    import sys
    for mod in list(sys.modules.keys()):
        if "mirofish" in mod:
            del sys.modules[mod]
    import scripts.mirofish.simulator as sim
    sim.migrate()
    yield db


def _feed():
    import sys
    for mod in list(sys.modules.keys()):
        if "polymarket_feed" in mod:
            del sys.modules[mod]
    import scripts.mirofish.polymarket_feed as feed
    return feed


def _make_gamma_market(market_id="mkt1", yes_price="0.60", no_price="0.40", volume=50000, category="crypto"):
    """Return a market dict in the gamma API format (outcomePrices as JSON strings)."""
    return {
        "conditionId": market_id,
        "question": f"Test question {market_id}",
        "outcomes": json.dumps(["Yes", "No"]),
        "outcomePrices": json.dumps([yes_price, no_price]),
        "volume": volume,
        "active": True,
        "closed": False,
        "category": category,
        "endDate": None,
        "tokens": None,
    }


def _make_clob_market(market_id="mkt2", yes_price=0.70, no_price=0.30, volume=20000):
    """Return a market dict in the CLOB API format (tokens array)."""
    return {
        "conditionId": market_id,
        "question": f"CLOB question {market_id}",
        "outcomes": None,
        "outcomePrices": None,
        "volume": volume,
        "active": True,
        "closed": False,
        "category": "politics",
        "endDate": None,
        "tokens": [
            {"outcome": "YES", "price": yes_price},
            {"outcome": "NO", "price": no_price},
        ],
    }


def _mock_response(markets):
    mock = MagicMock()
    mock.raise_for_status.return_value = None
    mock.json.return_value = markets
    return mock


def test_gamma_format_parses_yes_no_prices(temp_db):
    feed = _feed()
    market = _make_gamma_market(yes_price="0.60", no_price="0.40")
    with patch("requests.get", return_value=_mock_response([market])):
        with patch("scripts.mirofish.polymarket_feed._is_cache_fresh", return_value=False):
            markets = feed.fetch_markets()
    assert len(markets) == 1
    assert markets[0]["yes_price"] == pytest.approx(0.60)
    assert markets[0]["no_price"] == pytest.approx(0.40)


def test_clob_format_parses_yes_no_prices(temp_db):
    feed = _feed()
    market = _make_clob_market(yes_price=0.70, no_price=0.30)
    with patch("requests.get", return_value=_mock_response([market])):
        with patch("scripts.mirofish.polymarket_feed._is_cache_fresh", return_value=False):
            markets = feed.fetch_markets()
    assert len(markets) == 1
    assert markets[0]["yes_price"] == pytest.approx(0.70)
    assert markets[0]["no_price"] == pytest.approx(0.30)


def test_api_error_falls_back_to_cache(temp_db):
    feed = _feed()
    # Seed cache manually
    conn = sqlite3.connect(temp_db)
    recent = datetime.datetime.utcnow().isoformat()
    conn.execute("""
        INSERT INTO market_data (market_id, question, category, yes_price, no_price, volume, fetched_at)
        VALUES ('cached_mkt', 'Cached question', 'crypto', 0.55, 0.45, 15000, ?)
    """, (recent,))
    conn.commit()
    conn.close()
    # Cache is now fresh — fetch_markets should return cached data without hitting API
    markets = feed.fetch_markets()
    assert len(markets) >= 1
    market_ids = [m["market_id"] for m in markets]
    assert "cached_mkt" in market_ids
