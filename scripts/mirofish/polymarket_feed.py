#!/usr/bin/env python3
"""
Polymarket feed — fetches market data from gamma-api.polymarket.com and caches to SQLite.
"""
from __future__ import annotations
import os
import sqlite3
import datetime
import requests
from pathlib import Path

GAMMA_API = "https://gamma-api.polymarket.com/markets"
MIN_VOLUME = float(os.environ.get("MIROFISH_MIN_MARKET_VOLUME", "10000"))
CACHE_MAX_AGE_HOURS = 6


def _get_conn() -> sqlite3.Connection:
    db_path = Path(os.environ.get("CLAWMSON_DB_PATH", Path.home() / ".openclaw" / "clawmson.db"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _is_cache_fresh() -> bool:
    """True if we have market_data rows less than CACHE_MAX_AGE_HOURS old."""
    cutoff = (datetime.datetime.utcnow() -
              datetime.timedelta(hours=CACHE_MAX_AGE_HOURS)).isoformat()
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM market_data WHERE fetched_at > ?", (cutoff,)
        ).fetchone()
    return row["cnt"] > 0


def fetch_markets(categories: list[str] | None = None) -> list[dict]:
    """
    Fetch active Polymarket markets, filter by volume and category, cache to DB.
    Returns list of market dicts. Falls back to cached data if API is unavailable.
    """
    if categories is None:
        categories = ["crypto", "politics", "sports", "weather", "tech"]

    now = datetime.datetime.utcnow().isoformat()

    try:
        resp = requests.get(
            GAMMA_API,
            params={"active": "true", "closed": "false", "limit": 100},
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json()
        markets_raw = raw if isinstance(raw, list) else raw.get("data", raw.get("markets", []))
    except Exception as e:
        print(f"[mirofish/feed] Polymarket API error: {e}. Using cache.")
        return _load_cached_markets(categories)

    markets = []
    with _get_conn() as conn:
        for m in markets_raw:
            volume = float(m.get("volume", 0) or 0)
            if volume < MIN_VOLUME:
                continue

            # Extract prices from tokens list
            tokens = m.get("tokens", []) or []
            yes_price = no_price = None
            for tok in tokens:
                outcome = (tok.get("outcome") or "").upper()
                if outcome == "YES":
                    yes_price = float(tok.get("price", 0) or 0)
                elif outcome == "NO":
                    no_price = float(tok.get("price", 0) or 0)

            if yes_price is None or no_price is None:
                continue

            market_id = m.get("conditionId") or m.get("id") or ""
            question  = m.get("question", "")
            category  = (m.get("category") or "").lower()
            end_date  = m.get("endDate") or m.get("end_date")

            if not market_id or not question:
                continue

            conn.execute("""
                INSERT INTO market_data
                (market_id, question, category, yes_price, no_price, volume, end_date, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (market_id, question, category, yes_price, no_price, volume, end_date, now))

            markets.append({
                "market_id": market_id, "question": question, "category": category,
                "yes_price": yes_price, "no_price": no_price,
                "volume": volume, "end_date": end_date,
            })

    # Filter by category (post-insert so cache is always populated)
    filtered = [m for m in markets if not categories or m["category"] in categories]
    print(f"[mirofish/feed] Fetched {len(markets)} markets, {len(filtered)} after category filter")
    return filtered


def _load_cached_markets(categories: list[str]) -> list[dict]:
    """Return most recent snapshot per market from cache."""
    cutoff = (datetime.datetime.utcnow() -
              datetime.timedelta(hours=CACHE_MAX_AGE_HOURS)).isoformat()
    with _get_conn() as conn:
        rows = conn.execute("""
            SELECT md.*
            FROM market_data md
            INNER JOIN (
                SELECT market_id, MAX(fetched_at) AS latest
                FROM market_data WHERE fetched_at > ?
                GROUP BY market_id
            ) latest ON md.market_id = latest.market_id AND md.fetched_at = latest.latest
        """, (cutoff,)).fetchall()
    markets = [dict(r) for r in rows]
    if not markets:
        print("[mirofish/feed] Cache empty or stale. No markets available.")
    return [m for m in markets if not categories or m.get("category") in categories]


def get_recent_snapshots(market_id: str, limit: int = 3) -> list[dict]:
    """Return the `limit` most recent price snapshots for a market (oldest first)."""
    with _get_conn() as conn:
        rows = conn.execute("""
            SELECT yes_price, no_price, fetched_at
            FROM market_data
            WHERE market_id = ?
            ORDER BY fetched_at DESC
            LIMIT ?
        """, (market_id, limit)).fetchall()
    return list(reversed([dict(r) for r in rows]))


def get_latest_prices() -> dict[str, dict]:
    """Return {market_id: {yes_price, no_price}} from most recent snapshot per market."""
    with _get_conn() as conn:
        rows = conn.execute("""
            SELECT md.market_id, md.yes_price, md.no_price
            FROM market_data md
            INNER JOIN (
                SELECT market_id, MAX(fetched_at) AS latest
                FROM market_data GROUP BY market_id
            ) l ON md.market_id = l.market_id AND md.fetched_at = l.latest
        """).fetchall()
    return {r["market_id"]: {"yes_price": r["yes_price"], "no_price": r["no_price"]}
            for r in rows}
