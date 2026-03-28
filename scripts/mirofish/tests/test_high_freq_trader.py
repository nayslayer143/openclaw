"""Tests for high_freq_trader — startup, DB cleanup, wallet init."""
import sqlite3
import sys
import os
import datetime

# Ensure project root is importable
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
if _root not in sys.path:
    sys.path.insert(0, _root)

import pytest


def _make_db():
    """Create an in-memory SQLite DB with all required tables."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE paper_trades (
            id INTEGER PRIMARY KEY,
            market_id TEXT, question TEXT, direction TEXT,
            shares REAL, entry_price REAL, exit_price REAL,
            amount_usd REAL, pnl REAL, status TEXT,
            confidence REAL, reasoning TEXT, strategy TEXT,
            opened_at TEXT, closed_at TEXT,
            venue TEXT, expected_edge REAL, binary_outcome TEXT,
            resolved_price REAL, resolution_source TEXT,
            entry_fee REAL, exit_fee REAL
        );
        CREATE TABLE context (
            chat_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT,
            PRIMARY KEY (chat_id, key)
        );
        CREATE TABLE spot_prices (
            id INTEGER PRIMARY KEY,
            source TEXT, ticker TEXT, signal_type TEXT,
            direction TEXT, amount_usd REAL, description TEXT,
            fetched_at TEXT
        );
    """)
    return conn


def test_db_startup_wipes_open_trades():
    from scripts.mirofish.high_freq_trader import db_startup
    conn = _make_db()
    conn.execute(
        "INSERT INTO paper_trades (market_id, question, direction, shares, entry_price, "
        "amount_usd, status, confidence, reasoning, strategy, opened_at) "
        "VALUES ('KX-TEST', 'test?', 'YES', 10, 0.5, 100, 'open', 0.6, '', 'arb', '2026-03-27T00:00:00')"
    )
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM paper_trades WHERE status='open'").fetchone()[0] == 1

    db_startup(conn)

    assert conn.execute("SELECT COUNT(*) FROM paper_trades WHERE status='open'").fetchone()[0] == 0


def test_db_startup_clears_context_noise():
    from scripts.mirofish.high_freq_trader import db_startup
    conn = _make_db()
    for i in range(5):
        conn.execute(
            "INSERT INTO context (chat_id, key, value) VALUES ('mirofish', ?, '1000.00')",
            (f"wallet_reset_2026-03-24T{i:02d}:00:00",)
        )
    conn.commit()
    assert conn.execute(
        "SELECT COUNT(*) FROM context WHERE key LIKE 'wallet_reset_%'"
    ).fetchone()[0] == 5

    db_startup(conn)

    assert conn.execute(
        "SELECT COUNT(*) FROM context WHERE key LIKE 'wallet_reset_%'"
    ).fetchone()[0] == 0


def test_db_startup_sets_10k_balance():
    from scripts.mirofish.high_freq_trader import db_startup
    conn = _make_db()
    db_startup(conn)
    row = conn.execute(
        "SELECT value FROM context WHERE chat_id='mirofish' AND key='starting_balance'"
    ).fetchone()
    assert row is not None
    assert float(row["value"]) == 10000.0


def test_db_startup_adds_index():
    from scripts.mirofish.high_freq_trader import db_startup
    conn = _make_db()
    db_startup(conn)
    idx = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_pt_status_opened'"
    ).fetchone()
    assert idx is not None


def test_get_balance_reads_starting_plus_closed_pnl():
    from scripts.mirofish.high_freq_trader import get_balance
    conn = _make_db()
    conn.execute(
        "INSERT OR REPLACE INTO context (chat_id, key, value) VALUES ('mirofish', 'starting_balance', '10000.00')"
    )
    conn.execute(
        "INSERT INTO paper_trades (market_id, question, direction, shares, entry_price, "
        "amount_usd, pnl, status, confidence, reasoning, strategy, opened_at) "
        "VALUES ('KX-X', 'q', 'YES', 10, 0.5, 100, 250.0, 'closed_win', 1.0, '', 'arb', '2026-03-27T00:00:00')"
    )
    conn.commit()
    assert get_balance(conn) == 10250.0


from unittest.mock import patch, MagicMock


def test_fetch_kalshi_markets_filters_beyond_24h():
    """Markets closing more than 24h from now are excluded."""
    from scripts.mirofish.high_freq_trader import fetch_kalshi_markets

    now = datetime.datetime.utcnow()
    close_soon = (now + datetime.timedelta(hours=1)).isoformat()
    close_far  = (now + datetime.timedelta(hours=48)).isoformat()

    fake_event = {"event_ticker": "KXBTC-TEST"}
    fake_market_soon = {
        "ticker": "KXBTC-NEAR", "event_ticker": "KXBTC-TEST",
        "title": "BTC above $70k?", "category": "crypto",
        "yes_bid_dollars": "0.45", "yes_ask_dollars": "0.47",
        "no_bid_dollars": "0.53", "no_ask_dollars": "0.55",
        "volume_fp": "1000", "close_time": close_soon,
        "strike_type": "greater", "cap_strike": 70000.0,
    }
    fake_market_far = {
        "ticker": "KXBTC-FAR", "event_ticker": "KXBTC-TEST",
        "title": "BTC above $80k?", "category": "crypto",
        "yes_bid_dollars": "0.20", "yes_ask_dollars": "0.22",
        "no_bid_dollars": "0.78", "no_ask_dollars": "0.80",
        "volume_fp": "500", "close_time": close_far,
        "strike_type": "greater", "cap_strike": 80000.0,
    }

    def mock_call_kalshi(method, path, params=None):
        if params and params.get("series_ticker"):
            return {"events": [fake_event]}
        if params and params.get("event_ticker"):
            return {"markets": [fake_market_soon, fake_market_far]}
        return None

    with patch("scripts.mirofish.high_freq_trader._call_kalshi", side_effect=mock_call_kalshi):
        markets = fetch_kalshi_markets()

    tickers = [m["market_id"] for m in markets]
    assert "KXBTC-NEAR" in tickers
    assert "KXBTC-FAR" not in tickers


def test_fetch_kalshi_markets_normalizes_prices():
    """yes_price and no_price are 0-1 decimals after dividing by 100."""
    from scripts.mirofish.high_freq_trader import fetch_kalshi_markets

    now = datetime.datetime.utcnow()
    close_soon = (now + datetime.timedelta(hours=2)).isoformat()

    fake_event = {"event_ticker": "KXBTC-TEST"}
    fake_market = {
        "ticker": "KXBTC-NORM", "event_ticker": "KXBTC-TEST",
        "title": "BTC above $70k?", "category": "crypto",
        "yes_bid_dollars": "0.40", "yes_ask_dollars": "0.44",
        "no_bid_dollars": "0.56", "no_ask_dollars": "0.60",
        "volume_fp": "2000", "close_time": close_soon,
        "strike_type": "greater", "cap_strike": 70000.0,
    }

    def mock_call_kalshi(method, path, params=None):
        if params and params.get("series_ticker"):
            return {"events": [fake_event]}
        if params and params.get("event_ticker"):
            return {"markets": [fake_market]}
        return None

    with patch("scripts.mirofish.high_freq_trader._call_kalshi", side_effect=mock_call_kalshi):
        markets = fetch_kalshi_markets()

    assert len(markets) == 1
    m = markets[0]
    assert m["venue"] == "kalshi"
    assert 0.0 < m["yes_price"] < 1.0
    assert 0.0 < m["no_price"] < 1.0
    assert m["yes_bid"] < m["yes_ask"]


def test_fetch_kalshi_markets_handles_z_suffix_timestamps():
    """Markets with Z-suffix close_time are correctly filtered."""
    from scripts.mirofish.high_freq_trader import fetch_kalshi_markets

    now = datetime.datetime.utcnow()
    # A market closing in 1 hour, using Z-suffix timestamp (Kalshi API format)
    close_soon_z = (now + datetime.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

    fake_event = {"event_ticker": "KXBTC-ZTEST"}
    fake_market = {
        "ticker": "KXBTC-ZCLOSE", "event_ticker": "KXBTC-ZTEST",
        "title": "BTC above $70k?", "category": "crypto",
        "yes_bid_dollars": "0.45", "yes_ask_dollars": "0.47",
        "no_bid_dollars": "0.53", "no_ask_dollars": "0.55",
        "volume_fp": "1000", "close_time": close_soon_z,
        "strike_type": "greater", "cap_strike": 70000.0,
    }

    def mock_call_kalshi(method, path, params=None):
        if params and params.get("series_ticker"):
            return {"events": [fake_event]}
        if params and params.get("event_ticker"):
            return {"markets": [fake_market]}
        return None

    with patch("scripts.mirofish.high_freq_trader._call_kalshi", side_effect=mock_call_kalshi):
        markets = fetch_kalshi_markets()

    # Should be included (closes in 1 hour, well within 24h window)
    assert any(m["market_id"] == "KXBTC-ZCLOSE" for m in markets)


def test_fetch_polymarket_markets_filters_beyond_24h():
    """Polymarket markets closing > 24h from now are excluded."""
    from scripts.mirofish.high_freq_trader import fetch_polymarket_markets

    now = datetime.datetime.utcnow()
    close_soon = (now + datetime.timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
    close_far  = (now + datetime.timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")

    fake_response = [
        {
            "conditionId": "0xabc", "question": "Will it rain?",
            "category": "weather", "volume": "5000",
            "endDate": close_soon, "active": True, "closed": False,
            "outcomePrices": ["0.65", "0.35"], "outcomes": ["Yes", "No"],
        },
        {
            "conditionId": "0xdef", "question": "Election winner?",
            "category": "politics", "volume": "50000",
            "endDate": close_far, "active": True, "closed": False,
            "outcomePrices": ["0.55", "0.45"], "outcomes": ["Yes", "No"],
        },
    ]

    with patch("scripts.mirofish.high_freq_trader.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = fake_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        markets = fetch_polymarket_markets()

    ids = [m["market_id"] for m in markets]
    assert "0xabc" in ids
    assert "0xdef" not in ids


def test_fetch_polymarket_markets_normalizes_fields():
    """Polymarket markets have correct venue and price fields."""
    from scripts.mirofish.high_freq_trader import fetch_polymarket_markets

    now = datetime.datetime.utcnow()
    close_soon = (now + datetime.timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")

    fake_response = [{
        "conditionId": "0x123", "question": "BTC above $70k today?",
        "category": "crypto", "volume": "20000",
        "endDate": close_soon, "active": True, "closed": False,
        "outcomePrices": ["0.72", "0.28"], "outcomes": ["Yes", "No"],
    }]

    with patch("scripts.mirofish.high_freq_trader.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = fake_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        markets = fetch_polymarket_markets()

    assert len(markets) == 1
    m = markets[0]
    assert m["venue"] == "polymarket"
    assert abs(m["yes_price"] - 0.72) < 0.001
    assert abs(m["no_price"] - 0.28) < 0.001
    assert m["event_ticker"] == "0x123"[:20]
