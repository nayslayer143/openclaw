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
