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


# ---------------------------------------------------------------------------
# Task 10: Priority scoring + _normalize_all
# ---------------------------------------------------------------------------

def test_priority_scoring_and_cap(temp_db):
    cf = _cf()
    # Create signals with known priorities
    signals = [
        {"source": "crucix_delta", "signal_type": "critical_change", "ticker": "META:VIX"},
        {"source": "crucix_ideas", "signal_type": "crucix_idea", "ticker": "IDEA:1"},
        {"source": "tSignals", "signal_type": "military_strike", "ticker": "MIL:STRIKE"},
        {"source": "telegram", "signal_type": "urgent_intel", "ticker": "GEO:TG"},
        {"source": "gdelt", "signal_type": "conflict_event", "ticker": "GEO:GLOBAL"},
    ]
    scored = cf._sort_by_priority(signals)
    # Delta critical (100) > ideas (90) > tSignals (80) > telegram (70) > gdelt (10)
    assert scored[0]["source"] == "crucix_delta"
    assert scored[1]["source"] == "crucix_ideas"
    assert scored[2]["source"] == "tSignals"
    assert scored[3]["source"] == "telegram"
    assert scored[4]["source"] == "gdelt"


def test_normalize_all_combines_domains(temp_db):
    cf = _cf()
    data = {
        "gdelt": {"conflicts": 42, "crisis": 5, "totalArticles": 100,
                   "geoPoints": [{"name": "Kyiv", "count": 12}]},
        "acled": {"deadliestEvents": []},
        "tg": {"urgent": []},
        "fred": [], "energy": {}, "treasury": {}, "bls": [],
        "gscpi": {}, "markets": {},
        "thermal": [], "tSignals": [], "air": [], "space": {}, "sdr": {},
        "noaa": {}, "nuke": [], "nukeSignals": [], "epa": {}, "who": [],
        "chokepoints": [],
        "delta": {"summary": {"direction": "risk-off", "criticalChanges": 1},
                  "signals": []},
        "ideas": [],
        "health": [{"n": "GDELT", "err": False, "stale": False}],
    }
    signals = cf._normalize_all(data)
    assert isinstance(signals, list)
    assert len(signals) >= 2  # At minimum: GDELT conflict + regime signal
    # All signals have required keys
    required = {"source", "ticker", "signal_type", "direction", "description", "fetched_at"}
    for s in signals:
        assert required.issubset(s.keys()), f"Missing keys in {s}"


# ---------------------------------------------------------------------------
# Task 11: Caching layer
# ---------------------------------------------------------------------------

def test_store_and_retrieve_cached(temp_db):
    cf = _cf()
    signals = [{
        "source": "gdelt", "ticker": "GEO:KYIV", "signal_type": "conflict_event",
        "direction": "bearish", "amount_usd": None,
        "description": "test signal", "fetched_at": datetime.datetime.utcnow().isoformat(),
    }]
    cf._store_signals(signals)
    cached = cf.get_cached()
    assert len(cached) >= 1
    assert cached[0]["ticker"] == "GEO:KYIV"


def test_old_signals_purged(temp_db):
    import sqlite3 as sql
    cf = _cf()
    # Insert a signal from 25 hours ago
    old_time = (datetime.datetime.utcnow() - datetime.timedelta(hours=25)).isoformat()
    conn = sql.connect(temp_db)
    conn.execute("""
        INSERT INTO crucix_signals
        (source, ticker, signal_type, direction, amount_usd, description, fetched_at)
        VALUES ('gdelt', 'GEO:OLD', 'conflict_event', 'bearish', NULL, 'old signal', ?)
    """, (old_time,))
    conn.commit()
    conn.close()

    # Purge should remove it
    cf._purge_old_signals()
    cached = cf.get_cached()
    old = [s for s in cached if s["ticker"] == "GEO:OLD"]
    assert len(old) == 0


def test_cache_freshness(temp_db):
    cf = _cf()
    # Empty DB → not fresh
    assert cf._is_cache_fresh() is False
    # Insert recent signal → fresh
    cf._store_signals([{
        "source": "test", "ticker": "TEST:1", "signal_type": "test",
        "direction": "neutral", "amount_usd": None,
        "description": "test", "fetched_at": datetime.datetime.utcnow().isoformat(),
    }])
    assert cf._is_cache_fresh() is True


# ---------------------------------------------------------------------------
# Task 12: fetch() — full implementation
# ---------------------------------------------------------------------------

def test_fetch_integration_with_mock(temp_db, monkeypatch):
    cf = _cf()
    sample_response = {
        "gdelt": {"conflicts": 5, "crisis": 1, "totalArticles": 50,
                   "geoPoints": [{"name": "Kyiv", "count": 3}]},
        "acled": {"deadliestEvents": []},
        "tg": {"urgent": []},
        "fred": [], "energy": {}, "treasury": {}, "bls": [],
        "gscpi": {}, "markets": {},
        "thermal": [], "tSignals": [], "air": [], "space": {}, "sdr": {},
        "noaa": {}, "nuke": [], "nukeSignals": [], "epa": {}, "who": [],
        "chokepoints": [],
        "delta": {"summary": {"direction": "mixed", "criticalChanges": 0}, "signals": []},
        "ideas": [],
        "health": [],
        "meta": {"sourcesQueried": 29, "sourcesOk": 29},
    }
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = sample_response

    with patch("requests.get", return_value=mock_resp):
        signals = cf.fetch()

    assert isinstance(signals, list)
    assert len(signals) >= 1
    # Verify signals were cached
    cached = cf.get_cached()
    assert len(cached) >= 1


def test_fetch_crucix_down_returns_empty(temp_db):
    cf = _cf()
    with patch("requests.get", side_effect=requests.exceptions.ConnectionError("refused")):
        signals = cf.fetch()
    assert signals == []


def test_fetch_uses_cache_when_fresh(temp_db):
    cf = _cf()
    # Seed cache
    cf._store_signals([{
        "source": "gdelt", "ticker": "GEO:TEST", "signal_type": "conflict_event",
        "direction": "bearish", "amount_usd": None,
        "description": "cached", "fetched_at": datetime.datetime.utcnow().isoformat(),
    }])
    # Should not hit API
    with patch("requests.get", side_effect=AssertionError("should not hit API")):
        signals = cf.fetch()
    assert len(signals) >= 1
    assert signals[0]["ticker"] == "GEO:TEST"


def test_prompt_two_pass_injection(temp_db):
    import scripts.mirofish.trading_brain as tb
    captured: list[str] = []

    def fake_ollama(prompt: str) -> str:
        captured.append(prompt)
        return "[]"

    idea_signal = {
        "source": "crucix_ideas", "ticker": "IDEA:1",
        "signal_type": "crucix_idea", "direction": "bullish",
        "amount_usd": None, "fetched_at": datetime.datetime.utcnow().isoformat(),
        "description": "[long|Medium|swing] Test Idea — test text",
    }
    regime_signal = {
        "source": "crucix_delta", "ticker": "META:REGIME",
        "signal_type": "regime_signal", "direction": "bearish",
        "amount_usd": None, "fetched_at": datetime.datetime.utcnow().isoformat(),
        "description": "Regime: risk-off | 2 critical changes",
    }
    raw_signal = {
        "source": "gdelt", "ticker": "GEO:UKRAINE",
        "signal_type": "conflict_event", "direction": "bearish",
        "amount_usd": None, "fetched_at": datetime.datetime.utcnow().isoformat(),
        "description": "GDELT: 42 conflicts",
    }
    markets = [{"market_id": "m1", "question": "Test?",
                "yes_price": 0.50, "no_price": 0.50, "volume": 50000}]
    wallet = {"balance": 1000.0, "open_positions": 0}

    with patch.object(tb, "_call_ollama", side_effect=fake_ollama):
        tb.analyze(markets, wallet, signals=[idea_signal, regime_signal, raw_signal])

    assert len(captured) == 1
    prompt = captured[0]
    ideas_pos = prompt.find("OSINT Intelligence Summary")
    raw_pos = prompt.find("Active market signals")
    assert ideas_pos > 0, "Ideas block missing from prompt"
    assert raw_pos > 0, "Raw signals block missing from prompt"
    assert ideas_pos < raw_pos, "Ideas block must appear before raw signals"
    assert "Test Idea" in prompt
    assert "risk-off" in prompt


def test_prompt_no_ideas_omits_block(temp_db):
    import scripts.mirofish.trading_brain as tb
    captured: list[str] = []

    def fake_ollama(prompt: str) -> str:
        captured.append(prompt)
        return "[]"

    raw_signal = {
        "source": "options_flow", "ticker": "NVDA",
        "signal_type": "call_sweep", "direction": "bullish",
        "amount_usd": 2500000, "fetched_at": datetime.datetime.utcnow().isoformat(),
        "description": "NVDA call_sweep $2.5M",
    }
    markets = [{"market_id": "m1", "question": "Test?",
                "yes_price": 0.50, "no_price": 0.50, "volume": 50000}]
    wallet = {"balance": 1000.0, "open_positions": 0}

    with patch.object(tb, "_call_ollama", side_effect=fake_ollama):
        tb.analyze(markets, wallet, signals=[raw_signal])

    prompt = captured[0]
    assert "OSINT Intelligence Summary" not in prompt
    assert "Active market signals" in prompt
    assert "NVDA" in prompt


def test_signal_dict_shape_all_domains(temp_db):
    """Every signal from a full normalize_all pass must have the required keys and types."""
    cf = _cf()
    data = {
        "gdelt": {"conflicts": 20, "crisis": 5, "totalArticles": 500,
                   "geoPoints": [{"name": "Kyiv", "count": 10}]},
        "acled": {"deadliestEvents": [
            {"date": "2026-03-23", "type": "Airstrike", "country": "Syria",
             "location": "Aleppo", "fatalities": 10}]},
        "tg": {"urgent": [{"channel": "test", "text": "Breaking news",
                            "views": 1000, "urgentFlags": ["breaking"]}]},
        "fred": [{"id": "VIXCLS", "label": "VIX", "value": 25, "momChangePct": 12.0,
                  "momChange": 3.0, "recent": [22, 25]}],
        "energy": {"signals": [{"type": "SPIKE", "severity": "high", "value": 100}]},
        "treasury": {"signals": [{"type": "DEBT_MILESTONE", "severity": "high",
                                   "threshold": 36000000000000}]},
        "bls": [], "gscpi": {"value": 1.5, "interpretation": "High"},
        "markets": {"crypto": [{"symbol": "BTC-USD", "name": "BTC",
                                 "price": 42000, "changePct": 5.0, "change": 2000}],
                    "indexes": [], "commodities": []},
        "thermal": [{"region": "Ukraine", "det": 100, "hc": 50, "fires": []}],
        "tSignals": [{"type": "MILITARY_STRIKE", "confidence": 0.95, "lat": 48, "lon": 37}],
        "air": [{"region": "Eastern Europe", "total": 50, "noCallsign": 15}],
        "space": {"signals": [{"type": "MILSAT", "country": "China", "count": 2}],
                  "recentLaunches": [{"name": "Falcon 9", "country": "US"}]},
        "sdr": {},
        "noaa": {"alerts": [{"event": "Tornado", "severity": "Extreme",
                              "headline": "Tornado warning"}]},
        "nuke": [], "nukeSignals": [{"type": "ELEVATED", "location": "Test",
                                      "cpm": 900, "severity": "high"}],
        "epa": {}, "who": [{"title": "Outbreak", "summary": "test"}],
        "chokepoints": [{"label": "Suez Canal", "note": "key route"}],
        "delta": {"summary": {"direction": "risk-off", "criticalChanges": 1},
                  "signals": [{"type": "VIX_SPIKE", "severity": "critical",
                               "from": 20, "to": 25}]},
        "ideas": [{"title": "Test", "text": "test idea", "type": "long",
                   "confidence": "High", "horizon": "swing"}],
        "health": [],
    }
    signals = cf._normalize_all(data)
    assert len(signals) > 0

    required_keys = {"source", "ticker", "signal_type", "direction", "description", "fetched_at"}
    valid_directions = {"bullish", "bearish", "neutral"}

    for s in signals:
        missing = required_keys - set(s.keys())
        assert not missing, f"Signal missing keys {missing}: {s}"
        assert s["direction"] in valid_directions, f"Bad direction '{s['direction']}' in {s}"
        assert isinstance(s["ticker"], str) and len(s["ticker"]) > 0
        assert isinstance(s["description"], str) and len(s["description"]) > 0
        assert "amount_usd" in s
