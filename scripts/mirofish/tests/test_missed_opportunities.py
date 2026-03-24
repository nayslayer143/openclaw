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
    import scripts.mirofish.missed_opportunities as mo
    mo.migrate()
    yield db


def _mo():
    import sys
    for mod in list(sys.modules.keys()):
        if "missed_opportunities" in mod:
            del sys.modules[mod]
    import scripts.mirofish.missed_opportunities as mo
    return mo


def test_migrate_creates_table(temp_db):
    conn = sqlite3.connect(temp_db)
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    conn.close()
    assert "missed_opportunities" in tables


def test_record_missed(temp_db):
    mo = _mo()
    mo.record_missed("mkt-1", "YES", "momentum", 0.50, 0.15, 50.0, "kelly_negative")
    conn = sqlite3.connect(temp_db)
    rows = conn.execute("SELECT * FROM missed_opportunities").fetchall()
    conn.close()
    assert len(rows) == 1


def test_resolve_with_market_data(temp_db):
    mo = _mo()
    mo.record_missed("mkt-1", "YES", "momentum", 0.50, 0.15, 50.0, "cap_exceeded")

    # Seed market data with current price
    conn = sqlite3.connect(temp_db)
    conn.execute("""
        INSERT INTO market_data
        (market_id, question, category, yes_price, no_price, volume, fetched_at)
        VALUES ('mkt-1', 'Test?', 'crypto', 0.65, 0.35, 50000, ?)
    """, (datetime.datetime.utcnow().isoformat(),))
    conn.commit()
    conn.close()

    resolved = mo.resolve_missed_opportunities()
    assert resolved == 1

    conn = sqlite3.connect(temp_db)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM missed_opportunities WHERE id=1").fetchone()
    conn.close()
    assert row["status"] == "resolved"
    assert row["counterfactual_pnl"] > 0  # price went up, YES was right


def test_summary_computation(temp_db):
    mo = _mo()
    # Record and resolve two missed opps
    mo.record_missed("m1", "YES", "momentum", 0.40, 0.15, 50.0, "cap")
    mo.record_missed("m2", "YES", "momentum", 0.50, 0.10, 50.0, "kelly")

    conn = sqlite3.connect(temp_db)
    now = datetime.datetime.utcnow().isoformat()
    conn.execute("""
        INSERT INTO market_data (market_id, question, category, yes_price, no_price, volume, fetched_at)
        VALUES ('m1', 'T1', 'c', 0.55, 0.45, 1000, ?)
    """, (now,))
    conn.execute("""
        INSERT INTO market_data (market_id, question, category, yes_price, no_price, volume, fetched_at)
        VALUES ('m2', 'T2', 'c', 0.45, 0.55, 1000, ?)
    """, (now,))
    conn.commit()
    conn.close()

    mo.resolve_missed_opportunities()
    summaries = mo.get_summary("momentum")
    assert len(summaries) == 1
    assert summaries[0].total_missed == 2


def test_summary_empty(temp_db):
    mo = _mo()
    summaries = mo.get_summary()
    assert summaries == []
