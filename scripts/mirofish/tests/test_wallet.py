# scripts/mirofish/tests/test_wallet.py
from __future__ import annotations
import os
import sqlite3
import tempfile
from pathlib import Path
from statistics import mean, stdev
import pytest

# Point at a temp DB for all wallet tests
@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    db = str(tmp_path / "test.db")
    monkeypatch.setenv("CLAWMSON_DB_PATH", db)
    # Force re-import with new env var
    import sys
    for mod in list(sys.modules.keys()):
        if "mirofish" in mod or "clawmson" in mod:
            del sys.modules[mod]
    import scripts.mirofish.simulator as sim
    sim.DB_PATH = Path(db)
    sim.migrate()
    yield db


def _get_wallet():
    # Re-import after env var is set
    import sys
    for mod in list(sys.modules.keys()):
        if "paper_wallet" in mod:
            del sys.modules[mod]
    import scripts.mirofish.paper_wallet as pw
    return pw


# ── Balance derivation ─────────────────────────────────────────────────────
def test_starting_balance_is_1000(temp_db):
    pw = _get_wallet()
    state = pw.get_state()
    assert state["starting_balance"] == 1000.0
    assert state["balance"] == 1000.0   # no trades yet


def test_balance_includes_realized_pnl(temp_db):
    pw = _get_wallet()
    # Manually insert a closed winning trade
    conn = sqlite3.connect(temp_db)
    conn.execute("""
        INSERT INTO paper_trades
        (market_id, question, direction, shares, entry_price, exit_price,
         amount_usd, pnl, status, opened_at, closed_at)
        VALUES ('mkt1', 'test', 'YES', 100, 0.50, 0.70, 50.0, 20.0, 'closed_win',
                '2026-01-01T00:00:00', '2026-01-02T00:00:00')
    """)
    conn.commit(); conn.close()
    state = pw.get_state()
    assert state["balance"] == pytest.approx(1020.0)


def test_balance_includes_unrealized_pnl(temp_db):
    pw = _get_wallet()
    # Open YES trade at 0.40, market now at 0.60 → unrealized = shares*(0.60-0.40)
    conn = sqlite3.connect(temp_db)
    conn.execute("""
        INSERT INTO paper_trades
        (market_id, question, direction, shares, entry_price,
         amount_usd, status, opened_at)
        VALUES ('mkt2', 'open trade', 'YES', 100, 0.40, 40.0, 'open', '2026-01-01T00:00:00')
    """)
    # Seed a current price snapshot
    conn.execute("""
        INSERT INTO market_data (market_id, question, yes_price, no_price, fetched_at)
        VALUES ('mkt2', 'open trade', 0.60, 0.40, '2026-01-01T01:00:00')
    """)
    conn.commit(); conn.close()
    state = pw.get_state()
    assert state["balance"] == pytest.approx(1020.0)  # 1000 + 100*(0.60-0.40)


# ── Position cap ───────────────────────────────────────────────────────────
def test_position_cap_rejects_over_10pct(temp_db):
    pw = _get_wallet()
    from types import SimpleNamespace
    decision = SimpleNamespace(
        market_id="mkt3", question="big bet", direction="YES",
        amount_usd=101.0,  # 10.1% of $1000
        entry_price=0.50, shares=202.0,
        confidence=0.8, reasoning="test", strategy="momentum"
    )
    result = pw.execute_trade(decision)
    assert result is None  # rejected


def test_position_cap_allows_exactly_10pct(temp_db):
    pw = _get_wallet()
    from types import SimpleNamespace
    decision = SimpleNamespace(
        market_id="mkt4", question="10pct bet", direction="YES",
        amount_usd=100.0,  # exactly 10%
        entry_price=0.50, shares=200.0,
        confidence=0.8, reasoning="test", strategy="momentum"
    )
    result = pw.execute_trade(decision)
    assert result is not None
    assert result["status"] == "open"


# ── Stop management ────────────────────────────────────────────────────────
def test_stop_loss_closes_at_minus_20pct(temp_db):
    pw = _get_wallet()
    conn = sqlite3.connect(temp_db)
    # YES trade: bought 100 shares at 0.50 for $50. Stop at -20% = P&L < -$10
    # Current yes_price = 0.40 → unrealized = 100*(0.40-0.50) = -$10 = -20%
    conn.execute("""
        INSERT INTO paper_trades (id, market_id, question, direction, shares,
         entry_price, amount_usd, status, opened_at)
        VALUES (1, 'mkt5', 'stop test', 'YES', 100, 0.50, 50.0, 'open', '2026-01-01T00:00:00')
    """)
    conn.commit(); conn.close()
    current_prices = {"mkt5": {"yes_price": 0.40, "no_price": 0.60}}
    closed = pw.check_stops(current_prices)
    assert len(closed) == 1
    assert closed[0]["status"] == "closed_loss"
    assert closed[0]["exit_price"] == pytest.approx(0.40)


def test_take_profit_closes_at_plus_50pct(temp_db):
    pw = _get_wallet()
    conn = sqlite3.connect(temp_db)
    # YES trade: bought 100 shares at 0.40 for $40. Take-profit at +50% = P&L > +$20
    # Current yes_price = 0.60 → unrealized = 100*(0.60-0.40) = +$20 = +50%
    conn.execute("""
        INSERT INTO paper_trades (id, market_id, question, direction, shares,
         entry_price, amount_usd, status, opened_at)
        VALUES (2, 'mkt6', 'profit test', 'YES', 100, 0.40, 40.0, 'open', '2026-01-01T00:00:00')
    """)
    conn.commit(); conn.close()
    current_prices = {"mkt6": {"yes_price": 0.60, "no_price": 0.40}}
    closed = pw.check_stops(current_prices)
    assert len(closed) == 1
    assert closed[0]["status"] == "closed_win"


# ── Sharpe ratio ───────────────────────────────────────────────────────────
def test_sharpe_returns_correct_value(temp_db):
    pw = _get_wallet()
    # Inject 14 days of daily_pnl with known returns
    conn = sqlite3.connect(temp_db)
    returns = [0.02, 0.01, 0.03, -0.01, 0.02, 0.01, 0.04,
               0.01, 0.02, -0.01, 0.03, 0.01, 0.02, 0.01]
    balance = 1000.0
    for i, r in enumerate(returns):
        balance *= (1 + r)
        conn.execute("""
            INSERT INTO daily_pnl (date, balance, roi_pct, open_positions, total_trades, win_rate)
            VALUES (?, ?, ?, 0, 0, 0.0)
        """, (f"2026-01-{i+1:02d}", balance, r))
    conn.commit(); conn.close()
    state = pw.get_state()
    expected = mean(returns) / stdev(returns)
    assert state["sharpe_ratio"] == pytest.approx(expected, rel=1e-3)


def test_sharpe_returns_none_when_std_is_zero(temp_db):
    pw = _get_wallet()
    conn = sqlite3.connect(temp_db)
    for i in range(14):
        conn.execute("""
            INSERT INTO daily_pnl (date, balance, roi_pct, open_positions, total_trades, win_rate)
            VALUES (?, ?, ?, 0, 0, 0.0)
        """, (f"2026-01-{i+1:02d}", 1000.0, 0.01))
    conn.commit(); conn.close()
    state = pw.get_state()
    assert state["sharpe_ratio"] is None


# ── Max drawdown ───────────────────────────────────────────────────────────
def test_max_drawdown_calculation(temp_db):
    pw = _get_wallet()
    conn = sqlite3.connect(temp_db)
    # Balances: 1000 → 1100 (peak) → 880 → 990
    # Drawdown from peak 1100 to 880 = (1100-880)/1100 = 0.2 = 20%
    for date, bal in [("2026-01-01", 1000), ("2026-01-02", 1100),
                      ("2026-01-03", 880),  ("2026-01-04", 990)]:
        roi = (bal - 1000) / 1000
        conn.execute("""
            INSERT INTO daily_pnl (date, balance, roi_pct, open_positions, total_trades, win_rate)
            VALUES (?, ?, ?, 0, 0, 0.0)
        """, (date, bal, roi))
    conn.commit(); conn.close()
    state = pw.get_state()
    assert state["max_drawdown"] == pytest.approx(0.2, rel=1e-3)
