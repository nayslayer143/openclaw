# tests/test_crucix_feed.py
from __future__ import annotations
import datetime
import sqlite3
import requests
import pytest
from unittest.mock import patch, MagicMock


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


def _cf():
    """Re-import crucix_feed with clean state."""
    import sys
    for mod in list(sys.modules.keys()):
        if "crucix_feed" in mod:
            del sys.modules[mod]
    import scripts.mirofish.crucix_feed as cf
    return cf


def test_crucix_signals_table_exists(temp_db):
    conn = sqlite3.connect(temp_db)
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='crucix_signals'"
    ).fetchone()
    conn.close()
    assert row is not None, "crucix_signals table should exist after migration"


def test_module_interface_exists(temp_db):
    cf = _cf()
    assert cf.source_name == "crucix"
    assert callable(cf.fetch)
    assert callable(cf.get_cached)


def test_build_health_map_and_filtering(temp_db):
    cf = _cf()
    health = [
        {"n": "GDELT", "err": False, "stale": False},
        {"n": "FRED", "err": True, "stale": False},
        {"n": "NOAA", "err": False, "stale": True},
        {"n": "ACLED", "err": False, "stale": False},
    ]
    hmap = cf._build_health_map(health)
    assert cf._is_source_healthy(hmap, "gdelt") is True
    assert cf._is_source_healthy(hmap, "GDELT") is True
    assert cf._is_source_healthy(hmap, "fred") is False   # err=True
    assert cf._is_source_healthy(hmap, "noaa") is False    # stale=True
    assert cf._is_source_healthy(hmap, "acled") is True
    assert cf._is_source_healthy(hmap, "unknown") is True  # missing → assume healthy
