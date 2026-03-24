"""Tests for telegram_digest, scoring_experiments, and calibration modules."""
from __future__ import annotations
import sqlite3
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
    import scripts.mirofish.strategy_tracker as st
    st.migrate()
    import scripts.mirofish.calibration as cal
    cal.migrate()
    import scripts.mirofish.scoring_experiments as se
    se.migrate()
    yield db


# ---------------------------------------------------------------------------
# Telegram digest
# ---------------------------------------------------------------------------

def test_format_strategy_rankings_empty():
    from scripts.mirofish.telegram_digest import format_strategy_rankings
    from scripts.mirofish.strategy_tracker import StrategyReport
    reports = [StrategyReport(
        strategy="test", total_trades=0, wins=0, losses=0,
        win_rate=0, avg_expected_edge=0, avg_realized_pnl=0,
        capture_rate=0, total_pnl=0, sharpe=None, max_drawdown=0, roi_pct=0,
    )]
    msg = format_strategy_rankings(reports)
    assert "No active strategies" in msg


def test_format_strategy_rankings_active():
    from scripts.mirofish.telegram_digest import format_strategy_rankings
    from scripts.mirofish.strategy_tracker import StrategyReport
    reports = [StrategyReport(
        strategy="momentum", total_trades=10, wins=7, losses=3,
        win_rate=0.7, avg_expected_edge=0.1, avg_realized_pnl=5.0,
        capture_rate=0.8, total_pnl=50.0, sharpe=1.5, max_drawdown=0.1,
        roi_pct=10.0, allocation_pct=0.6,
    )]
    msg = format_strategy_rankings(reports)
    assert "momentum" in msg
    assert "60%" in msg


def test_format_daily_summary():
    from scripts.mirofish.telegram_digest import format_daily_summary
    wallet = {"balance": 1050.0, "starting_balance": 1000.0,
              "open_positions": 3, "win_rate": 0.65, "sharpe_ratio": 1.2,
              "max_drawdown": 0.08}
    msg = format_daily_summary(wallet)
    assert "$1,050" in msg
    assert "+5.0%" in msg


# ---------------------------------------------------------------------------
# Scoring experiments
# ---------------------------------------------------------------------------

def test_run_experiments(temp_db):
    from scripts.mirofish.scoring_experiments import run_experiments
    results = run_experiments()
    assert len(results) == 5  # 5 configs
    assert all(r.name for r in results)


def test_experiment_result_to_dict(temp_db):
    from scripts.mirofish.scoring_experiments import run_experiments
    results = run_experiments()
    d = results[0].to_dict()
    assert "name" in d
    assert "allocations" in d


def test_snapshot_experiments(temp_db):
    from scripts.mirofish.scoring_experiments import snapshot_experiments
    snapshot_experiments()
    conn = sqlite3.connect(temp_db)
    rows = conn.execute("SELECT * FROM scoring_experiments").fetchall()
    conn.close()
    assert len(rows) == 5


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------

def test_calibration_migrate(temp_db):
    conn = sqlite3.connect(temp_db)
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    conn.close()
    assert "scenario_archive" in tables
    assert "calibration_params" in tables
    assert "promotion_candidates" in tables


def test_archive_and_find_scenario(temp_db):
    from scripts.mirofish.calibration import archive_trade, find_similar_scenarios
    archive_trade(
        market_id="m1", question="BTC above $150k?", category="crypto",
        strategy="momentum", direction="YES", entry_price=0.50,
        exit_price=0.65, pnl=15.0, status="closed_win",
        tags=["btc", "threshold"],
    )
    scenarios = find_similar_scenarios(category="crypto")
    assert len(scenarios) == 1
    assert scenarios[0]["market_id"] == "m1"


def test_scenario_stats(temp_db):
    from scripts.mirofish.calibration import archive_trade, get_scenario_stats
    archive_trade("m1", "Q1", "crypto", "arb", "YES", 0.40, 0.55, 10.0, "closed_win")
    archive_trade("m2", "Q2", "crypto", "arb", "NO", 0.60, 0.50, -5.0, "closed_loss")
    stats = get_scenario_stats(category="crypto")
    assert stats["count"] == 2
    assert stats["win_rate"] == 0.5


def test_promotion_eligibility(temp_db):
    from scripts.mirofish.calibration import check_promotion_eligibility
    status = check_promotion_eligibility("momentum")
    assert status.status in ("testing", "eligible")
    assert isinstance(status.meets_criteria, dict)


def test_promotion_status_to_dict(temp_db):
    from scripts.mirofish.calibration import check_promotion_eligibility
    status = check_promotion_eligibility("momentum")
    d = status.to_dict()
    assert "name" in d
    assert "status" in d
    assert "criteria" in d
