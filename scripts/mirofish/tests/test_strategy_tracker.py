from __future__ import annotations

import sqlite3
import datetime
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
    import scripts.mirofish.strategy_tracker as tracker
    tracker.migrate()
    yield db


def _tracker():
    import sys
    for mod in list(sys.modules.keys()):
        if "strategy_tracker" in mod:
            del sys.modules[mod]
    import scripts.mirofish.strategy_tracker as tracker
    return tracker


def _seed_trades(db_path: str, trades: list[dict]) -> None:
    """Insert paper_trades rows for testing."""
    conn = sqlite3.connect(db_path)
    for t in trades:
        conn.execute("""
            INSERT INTO paper_trades
            (market_id, question, direction, shares, entry_price, exit_price,
             amount_usd, pnl, status, confidence, reasoning, strategy, opened_at, closed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            t.get("market_id", "mkt-1"),
            t.get("question", "Test?"),
            t.get("direction", "YES"),
            t.get("shares", 100),
            t.get("entry_price", 0.50),
            t.get("exit_price"),
            t.get("amount_usd", 50.0),
            t.get("pnl"),
            t.get("status", "open"),
            t.get("confidence", 0.70),
            t.get("reasoning", "test"),
            t.get("strategy", "momentum"),
            t.get("opened_at", datetime.datetime.utcnow().isoformat()),
            t.get("closed_at"),
        ))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_migrate_creates_tables(temp_db):
    conn = sqlite3.connect(temp_db)
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    conn.close()
    assert "strategy_performance" in tables
    assert "strategy_stats" in tables


def test_record_trade_open(temp_db):
    tracker = _tracker()
    tracker.record_trade_open(
        trade_id=1, strategy="momentum", market_id="mkt-1",
        direction="YES", entry_price=0.50, expected_edge=0.15,
        amount_usd=50.0, confidence=0.70,
    )
    conn = sqlite3.connect(temp_db)
    rows = conn.execute("SELECT * FROM strategy_performance").fetchall()
    conn.close()
    assert len(rows) == 1


def test_record_trade_close(temp_db):
    tracker = _tracker()
    tracker.record_trade_open(
        trade_id=1, strategy="arbitrage", market_id="mkt-1",
        direction="YES", entry_price=0.40, expected_edge=0.05,
        amount_usd=50.0, confidence=0.80,
    )
    tracker.record_trade_close(
        trade_id=1, exit_price=0.55, realized_pnl=15.0, status="closed_win",
    )
    conn = sqlite3.connect(temp_db)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM strategy_performance WHERE trade_id=1").fetchone()
    conn.close()
    assert row["status"] == "closed_win"
    assert row["realized_pnl"] == 15.0


def test_sync_from_paper_trades(temp_db):
    tracker = _tracker()
    _seed_trades(temp_db, [
        {"strategy": "momentum", "status": "closed_win", "pnl": 10.0,
         "exit_price": 0.60, "confidence": 0.70},
        {"strategy": "arbitrage", "status": "closed_loss", "pnl": -5.0,
         "exit_price": 0.45, "confidence": 0.90},
        {"strategy": "momentum", "status": "open", "confidence": 0.65},
    ])
    synced = tracker.sync_from_paper_trades()
    assert synced == 3

    conn = sqlite3.connect(temp_db)
    rows = conn.execute("SELECT * FROM strategy_performance").fetchall()
    closed = conn.execute(
        "SELECT * FROM strategy_performance WHERE status != 'open'"
    ).fetchall()
    conn.close()
    assert len(rows) == 3
    assert len(closed) == 2


def test_sync_is_idempotent(temp_db):
    tracker = _tracker()
    _seed_trades(temp_db, [
        {"strategy": "momentum", "status": "closed_win", "pnl": 10.0,
         "exit_price": 0.60},
    ])
    n1 = tracker.sync_from_paper_trades()
    n2 = tracker.sync_from_paper_trades()
    assert n1 == 1
    assert n2 == 0


def test_compute_strategy_report_empty(temp_db):
    tracker = _tracker()
    report = tracker.compute_strategy_report("momentum")
    assert report.total_trades == 0
    assert report.win_rate == 0.0
    assert report.capture_rate == 0.0


def test_compute_strategy_report_with_trades(temp_db):
    tracker = _tracker()
    now = datetime.datetime.utcnow().isoformat()
    # Record 3 closed momentum trades
    for i, (pnl, status) in enumerate([(10.0, "closed_win"), (5.0, "closed_win"), (-8.0, "closed_loss")]):
        tracker.record_trade_open(
            trade_id=i + 1, strategy="momentum", market_id=f"mkt-{i}",
            direction="YES", entry_price=0.50, expected_edge=0.10,
            amount_usd=50.0, confidence=0.70,
        )
        tracker.record_trade_close(
            trade_id=i + 1, exit_price=0.50 + pnl / 100,
            realized_pnl=pnl, status=status,
        )

    report = tracker.compute_strategy_report("momentum")
    assert report.total_trades == 3
    assert report.wins == 2
    assert report.losses == 1
    assert report.win_rate == pytest.approx(2 / 3)
    assert report.total_pnl == pytest.approx(7.0)
    assert report.capture_rate > 0


def test_tournament_with_no_data(temp_db):
    tracker = _tracker()
    reports = tracker.run_tournament()
    # All strategies get equal allocation
    for r in reports:
        assert r.allocation_pct == pytest.approx(1.0 / len(tracker.ALL_STRATEGIES))


def test_tournament_allocates_to_performers(temp_db):
    tracker = _tracker()
    # Seed a strong momentum strategy with varied returns (so stdev > 0)
    momentum_pnls = [7.5, 5.0, 10.0, 3.0, 8.0, 6.0, 9.0, 4.0, 7.0, 12.0]
    for i, pnl in enumerate(momentum_pnls):
        tracker.record_trade_open(
            trade_id=100 + i, strategy="momentum", market_id=f"mkt-m{i}",
            direction="YES", entry_price=0.40, expected_edge=0.15,
            amount_usd=50.0, confidence=0.80,
        )
        tracker.record_trade_close(
            trade_id=100 + i, exit_price=0.40 + pnl / 100,
            realized_pnl=pnl, status="closed_win",
        )

    # Seed a weak arbitrage strategy — all losses
    for i in range(10):
        tracker.record_trade_open(
            trade_id=200 + i, strategy="arbitrage", market_id=f"mkt-a{i}",
            direction="YES", entry_price=0.48, expected_edge=0.03,
            amount_usd=50.0, confidence=0.60,
        )
        tracker.record_trade_close(
            trade_id=200 + i, exit_price=0.47,
            realized_pnl=-0.5, status="closed_loss",
        )

    reports = tracker.run_tournament()
    allocs = {r.strategy: r.allocation_pct for r in reports}

    # Momentum (all wins, positive Sharpe) should get more than arbitrage (all losses)
    assert allocs["momentum"] > allocs["arbitrage"]


def test_get_strategy_allocation_returns_dict(temp_db):
    tracker = _tracker()
    allocs = tracker.get_strategy_allocation()
    assert isinstance(allocs, dict)
    assert "momentum" in allocs
    assert "arbitrage" in allocs
    total = sum(allocs.values())
    assert total == pytest.approx(1.0)


def test_snapshot_stats_writes_to_db(temp_db):
    tracker = _tracker()
    # Seed some data
    tracker.record_trade_open(
        trade_id=1, strategy="momentum", market_id="mkt-1",
        direction="YES", entry_price=0.50, expected_edge=0.10,
        amount_usd=50.0, confidence=0.70,
    )
    tracker.record_trade_close(
        trade_id=1, exit_price=0.60, realized_pnl=10.0, status="closed_win",
    )

    tracker.snapshot_stats()

    conn = sqlite3.connect(temp_db)
    rows = conn.execute("SELECT * FROM strategy_stats").fetchall()
    conn.close()
    assert len(rows) >= 1


def test_capture_rate_calculation(temp_db):
    """Capture rate = realized_pnl_total / (expected_edge * amount_usd total)."""
    tracker = _tracker()

    # Trade with expected_edge=0.10, amount=100 → expected_pnl = $10
    # Realized $8 → capture_rate = 8/10 = 0.80
    tracker.record_trade_open(
        trade_id=1, strategy="price_lag_arb", market_id="mkt-1",
        direction="YES", entry_price=0.40, expected_edge=0.10,
        amount_usd=100.0, confidence=0.80,
    )
    tracker.record_trade_close(
        trade_id=1, exit_price=0.48, realized_pnl=8.0, status="closed_win",
    )

    report = tracker.compute_strategy_report("price_lag_arb")
    assert report.capture_rate == pytest.approx(0.80)
