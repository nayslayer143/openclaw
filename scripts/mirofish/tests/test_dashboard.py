#!/usr/bin/env python3
"""
Tests for scripts/mirofish/dashboard.py
TDD: these tests are written before the implementation.
"""
from __future__ import annotations
import os
import sqlite3
import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    db = str(tmp_path / "test.db")
    monkeypatch.setenv("CLAWMSON_DB_PATH", db)
    monkeypatch.setenv("MIROFISH_REPORTS_DIR", str(tmp_path / "reports"))
    import sys
    for mod in list(sys.modules.keys()):
        if "mirofish" in mod:
            del sys.modules[mod]
    import scripts.mirofish.simulator as sim
    sim.migrate()
    yield db


def _dashboard():
    import scripts.mirofish.dashboard as dash
    return dash


def _insert_daily_pnl(db_path: str, rows: list[tuple]):
    """Insert (date, balance, roi_pct) tuples into daily_pnl."""
    conn = sqlite3.connect(db_path)
    for date, balance, roi_pct in rows:
        conn.execute("""
            INSERT OR IGNORE INTO daily_pnl
            (date, balance, roi_pct, open_positions, total_trades, win_rate)
            VALUES (?, ?, ?, 0, 0, 0.0)
        """, (date, balance, roi_pct))
    conn.commit()
    conn.close()


def _insert_closed_trades(db_path: str, statuses: list[str]):
    """Insert closed trades with given statuses."""
    conn = sqlite3.connect(db_path)
    for i, status in enumerate(statuses):
        conn.execute("""
            INSERT INTO paper_trades
            (market_id, question, direction, shares, entry_price, amount_usd,
             pnl, status, opened_at, closed_at)
            VALUES (?, 'Test Q', 'YES', 100, 0.50, 50.0, ?, ?, '2026-01-01T00:00:00', '2026-01-02T00:00:00')
        """, (f"mkt{i}", 5.0 if status == "closed_win" else -5.0, status))
    conn.commit()
    conn.close()


# ── Test 1: Graduation requires minimum history ─────────────────────────────

def test_graduation_requires_minimum_history(temp_db):
    """5 daily rows + all profitable — still not ready due to < 7 days history."""
    # 5 days of positive ROI
    rows = [(f"2026-01-{i+1:02d}", 1000.0 + i * 10, 0.01) for i in range(5)]
    _insert_daily_pnl(temp_db, rows)
    # All wins to satisfy win rate
    _insert_closed_trades(temp_db, ["closed_win"] * 20)

    dash = _dashboard()
    result = dash.check_graduation()

    assert result["ready"] is False
    assert result["has_minimum_history"] is False
    assert result["history_days"] == 5


# ── Test 2: Graduation passes all criteria ──────────────────────────────────

def test_graduation_passes_all_criteria(temp_db):
    """15 days of positive ROI, high win rate, Sharpe > 1, no drawdown → ready=True."""
    # 15 days of varying positive returns (stdev > 0, mean/stdev > 1)
    # Use returns: 0.04, 0.03, 0.05, 0.04, 0.03, 0.05, 0.04, 0.03, 0.05, 0.04, 0.03, 0.05, 0.04, 0.03, 0.05
    returns = [0.04, 0.03, 0.05, 0.04, 0.03, 0.05, 0.04, 0.03, 0.05, 0.04, 0.03, 0.05, 0.04, 0.03, 0.05]
    balance = 1000.0
    rows = []
    for i, r in enumerate(returns):
        balance *= (1 + r)
        rows.append((f"2026-01-{i+1:02d}", balance, r))
    _insert_daily_pnl(temp_db, rows)

    # 20 wins, 0 losses → win_rate = 1.0 > 0.55
    _insert_closed_trades(temp_db, ["closed_win"] * 20)

    dash = _dashboard()
    result = dash.check_graduation()

    assert result["ready"] is True
    assert result["has_minimum_history"] is True
    assert result["history_days"] == 15
    assert result["roi_7d"] > 0
    assert result["win_rate"] > 0.55
    assert result["sharpe_all_time"] is not None
    assert result["sharpe_all_time"] > 1.0
    assert result["max_drawdown"] < 0.25
    assert result["criteria"]["min_history"] is True
    assert result["criteria"]["roi_7d_positive"] is True
    assert result["criteria"]["win_rate_55pct"] is True
    assert result["criteria"]["sharpe_above_1"] is True
    assert result["criteria"]["drawdown_below_25pct"] is True


# ── Test 3: Sharpe is None when insufficient history ────────────────────────

def test_graduation_sharpe_none_when_insufficient_history(temp_db):
    """Only 5 daily_pnl rows → sharpe_all_time=None, sharpe_above_1=False."""
    rows = [(f"2026-01-{i+1:02d}", 1000.0 + i * 10, 0.01) for i in range(5)]
    _insert_daily_pnl(temp_db, rows)

    dash = _dashboard()
    result = dash.check_graduation()

    assert result["sharpe_all_time"] is None
    assert result["criteria"]["sharpe_above_1"] is False


# ── Test 4: Graduation fails when one criterion fails ───────────────────────

def test_graduation_fails_when_one_criterion_fails(temp_db):
    """15 days of positive returns + only closed_loss trades → win_rate fails."""
    returns = [0.04, 0.03, 0.05, 0.04, 0.03, 0.05, 0.04, 0.03, 0.05, 0.04, 0.03, 0.05, 0.04, 0.03, 0.05]
    balance = 1000.0
    rows = []
    for i, r in enumerate(returns):
        balance *= (1 + r)
        rows.append((f"2026-01-{i+1:02d}", balance, r))
    _insert_daily_pnl(temp_db, rows)

    # All losses → win_rate = 0.0 < 0.55
    _insert_closed_trades(temp_db, ["closed_loss"] * 20)

    dash = _dashboard()
    result = dash.check_graduation()

    assert result["ready"] is False
    assert result["criteria"]["win_rate_55pct"] is False


# ── Test 5: maybe_snapshot writes only once per day ─────────────────────────

def test_maybe_snapshot_writes_once_per_day(temp_db):
    """Calling maybe_snapshot() twice on the same day inserts only one row."""
    dash = _dashboard()

    mock_state = {
        "balance": 1050.0,
        "starting_balance": 1000.0,
        "win_rate": 0.6,
        "total_trades": 5,
        "open_positions": 2,
        "sharpe_ratio": None,
        "max_drawdown": 0.05,
    }
    mock_prices = {}

    with patch("scripts.mirofish.paper_wallet.get_state", return_value=mock_state), \
         patch("scripts.mirofish.paper_wallet.get_open_positions", return_value=[]), \
         patch("scripts.mirofish.polymarket_feed.get_latest_prices", return_value=mock_prices):
        result1 = dash.maybe_snapshot()
        result2 = dash.maybe_snapshot()

    conn = sqlite3.connect(temp_db)
    count = conn.execute("SELECT COUNT(*) as cnt FROM daily_pnl").fetchone()[0]
    conn.close()

    assert result1 is True
    assert result2 is False
    assert count == 1


# ── Test 6: generate_report writes a markdown file ──────────────────────────

def test_generate_report_writes_file(tmp_path, temp_db):
    """generate_report("daily") creates a .md file containing expected sections."""
    dash = _dashboard()

    mock_state = {
        "balance": 1050.0,
        "starting_balance": 1000.0,
        "win_rate": 0.6,
        "total_trades": 5,
        "open_positions": 2,
        "sharpe_ratio": None,
        "max_drawdown": 0.05,
    }

    with patch("scripts.mirofish.paper_wallet.get_state", return_value=mock_state), \
         patch("scripts.mirofish.paper_wallet.get_open_positions", return_value=[]):
        report_path = dash.generate_report("daily")

    assert report_path.exists()
    content = report_path.read_text()
    assert "Mirofish" in content
    assert "Graduation Status" in content
