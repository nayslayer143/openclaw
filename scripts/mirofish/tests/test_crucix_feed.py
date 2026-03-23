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


def test_normalize_meta_regime_signal(temp_db):
    cf = _cf()
    data = {
        "delta": {
            "summary": {"totalChanges": 5, "criticalChanges": 2, "direction": "risk-off"},
            "signals": [
                {"type": "VIX_SPIKE", "severity": "critical", "from": 16.2, "to": 18.5}
            ],
        },
        "ideas": [
            {
                "title": "Conflict-Energy Nexus",
                "text": "4 urgent conflict signals with WTI at $72.45",
                "type": "long",
                "confidence": "Medium",
                "horizon": "swing",
            }
        ],
        "health": [],
    }
    signals = cf._normalize_meta(data)

    # Should have: 1 regime, 1 critical change, 1 idea = 3 signals
    assert len(signals) == 3

    regime = [s for s in signals if s["signal_type"] == "regime_signal"]
    assert len(regime) == 1
    assert regime[0]["source"] == "crucix_delta"
    assert regime[0]["ticker"] == "META:REGIME"
    assert regime[0]["direction"] == "bearish"  # risk-off → bearish

    critical = [s for s in signals if s["signal_type"] == "critical_change"]
    assert len(critical) == 1
    assert critical[0]["source"] == "crucix_delta"
    assert critical[0]["ticker"] == "META:VIX_SPIKE"
    assert critical[0]["direction"] == "bearish"

    ideas = [s for s in signals if s["signal_type"] == "crucix_idea"]
    assert len(ideas) == 1
    assert ideas[0]["source"] == "crucix_ideas"
    assert ideas[0]["ticker"] == "IDEA:1"
    assert ideas[0]["direction"] == "bullish"  # long → bullish
    assert "Conflict-Energy Nexus" in ideas[0]["description"]


def test_normalize_geopolitical(temp_db):
    cf = _cf()
    data = {
        "gdelt": {
            "totalArticles": 2145, "conflicts": 42, "crisis": 23,
            "topTitles": ["Ukraine military reports new ops"],
            "geoPoints": [{"lat": 50.4, "lon": 30.5, "name": "Kyiv", "count": 12}],
        },
        "acled": {
            "totalEvents": 156, "totalFatalities": 3421,
            "deadliestEvents": [{
                "date": "2026-03-23", "type": "Airstrike", "country": "Syria",
                "location": "Aleppo", "fatalities": 47, "lat": 36.2, "lon": 37.2,
            }],
        },
        "tg": {
            "posts": 4521,
            "urgent": [{
                "channel": "intelslava", "text": "Breaking: Military movement confirmed",
                "views": 12500, "date": "2026-03-23T14:30:00Z",
                "urgentFlags": ["breaking", "military"],
            }],
        },
    }
    signals = cf._normalize_geopolitical(data)
    assert len(signals) >= 3

    # Check GDELT signal
    gdelt = [s for s in signals if s["source"] == "gdelt"]
    assert len(gdelt) >= 1
    assert gdelt[0]["ticker"].startswith("GEO:")
    assert gdelt[0]["direction"] == "bearish"  # 42 conflicts

    # Check ACLED signal
    acled = [s for s in signals if s["source"] == "acled"]
    assert len(acled) >= 1
    assert acled[0]["ticker"] == "GEO:SYRIA"
    assert acled[0]["signal_type"] == "airstrike"
    assert acled[0]["direction"] == "bearish"

    # Check Telegram urgent
    tg = [s for s in signals if s["source"] == "telegram"]
    assert len(tg) >= 1
    assert tg[0]["ticker"] == "GEO:TELEGRAM"
    assert tg[0]["direction"] == "bearish"


def test_normalize_economic(temp_db):
    cf = _cf()
    data = {
        "fred": [
            {"id": "VIXCLS", "label": "VIX", "value": 22.5, "date": "2026-03-23",
             "momChange": 2.3, "momChangePct": 11.4, "recent": [20.2, 22.5]},
            {"id": "UNRATE", "label": "Unemployment Rate", "value": 4.1,
             "date": "2026-03-23", "momChange": 0.01, "momChangePct": 0.2, "recent": [4.09, 4.1]},
        ],
        "energy": {
            "wti": 72.45, "brent": 76.20, "natgas": 2.85,
            "signals": [{"type": "INVENTORY_SPIKE", "severity": "medium", "value": 421500}],
        },
        "treasury": {
            "totalDebt": "36450000000000",
            "signals": [{"type": "DEBT_MILESTONE", "severity": "high", "threshold": 36000000000000}],
        },
        "bls": [{"id": "UNRATE", "label": "Unemployment Rate", "value": 4.1,
                  "momChange": 0.05, "momChangePct": 1.23}],
        "gscpi": {"value": 1.5, "interpretation": "High pressure"},
        "markets": {
            "crypto": [{"symbol": "BTC-USD", "name": "Bitcoin", "price": 42350,
                        "change": 1200, "changePct": 2.92}],
            "indexes": [{"symbol": "^GSPC", "name": "S&P 500", "price": 4278.5,
                         "change": -45.1, "changePct": -1.04}],
            "commodities": [],
            "vix": {"value": 22.5, "change": 2.3, "changePct": 11.4},
        },
    }
    signals = cf._normalize_economic(data)

    # VIX at 22.5 with 11.4% MoM should trigger
    vix = [s for s in signals if "VIXCLS" in s["ticker"]]
    assert len(vix) >= 1
    assert vix[0]["direction"] == "bearish"  # VIX > 20

    # UNRATE with 0.2% MoM should NOT trigger (below 3% threshold)
    unrate_fred = [s for s in signals if s["source"] == "fred" and "UNRATE" in s["ticker"]]
    assert len(unrate_fred) == 0

    # Energy inventory signal
    energy = [s for s in signals if s["source"] == "energy"]
    assert len(energy) >= 1

    # Treasury debt milestone
    treasury = [s for s in signals if s["source"] == "treasury"]
    assert len(treasury) >= 1
    assert treasury[0]["direction"] == "bearish"

    # GSCPI > 1.0 → bearish
    gscpi = [s for s in signals if "SUPPLY_CHAIN" in s["ticker"]]
    assert len(gscpi) == 1
    assert gscpi[0]["direction"] == "bearish"


def test_normalize_military(temp_db):
    cf = _cf()
    data = {
        "thermal": [{"region": "Ukraine", "det": 245, "hc": 189,
                      "fires": [{"lat": 48.5, "lon": 38.2, "frp": 15.3}]}],
        "tSignals": [{"type": "MILITARY_STRIKE", "confidence": 0.92,
                       "lat": 48.1, "lon": 37.8}],
        "air": [{"region": "Eastern Europe", "total": 47, "noCallsign": 12}],
        "space": {
            "signals": [{"type": "MILITARY_SAT_DEPLOYMENT", "country": "China", "count": 3}],
            "recentLaunches": [{"name": "Falcon 9", "country": "United States",
                                 "epoch": "2026-03-22T15:30:00Z"}],
        },
        "sdr": {"total": 456, "online": 423, "zones": []},
    }
    signals = cf._normalize_military(data)

    # tSignals with confidence > 0.8 should generate a signal
    strikes = [s for s in signals if s["signal_type"] == "military_strike"]
    assert len(strikes) == 1
    assert strikes[0]["ticker"] == "MIL:STRIKE"
    assert strikes[0]["direction"] == "bearish"

    # Thermal fires
    thermal = [s for s in signals if s["source"] == "thermal"]
    assert len(thermal) >= 1

    # Air unidentified
    air = [s for s in signals if s["source"] == "air"]
    assert len(air) >= 1
    assert air[0]["ticker"] == "AIR:EASTERN_EUROPE"

    # Space military sat deployment
    space = [s for s in signals if s["signal_type"] == "satellite_deployment"]
    assert len(space) >= 1


def test_normalize_environmental(temp_db):
    cf = _cf()
    data = {
        "noaa": {
            "totalAlerts": 3,
            "alerts": [
                {"event": "Tornado Warning", "severity": "Severe",
                 "headline": "Tornado Warning for parts of Texas"},
                {"event": "Winter Advisory", "severity": "Minor",
                 "headline": "Light snow expected"},
            ],
        },
        "nuke": [{"site": "Fukushima", "anom": False, "cpm": 125}],
        "nukeSignals": [{"type": "ELEVATED_READING", "location": "Chernobyl",
                          "cpm": 850, "severity": "high"}],
        "epa": {"totalReadings": 1, "stations": []},
        "who": [{"title": "MERS update", "date": "2026-03-21",
                  "summary": "7 new cases in Saudi Arabia"}],
    }
    signals = cf._normalize_environmental(data)

    # Only Severe/Extreme NOAA alerts
    noaa = [s for s in signals if s["source"] == "noaa"]
    assert len(noaa) == 1  # Tornado (Severe) yes, Winter Advisory (Minor) no
    assert noaa[0]["direction"] == "bearish"

    # nukeSignals always bearish
    nuke = [s for s in signals if s["signal_type"] == "radiation_anomaly"]
    assert len(nuke) == 1
    assert nuke[0]["direction"] == "bearish"

    # Non-anomalous nuke sites should NOT generate signals
    nuke_readings = [s for s in signals if s["signal_type"] == "radiation_reading"]
    assert len(nuke_readings) == 0  # anom=False → skipped

    # WHO outbreak
    who = [s for s in signals if s["source"] == "who"]
    assert len(who) == 1
    assert who[0]["direction"] == "bearish"


def test_normalize_maritime(temp_db):
    cf = _cf()
    data = {
        "chokepoints": [
            {"label": "Strait of Hormuz", "note": "Persian Gulf gateway",
             "lat": 26.5, "lon": 56.0},
        ],
    }
    signals = cf._normalize_maritime(data)
    assert len(signals) == 1
    assert signals[0]["ticker"] == "SEA:STRAIT_OF_HORMUZ"
    assert signals[0]["direction"] == "neutral"
