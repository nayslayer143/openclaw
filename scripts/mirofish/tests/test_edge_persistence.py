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
    import scripts.mirofish.edge_persistence as ep
    ep.migrate()
    yield db


def _ep():
    import sys
    for mod in list(sys.modules.keys()):
        if "edge_persistence" in mod:
            del sys.modules[mod]
    import scripts.mirofish.edge_persistence as ep
    return ep


def test_migrate_creates_tables(temp_db):
    conn = sqlite3.connect(temp_db)
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    conn.close()
    assert "edge_observations" in tables
    assert "edge_halflife" in tables


def test_record_observation(temp_db):
    ep = _ep()
    ep.record_edge_observation("mkt-1", "momentum", 0.10, 0.05, 60.0)
    conn = sqlite3.connect(temp_db)
    rows = conn.execute("SELECT * FROM edge_observations").fetchall()
    conn.close()
    assert len(rows) == 1


def test_halflife_needs_minimum_data(temp_db):
    ep = _ep()
    ep.record_edge_observation("m1", "momentum", 0.10, 0.08, 30.0)
    result = ep.compute_halflife("momentum")
    assert result is None  # need >= 3 observations


def test_halflife_computation(temp_db):
    ep = _ep()
    # Simulate edge decaying over time: 10% → 5% in 60min, etc.
    ep.record_edge_observation("m1", "momentum", 0.10, 0.05, 60.0)
    ep.record_edge_observation("m2", "momentum", 0.12, 0.06, 45.0)
    ep.record_edge_observation("m3", "momentum", 0.08, 0.04, 50.0)
    ep.record_edge_observation("m4", "momentum", 0.15, 0.07, 70.0)

    result = ep.compute_halflife("momentum")
    assert result is not None
    assert result.strategy == "momentum"
    assert result.halflife_min > 0
    assert result.sample_count == 4
    assert result.urgency in ("high", "medium", "low")


def test_halflife_persisted(temp_db):
    ep = _ep()
    ep.record_edge_observation("m1", "arb", 0.05, 0.02, 20.0)
    ep.record_edge_observation("m2", "arb", 0.04, 0.01, 15.0)
    ep.record_edge_observation("m3", "arb", 0.06, 0.02, 25.0)

    ep.compute_halflife("arb")

    conn = sqlite3.connect(temp_db)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM edge_halflife WHERE strategy='arb'").fetchone()
    conn.close()
    assert row is not None
    assert row["halflife_min"] > 0


def test_urgency_lookup(temp_db):
    ep = _ep()
    # Default when no data
    assert ep.get_urgency("unknown") == "medium"


def test_lifetime_to_dict(temp_db):
    ep = _ep()
    ep.record_edge_observation("m1", "test", 0.10, 0.05, 60.0)
    ep.record_edge_observation("m2", "test", 0.12, 0.06, 45.0)
    ep.record_edge_observation("m3", "test", 0.08, 0.04, 50.0)

    result = ep.compute_halflife("test")
    assert result is not None
    d = result.to_dict()
    assert "halflife_min" in d
    assert "urgency" in d
