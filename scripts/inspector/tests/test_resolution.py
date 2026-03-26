"""
Tests for Inspector Gadget — Resolution Auditor (Task 4).
All tests use mocks — no live DB or API calls.
"""

import pytest
from unittest.mock import MagicMock
from inspector.resolution_auditor import ResolutionAuditor


def _closed_trade(direction="YES", status="closed_win", exit_price=0.95,
                  entry_price=0.50, shares=100.0, pnl=45.0):
    return {"id": 1, "market_id": "0xABC", "direction": direction,
            "status": status, "exit_price": exit_price, "entry_price": entry_price,
            "shares": shares, "pnl": pnl, "closed_at": "2026-03-25T12:00:00"}


def test_open_trade_skipped():
    ra = ResolutionAuditor(db=MagicMock(), poly=MagicMock())
    result = ra.audit_trade({"id": 1, "status": "open", "market_id": "0xABC"})
    assert result is None


def test_yes_win_matches_yes_resolution():
    poly = MagicMock()
    poly.get_resolution.return_value = {"closed": True, "resolution": "YES"}
    ra = ResolutionAuditor(db=MagicMock(), poly=poly)
    result = ra.audit_trade(_closed_trade(direction="YES", status="closed_win"))
    assert result["match"] == 1


def test_yes_win_with_no_resolution_is_mismatch():
    poly = MagicMock()
    poly.get_resolution.return_value = {"closed": True, "resolution": "NO"}
    ra = ResolutionAuditor(db=MagicMock(), poly=poly)
    result = ra.audit_trade(_closed_trade(direction="YES", status="closed_win"))
    assert result["match"] == 0


def test_no_win_matches_no_resolution():
    poly = MagicMock()
    poly.get_resolution.return_value = {"closed": True, "resolution": "NO"}
    ra = ResolutionAuditor(db=MagicMock(), poly=poly)
    result = ra.audit_trade(_closed_trade(direction="NO", status="closed_win"))
    assert result["match"] == 1


def test_unresolved_market_is_unverifiable():
    poly = MagicMock()
    poly.get_resolution.return_value = {"closed": False, "resolution": None}
    ra = ResolutionAuditor(db=MagicMock(), poly=poly)
    result = ra.audit_trade(_closed_trade())
    assert result["match"] == -1


def test_market_not_found_is_unverifiable():
    poly = MagicMock()
    poly.get_resolution.return_value = None
    ra = ResolutionAuditor(db=MagicMock(), poly=poly)
    result = ra.audit_trade(_closed_trade())
    assert result["match"] == -1
    assert result["actual_resolution"] == "NOT_FOUND"


def test_expired_trade_always_matches():
    poly = MagicMock()
    poly.get_resolution.return_value = {"closed": True, "resolution": "NO"}
    ra = ResolutionAuditor(db=MagicMock(), poly=poly)
    result = ra.audit_trade(_closed_trade(status="expired"))
    assert result["match"] == 1


def test_recalculated_pnl_correct():
    poly = MagicMock()
    poly.get_resolution.return_value = {"closed": True, "resolution": "YES"}
    ra = ResolutionAuditor(db=MagicMock(), poly=poly)
    result = ra.audit_trade(_closed_trade(exit_price=0.95, entry_price=0.50, shares=100.0, pnl=45.0))
    # (0.95 - 0.50) * 100 = 45.0
    assert abs(result["recalculated_pnl"] - 45.0) < 0.001


def test_pnl_delta_computed():
    poly = MagicMock()
    poly.get_resolution.return_value = {"closed": True, "resolution": "YES"}
    ra = ResolutionAuditor(db=MagicMock(), poly=poly)
    # claimed pnl=40.0, but actual should be 45.0 → delta=5.0
    result = ra.audit_trade(_closed_trade(exit_price=0.95, entry_price=0.50, shares=100.0, pnl=40.0))
    assert abs(result["pnl_delta"] - 5.0) < 0.001
