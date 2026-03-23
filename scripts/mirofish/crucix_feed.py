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


_DIRECTION_MAP_REGIME = {"risk-on": "bullish", "risk-off": "bearish", "mixed": "neutral"}
_DIRECTION_MAP_IDEA = {"long": "bullish", "hedge": "bearish", "watch": "neutral"}

# Delta critical change types that imply bearish
_BEARISH_DELTA_TYPES = {
    "VIX_SPIKE", "YIELD_INVERSION", "CREDIT_SPREAD_WIDENING",
    "DEBT_MILESTONE", "INVENTORY_SPIKE", "ELEVATED_READING",
    "MILITARY_SAT_DEPLOYMENT",
}

# IDs where a high value is bearish
_BEARISH_HIGH_INDICATORS = {"VIXCLS", "BAMLH0A0HYM2", "UNRATE", "T10Y2Y"}


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
