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


def _make_kalshi_market(yes_price=0.45, no_price=0.57, strike=70000.0, strike_type="greater",
                        ticker="KXBTC-T", event="KXBTC-E"):
    return {
        "market_id": ticker, "question": "BTC above $70k?", "venue": "kalshi",
        "yes_price": yes_price, "no_price": no_price,
        "yes_bid": yes_price - 0.02, "yes_ask": yes_price + 0.02,
        "event_ticker": event, "close_time": "2099-01-01T00:00:00",
        "category": "crypto", "cap_strike": strike, "strike_type": strike_type,
    }


def _make_poly_market(yes_price=0.65, no_price=0.35, mid="0xABC", question="Will it rain?"):
    return {
        "market_id": mid, "question": question, "venue": "polymarket",
        "yes_price": yes_price, "no_price": no_price,
        "yes_bid": yes_price, "yes_ask": yes_price,
        "event_ticker": mid[:20], "close_time": "2099-01-01T00:00:00",
        "category": "weather", "cap_strike": None, "strike_type": "",
    }


def test_score_market_arb_kalshi_detects_gap():
    """arb strategy fires when yes+no > 1 + MIN_EDGE_KALSHI_ARB on Kalshi."""
    from scripts.mirofish.high_freq_trader import score_market
    # yes=0.45, no=0.57 → sum=1.02, gap=0.02 >= MIN_EDGE_KALSHI_ARB=0.02
    m = _make_kalshi_market(yes_price=0.45, no_price=0.57)
    sig = score_market(m, spot_prices={}, open_ids=set(), events_traded=set(), weights={})
    assert sig is not None
    assert sig.strategy == "arb"
    assert sig.venue == "kalshi"


def test_score_market_arb_polymarket_lower_threshold():
    """arb strategy fires at lower edge threshold on Polymarket (MIN_EDGE_POLY=0.003)."""
    from scripts.mirofish.high_freq_trader import score_market
    # yes=0.48, no=0.53 → gap=0.01, above MIN_EDGE_POLY=0.003
    m = _make_poly_market(yes_price=0.48, no_price=0.53)
    sig = score_market(m, spot_prices={}, open_ids=set(), events_traded=set(), weights={})
    assert sig is not None
    assert sig.strategy == "arb"
    assert sig.venue == "polymarket"


def test_score_market_skips_already_open():
    """Returns None if market_id is already in open_ids."""
    from scripts.mirofish.high_freq_trader import score_market
    m = _make_kalshi_market(yes_price=0.45, no_price=0.57)
    sig = score_market(m, spot_prices={}, open_ids={"KXBTC-T"}, events_traded=set(), weights={})
    assert sig is None


def test_score_market_skips_duplicate_event():
    """Returns None if event_ticker already traded this cycle."""
    from scripts.mirofish.high_freq_trader import score_market
    m = _make_kalshi_market(yes_price=0.45, no_price=0.57)
    sig = score_market(m, spot_prices={}, open_ids=set(), events_traded={"KXBTC-E"}, weights={})
    assert sig is None


def test_score_market_spot_lag_yes_when_spot_above_strike():
    """spot_lag fires YES when spot clearly above strike (>MIN_EDGE_KALSHI_SPOT away)."""
    from scripts.mirofish.high_freq_trader import score_market
    # BTC spot=75000, strike=70000 → dist=0.0714 > 0.025 → YES
    m = _make_kalshi_market(yes_price=0.45, no_price=0.53, strike=70000.0, strike_type="greater")
    sig = score_market(
        m, spot_prices={"BTC": 75000.0},
        open_ids=set(), events_traded=set(), weights={}
    )
    assert sig is not None
    assert sig.direction == "YES"
    assert sig.strategy == "spot_lag"


def test_score_market_mean_reversion_poly():
    """mean_reversion fires on Polymarket when YES >= 0.85 (fade it, bet NO)."""
    from scripts.mirofish.high_freq_trader import score_market
    m = _make_poly_market(yes_price=0.92, no_price=0.08)
    sig = score_market(m, spot_prices={}, open_ids=set(), events_traded=set(), weights={})
    assert sig is not None
    assert sig.direction == "NO"
    assert sig.strategy == "mean_reversion"


def test_score_market_no_edge_returns_none():
    """Returns None when no strategy finds sufficient edge."""
    from scripts.mirofish.high_freq_trader import score_market
    m = _make_poly_market(yes_price=0.50, no_price=0.50)
    sig = score_market(m, spot_prices={}, open_ids=set(), events_traded=set(), weights={})
    assert sig is None


def test_place_trade_inserts_to_db():
    from scripts.mirofish.high_freq_trader import place_trade, TradeSignal
    import pytest
    conn = _make_db()
    conn.execute("INSERT OR REPLACE INTO context (chat_id, key, value) VALUES ('mirofish', 'starting_balance', '10000.00')")
    conn.commit()
    sig = TradeSignal(
        market_id="KXBTC-TEST", question="BTC above $70k?", venue="kalshi",
        direction="YES", edge=0.05, strategy="arb",
        entry_price=0.45, amount_usd=300.0, shares=666.0, fee=9.45,
    )
    trade_id = place_trade(conn, sig, balance=10000.0)
    assert trade_id is not None
    row = conn.execute("SELECT * FROM paper_trades WHERE id=?", (trade_id,)).fetchone()
    assert row["market_id"] == "KXBTC-TEST"
    assert row["direction"] == "YES"
    assert row["status"] == "open"
    assert row["venue"] == "kalshi"
    assert abs(row["entry_fee"] - 9.45) < 0.01
    assert row["strategy"] == "arb"
    assert abs(row["expected_edge"] - 0.05) < 0.001

def test_place_trade_skips_zero_shares():
    from scripts.mirofish.high_freq_trader import place_trade, TradeSignal
    conn = _make_db()
    sig = TradeSignal(
        market_id="KXBTC-ZERO", question="test", venue="kalshi",
        direction="YES", edge=0.05, strategy="arb",
        entry_price=0.0, amount_usd=100.0, shares=0.0, fee=0.0,
    )
    assert place_trade(conn, sig, balance=10000.0) is None

def test_get_open_ids_returns_set():
    from scripts.mirofish.high_freq_trader import get_open_ids
    conn = _make_db()
    conn.execute(
        "INSERT INTO paper_trades (market_id, question, direction, shares, entry_price, "
        "amount_usd, status, confidence, reasoning, strategy, opened_at) "
        "VALUES ('KX-OPEN', 'q', 'YES', 10, 0.5, 100, 'open', 0.6, '', 'arb', '2026-03-27T00:00:00')"
    )
    conn.execute(
        "INSERT INTO paper_trades (market_id, question, direction, shares, entry_price, "
        "amount_usd, status, confidence, reasoning, strategy, opened_at) "
        "VALUES ('KX-CLOSED', 'q', 'YES', 10, 0.5, 100, 'closed_win', 0.6, '', 'arb', '2026-03-27T00:00:00')"
    )
    conn.commit()
    ids = get_open_ids(conn)
    assert "KX-OPEN" in ids
    assert "KX-CLOSED" not in ids


def test_resolve_expired_kalshi_win():
    from scripts.mirofish.high_freq_trader import resolve_expired
    conn = _make_db()
    conn.execute(
        "INSERT INTO paper_trades (market_id, question, direction, shares, entry_price, "
        "amount_usd, status, confidence, reasoning, strategy, opened_at, venue) "
        "VALUES ('KXBTC-TEST', 'q', 'YES', 100.0, 0.45, 45.0, 'open', 0.8, '', 'arb', '2026-03-27T00:00:00', 'kalshi')"
    )
    conn.commit()
    with patch("scripts.mirofish.high_freq_trader._call_kalshi",
               return_value={"market": {"result": "yes", "status": "finalized"}}):
        resolved = resolve_expired(conn)
    assert resolved == 1
    row = conn.execute("SELECT status, pnl, exit_price FROM paper_trades WHERE market_id='KXBTC-TEST'").fetchone()
    assert row["status"] == "closed_win"
    assert abs(row["exit_price"] - 1.0) < 0.001
    assert row["pnl"] > 0

def test_resolve_expired_kalshi_loss():
    from scripts.mirofish.high_freq_trader import resolve_expired
    conn = _make_db()
    conn.execute(
        "INSERT INTO paper_trades (market_id, question, direction, shares, entry_price, "
        "amount_usd, status, confidence, reasoning, strategy, opened_at, venue) "
        "VALUES ('KXBTC-LOSS', 'q', 'NO', 50.0, 0.53, 26.5, 'open', 0.6, '', 'arb', '2026-03-27T00:00:00', 'kalshi')"
    )
    conn.commit()
    with patch("scripts.mirofish.high_freq_trader._call_kalshi",
               return_value={"market": {"result": "yes", "status": "finalized"}}):
        resolve_expired(conn)
    row = conn.execute("SELECT status, pnl FROM paper_trades WHERE market_id='KXBTC-LOSS'").fetchone()
    assert row["status"] == "closed_loss"
    assert row["pnl"] < 0

def test_resolve_expired_skips_no_result():
    from scripts.mirofish.high_freq_trader import resolve_expired
    conn = _make_db()
    conn.execute(
        "INSERT INTO paper_trades (market_id, question, direction, shares, entry_price, "
        "amount_usd, status, confidence, reasoning, strategy, opened_at, venue) "
        "VALUES ('KXBTC-PEND', 'q', 'YES', 10.0, 0.50, 5.0, 'open', 0.5, '', 'arb', '2026-03-27T00:00:00', 'kalshi')"
    )
    conn.commit()
    with patch("scripts.mirofish.high_freq_trader._call_kalshi",
               return_value={"market": {"result": "", "status": "open"}}):
        resolved = resolve_expired(conn)
    assert resolved == 0
