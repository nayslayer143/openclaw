#!/usr/bin/env python3
"""
Unusual Whales feed — fetches options flow, dark pool, congressional trades,
and institutional holdings. Caches to uw_signals SQLite table. Satisfies the
DataFeed protocol (base_feed.py) via module-level fetch() and get_cached().

Graceful degradation: returns [] immediately if UNUSUAL_WHALES_API_KEY not set.
"""
from __future__ import annotations
import os
import sqlite3
import datetime
import requests
from pathlib import Path

UW_BASE_URL = "https://api.unusualwhales.com"

source_name = "unusual_whales"

_warned_no_key: bool = False  # log warning once per process


def _get_conn() -> sqlite3.Connection:
    db_path = Path(os.environ.get("CLAWMSON_DB_PATH",
                                   Path.home() / ".openclaw" / "clawmson.db"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _call_uw(endpoint: str, params: dict | None = None) -> list[dict]:
    """GET {UW_BASE_URL}{endpoint} with Bearer auth. Returns data array or [] on error."""
    api_key = os.environ.get("UNUSUAL_WHALES_API_KEY", "")
    try:
        resp = requests.get(
            f"{UW_BASE_URL}{endpoint}",
            params=params or {},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
        if resp.status_code == 401:
            print("[uw_feed] 401 Unauthorized — check UNUSUAL_WHALES_API_KEY")
            return []
        if resp.status_code == 429:
            print("[uw_feed] 429 Rate limited")
            return []
        resp.raise_for_status()
        return resp.json().get("data", [])
    except Exception as e:
        print(f"[uw_feed] API error ({endpoint}): {e}")
        return []


def _is_cache_fresh() -> bool:
    """True if any uw_signals row was fetched within UW_CACHE_TTL_HOURS."""
    ttl = float(os.environ.get("UW_CACHE_TTL_HOURS", "1.0"))
    cutoff = (datetime.datetime.utcnow() -
              datetime.timedelta(hours=ttl)).isoformat()
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM uw_signals WHERE fetched_at > ?", (cutoff,)
        ).fetchone()
    return row["cnt"] > 0


def _normalize_options_flow(item: dict) -> dict | None:
    """Convert UW options flow item to normalized signal dict."""
    ticker = (item.get("ticker") or "").upper()
    if not ticker:
        return None

    opt_type = (item.get("type") or "").lower()
    is_sweep = item.get("has_sweep") or item.get("is_sweep", False)

    if opt_type == "call":
        direction = "bullish"
        signal_type = "call_sweep" if is_sweep else "call_block"
    elif opt_type == "put":
        direction = "bearish"
        signal_type = "put_sweep" if is_sweep else "put_block"
    else:
        return None

    try:
        premium = float(item.get("total_premium") or 0)
    except (ValueError, TypeError):
        premium = 0.0

    try:
        vol_oi = float(item.get("volume_oi_ratio") or 0)
    except (ValueError, TypeError):
        vol_oi = 0.0

    expiry = item.get("expiry", "")
    strike = item.get("strike", "")
    premium_m = premium / 1_000_000
    description = (
        f"{ticker} {signal_type} {strike} exp {expiry} — "
        f"${premium_m:.1f}M premium, vol/OI {vol_oi:.1f}x"
    )

    return {
        "source": "options_flow",
        "ticker": ticker,
        "signal_type": signal_type,
        "direction": direction,
        "amount_usd": premium,
        "description": description,
        "fetched_at": datetime.datetime.utcnow().isoformat(),
    }


def _normalize_dark_pool(item: dict) -> dict | None:
    """Convert UW dark pool item to normalized signal dict."""
    ticker = (item.get("ticker") or "").upper()
    if not ticker:
        return None

    try:
        size = float(item.get("size") or 0)
        price = float(item.get("price") or 0)
        premium = size * price
    except (ValueError, TypeError):
        premium = 0.0
        price = 0.0

    premium_m = premium / 1_000_000
    description = f"{ticker} dark pool block — ${premium_m:.1f}M at ${price:.2f}"

    return {
        "source": "dark_pool",
        "ticker": ticker,
        "signal_type": "dark_pool_block",
        "direction": "neutral",
        "amount_usd": premium,
        "description": description,
        "fetched_at": datetime.datetime.utcnow().isoformat(),
    }


def _normalize_congressional(item: dict) -> dict | None:
    """Convert UW congressional trade item to normalized signal dict."""
    ticker = (item.get("ticker") or "").upper()
    name = item.get("name", "")
    if not ticker or not name:
        return None

    txn_type = (item.get("txn_type") or "").strip().lower()
    if txn_type == "buy":
        direction, signal_type = "bullish", "buy"
    elif "sale" in txn_type or txn_type == "sell":
        direction, signal_type = "bearish", "sell"
    else:
        direction, signal_type = "neutral", "buy"

    member_type = item.get("member_type", "")
    amounts = item.get("amounts", "")
    filed_at = item.get("filed_at_date", "")

    # Extract midpoint of amounts range for amount_usd
    import re
    amount_usd = 0.0
    if amounts:
        nums = re.findall(r'[\d,]+', amounts)
        vals = [float(n.replace(",", "")) for n in nums if n.replace(",", "").isdigit()]
        if vals:
            amount_usd = sum(vals) / len(vals)

    description = (
        f"{ticker} {signal_type} by {name} ({member_type}) "
        f"— {amounts} (filed {filed_at})"
    )

    return {
        "source": "congressional",
        "ticker": ticker,
        "signal_type": signal_type,
        "direction": direction,
        "amount_usd": amount_usd,
        "description": description,
        "fetched_at": datetime.datetime.utcnow().isoformat(),
    }


def _normalize_institutional(item: dict) -> dict | None:
    """Convert UW institutional filing item to normalized signal dict."""
    ticker = (item.get("ticker") or "").upper()
    if not ticker:
        return None

    try:
        units_change = int(item.get("units_change") or 0)
    except (ValueError, TypeError):
        units_change = 0

    if units_change > 0:
        direction = "bullish"
        signal_type = "new_position" if item.get("first_buy") else "increased"
    elif units_change < 0:
        direction, signal_type = "bearish", "decreased"
    else:
        direction, signal_type = "neutral", "closed"

    try:
        value = float(item.get("value") or 0)
    except (ValueError, TypeError):
        value = 0.0

    institution = item.get("full_name") or item.get("institution") or "Institution"
    description = (
        f"{ticker} {signal_type} by {institution} — "
        f"{units_change:+,} units (${value:,.0f})"
    )

    return {
        "source": "institutional",
        "ticker": ticker,
        "signal_type": signal_type,
        "direction": direction,
        "amount_usd": value,
        "description": description,
        "fetched_at": datetime.datetime.utcnow().isoformat(),
    }


def _store_signals(signals: list[dict]) -> None:
    """Batch INSERT OR IGNORE into uw_signals. UNIQUE constraint handles dedup."""
    if not signals:
        return
    try:
        with _get_conn() as conn:
            conn.executemany("""
                INSERT OR IGNORE INTO uw_signals
                (source, ticker, signal_type, direction, amount_usd, description, fetched_at)
                VALUES (:source, :ticker, :signal_type, :direction,
                        :amount_usd, :description, :fetched_at)
            """, signals)
    except Exception as e:
        print(f"[uw_feed] DB write error: {e}")


def get_cached() -> list[dict]:
    """Return signals from uw_signals fetched within UW_CACHE_TTL_HOURS. No live fetch."""
    ttl = float(os.environ.get("UW_CACHE_TTL_HOURS", "1.0"))
    cutoff = (datetime.datetime.utcnow() -
              datetime.timedelta(hours=ttl)).isoformat()
    with _get_conn() as conn:
        rows = conn.execute("""
            SELECT source, ticker, signal_type, direction, amount_usd, description, fetched_at
            FROM uw_signals WHERE fetched_at > ?
            ORDER BY fetched_at DESC
        """, (cutoff,)).fetchall()
    return [dict(r) for r in rows]


def fetch() -> list[dict]:
    """
    Fetch all 4 signal groups from UW API, cache to uw_signals, return list.
    Returns [] immediately if UNUSUAL_WHALES_API_KEY not set (logs once).
    On API failure, returns cached signals or []. Never raises.
    """
    global _warned_no_key

    api_key = os.environ.get("UNUSUAL_WHALES_API_KEY", "")
    if not api_key:
        if not _warned_no_key:
            print("[uw_feed] UNUSUAL_WHALES_API_KEY not set — skipping UW signals")
            _warned_no_key = True
        return []

    if _is_cache_fresh():
        print("[uw_feed] Cache fresh — skipping live fetch")
        return get_cached()

    limit = int(os.environ.get("UW_SIGNAL_LIMIT", "50"))
    normalizers = [
        ("/api/option-trades/flow-alerts", _normalize_options_flow),
        ("/api/darkpool/recent",            _normalize_dark_pool),
        ("/api/congress/recent-trades",     _normalize_congressional),
        ("/api/institutions/latest_filings", _normalize_institutional),
    ]

    all_signals: list[dict] = []
    for endpoint, normalizer in normalizers:
        for item in _call_uw(endpoint, {"limit": limit}):
            sig = normalizer(item)
            if sig:
                all_signals.append(sig)

    if not all_signals:
        print("[uw_feed] No signals from live fetch — falling back to cache")
        return get_cached()

    _store_signals(all_signals)
    tickers = len(set(s["ticker"] for s in all_signals))
    print(f"[uw_feed] Fetched {len(all_signals)} signals from {tickers} tickers")
    return all_signals
