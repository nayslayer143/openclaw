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
    yield db


def _dq():
    import sys
    for mod in list(sys.modules.keys()):
        if "data_quality" in mod:
            del sys.modules[mod]
    import scripts.mirofish.data_quality as dq
    return dq


def _seed_snapshots(db_path: str, rows: list[dict]) -> None:
    conn = sqlite3.connect(db_path)
    for r in rows:
        conn.execute("""
            INSERT INTO market_data
            (market_id, question, category, yes_price, no_price, volume, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            r.get("market_id", "m1"),
            r.get("question", "Test?"),
            r.get("category", "crypto"),
            r.get("yes_price", 0.50),
            r.get("no_price", 0.50),
            r.get("volume", 50000),
            r.get("fetched_at", datetime.datetime.utcnow().isoformat()),
        ))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Tests — invalid prices
# ---------------------------------------------------------------------------

def test_valid_prices_no_alerts(temp_db):
    dq = _dq()
    markets = [{"market_id": "m1", "yes_price": 0.50, "no_price": 0.50}]
    alerts = dq.check_invalid_prices(markets)
    assert len(alerts) == 0


def test_negative_price_flagged(temp_db):
    dq = _dq()
    markets = [{"market_id": "m1", "yes_price": -0.10, "no_price": 0.50}]
    alerts = dq.check_invalid_prices(markets)
    assert len(alerts) == 1
    assert alerts[0].alert_type == "invalid_price"
    assert alerts[0].severity == "critical"


def test_price_over_one_flagged(temp_db):
    dq = _dq()
    markets = [{"market_id": "m1", "yes_price": 1.50, "no_price": 0.50}]
    alerts = dq.check_invalid_prices(markets)
    assert len(alerts) >= 1
    assert any(a.alert_type == "invalid_price" for a in alerts)


def test_prices_not_summing_to_one(temp_db):
    dq = _dq()
    markets = [{"market_id": "m1", "yes_price": 0.30, "no_price": 0.30}]
    alerts = dq.check_invalid_prices(markets)
    # yes + no = 0.60, below 0.80 threshold
    assert len(alerts) == 1
    assert alerts[0].alert_type == "invalid_price"
    assert alerts[0].severity == "warning"


# ---------------------------------------------------------------------------
# Tests — price jumps
# ---------------------------------------------------------------------------

def test_price_jump_detected(temp_db):
    dq = _dq()
    # Seed two snapshots: m1 at 0.50, then current at 0.80 (60% jump)
    _seed_snapshots(temp_db, [
        {"market_id": "m1", "yes_price": 0.50, "no_price": 0.50,
         "fetched_at": "2026-03-15T10:00:00"},
        {"market_id": "m1", "yes_price": 0.50, "no_price": 0.50,
         "fetched_at": "2026-03-15T12:00:00"},
    ])
    markets = [{"market_id": "m1", "yes_price": 0.80, "no_price": 0.20}]
    alerts = dq.check_price_jumps(markets)
    assert any(a.alert_type == "price_jump" for a in alerts)


def test_small_price_change_no_alert(temp_db):
    dq = _dq()
    _seed_snapshots(temp_db, [
        {"market_id": "m1", "yes_price": 0.50, "no_price": 0.50,
         "fetched_at": "2026-03-15T10:00:00"},
        {"market_id": "m1", "yes_price": 0.50, "no_price": 0.50,
         "fetched_at": "2026-03-15T12:00:00"},
    ])
    markets = [{"market_id": "m1", "yes_price": 0.52, "no_price": 0.48}]
    alerts = dq.check_price_jumps(markets)
    assert len(alerts) == 0


# ---------------------------------------------------------------------------
# Tests — stuck prices
# ---------------------------------------------------------------------------

def test_stuck_price_detected(temp_db):
    dq = _dq()
    _seed_snapshots(temp_db, [
        {"market_id": "m1", "yes_price": 0.50, "fetched_at": "2026-03-15T10:00:00"},
        {"market_id": "m1", "yes_price": 0.50, "fetched_at": "2026-03-15T12:00:00"},
        {"market_id": "m1", "yes_price": 0.50, "fetched_at": "2026-03-15T14:00:00"},
    ])
    markets = [{"market_id": "m1", "yes_price": 0.50, "no_price": 0.50}]
    alerts = dq.check_stuck_prices(markets)
    assert any(a.alert_type == "stuck_price" for a in alerts)


def test_moving_price_not_stuck(temp_db):
    dq = _dq()
    _seed_snapshots(temp_db, [
        {"market_id": "m1", "yes_price": 0.48, "fetched_at": "2026-03-15T10:00:00"},
        {"market_id": "m1", "yes_price": 0.50, "fetched_at": "2026-03-15T12:00:00"},
        {"market_id": "m1", "yes_price": 0.52, "fetched_at": "2026-03-15T14:00:00"},
    ])
    markets = [{"market_id": "m1", "yes_price": 0.52, "no_price": 0.48}]
    alerts = dq.check_stuck_prices(markets)
    assert len(alerts) == 0


# ---------------------------------------------------------------------------
# Tests — validate_markets + filter
# ---------------------------------------------------------------------------

def test_validate_markets_full(temp_db):
    dq = _dq()
    markets = [
        {"market_id": "good", "yes_price": 0.50, "no_price": 0.50},
        {"market_id": "bad", "yes_price": -0.10, "no_price": 0.50},
    ]
    report = dq.validate_markets(markets)
    assert report.total_markets == 2
    assert len(report.alerts) >= 1
    assert "bad" in report.blocked_ids


def test_filter_tradeable_removes_blocked(temp_db):
    dq = _dq()
    markets = [
        {"market_id": "good", "yes_price": 0.50, "no_price": 0.50},
        {"market_id": "bad", "yes_price": -0.10, "no_price": 0.50},
    ]
    filtered = dq.filter_tradeable(markets)
    ids = [m["market_id"] for m in filtered]
    assert "good" in ids
    assert "bad" not in ids


def test_report_to_dict(temp_db):
    dq = _dq()
    markets = [{"market_id": "m1", "yes_price": 0.50, "no_price": 0.50}]
    report = dq.validate_markets(markets)
    d = report.to_dict()
    assert "checked_at" in d
    assert "alert_count" in d
    assert "markets_blocked" in d
