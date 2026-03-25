#!/usr/bin/env python3
"""
Kalshi feed — fetches market data from Kalshi's REST API and caches to SQLite.
Duck-type compatible with the DataFeed protocol (base_feed.py) via module-level
fetch() and get_cached().

Auth: RSA key-pair signature (KALSHI-ACCESS-KEY, KALSHI-ACCESS-TIMESTAMP, KALSHI-ACCESS-SIGNATURE).
Env vars:
    KALSHI_API_KEY_ID       — API key ID from Kalshi dashboard
    KALSHI_PRIVATE_KEY_PATH — path to RSA private key PEM file
    KALSHI_API_ENV          — "demo" (default) or "prod"

Graceful degradation: returns [] immediately if credentials not set.
"""
from __future__ import annotations

import base64
import datetime
import os
import sqlite3
import time
from pathlib import Path

import requests

source_name = "kalshi"

DEMO_API = "https://demo-api.kalshi.co/trade-api/v2"
PROD_API = "https://api.elections.kalshi.com/trade-api/v2"
CACHE_MAX_AGE_HOURS = 6
PAGE_LIMIT = 200  # max per-page from Kalshi API

_warned_no_key: bool = False


# ---------------------------------------------------------------------------
# DB helpers (same pattern as polymarket_feed / uw_feed)
# ---------------------------------------------------------------------------

def _get_conn() -> sqlite3.Connection:
    db_path = Path(os.environ.get("CLAWMSON_DB_PATH",
                                   Path.home() / ".openclaw" / "clawmson.db"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS kalshi_markets (
            ticker        TEXT NOT NULL,
            event_ticker  TEXT,
            title         TEXT,
            category      TEXT,
            yes_bid       REAL,
            yes_ask       REAL,
            no_bid        REAL,
            no_ask        REAL,
            last_price    REAL,
            volume        REAL,
            volume_24h    REAL,
            open_interest REAL,
            status        TEXT,
            close_time    TEXT,
            rules_primary TEXT,
            strike_type   TEXT,
            cap_strike    REAL,
            floor_strike  REAL,
            fetched_at    TEXT NOT NULL
        )
    """)


def _is_cache_fresh() -> bool:
    cutoff = (datetime.datetime.utcnow() -
              datetime.timedelta(hours=CACHE_MAX_AGE_HOURS)).isoformat()
    with _get_conn() as conn:
        _ensure_table(conn)
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM kalshi_markets WHERE fetched_at > ?",
            (cutoff,),
        ).fetchone()
    return row["cnt"] > 0


# ---------------------------------------------------------------------------
# RSA signature auth
# ---------------------------------------------------------------------------

def _get_api_base() -> str:
    env = os.environ.get("KALSHI_API_ENV", "demo").lower()
    return PROD_API if env == "prod" else DEMO_API


def _load_private_key():
    """Load RSA private key from PEM file. Returns None if not configured."""
    key_path = os.environ.get("KALSHI_PRIVATE_KEY_PATH", "")
    if not key_path or not Path(key_path).exists():
        return None
    try:
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
        with open(key_path, "rb") as f:
            return load_pem_private_key(f.read(), password=None)
    except Exception as e:
        print(f"[kalshi_feed] Failed to load private key: {e}")
        return None


def _sign_request(private_key, timestamp_str: str, method: str, path: str) -> str:
    """
    Sign (timestamp + method + path) with RSA-SHA256, return base64 signature.
    Kalshi requires signing the path WITHOUT query parameters.
    """
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    message = (timestamp_str + method.upper() + path).encode("utf-8")
    signature = private_key.sign(
        message,
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode("utf-8")


def _auth_headers(method: str, path: str) -> dict | None:
    """
    Build Kalshi auth headers. Returns None if credentials not configured.
    """
    global _warned_no_key

    api_key_id = os.environ.get("KALSHI_API_KEY_ID", "")
    if not api_key_id:
        if not _warned_no_key:
            print("[kalshi_feed] KALSHI_API_KEY_ID not set — skipping Kalshi feed")
            _warned_no_key = True
        return None

    private_key = _load_private_key()
    if private_key is None:
        if not _warned_no_key:
            print("[kalshi_feed] KALSHI_PRIVATE_KEY_PATH not set or invalid — skipping")
            _warned_no_key = True
        return None

    timestamp_str = str(int(time.time() * 1000))
    signature = _sign_request(private_key, timestamp_str, method, path)

    return {
        "KALSHI-ACCESS-KEY": api_key_id,
        "KALSHI-ACCESS-TIMESTAMP": timestamp_str,
        "KALSHI-ACCESS-SIGNATURE": signature,
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------

def _call_kalshi(method: str, path: str, params: dict | None = None) -> dict | None:
    """Make an authenticated request to Kalshi API. Returns parsed JSON or None."""
    headers = _auth_headers(method, path)
    if headers is None:
        return None

    base = _get_api_base()
    url = f"{base}{path}"

    try:
        resp = requests.request(
            method,
            url,
            params=params,
            headers=headers,
            timeout=30,
        )
        if resp.status_code == 401:
            print("[kalshi_feed] 401 Unauthorized — check API credentials")
            return None
        if resp.status_code == 429:
            print("[kalshi_feed] 429 Rate limited — backing off")
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[kalshi_feed] API error: {e}")
        return None


def _adapt_market_fields(m: dict) -> dict:
    """
    Adapt Kalshi API v2 field names to our internal format.
    v2 uses _dollars suffix for prices and _fp suffix for volume.
    """
    def _dollars_to_cents(val):
        """Convert dollar string like '0.4200' to cents int like 42."""
        if val is None:
            return None
        try:
            f = float(val)
            if f > 0:
                return int(round(f * 100))
        except (ValueError, TypeError):
            pass
        return None

    # Map v2 fields to our expected format
    m.setdefault("yes_bid", _dollars_to_cents(m.get("yes_bid_dollars")))
    m.setdefault("yes_ask", _dollars_to_cents(m.get("yes_ask_dollars")))
    m.setdefault("no_bid", _dollars_to_cents(m.get("no_bid_dollars")))
    m.setdefault("no_ask", _dollars_to_cents(m.get("no_ask_dollars")))
    m.setdefault("last_price", _dollars_to_cents(m.get("last_price_dollars") or m.get("previous_price_dollars")))
    m.setdefault("volume", float(m.get("volume_fp", 0) or 0))
    m.setdefault("volume_24h", float(m.get("volume_24h_fp", 0) or 0))
    m.setdefault("open_interest", float(m.get("open_interest_fp", 0) or 0))
    m.setdefault("rules_primary", m.get("rules_primary", ""))
    m.setdefault("category", m.get("category", ""))

    return m


def fetch_markets_page(cursor: str | None = None, status: str = "open") -> tuple[list[dict], str | None]:
    """
    Fetch one page of markets. Returns (markets_list, next_cursor).
    next_cursor is None when no more pages.
    Filters out MVE combo markets and inactive zero-liquidity markets.
    """
    params: dict = {"limit": PAGE_LIMIT, "status": status}
    if cursor:
        params["cursor"] = cursor

    data = _call_kalshi("GET", "/markets", params=params)
    if data is None:
        return [], None

    raw_markets = data.get("markets", [])
    # Adapt field names and filter out MVE combo markets (low quality noise)
    markets = []
    for m in raw_markets:
        _adapt_market_fields(m)
        # Skip MVE combo markets — they're multi-leg parlays with no liquidity
        if m.get("mve_collection_ticker") or "KXMVE" in m.get("ticker", ""):
            continue
        markets.append(m)

    next_cursor = data.get("cursor")
    if not next_cursor:
        next_cursor = None

    return markets, next_cursor


def fetch_orderbook(ticker: str) -> dict | None:
    """Fetch orderbook for a specific market ticker."""
    data = _call_kalshi("GET", f"/markets/{ticker}/orderbook")
    if data is None:
        return None
    return data.get("orderbook", data)


# ---------------------------------------------------------------------------
# Main feed functions (DataFeed protocol)
# ---------------------------------------------------------------------------

# Series tickers for markets we actually care about
# Ordered by resolution speed: 15min → hourly → daily → weekly → long-term
TARGET_SERIES = [
    # 15-minute crypto (fastest feedback)
    "KXDOGE15M",   # Dogecoin 15min
    "KXADA15M",    # Cardano 15min
    "KXBNB15M",    # BNB 15min
    "KXBCH15M",    # Bitcoin Cash 15min
    # Hourly
    "INXI",        # S&P 500 hourly
    "NASDAQ100I",  # Nasdaq-100 hourly
    "KXUSDJPYH",   # USD/JPY hourly
    "KXTEMPNYCH",  # NYC temperature hourly
    # Daily crypto
    "KXBTC",       # Bitcoin price (daily ranges)
    "KXBTCMAXD",   # BTC daily max
    "KXETH",       # Ethereum price
    # Daily financials
    "KXINXSPX",    # S&P 500 daily
    "KXINXNDX",    # Nasdaq daily
    "KXGOLDD",     # Gold daily
    "KXSILVERD",   # Silver daily
    "KXTNOTED",    # 10Y Treasury daily
    "KXUSDJPY",    # USD/JPY daily
    # Daily other
    "KXHIGHTDC",   # DC temperature daily
    "KXHIGHTSFO",  # SF temperature daily
    "KXTRUMPACT",  # "Will Trump do anything today?"
    "KXTRUMPPOLLDAILY",  # Trump approval daily
    "KXTSA",       # TSA check-ins daily
    # Sports (resolve same day/week)
    "KXNBA",       # NBA
    "KXNFL",       # NFL
    "KXMLB",       # MLB
    "KXNCAA",      # NCAA
    "KXSOCCER",    # Soccer
    # Weekly/medium-term
    "KXFEDRATE",   # Fed rate decisions
    "KXCPI",       # CPI / inflation
    "KXJOBLESS",   # Jobless claims
    "KXELECTION",  # Elections
    "KXTARIFF",    # Tariffs
    "KXNEWPOPE",   # Pope
]


def _fetch_event_markets(series_ticker: str) -> list[dict]:
    """Fetch markets for a specific series by querying events first."""
    data = _call_kalshi("GET", "/events", params={
        "series_ticker": series_ticker, "status": "open", "limit": 10,
    })
    if not data:
        return []

    markets = []
    for event in data.get("events", []):
        evt_ticker = event.get("event_ticker", "")
        if not evt_ticker:
            continue
        mdata = _call_kalshi("GET", "/markets", params={
            "event_ticker": evt_ticker, "status": "open", "limit": 100,
        })
        if mdata:
            for m in mdata.get("markets", []):
                _adapt_market_fields(m)
                if not m.get("mve_collection_ticker"):
                    markets.append(m)

    return markets


def fetch(categories: list[str] | None = None, max_pages: int = 5) -> list[dict]:
    """
    Fetch active Kalshi markets, cache to DB. Returns list of market dicts.
    Queries by series ticker to get real markets (skips MVE combo spam).
    Falls back to cached data if API is unavailable.
    """
    if _auth_headers("GET", "/markets") is None:
        return []

    if _is_cache_fresh():
        print("[kalshi_feed] Cache fresh — skipping live fetch")
        return get_cached(categories)

    now = datetime.datetime.utcnow().isoformat()
    all_markets: list[dict] = []
    seen_tickers: set[str] = set()

    # Fetch by series to get real markets
    for series in TARGET_SERIES:
        series_markets = _fetch_event_markets(series)
        for m in series_markets:
            ticker = m.get("ticker", "")
            if ticker and ticker not in seen_tickers:
                seen_tickers.add(ticker)
                all_markets.append(m)

    if not all_markets:
        print("[kalshi_feed] No markets from API — using cache")
        return get_cached(categories)

    # Cache to DB
    with _get_conn() as conn:
        _ensure_table(conn)
        for m in all_markets:
            conn.execute("""
                INSERT INTO kalshi_markets
                (ticker, event_ticker, title, category, yes_bid, yes_ask,
                 no_bid, no_ask, last_price, volume, volume_24h, open_interest,
                 status, close_time, rules_primary, strike_type, cap_strike,
                 floor_strike, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                m.get("ticker", ""),
                m.get("event_ticker", ""),
                m.get("title", ""),
                (m.get("category") or "").lower(),
                _cents_to_float(m.get("yes_bid")),
                _cents_to_float(m.get("yes_ask")),
                _cents_to_float(m.get("no_bid")),
                _cents_to_float(m.get("no_ask")),
                _cents_to_float(m.get("last_price")),
                float(m.get("volume", 0) or 0),
                float(m.get("volume_24h", 0) or 0),
                float(m.get("open_interest", 0) or 0),
                m.get("status", ""),
                m.get("close_time") or m.get("expiration_time", ""),
                m.get("rules_primary", ""),
                m.get("strike_type", ""),
                _safe_float(m.get("cap_strike")),
                _safe_float(m.get("floor_strike")),
                now,
            ))

    filtered = _filter_categories(all_markets, categories)
    print(f"[kalshi_feed] Fetched {len(all_markets)} markets, {len(filtered)} after category filter")
    return [_normalize_market_dict(m) for m in filtered]


def get_cached(categories: list[str] | None = None) -> list[dict]:
    """Return most recent snapshot per market from cache."""
    cutoff = (datetime.datetime.utcnow() -
              datetime.timedelta(hours=CACHE_MAX_AGE_HOURS)).isoformat()
    with _get_conn() as conn:
        _ensure_table(conn)
        rows = conn.execute("""
            SELECT km.*
            FROM kalshi_markets km
            INNER JOIN (
                SELECT ticker, MAX(fetched_at) AS latest
                FROM kalshi_markets WHERE fetched_at > ?
                GROUP BY ticker
            ) latest ON km.ticker = latest.ticker AND km.fetched_at = latest.latest
        """, (cutoff,)).fetchall()

    markets = [dict(r) for r in rows]
    if not markets:
        print("[kalshi_feed] Cache empty or stale. No markets available.")
    filtered = _filter_categories(markets, categories)
    return [_normalize_market_dict(m) for m in filtered]


def get_latest_prices() -> dict[str, dict]:
    """Return {ticker: {yes_bid, yes_ask, no_bid, no_ask, last_price}} from most recent snapshot."""
    with _get_conn() as conn:
        _ensure_table(conn)
        rows = conn.execute("""
            SELECT km.ticker, km.yes_bid, km.yes_ask, km.no_bid, km.no_ask, km.last_price
            FROM kalshi_markets km
            INNER JOIN (
                SELECT ticker, MAX(fetched_at) AS latest
                FROM kalshi_markets GROUP BY ticker
            ) l ON km.ticker = l.ticker AND km.fetched_at = l.latest
        """).fetchall()
    return {
        r["ticker"]: {
            "yes_bid": r["yes_bid"], "yes_ask": r["yes_ask"],
            "no_bid": r["no_bid"], "no_ask": r["no_ask"],
            "last_price": r["last_price"],
        }
        for r in rows
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cents_to_float(val) -> float | None:
    """Kalshi prices are in cents (0-99). Convert to 0.00-0.99 decimal."""
    if val is None:
        return None
    try:
        return float(val) / 100.0
    except (ValueError, TypeError):
        return None


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _filter_categories(markets: list[dict], categories: list[str] | None) -> list[dict]:
    if not categories:
        return markets
    cats = {c.lower() for c in categories}
    return [m for m in markets if (m.get("category") or "").lower() in cats or not m.get("category")]


def _normalize_market_dict(m: dict) -> dict:
    """Flatten a Kalshi market into a consistent dict for downstream consumers."""
    return {
        "market_id": m.get("ticker", ""),
        "event_ticker": m.get("event_ticker", ""),
        "question": m.get("title", ""),
        "category": (m.get("category") or "").lower(),
        "yes_bid": m.get("yes_bid") if isinstance(m.get("yes_bid"), float) else _cents_to_float(m.get("yes_bid")),
        "yes_ask": m.get("yes_ask") if isinstance(m.get("yes_ask"), float) else _cents_to_float(m.get("yes_ask")),
        "no_bid": m.get("no_bid") if isinstance(m.get("no_bid"), float) else _cents_to_float(m.get("no_bid")),
        "no_ask": m.get("no_ask") if isinstance(m.get("no_ask"), float) else _cents_to_float(m.get("no_ask")),
        "last_price": m.get("last_price") if isinstance(m.get("last_price"), float) else _cents_to_float(m.get("last_price")),
        "volume": float(m.get("volume", 0) or 0),
        "volume_24h": float(m.get("volume_24h", 0) or 0),
        "open_interest": float(m.get("open_interest", 0) or 0),
        "status": m.get("status", ""),
        "close_time": m.get("close_time") or m.get("expiration_time", ""),
        "rules_primary": m.get("rules_primary", ""),
        "strike_type": m.get("strike_type", ""),
        "cap_strike": _safe_float(m.get("cap_strike")),
        "floor_strike": _safe_float(m.get("floor_strike")),
        "venue": "kalshi",
    }


# ---------------------------------------------------------------------------
# MarketEvent normalization
# ---------------------------------------------------------------------------

def to_market_event(raw: dict) -> "MarketEvent":
    """Convert a Kalshi market dict into a canonical MarketEvent."""
    from scripts.mirofish.market_event import MarketEventNormalizer
    return MarketEventNormalizer.normalize_kalshi(raw)


if __name__ == "__main__":
    markets = fetch()
    print(f"[kalshi_feed] Refreshed {len(markets)} markets to DB")
