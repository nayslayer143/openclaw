"""
Tests for StatsAuditor (Task 5).
"""

import pytest
from dataclasses import asdict
from inspector.stats_auditor import StatsAuditor, RedFlag


def _make_trades(win_rate: float, n: int = 100):
    trades = []
    wins = int(n * win_rate)
    for i in range(n):
        pnl = 10.0 if i < wins else -10.0
        st = "closed_win" if i < wins else "closed_loss"
        trades.append({"id": i, "pnl": pnl, "amount_usd": 50.0,
                       "entry_price": 0.5, "confidence": 0.7,
                       "strategy": "test", "status": st})
    return trades


def test_high_win_rate_flagged():
    sa = StatsAuditor()
    flags = sa.check_win_rate(_make_trades(0.90, 100))
    assert any(f.severity == "critical" for f in flags)


def test_normal_win_rate_clean():
    sa = StatsAuditor()
    flags = sa.check_win_rate(_make_trades(0.60, 100))
    assert len(flags) == 0


def test_small_sample_skipped():
    sa = StatsAuditor()
    flags = sa.check_win_rate(_make_trades(0.90, 10))  # < MIN_SAMPLE
    assert len(flags) == 0


def test_position_size_violation_critical():
    sa = StatsAuditor()
    flags = sa.check_position_size({"amount_usd": 160.0}, 1000.0)  # 16% > 15%
    assert any(f.severity == "critical" for f in flags)


def test_position_size_violation_high():
    sa = StatsAuditor()
    flags = sa.check_position_size({"amount_usd": 110.0}, 1000.0)  # 11% > 10.5%
    assert any(f.severity == "high" for f in flags)


def test_position_size_ok():
    sa = StatsAuditor()
    flags = sa.check_position_size({"amount_usd": 95.0}, 1000.0)  # 9.5% — fine
    assert len(flags) == 0


def test_zero_variance_sharpe_flagged():
    sa = StatsAuditor()
    rows = [{"roi_pct": 0.01} for _ in range(10)]
    flags = sa.check_sharpe(rows)
    assert any(f.severity == "critical" for f in flags)


def test_high_sharpe_flagged():
    sa = StatsAuditor()
    # Std dev 0.001 → huge Sharpe
    rows = [{"roi_pct": 0.05 + (i * 0.0001)} for i in range(10)]
    flags = sa.check_sharpe(rows)
    assert any(f.severity == "high" for f in flags)


def test_losing_streaks_flagged_when_absent():
    sa = StatsAuditor()
    # 40 straight wins — no losing streak
    trades = [{"status": "closed_win"} for _ in range(40)]
    flags = sa.check_no_losing_streaks(trades)
    assert any(f.severity == "medium" for f in flags)
