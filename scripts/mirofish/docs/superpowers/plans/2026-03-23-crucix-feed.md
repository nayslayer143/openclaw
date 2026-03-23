# Crucix OSINT Feed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `crucix_feed.py` DataFeed module that fetches all 29 OSINT sources from the local Crucix API, normalizes them into the standard signal dict shape, and injects them into the Ollama prompt via two-pass format.

**Architecture:** Single-file module (`crucix_feed.py`) with six internal domain normalizer functions, priority scoring, TTL-based SQLite caching, and graceful degradation. Integrates into the existing `simulator.py` run loop and `trading_brain.py` prompt builder.

**Tech Stack:** Python 3.10+, requests, sqlite3, pytest

**Spec:** `docs/superpowers/specs/2026-03-23-crucix-feed-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `crucix_feed.py` | **Create** | Crucix DataFeed module — fetch, normalize, cache, export |
| `tests/test_crucix_feed.py` | **Create** | All unit + integration tests for the feed |
| `simulator.py` | **Edit** (lines 23-91, 102-132) | Add migration SQL + import/merge Crucix signals in run_loop |
| `trading_brain.py` | **Edit** (lines 17, 162-179) | Add MERGED_SIGNAL_LIMIT + two-pass prompt injection |
| `tests/test_uw_feed.py` | **Edit** (line 142) | Remove "Unusual Whales" assertion (now redundant with line 140) |

---

### Task 1: DB Migration — Add `crucix_signals` table

**Files:**
- Modify: `simulator.py:75-91` (append to MIGRATION_SQL)

- [ ] **Step 1: Write the failing test**

File: `tests/test_crucix_feed.py`

```python
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


def test_crucix_signals_table_exists(temp_db):
    conn = sqlite3.connect(temp_db)
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='crucix_signals'"
    ).fetchone()
    conn.close()
    assert row is not None, "crucix_signals table should exist after migration"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/openclaw && python -m pytest scripts/mirofish/tests/test_crucix_feed.py::test_crucix_signals_table_exists -v`
Expected: FAIL — table does not exist yet

- [ ] **Step 3: Add migration SQL to simulator.py**

In `simulator.py`, append after the `uw_signals` block (after line 87, before `INSERT OR IGNORE INTO context`):

```sql
CREATE TABLE IF NOT EXISTS crucix_signals (
    id          INTEGER PRIMARY KEY,
    source      TEXT NOT NULL,
    ticker      TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    direction   TEXT NOT NULL,
    amount_usd  REAL,
    description TEXT NOT NULL,
    fetched_at  TEXT NOT NULL,
    UNIQUE (source, ticker, signal_type, fetched_at)
);
CREATE INDEX IF NOT EXISTS idx_crucix_signals_ticker_time
    ON crucix_signals(ticker, fetched_at);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/openclaw && python -m pytest scripts/mirofish/tests/test_crucix_feed.py::test_crucix_signals_table_exists -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd ~/openclaw
git add scripts/mirofish/simulator.py scripts/mirofish/tests/test_crucix_feed.py
git commit -m "feat(mirofish): add crucix_signals table migration"
```

---

### Task 2: Module scaffold — config, _get_conn, interface stubs

**Files:**
- Create: `crucix_feed.py`
- Test: `tests/test_crucix_feed.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_crucix_feed.py`:

```python
def _cf():
    """Re-import crucix_feed with clean state."""
    import sys
    for mod in list(sys.modules.keys()):
        if "crucix_feed" in mod:
            del sys.modules[mod]
    import scripts.mirofish.crucix_feed as cf
    return cf


def test_module_interface_exists(temp_db):
    cf = _cf()
    assert cf.source_name == "crucix"
    assert callable(cf.fetch)
    assert callable(cf.get_cached)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/openclaw && python -m pytest scripts/mirofish/tests/test_crucix_feed.py::test_module_interface_exists -v`
Expected: FAIL — module does not exist

- [ ] **Step 3: Create crucix_feed.py scaffold**

File: `crucix_feed.py`

```python
#!/usr/bin/env python3
"""
Crucix OSINT feed — fetches all 29 intelligence sources from the local
Crucix Express.js API (/api/data), normalizes into the standard signal
dict shape, caches to crucix_signals SQLite table.

Duck-type compatible with DataFeed protocol (base_feed.py) via module-level
fetch() and get_cached(). isinstance(this_module, DataFeed) will return False —
callers must duck-type against the module, not use isinstance().
"""
from __future__ import annotations
import os
import sqlite3
import datetime
import requests
from pathlib import Path

source_name = "crucix"

CRUCIX_BASE_URL = os.environ.get("CRUCIX_BASE_URL", "http://localhost:3117")
CRUCIX_CACHE_TTL_HOURS = float(os.environ.get("CRUCIX_CACHE_TTL_HOURS", "0.25"))
CRUCIX_SIGNAL_LIMIT = int(os.environ.get("CRUCIX_SIGNAL_LIMIT", "20"))
CRUCIX_TIMEOUT = 30


def _get_conn() -> sqlite3.Connection:
    db_path = Path(os.environ.get("CLAWMSON_DB_PATH",
                                   Path.home() / ".openclaw" / "clawmson.db"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _now_iso() -> str:
    return datetime.datetime.utcnow().isoformat()


def get_cached() -> list[dict]:
    """Return signals from crucix_signals fetched within CRUCIX_CACHE_TTL_HOURS."""
    cutoff = (datetime.datetime.utcnow() -
              datetime.timedelta(hours=CRUCIX_CACHE_TTL_HOURS)).isoformat()
    try:
        with _get_conn() as conn:
            rows = conn.execute("""
                SELECT source, ticker, signal_type, direction, amount_usd,
                       description, fetched_at
                FROM crucix_signals WHERE fetched_at > ?
                ORDER BY fetched_at DESC
            """, (cutoff,)).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"[crucix_feed] Cache read error: {e}")
        return []


def fetch() -> list[dict]:
    """Fetch from Crucix /api/data, normalize all sources, cache, return signals."""
    # Stub — will be implemented in Task 12
    return []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/openclaw && python -m pytest scripts/mirofish/tests/test_crucix_feed.py::test_module_interface_exists -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd ~/openclaw
git add scripts/mirofish/crucix_feed.py scripts/mirofish/tests/test_crucix_feed.py
git commit -m "feat(mirofish): crucix_feed module scaffold with config and stubs"
```

---

### Task 3: Health filtering utility

**Files:**
- Modify: `crucix_feed.py`
- Test: `tests/test_crucix_feed.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_crucix_feed.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/openclaw && python -m pytest scripts/mirofish/tests/test_crucix_feed.py::test_build_health_map_and_filtering -v`
Expected: FAIL — functions don't exist

- [ ] **Step 3: Implement health filtering in crucix_feed.py**

Add after `_now_iso()`:

```python
def _build_health_map(health: list[dict]) -> dict[str, dict]:
    """Build {lowercase_name: {err, stale}} lookup from Crucix health array."""
    return {
        h.get("n", "").lower(): h
        for h in health
        if h.get("n")
    }


def _is_source_healthy(hmap: dict[str, dict], source_key: str) -> bool:
    """True if source is not errored or stale. Missing sources assumed healthy."""
    entry = hmap.get(source_key.lower())
    if entry is None:
        return True
    return not entry.get("err", False) and not entry.get("stale", False)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/openclaw && python -m pytest scripts/mirofish/tests/test_crucix_feed.py::test_build_health_map_and_filtering -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd ~/openclaw
git add scripts/mirofish/crucix_feed.py scripts/mirofish/tests/test_crucix_feed.py
git commit -m "feat(mirofish): crucix health filtering utility"
```

---

### Task 4: _normalize_meta — delta + ideas

This is the most critical normalizer — it produces the signals that `trading_brain.py` partitions for two-pass injection.

**Files:**
- Modify: `crucix_feed.py`
- Test: `tests/test_crucix_feed.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_crucix_feed.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/openclaw && python -m pytest scripts/mirofish/tests/test_crucix_feed.py::test_normalize_meta_regime_signal -v`
Expected: FAIL

- [ ] **Step 3: Implement _normalize_meta**

Add to `crucix_feed.py`:

```python
_DIRECTION_MAP_REGIME = {"risk-on": "bullish", "risk-off": "bearish", "mixed": "neutral"}
_DIRECTION_MAP_IDEA = {"long": "bullish", "hedge": "bearish", "watch": "neutral"}

# Delta critical change types that imply bearish
_BEARISH_DELTA_TYPES = {
    "VIX_SPIKE", "YIELD_INVERSION", "CREDIT_SPREAD_WIDENING",
    "DEBT_MILESTONE", "INVENTORY_SPIKE", "ELEVATED_READING",
    "MILITARY_SAT_DEPLOYMENT",
}


def _normalize_meta(data: dict) -> list[dict]:
    """Normalize delta summary, delta signals, and ideas into signal dicts.

    IMPORTANT: Uses source="crucix_delta" for delta signals and
    source="crucix_ideas" for idea signals — these exact values are
    required by trading_brain.py for two-pass prompt partitioning.
    """
    signals: list[dict] = []
    now = _now_iso()

    # Delta summary → regime signal
    delta = data.get("delta") or {}
    summary = delta.get("summary") or {}
    direction_raw = summary.get("direction", "mixed")
    if direction_raw:
        changes = summary.get("criticalChanges", summary.get("totalChanges", 0))
        signals.append({
            "source": "crucix_delta",
            "ticker": "META:REGIME",
            "signal_type": "regime_signal",
            "direction": _DIRECTION_MAP_REGIME.get(direction_raw, "neutral"),
            "amount_usd": None,
            "description": (
                f"Regime: {direction_raw} | {changes} critical changes"
            ),
            "fetched_at": now,
        })

    # Delta signals → critical changes
    for sig in delta.get("signals", []):
        sig_type = sig.get("type", "UNKNOWN")
        direction = "bearish" if sig_type in _BEARISH_DELTA_TYPES else "neutral"
        severity = sig.get("severity", "")
        from_val = sig.get("from", "")
        to_val = sig.get("to", "")
        signals.append({
            "source": "crucix_delta",
            "ticker": f"META:{sig_type}",
            "signal_type": "critical_change",
            "direction": direction,
            "amount_usd": None,
            "description": f"{sig_type} ({severity}): {from_val} -> {to_val}",
            "fetched_at": now,
        })

    # Ideas → trade ideas
    for i, idea in enumerate(data.get("ideas") or [], start=1):
        idea_type = idea.get("type", "watch")
        signals.append({
            "source": "crucix_ideas",
            "ticker": f"IDEA:{i}",
            "signal_type": "crucix_idea",
            "direction": _DIRECTION_MAP_IDEA.get(idea_type, "neutral"),
            "amount_usd": None,
            "description": (
                f"[{idea_type}|{idea.get('confidence', '?')}|{idea.get('horizon', '?')}] "
                f"{idea.get('title', '')} — {idea.get('text', '')}"
            ),
            "fetched_at": now,
        })

    return signals
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/openclaw && python -m pytest scripts/mirofish/tests/test_crucix_feed.py::test_normalize_meta_regime_signal -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd ~/openclaw
git add scripts/mirofish/crucix_feed.py scripts/mirofish/tests/test_crucix_feed.py
git commit -m "feat(mirofish): crucix _normalize_meta — delta + ideas normalizer"
```

---

### Task 5: _normalize_geopolitical — GDELT, ACLED, Telegram

**Files:**
- Modify: `crucix_feed.py`
- Test: `tests/test_crucix_feed.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/openclaw && python -m pytest scripts/mirofish/tests/test_crucix_feed.py::test_normalize_geopolitical -v`
Expected: FAIL

- [ ] **Step 3: Implement _normalize_geopolitical**

```python
def _normalize_geopolitical(data: dict) -> list[dict]:
    """Normalize GDELT, ACLED, and Telegram urgent into signal dicts."""
    signals: list[dict] = []
    now = _now_iso()

    # GDELT — aggregate conflict/crisis counts
    gdelt = data.get("gdelt") or {}
    conflicts = gdelt.get("conflicts", 0) or 0
    crisis = gdelt.get("crisis", 0) or 0
    if conflicts > 0 or crisis > 0:
        top_region = "GLOBAL"
        geo_points = gdelt.get("geoPoints") or []
        if geo_points:
            top_region = (geo_points[0].get("name") or "GLOBAL").upper().replace(" ", "_")
        signals.append({
            "source": "gdelt",
            "ticker": f"GEO:{top_region}",
            "signal_type": "conflict_event" if conflicts > crisis else "crisis_event",
            "direction": "bearish" if conflicts > 10 or crisis > 10 else "neutral",
            "amount_usd": None,
            "description": (
                f"GDELT: {conflicts} conflicts, {crisis} crises across "
                f"{gdelt.get('totalArticles', 0)} articles"
            ),
            "fetched_at": now,
        })

    # ACLED — individual deadliest events
    acled = data.get("acled") or {}
    for event in (acled.get("deadliestEvents") or []):
        country = (event.get("country") or "UNKNOWN").upper().replace(" ", "_")
        event_type = (event.get("type") or "conflict").lower().replace(" ", "_").replace("/", "_")
        fatalities = event.get("fatalities", 0) or 0
        signals.append({
            "source": "acled",
            "ticker": f"GEO:{country}",
            "signal_type": event_type,
            "direction": "bearish",
            "amount_usd": None,
            "description": (
                f"ACLED: {event.get('type', '?')} in {event.get('location', '?')}, "
                f"{event.get('country', '?')} — {fatalities} fatalities"
            ),
            "fetched_at": now,
        })

    # Telegram urgent posts
    tg = data.get("tg") or {}
    for post in (tg.get("urgent") or []):
        text = post.get("text", "")[:120]
        channel = post.get("channel", "unknown")
        signals.append({
            "source": "telegram",
            "ticker": "GEO:TELEGRAM",
            "signal_type": "urgent_intel",
            "direction": "bearish",
            "amount_usd": None,
            "description": f"TG @{channel}: {text}",
            "fetched_at": now,
        })

    return signals
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/openclaw && python -m pytest scripts/mirofish/tests/test_crucix_feed.py::test_normalize_geopolitical -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd ~/openclaw
git add scripts/mirofish/crucix_feed.py scripts/mirofish/tests/test_crucix_feed.py
git commit -m "feat(mirofish): crucix _normalize_geopolitical — GDELT/ACLED/Telegram"
```

---

### Task 6: _normalize_economic — FRED, energy, treasury, BLS, GSCPI, markets

**Files:**
- Modify: `crucix_feed.py`
- Test: `tests/test_crucix_feed.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/openclaw && python -m pytest scripts/mirofish/tests/test_crucix_feed.py::test_normalize_economic -v`
Expected: FAIL

- [ ] **Step 3: Implement _normalize_economic**

```python
# IDs where a high value is bearish
_BEARISH_HIGH_INDICATORS = {"VIXCLS", "BAMLH0A0HYM2", "UNRATE", "T10Y2Y"}


def _normalize_economic(data: dict) -> list[dict]:
    """Normalize FRED, energy, treasury, BLS, GSCPI, markets into signal dicts."""
    signals: list[dict] = []
    now = _now_iso()

    # FRED indicators — only emit if momChangePct > 3% (significant move)
    for ind in data.get("fred") or []:
        mom_pct = abs(ind.get("momChangePct") or 0)
        if mom_pct < 3.0:
            continue
        ind_id = ind.get("id", "UNKNOWN")
        value = ind.get("value", 0)
        # Direction logic for bearish-high indicators
        if ind_id in _BEARISH_HIGH_INDICATORS:
            # Each indicator has a "elevated" threshold
            thresholds = {"VIXCLS": 20, "BAMLH0A0HYM2": 4.0, "UNRATE": 5.0, "T10Y2Y": 0}
            threshold = thresholds.get(ind_id, 0)
            direction = "bearish" if value > threshold else "neutral"
        else:
            direction = "neutral"
        signals.append({
            "source": "fred",
            "ticker": f"MACRO:{ind_id}",
            "signal_type": "indicator_spike" if mom_pct > 5 else "indicator_level",
            "direction": direction,
            "amount_usd": None,
            "description": (
                f"{ind.get('label', ind_id)}: {value} "
                f"({'+' if (ind.get('momChange') or 0) >= 0 else ''}"
                f"{ind.get('momChangePct', 0):.1f}% MoM)"
            ),
            "fetched_at": now,
        })

    # Energy signals (pre-computed by Crucix)
    energy = data.get("energy") or {}
    for sig in energy.get("signals") or []:
        signals.append({
            "source": "energy",
            "ticker": f"ENERGY:{sig.get('type', 'UNKNOWN')}",
            "signal_type": "inventory_signal",
            "direction": "bearish",
            "amount_usd": None,
            "description": (
                f"Energy: {sig.get('type', '?')} ({sig.get('severity', '?')}) "
                f"— value: {sig.get('value', '?')}"
            ),
            "fetched_at": now,
        })

    # Treasury debt milestones
    treasury = data.get("treasury") or {}
    for sig in treasury.get("signals") or []:
        signals.append({
            "source": "treasury",
            "ticker": "MACRO:DEBT",
            "signal_type": "debt_milestone",
            "direction": "bearish",
            "amount_usd": None,
            "description": (
                f"US Debt: {sig.get('type', '?')} ({sig.get('severity', '?')}) "
                f"— threshold: ${sig.get('threshold', 0):,.0f}"
            ),
            "fetched_at": now,
        })

    # GSCPI — supply chain pressure
    gscpi = data.get("gscpi") or {}
    gscpi_val = gscpi.get("value")
    if gscpi_val is not None:
        if gscpi_val > 1.0:
            direction = "bearish"
        elif gscpi_val < -0.5:
            direction = "bullish"
        else:
            direction = "neutral"
        signals.append({
            "source": "gscpi",
            "ticker": "MACRO:SUPPLY_CHAIN",
            "signal_type": "supply_chain_pressure",
            "direction": direction,
            "amount_usd": None,
            "description": f"GSCPI: {gscpi_val:.2f} ({gscpi.get('interpretation', '')})",
            "fetched_at": now,
        })

    # BLS labor indicators — only emit if significant MoM change
    for ind in data.get("bls") or []:
        mom_pct = abs(ind.get("momChangePct") or 0)
        if mom_pct < 3.0:
            continue
        ind_id = ind.get("id", "UNKNOWN")
        value = ind.get("value", 0)
        raw_change = ind.get("momChange", 0) or 0
        direction = "bearish" if ind_id == "UNRATE" and raw_change > 0 else "neutral"
        signals.append({
            "source": "bls",
            "ticker": f"MACRO:{ind_id}",
            "signal_type": "labor_signal",
            "direction": direction,
            "amount_usd": None,
            "description": (
                f"BLS {ind.get('label', ind_id)}: {value} "
                f"({'+' if raw_change >= 0 else ''}{mom_pct:.1f}% MoM)"
            ),
            "fetched_at": now,
        })

    # Markets — crypto and indexes with significant moves (>2%)
    markets = data.get("markets") or {}
    for category, prefix in [("crypto", "CRYPTO"), ("indexes", "INDEX"), ("commodities", "COMMODITY")]:
        for item in markets.get(category) or []:
            change_pct = abs(item.get("changePct") or 0)
            if change_pct < 2.0:
                continue
            symbol = (item.get("symbol") or "?").replace("^", "").replace("-USD", "")
            raw_pct = item.get("changePct", 0)
            direction = "bullish" if raw_pct > 0 else "bearish"
            signals.append({
                "source": "markets",
                "ticker": f"{prefix}:{symbol}",
                "signal_type": "price_move",
                "direction": direction,
                "amount_usd": None,
                "description": (
                    f"{item.get('name', symbol)}: ${item.get('price', 0):,.2f} "
                    f"({'+' if raw_pct >= 0 else ''}{raw_pct:.1f}%)"
                ),
                "fetched_at": now,
            })

    return signals
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/openclaw && python -m pytest scripts/mirofish/tests/test_crucix_feed.py::test_normalize_economic -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd ~/openclaw
git add scripts/mirofish/crucix_feed.py scripts/mirofish/tests/test_crucix_feed.py
git commit -m "feat(mirofish): crucix _normalize_economic — FRED/energy/treasury/GSCPI/markets"
```

---

### Task 7: _normalize_military — thermal, tSignals, air, space, SDR

**Files:**
- Modify: `crucix_feed.py`
- Test: `tests/test_crucix_feed.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/openclaw && python -m pytest scripts/mirofish/tests/test_crucix_feed.py::test_normalize_military -v`
Expected: FAIL

- [ ] **Step 3: Implement _normalize_military**

```python
def _normalize_military(data: dict) -> list[dict]:
    """Normalize thermal, tSignals, air, space, SDR into signal dicts."""
    signals: list[dict] = []
    now = _now_iso()

    # Thermal anomalies — high-confidence fire regions
    for region_data in data.get("thermal") or []:
        region = (region_data.get("region") or "UNKNOWN").upper().replace(" ", "_")
        hc = region_data.get("hc", 0) or 0
        if hc > 0:
            signals.append({
                "source": "thermal",
                "ticker": f"MIL:{region}",
                "signal_type": "fire_anomaly",
                "direction": "bearish",
                "amount_usd": None,
                "description": (
                    f"FIRMS {region}: {hc} high-confidence detections, "
                    f"{region_data.get('det', 0)} total"
                ),
                "fetched_at": now,
            })

    # Military strike signals (from Crucix correlation engine)
    for sig in data.get("tSignals") or []:
        confidence = sig.get("confidence", 0) or 0
        if confidence < 0.8:
            continue
        signals.append({
            "source": "tSignals",
            "ticker": "MIL:STRIKE",
            "signal_type": "military_strike",
            "direction": "bearish",
            "amount_usd": None,
            "description": (
                f"Military strike detected (conf={confidence:.2f}) "
                f"at {sig.get('lat', '?')}, {sig.get('lon', '?')}"
            ),
            "fetched_at": now,
        })

    # Air — unidentified aircraft (no callsign)
    for zone in data.get("air") or []:
        no_cs = zone.get("noCallsign", 0) or 0
        if no_cs < 5:
            continue
        region = (zone.get("region") or "UNKNOWN").upper().replace(" ", "_")
        signals.append({
            "source": "air",
            "ticker": f"AIR:{region}",
            "signal_type": "unidentified_aircraft",
            "direction": "bearish",
            "amount_usd": None,
            "description": (
                f"OpenSky {zone.get('region', '?')}: {no_cs} unidentified aircraft "
                f"of {zone.get('total', 0)} total"
            ),
            "fetched_at": now,
        })

    # Space — military satellite deployments
    space = data.get("space") or {}
    for sig in space.get("signals") or []:
        signals.append({
            "source": "space",
            "ticker": "SPACE:MILSAT",
            "signal_type": "satellite_deployment",
            "direction": "bearish",
            "amount_usd": None,
            "description": (
                f"Space: {sig.get('type', '?')} — {sig.get('country', '?')} "
                f"({sig.get('count', '?')} sats)"
            ),
            "fetched_at": now,
        })

    # Space — recent launches (context signal)
    for launch in space.get("recentLaunches") or []:
        signals.append({
            "source": "space",
            "ticker": "SPACE:LAUNCH",
            "signal_type": "launch_event",
            "direction": "neutral",
            "amount_usd": None,
            "description": (
                f"Launch: {launch.get('name', '?')} ({launch.get('country', '?')})"
            ),
            "fetched_at": now,
        })

    # SDR — omitted unless zones have anomalous data (minimal for now)

    return signals
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/openclaw && python -m pytest scripts/mirofish/tests/test_crucix_feed.py::test_normalize_military -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd ~/openclaw
git add scripts/mirofish/crucix_feed.py scripts/mirofish/tests/test_crucix_feed.py
git commit -m "feat(mirofish): crucix _normalize_military — thermal/strikes/air/space"
```

---

### Task 8: _normalize_environmental — NOAA, nuke, nukeSignals, EPA, WHO

**Files:**
- Modify: `crucix_feed.py`
- Test: `tests/test_crucix_feed.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/openclaw && python -m pytest scripts/mirofish/tests/test_crucix_feed.py::test_normalize_environmental -v`
Expected: FAIL

- [ ] **Step 3: Implement _normalize_environmental**

```python
def _normalize_environmental(data: dict) -> list[dict]:
    """Normalize NOAA, nuke, nukeSignals, EPA, WHO into signal dicts."""
    signals: list[dict] = []
    now = _now_iso()

    # NOAA — only Severe or Extreme alerts
    noaa = data.get("noaa") or {}
    for alert in noaa.get("alerts") or []:
        severity = (alert.get("severity") or "").lower()
        if severity not in ("severe", "extreme"):
            continue
        event = (alert.get("event") or "WEATHER").upper().replace(" ", "_")
        signals.append({
            "source": "noaa",
            "ticker": f"ENV:{event}",
            "signal_type": "severe_weather",
            "direction": "bearish",
            "amount_usd": None,
            "description": f"NOAA: {alert.get('headline', alert.get('event', '?'))}",
            "fetched_at": now,
        })

    # Nuke sites — only anomalies
    for site in data.get("nuke") or []:
        if not site.get("anom"):
            continue
        signals.append({
            "source": "nuke",
            "ticker": "ENV:RADIATION",
            "signal_type": "radiation_reading",
            "direction": "bearish",
            "amount_usd": None,
            "description": (
                f"Safecast: Anomaly at {site.get('site', '?')} — "
                f"{site.get('cpm', '?')} CPM"
            ),
            "fetched_at": now,
        })

    # Nuclear signal alerts (always bearish)
    for sig in data.get("nukeSignals") or []:
        signals.append({
            "source": "nukeSignals",
            "ticker": "ENV:RADIATION",
            "signal_type": "radiation_anomaly",
            "direction": "bearish",
            "amount_usd": None,
            "description": (
                f"Nuclear: {sig.get('type', '?')} at {sig.get('location', '?')} — "
                f"{sig.get('cpm', '?')} CPM ({sig.get('severity', '?')})"
            ),
            "fetched_at": now,
        })

    # WHO disease outbreaks
    for outbreak in data.get("who") or []:
        signals.append({
            "source": "who",
            "ticker": "ENV:OUTBREAK",
            "signal_type": "disease_outbreak",
            "direction": "bearish",
            "amount_usd": None,
            "description": f"WHO: {outbreak.get('title', '?')}",
            "fetched_at": now,
        })

    return signals
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/openclaw && python -m pytest scripts/mirofish/tests/test_crucix_feed.py::test_normalize_environmental -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd ~/openclaw
git add scripts/mirofish/crucix_feed.py scripts/mirofish/tests/test_crucix_feed.py
git commit -m "feat(mirofish): crucix _normalize_environmental — NOAA/nuke/WHO"
```

---

### Task 9: _normalize_maritime — chokepoints

**Files:**
- Modify: `crucix_feed.py`
- Test: `tests/test_crucix_feed.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/openclaw && python -m pytest scripts/mirofish/tests/test_crucix_feed.py::test_normalize_maritime -v`
Expected: FAIL

- [ ] **Step 3: Implement _normalize_maritime**

```python
def _normalize_maritime(data: dict) -> list[dict]:
    """Normalize chokepoint data into signal dicts."""
    signals: list[dict] = []
    now = _now_iso()
    for cp in data.get("chokepoints") or []:
        label = (cp.get("label") or "UNKNOWN").upper().replace(" ", "_")
        signals.append({
            "source": "maritime",
            "ticker": f"SEA:{label}",
            "signal_type": "chokepoint_status",
            "direction": "neutral",
            "amount_usd": None,
            "description": f"Chokepoint: {cp.get('label', '?')} — {cp.get('note', '')}",
            "fetched_at": now,
        })
    return signals
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/openclaw && python -m pytest scripts/mirofish/tests/test_crucix_feed.py::test_normalize_maritime -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd ~/openclaw
git add scripts/mirofish/crucix_feed.py scripts/mirofish/tests/test_crucix_feed.py
git commit -m "feat(mirofish): crucix _normalize_maritime — chokepoints"
```

---

### Task 10: Priority scoring + _normalize_all

**Files:**
- Modify: `crucix_feed.py`
- Test: `tests/test_crucix_feed.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/openclaw && python -m pytest scripts/mirofish/tests/test_crucix_feed.py::test_priority_scoring_and_cap scripts/mirofish/tests/test_crucix_feed.py::test_normalize_all_combines_domains -v`
Expected: FAIL

- [ ] **Step 3: Implement priority scoring and _normalize_all**

```python
_PRIORITY_MAP = {
    ("crucix_delta", "critical_change"): 100,
    ("crucix_delta", "regime_signal"): 100,
    ("crucix_ideas", "crucix_idea"): 90,
    ("tSignals", "military_strike"): 80,
    ("telegram", "urgent_intel"): 70,
    ("acled",): 60,  # any acled signal type
    ("fred", "indicator_spike"): 50,
    ("fred", "indicator_level"): 50,
    ("energy",): 45,
    ("noaa", "severe_weather"): 40,
    ("nukeSignals", "radiation_anomaly"): 35,
}


def _priority_score(signal: dict) -> int:
    """Map (source, signal_type) to priority score. Default 10."""
    source = signal.get("source", "")
    sig_type = signal.get("signal_type", "")
    # Try exact match first
    score = _PRIORITY_MAP.get((source, sig_type))
    if score is not None:
        return score
    # Try source-only match
    score = _PRIORITY_MAP.get((source,))
    if score is not None:
        return score
    return 10


def _sort_by_priority(signals: list[dict]) -> list[dict]:
    """Sort signals by priority score descending."""
    return sorted(signals, key=_priority_score, reverse=True)


def _strip_unhealthy(data: dict, source_keys: list[str], hmap: dict) -> dict:
    """Return a copy of data with unhealthy source keys replaced by empty values.

    This ensures normalizers never process data from sources marked err/stale.
    """
    filtered = dict(data)
    for key in source_keys:
        if not _is_source_healthy(hmap, key):
            print(f"[crucix_feed] Stripping unhealthy source: {key}")
            original = data.get(key)
            # Replace with empty version of the same type
            if isinstance(original, list):
                filtered[key] = []
            elif isinstance(original, dict):
                filtered[key] = {}
            else:
                filtered[key] = None
    return filtered


def _normalize_all(data: dict) -> list[dict]:
    """Run all normalizers, filter by health per-source, sort by priority, cap."""
    hmap = _build_health_map(data.get("health") or [])

    all_signals: list[dict] = []
    normalizers = [
        (["gdelt", "acled", "tg"], _normalize_geopolitical),
        (["fred", "energy", "treasury", "bls", "gscpi", "markets"], _normalize_economic),
        (["thermal", "tSignals", "air", "space", "sdr"], _normalize_military),
        (["noaa", "nuke", "nukeSignals", "epa", "who"], _normalize_environmental),
        (["chokepoints"], _normalize_maritime),
        (["delta", "ideas"], _normalize_meta),
    ]

    for source_keys, normalizer in normalizers:
        # Strip unhealthy sources from data before passing to normalizer
        filtered_data = _strip_unhealthy(data, source_keys, hmap)

        try:
            domain_signals = normalizer(filtered_data)
            all_signals.extend(domain_signals)
        except Exception as e:
            print(f"[crucix_feed] Normalizer error ({source_keys}): {e}")

    # Sort by priority and cap
    all_signals = _sort_by_priority(all_signals)
    return all_signals[:CRUCIX_SIGNAL_LIMIT]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/openclaw && python -m pytest scripts/mirofish/tests/test_crucix_feed.py::test_priority_scoring_and_cap scripts/mirofish/tests/test_crucix_feed.py::test_normalize_all_combines_domains -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd ~/openclaw
git add scripts/mirofish/crucix_feed.py scripts/mirofish/tests/test_crucix_feed.py
git commit -m "feat(mirofish): crucix priority scoring and _normalize_all assembler"
```

---

### Task 11: Caching layer — store, purge, freshness check

**Files:**
- Modify: `crucix_feed.py`
- Test: `tests/test_crucix_feed.py`

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/openclaw && python -m pytest scripts/mirofish/tests/test_crucix_feed.py::test_store_and_retrieve_cached scripts/mirofish/tests/test_crucix_feed.py::test_old_signals_purged scripts/mirofish/tests/test_crucix_feed.py::test_cache_freshness -v`
Expected: FAIL

- [ ] **Step 3: Implement caching functions in crucix_feed.py**

```python
def _is_cache_fresh() -> bool:
    """True if any crucix_signals row was fetched within CRUCIX_CACHE_TTL_HOURS."""
    cutoff = (datetime.datetime.utcnow() -
              datetime.timedelta(hours=CRUCIX_CACHE_TTL_HOURS)).isoformat()
    try:
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM crucix_signals WHERE fetched_at > ?",
                (cutoff,)
            ).fetchone()
        return row["cnt"] > 0
    except Exception:
        return False


def _store_signals(signals: list[dict]) -> None:
    """Batch INSERT OR IGNORE into crucix_signals."""
    if not signals:
        return
    try:
        with _get_conn() as conn:
            conn.executemany("""
                INSERT OR IGNORE INTO crucix_signals
                (source, ticker, signal_type, direction, amount_usd, description, fetched_at)
                VALUES (:source, :ticker, :signal_type, :direction,
                        :amount_usd, :description, :fetched_at)
            """, signals)
    except Exception as e:
        print(f"[crucix_feed] DB write error: {e}")


def _purge_old_signals() -> None:
    """Delete crucix_signals rows older than 24 hours."""
    cutoff = (datetime.datetime.utcnow() -
              datetime.timedelta(hours=24)).isoformat()
    try:
        with _get_conn() as conn:
            conn.execute("DELETE FROM crucix_signals WHERE fetched_at < ?", (cutoff,))
    except Exception as e:
        print(f"[crucix_feed] Purge error: {e}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/openclaw && python -m pytest scripts/mirofish/tests/test_crucix_feed.py::test_store_and_retrieve_cached scripts/mirofish/tests/test_crucix_feed.py::test_old_signals_purged scripts/mirofish/tests/test_crucix_feed.py::test_cache_freshness -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd ~/openclaw
git add scripts/mirofish/crucix_feed.py scripts/mirofish/tests/test_crucix_feed.py
git commit -m "feat(mirofish): crucix caching — store, purge, freshness check"
```

---

### Task 12: fetch() — main entry point with graceful degradation

**Files:**
- Modify: `crucix_feed.py`
- Test: `tests/test_crucix_feed.py`

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/openclaw && python -m pytest scripts/mirofish/tests/test_crucix_feed.py::test_fetch_integration_with_mock scripts/mirofish/tests/test_crucix_feed.py::test_fetch_crucix_down_returns_empty scripts/mirofish/tests/test_crucix_feed.py::test_fetch_uses_cache_when_fresh -v`
Expected: FAIL (fetch() is still a stub returning [])

- [ ] **Step 3: Implement fetch()**

Replace the stub `fetch()` in `crucix_feed.py`:

```python
def fetch() -> list[dict]:
    """
    Fetch from Crucix /api/data, normalize all 29 sources, cache, return signals.
    On failure, returns cached signals or []. Never raises.
    """
    if _is_cache_fresh():
        print("[crucix_feed] Cache fresh — skipping live fetch")
        return get_cached()

    try:
        resp = requests.get(
            f"{CRUCIX_BASE_URL}/api/data",
            timeout=CRUCIX_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.ConnectionError:
        print("[crucix_feed] Crucix unreachable — falling back to cache")
        return get_cached()
    except requests.exceptions.Timeout:
        print("[crucix_feed] Crucix timeout — falling back to cache")
        return get_cached()
    except Exception as e:
        print(f"[crucix_feed] Fetch error: {e}")
        return get_cached()

    if not isinstance(data, dict):
        print("[crucix_feed] Malformed response (not a dict) — falling back to cache")
        return get_cached()

    signals = _normalize_all(data)

    if not signals:
        print("[crucix_feed] No signals from normalization — falling back to cache")
        return get_cached()

    _purge_old_signals()
    _store_signals(signals)
    print(f"[crucix_feed] Fetched and normalized {len(signals)} signals")
    return signals
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/openclaw && python -m pytest scripts/mirofish/tests/test_crucix_feed.py::test_fetch_integration_with_mock scripts/mirofish/tests/test_crucix_feed.py::test_fetch_crucix_down_returns_empty scripts/mirofish/tests/test_crucix_feed.py::test_fetch_uses_cache_when_fresh -v`
Expected: PASS

- [ ] **Step 5: Run all crucix tests to confirm nothing is broken**

Run: `cd ~/openclaw && python -m pytest scripts/mirofish/tests/test_crucix_feed.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
cd ~/openclaw
git add scripts/mirofish/crucix_feed.py scripts/mirofish/tests/test_crucix_feed.py
git commit -m "feat(mirofish): crucix fetch() with graceful degradation"
```

---

### Task 13: trading_brain.py — two-pass prompt injection

**Files:**
- Modify: `trading_brain.py:14,162-179`
- Modify: `tests/test_uw_feed.py:142`
- Test: `tests/test_crucix_feed.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_crucix_feed.py`:

```python
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
    # Pass 1: Ideas block should appear BEFORE raw signals
    ideas_pos = prompt.find("OSINT Intelligence Summary")
    raw_pos = prompt.find("Active market signals")
    assert ideas_pos > 0, "Ideas block missing from prompt"
    assert raw_pos > 0, "Raw signals block missing from prompt"
    assert ideas_pos < raw_pos, "Ideas block must appear before raw signals"
    # Ideas block should contain the idea
    assert "Test Idea" in prompt
    assert "risk-off" in prompt
    # Raw signals block should NOT contain the idea or regime signal
    raw_section = prompt[raw_pos:]
    assert "crucix_ideas" not in raw_section.lower()


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
    assert "OSINT Intelligence Summary" not in prompt  # No ideas → no block
    assert "Active market signals" in prompt  # Raw block still present
    assert "NVDA" in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/openclaw && python -m pytest scripts/mirofish/tests/test_crucix_feed.py::test_prompt_two_pass_injection scripts/mirofish/tests/test_crucix_feed.py::test_prompt_no_ideas_omits_block -v`
Expected: FAIL

- [ ] **Step 3: Modify trading_brain.py — add MERGED_SIGNAL_LIMIT and two-pass logic**

Add at line 17 (after `MAX_POSITION_PCT`):

```python
MERGED_SIGNAL_LIMIT = int(os.environ.get("MERGED_SIGNAL_LIMIT", "30"))
```

Replace lines 162-179 (the `# Build optional UW signals block` section) with:

```python
    # Build two-pass signal blocks
    signals_block = ""
    if signals:
        # Partition signals for two-pass injection
        crucix_ideas = [s for s in signals if s.get("source") == "crucix_ideas"]
        regime_signals = [s for s in signals if s.get("source") == "crucix_delta"]
        raw_signals = [s for s in signals if s.get("source") not in ("crucix_ideas", "crucix_delta")]

        # Pass 1: Crucix OSINT Intelligence Summary (ideas + regime)
        ideas_block = ""
        if crucix_ideas or regime_signals:
            ideas_lines = []
            for rs in regime_signals:
                ideas_lines.append(f"Overall regime: {rs.get('description', 'unknown')}")
            for idea in crucix_ideas:
                ideas_lines.append(f"- {idea.get('description', '')}")
            ideas_block = (
                "\nCrucix OSINT Intelligence Summary:\n"
                + "\n".join(ideas_lines)
                + "\n"
            )

        # Pass 2: Raw signals (merged UW + Crucix, capped)
        raw_block = ""
        if raw_signals:
            recent = sorted(raw_signals, key=lambda s: s.get("fetched_at", ""), reverse=True)
            recent = recent[:MERGED_SIGNAL_LIMIT]
            signal_lines = "\n".join(
                f'- [{s.get("source", "").upper()}] {s.get("ticker", "?")} '
                f'{s.get("direction", "")} {s.get("signal_type", "")} '
                f'— {s.get("description", "")}'
                for s in recent
            )
            raw_block = (
                f"\nActive market signals:\n{signal_lines}\n\n"
                "When analyzing Polymarket markets, consider whether any of these signals "
                "suggest a related outcome is more or less likely. OSINT signals (geopolitical "
                "conflicts, economic indicators, military activity, environmental disasters) "
                "indicate macro regime shifts. Market flow signals (options sweeps, dark pool "
                "blocks, congressional trades) indicate where sophisticated money is positioning. "
                "Both can create edge in prediction markets tied to related outcomes.\n"
            )

        signals_block = ideas_block + raw_block
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `cd ~/openclaw && python -m pytest scripts/mirofish/tests/test_crucix_feed.py::test_prompt_two_pass_injection scripts/mirofish/tests/test_crucix_feed.py::test_prompt_no_ideas_omits_block -v`
Expected: PASS

- [ ] **Step 5: Fix test_uw_feed.py broken assertion**

In `tests/test_uw_feed.py`, **delete** line 142:

```python
    assert "Unusual Whales" in captured[0]
```

This assertion will fail after the header changes to `"Active market signals:"`. Line 140 already asserts `"Active market signals" in captured[0]`, so removing line 142 is correct (not replacing it, which would create a duplicate).

- [ ] **Step 6: Run existing UW tests to confirm nothing broke**

Run: `cd ~/openclaw && python -m pytest scripts/mirofish/tests/test_uw_feed.py -v`
Expected: All PASS

- [ ] **Step 7: Run ALL tests**

Run: `cd ~/openclaw && python -m pytest scripts/mirofish/tests/ -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
cd ~/openclaw
git add scripts/mirofish/trading_brain.py scripts/mirofish/tests/test_uw_feed.py scripts/mirofish/tests/test_crucix_feed.py
git commit -m "feat(mirofish): two-pass prompt injection for Crucix + UW signals"
```

---

### Task 14: simulator.py — import and merge Crucix signals in run_loop

**Files:**
- Modify: `simulator.py:122-132`

- [ ] **Step 1: Add Crucix import and merge in run_loop()**

After line 123 (`import scripts.mirofish.unusual_whales_feed as uw_feed`), add:

```python
        import scripts.mirofish.crucix_feed as crucix_feed
```

Replace lines 124-132 with:

```python
        uw_signals = uw_feed.fetch()
        if uw_signals:
            print(f"[mirofish] UW signals: {len(uw_signals)} "
                  f"({len(set(s['ticker'] for s in uw_signals))} tickers)")

        crucix_signals = crucix_feed.fetch()
        if crucix_signals:
            print(f"[mirofish] Crucix signals: {len(crucix_signals)}")

        all_signals = uw_signals + crucix_signals

        # 4. Analyze markets
        decisions = brain.analyze(markets, state, signals=all_signals or None)
        # Note: empty list collapses to None intentionally.
        # analyze() branches on `if signals:` so both None and [] skip injection.
        print(f"[mirofish] Brain returned {len(decisions)} trade decisions")
```

- [ ] **Step 2: Run the full test suite**

Run: `cd ~/openclaw && python -m pytest scripts/mirofish/tests/ -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
cd ~/openclaw
git add scripts/mirofish/simulator.py
git commit -m "feat(mirofish): integrate crucix_feed into simulator run_loop"
```

---

### Task 15: Signal dict shape validation test

A cross-cutting test that verifies every signal from a realistic Crucix response has the correct shape.

**Files:**
- Test: `tests/test_crucix_feed.py`

- [ ] **Step 1: Write and run the test**

```python
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
        assert "amount_usd" in s  # can be None but must be present
```

- [ ] **Step 2: Run the test**

Run: `cd ~/openclaw && python -m pytest scripts/mirofish/tests/test_crucix_feed.py::test_signal_dict_shape_all_domains -v`
Expected: PASS (implementation already complete)

- [ ] **Step 3: Run full test suite one final time**

Run: `cd ~/openclaw && python -m pytest scripts/mirofish/tests/ -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
cd ~/openclaw
git add scripts/mirofish/tests/test_crucix_feed.py
git commit -m "test(mirofish): add signal dict shape validation across all domains"
```

---

## Summary

| Task | What it builds | Commit message |
|------|---------------|----------------|
| 1 | DB migration | `feat(mirofish): add crucix_signals table migration` |
| 2 | Module scaffold | `feat(mirofish): crucix_feed module scaffold with config and stubs` |
| 3 | Health filtering | `feat(mirofish): crucix health filtering utility` |
| 4 | _normalize_meta | `feat(mirofish): crucix _normalize_meta — delta + ideas normalizer` |
| 5 | _normalize_geopolitical | `feat(mirofish): crucix _normalize_geopolitical — GDELT/ACLED/Telegram` |
| 6 | _normalize_economic | `feat(mirofish): crucix _normalize_economic — FRED/energy/treasury/GSCPI/markets` |
| 7 | _normalize_military | `feat(mirofish): crucix _normalize_military — thermal/strikes/air/space` |
| 8 | _normalize_environmental | `feat(mirofish): crucix _normalize_environmental — NOAA/nuke/WHO` |
| 9 | _normalize_maritime | `feat(mirofish): crucix _normalize_maritime — chokepoints` |
| 10 | Priority scoring + assembler | `feat(mirofish): crucix priority scoring and _normalize_all assembler` |
| 11 | Caching layer | `feat(mirofish): crucix caching — store, purge, freshness check` |
| 12 | fetch() entry point | `feat(mirofish): crucix fetch() with graceful degradation` |
| 13 | Two-pass prompt injection | `feat(mirofish): two-pass prompt injection for Crucix + UW signals` |
| 14 | Simulator integration | `feat(mirofish): integrate crucix_feed into simulator run_loop` |
| 15 | Shape validation test | `test(mirofish): add signal dict shape validation across all domains` |
