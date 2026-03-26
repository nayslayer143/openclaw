"""
Tests for Inspector Gadget — Trade Verifier (Task 3).
All tests use mocks — no live DB or API calls.
"""

import pytest
from unittest.mock import MagicMock
from inspector.verifier import TradeVerifier, VerificationStatus


def _make_trade(overrides=None):
    base = {
        "id": 1, "market_id": "0xABC", "direction": "YES",
        "shares": 100.0, "entry_price": 0.50, "exit_price": None,
        "amount_usd": 50.0, "pnl": None, "status": "open",
        "opened_at": "2026-03-24T10:00:00", "closed_at": None,
        "strategy": "momentum", "confidence": 0.7,
    }
    if overrides:
        base.update(overrides)
    return base


def test_impossible_negative_shares():
    tv = TradeVerifier(db=MagicMock(), poly=MagicMock())
    result = tv._check_math({"shares": -5, "entry_price": 0.5, "amount_usd": 10})
    assert result["status"] == VerificationStatus.IMPOSSIBLE


def test_impossible_price_out_of_range():
    tv = TradeVerifier(db=MagicMock(), poly=MagicMock())
    result = tv._check_math({"shares": 10, "entry_price": 1.5, "amount_usd": 15})
    assert result["status"] == VerificationStatus.IMPOSSIBLE


def test_impossible_zero_amount():
    tv = TradeVerifier(db=MagicMock(), poly=MagicMock())
    result = tv._check_math({"shares": 10, "entry_price": 0.5, "amount_usd": 0})
    assert result["status"] == VerificationStatus.IMPOSSIBLE


def test_math_discrepancy():
    tv = TradeVerifier(db=MagicMock(), poly=MagicMock())
    # 100 * 0.5 = 50, but claimed 999 → DISCREPANCY
    result = tv._check_math({"shares": 100, "entry_price": 0.5, "amount_usd": 999})
    assert result["status"] == VerificationStatus.DISCREPANCY


def test_math_verified_within_tolerance():
    tv = TradeVerifier(db=MagicMock(), poly=MagicMock())
    # 100 * 0.502 = 50.2, amount_usd = 50.0 → delta_pct = 0.004 < 0.015 → VERIFIED
    result = tv._check_math({"shares": 100, "entry_price": 0.502, "amount_usd": 50.0})
    assert result["status"] == VerificationStatus.VERIFIED


def test_price_impossible_market_not_found():
    poly = MagicMock()
    poly.get_market.return_value = None
    tv = TradeVerifier(db=MagicMock(), poly=poly)
    result = tv._check_price(_make_trade())
    assert result["status"] == VerificationStatus.IMPOSSIBLE


def test_price_unverifiable_non_polymarket_market():
    """Non-0x market IDs (e.g., Kalshi KX* IDs) should be UNVERIFIABLE, not IMPOSSIBLE."""
    poly = MagicMock()
    tv = TradeVerifier(db=MagicMock(), poly=poly)
    result = tv._check_price(_make_trade({"market_id": "KXBTC-26MAR2402-T77699.99"}))
    assert result["status"] == VerificationStatus.UNVERIFIABLE
    # Polymarket client should NOT be called for non-Polymarket markets
    poly.get_market.assert_not_called()


def test_price_unverifiable_no_history():
    poly = MagicMock()
    poly.get_market.return_value = {"question": "Will X?"}
    poly.get_price_at.return_value = None
    tv = TradeVerifier(db=MagicMock(), poly=poly)
    result = tv._check_price(_make_trade())
    assert result["status"] == VerificationStatus.UNVERIFIABLE


def test_price_discrepancy():
    poly = MagicMock()
    poly.get_market.return_value = {"question": "Will X?"}
    poly.get_price_at.return_value = 0.20  # claimed 0.50, actual 0.20 → delta 0.30 > 0.02
    tv = TradeVerifier(db=MagicMock(), poly=poly)
    result = tv._check_price(_make_trade())
    assert result["status"] == VerificationStatus.DISCREPANCY


def test_price_verified():
    poly = MagicMock()
    poly.get_market.return_value = {"question": "Will X?"}
    poly.get_price_at.return_value = 0.51  # claimed 0.50, delta 0.01 < 0.02 → VERIFIED
    tv = TradeVerifier(db=MagicMock(), poly=poly)
    result = tv._check_price(_make_trade())
    assert result["status"] == VerificationStatus.VERIFIED


def test_verify_trade_worst_status_wins():
    """If math is VERIFIED but price is IMPOSSIBLE, final should be IMPOSSIBLE."""
    poly = MagicMock()
    poly.get_market.return_value = None  # IMPOSSIBLE
    tv = TradeVerifier(db=MagicMock(), poly=poly)
    trade = _make_trade()
    result = tv.verify_trade(trade)
    assert result["status"] == VerificationStatus.IMPOSSIBLE.value


def test_verify_trade_computes_verified_pnl():
    """closed trade: verified_pnl = (exit - entry) * shares"""
    poly = MagicMock()
    poly.get_market.return_value = {"question": "Will X?"}
    poly.get_price_at.return_value = 0.50
    tv = TradeVerifier(db=MagicMock(), poly=poly)
    trade = _make_trade({"exit_price": 0.80, "pnl": 30.0})
    result = tv.verify_trade(trade)
    assert abs(result["verified_pnl"] - 30.0) < 0.01  # (0.80 - 0.50) * 100 = 30


def test_run_processes_all_trades(tmp_path):
    """run() should process all rows and return correct counts, not crash on bad trades."""
    import sqlite3
    # Create a minimal clawmson.db with 2 trades
    db_path = tmp_path / "clawmson.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""CREATE TABLE paper_trades (
        id INTEGER PRIMARY KEY, market_id TEXT, question TEXT, direction TEXT,
        shares REAL, entry_price REAL, exit_price REAL, amount_usd REAL,
        pnl REAL, status TEXT, confidence REAL, reasoning TEXT,
        strategy TEXT, opened_at TEXT, closed_at TEXT
    )""")
    conn.execute("INSERT INTO paper_trades VALUES (1,'0xABC','Q?','YES',100,0.5,NULL,50,NULL,'open',0.7,'','momentum','2026-03-24T10:00:00',NULL)")
    conn.execute("INSERT INTO paper_trades VALUES (2,'0xDEF','Q2?','NO',50,0.3,NULL,15,NULL,'open',0.6,'','arb','2026-03-24T11:00:00',NULL)")
    conn.commit()
    conn.close()

    poly = MagicMock()
    poly.get_market.return_value = {"question": "Q?"}
    poly.get_price_at.return_value = 0.50  # matches entry_price exactly

    inspector_db = MagicMock()
    inspector_db.insert.return_value = 1

    tv = TradeVerifier(db=inspector_db, poly=poly)
    result = tv.run(str(db_path))

    assert result["total"] == 2
    assert inspector_db.insert.call_count == 2
    assert result["errors"] == 0
