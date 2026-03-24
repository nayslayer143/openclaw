from __future__ import annotations

import sqlite3
import datetime
import pytest


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    db = str(tmp_path / "test.db")
    monkeypatch.setenv("CLAWMSON_DB_PATH", db)
    monkeypatch.setenv("BACKTEST_SLIPPAGE_BPS", "0")  # disable slippage for predictable tests
    import sys
    for mod in list(sys.modules.keys()):
        if "mirofish" in mod:
            del sys.modules[mod]
    import scripts.mirofish.simulator as sim
    sim.migrate()
    yield db


def _bt():
    import sys
    for mod in list(sys.modules.keys()):
        if "backtester" in mod:
            del sys.modules[mod]
    import scripts.mirofish.backtester as bt
    return bt


def _seed_market_data(db_path: str, markets: list[dict]) -> None:
    conn = sqlite3.connect(db_path)
    for m in markets:
        conn.execute("""
            INSERT INTO market_data
            (market_id, question, category, yes_price, no_price, volume, end_date, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            m.get("market_id", "mkt-1"),
            m.get("question", "Test?"),
            m.get("category", "crypto"),
            m.get("yes_price", 0.50),
            m.get("no_price", 0.50),
            m.get("volume", 50000),
            m.get("end_date", "2026-06-01T00:00:00Z"),
            m.get("fetched_at", "2026-03-15T12:00:00"),
        ))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_load_empty_data(temp_db):
    bt = _bt()
    snapshots = bt.load_historical_snapshots("2026-03-01", "2026-03-31")
    assert snapshots == {}


def test_load_historical_snapshots(temp_db):
    bt = _bt()
    _seed_market_data(temp_db, [
        {"market_id": "m1", "yes_price": 0.60, "no_price": 0.40,
         "fetched_at": "2026-03-15T12:00:00"},
        {"market_id": "m2", "yes_price": 0.70, "no_price": 0.30,
         "fetched_at": "2026-03-15T18:00:00"},
        {"market_id": "m1", "yes_price": 0.62, "no_price": 0.38,
         "fetched_at": "2026-03-16T12:00:00"},
    ])
    snapshots = bt.load_historical_snapshots("2026-03-01", "2026-03-31")
    assert "2026-03-15" in snapshots
    assert "2026-03-16" in snapshots
    assert len(snapshots["2026-03-15"]) == 2  # m1 and m2
    assert len(snapshots["2026-03-16"]) == 1  # m1 only


def test_sim_wallet_basic(temp_db):
    bt = _bt()
    wallet = bt.SimWallet(1000.0)
    assert wallet.balance == 1000.0
    assert wallet.get_state()["open_positions"] == 0


def test_sim_wallet_execute_trade(temp_db):
    bt = _bt()
    wallet = bt.SimWallet(1000.0)
    trade = bt.BacktestTrade(
        trade_id=0, market_id="m1", question="Test?",
        direction="YES", strategy="arbitrage",
        entry_price=0.50, amount_usd=50.0, shares=100.0,
    )
    ok = wallet.execute(trade)
    assert ok is True
    assert len(wallet.open_trades) == 1


def test_sim_wallet_rejects_overcap(temp_db):
    bt = _bt()
    wallet = bt.SimWallet(100.0)  # small balance
    trade = bt.BacktestTrade(
        trade_id=0, market_id="m1", question="Test?",
        direction="YES", strategy="arbitrage",
        entry_price=0.50, amount_usd=50.0, shares=100.0,  # 50% of balance > 10% cap
    )
    ok = wallet.execute(trade)
    assert ok is False


def test_sim_wallet_stop_loss(temp_db):
    bt = _bt()
    wallet = bt.SimWallet(1000.0)
    trade = bt.BacktestTrade(
        trade_id=0, market_id="m1", question="Test?",
        direction="YES", strategy="arbitrage",
        entry_price=0.50, amount_usd=50.0, shares=100.0,
    )
    wallet.execute(trade)

    # Price drops 25% → triggers -20% stop
    prices = {"m1": {"yes_price": 0.35, "no_price": 0.65}}
    closed = wallet.check_stops(prices, "2026-03-15")
    assert len(closed) == 1
    assert closed[0].status == "closed_loss"
    assert closed[0].pnl < 0


def test_sim_wallet_take_profit(temp_db):
    bt = _bt()
    wallet = bt.SimWallet(1000.0)
    trade = bt.BacktestTrade(
        trade_id=0, market_id="m1", question="Test?",
        direction="YES", strategy="arbitrage",
        entry_price=0.40, amount_usd=50.0, shares=125.0,
    )
    wallet.execute(trade)

    # Price jumps 60% → triggers +50% TP
    prices = {"m1": {"yes_price": 0.70, "no_price": 0.30}}
    closed = wallet.check_stops(prices, "2026-03-15")
    assert len(closed) == 1
    assert closed[0].status == "closed_win"
    assert closed[0].pnl > 0


def test_backtest_empty_data(temp_db):
    bt = _bt()
    result = bt.run_backtest("2026-03-01", "2026-03-31")
    assert result.ending_balance == result.starting_balance
    assert result.total_return_pct == 0.0
    assert len(result.all_trades) == 0


def test_backtest_with_arb_opportunity(temp_db):
    bt = _bt()
    # Seed a market with arb gap (yes + no = 0.90, gap = 0.10 > 0.03 threshold)
    _seed_market_data(temp_db, [
        {"market_id": "arb-mkt", "question": "Arb test?",
         "yes_price": 0.40, "no_price": 0.50,
         "fetched_at": "2026-03-15T12:00:00"},
        # Next day: prices converge (arb profit)
        {"market_id": "arb-mkt", "question": "Arb test?",
         "yes_price": 0.48, "no_price": 0.52,
         "fetched_at": "2026-03-16T12:00:00"},
    ])

    result = bt.run_backtest("2026-03-15", "2026-03-16", strategies=["arbitrage"])
    assert len(result.all_trades) >= 1
    assert result.strategy_results[0].strategy == "arbitrage"


def test_backtest_result_to_dict(temp_db):
    bt = _bt()
    result = bt.run_backtest("2026-03-01", "2026-03-31")
    d = result.to_dict()
    assert "from_date" in d
    assert "to_date" in d
    assert "strategies" in d
    assert "total_trades" in d


def test_strategy_result_computation(temp_db):
    bt = _bt()
    trades = [
        bt.BacktestTrade(trade_id=1, market_id="m1", question="T1",
                         direction="YES", strategy="test", entry_price=0.40,
                         exit_price=0.55, amount_usd=50, shares=125,
                         pnl=18.75, status="closed_win"),
        bt.BacktestTrade(trade_id=2, market_id="m2", question="T2",
                         direction="YES", strategy="test", entry_price=0.50,
                         exit_price=0.40, amount_usd=50, shares=100,
                         pnl=-10.0, status="closed_loss"),
    ]
    result = bt._compute_strategy_result("test", trades, 1000.0)
    assert result.total_trades == 2
    assert result.wins == 1
    assert result.losses == 1
    assert result.win_rate == 0.5
    assert result.total_pnl == pytest.approx(8.75)
    assert result.best_trade == pytest.approx(18.75)
    assert result.worst_trade == pytest.approx(-10.0)


def test_daily_snapshots_generated(temp_db):
    bt = _bt()
    _seed_market_data(temp_db, [
        {"market_id": "m1", "yes_price": 0.45, "no_price": 0.45,
         "fetched_at": "2026-03-15T12:00:00"},
        {"market_id": "m1", "yes_price": 0.50, "no_price": 0.50,
         "fetched_at": "2026-03-16T12:00:00"},
    ])
    result = bt.run_backtest("2026-03-15", "2026-03-16")
    assert len(result.daily_snapshots) == 2
    assert result.daily_snapshots[0].date == "2026-03-15"
