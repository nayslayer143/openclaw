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
