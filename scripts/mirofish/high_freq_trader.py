#!/usr/bin/env python3
"""
High-frequency paper trader daemon.
Loops every 30s: fetch markets → score → place → resolve → evolve.
Target: 100+ paper bets/hour across Kalshi (prod) and Polymarket.

Usage:
    python3 -m scripts.mirofish.high_freq_trader
"""
from __future__ import annotations

import os
import sys
import math
import signal
import time
import random
import datetime
import sqlite3
import requests
from collections import namedtuple
from pathlib import Path

# ── project root on sys.path ─────────────────────────────────────────────────
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

# ── Config ────────────────────────────────────────────────────────────────────
CYCLE_SLEEP         = int(os.environ.get("HFT_CYCLE_SLEEP", "30"))
MIN_EDGE_POLY       = float(os.environ.get("HFT_MIN_EDGE_POLY", "0.003"))
MIN_EDGE_KALSHI_ARB = float(os.environ.get("HFT_MIN_EDGE_KALSHI_ARB", "0.020"))
MIN_EDGE_KALSHI_SPOT= float(os.environ.get("HFT_MIN_EDGE_KALSHI_SPOT", "0.025"))
BASE_POS_POLY       = float(os.environ.get("HFT_BASE_POS_POLY", "0.015"))
BASE_POS_KALSHI     = float(os.environ.get("HFT_BASE_POS_KALSHI", "0.030"))
MAX_POS_PCT         = float(os.environ.get("HFT_MAX_POS_PCT", "0.05"))
MAX_KALSHI_PER_CYCLE= int(os.environ.get("HFT_MAX_KALSHI_PER_CYCLE", "15"))
MIN_ENTRY_PRICE     = 0.05
MAX_SPREAD_PCT      = 0.25
POLY_REFRESH_CYCLES = 5
MIN_POLY_VOLUME     = 1000.0
MAX_EXPIRY_HOURS    = 24.0

# Fee / execution
KALSHI_FEE_FACTOR   = 0.07
POLY_FEE_RATE       = 0.001
SLIPPAGE_BASE       = 0.003
FILL_MIN            = 0.85

KALSHI_SHORT_SERIES = [
    "KXDOGE15M", "KXADA15M", "KXBNB15M", "KXBCH15M",
    "KXBTC15M",  "KXETH15M",
    "INXI", "NASDAQ100I", "KXUSDJPYH",
    "KXBTCUSD", "KXETHUSD",
    "KXBTC", "KXETH", "KXSOL",
]

GAMMA_API = "https://gamma-api.polymarket.com/markets"

TradeSignal = namedtuple(
    "TradeSignal",
    ["market_id", "question", "venue", "direction", "edge",
     "strategy", "entry_price", "amount_usd", "shares", "fee"],
)


# ── DB helpers ────────────────────────────────────────────────────────────────

def _load_env():
    env_file = Path.home() / "openclaw" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def get_conn() -> sqlite3.Connection:
    db_path = Path(os.environ.get("CLAWMSON_DB_PATH",
                                   Path.home() / ".openclaw" / "clawmson.db"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    result = conn.execute("PRAGMA journal_mode=WAL").fetchone()
    if result and result[0] != "wal":
        print(f"[HFT] WARNING: WAL mode unavailable (got: {result[0]})")
    return conn


def get_balance(conn: sqlite3.Connection) -> float:
    """Balance = starting_balance + sum of all closed P&L."""
    row = conn.execute(
        "SELECT value FROM context WHERE chat_id='mirofish' AND key='starting_balance'"
    ).fetchone()
    starting = float(row["value"]) if row else 10000.0
    closed_pnl = conn.execute(
        "SELECT COALESCE(SUM(pnl), 0) FROM paper_trades WHERE status != 'open'"
    ).fetchone()[0] or 0.0
    return starting + closed_pnl


# ── Startup ───────────────────────────────────────────────────────────────────

def db_startup(conn: sqlite3.Connection) -> None:
    """
    One-time startup: wipe stale open positions, clear context noise,
    set $10k starting balance, add performance index.
    """
    count = conn.execute("SELECT COUNT(*) FROM paper_trades WHERE status='open'").fetchone()[0]
    conn.execute("DELETE FROM paper_trades WHERE status = 'open'")
    conn.execute("DELETE FROM context WHERE key LIKE 'wallet_reset_%'")
    conn.execute(
        "INSERT OR REPLACE INTO context (chat_id, key, value) "
        "VALUES ('mirofish', 'starting_balance', '10000.00')"
    )
    conn.execute(
        "INSERT OR REPLACE INTO context (chat_id, key, value) "
        "VALUES ('mirofish', 'trading_status', 'active')"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_pt_status_opened "
        "ON paper_trades(status, opened_at)"
    )
    conn.commit()
    print(f"[HFT] DB startup complete — wiped {count} stale open trades, $10,000 balance set")


# ── Kalshi market fetcher ─────────────────────────────────────────────────────

try:
    from scripts.mirofish.kalshi_feed import _call_kalshi, _adapt_market_fields
except ImportError:
    from kalshi_feed import _call_kalshi, _adapt_market_fields


def fetch_kalshi_markets() -> list[dict]:
    """
    Fetch all open Kalshi markets across target series that close within 24h.
    Returns list of normalized market dicts (venue="kalshi", prices 0-1 decimal).
    """
    now = datetime.datetime.utcnow()
    cutoff = now + datetime.timedelta(hours=MAX_EXPIRY_HOURS)
    seen: set[str] = set()
    markets: list[dict] = []

    for series in KALSHI_SHORT_SERIES:
        data = _call_kalshi("GET", "/events", params={
            "series_ticker": series, "status": "open", "limit": 10,
        })
        if not data:
            continue
        for event in data.get("events", []):
            evt_ticker = event.get("event_ticker", "")
            if not evt_ticker:
                continue
            mdata = _call_kalshi("GET", "/markets", params={
                "event_ticker": evt_ticker, "status": "open", "limit": 100,
            })
            if not mdata:
                continue
            for m in mdata.get("markets", []):
                _adapt_market_fields(m)
                ticker = m.get("ticker", "")
                if not ticker or ticker in seen:
                    continue
                if m.get("mve_collection_ticker") or "KXMVE" in ticker:
                    continue
                # Filter to <24hr closing (parse to datetime to handle Z-suffix correctly)
                close_time = m.get("close_time") or m.get("expiration_time", "")
                if not close_time:
                    continue
                try:
                    ct_str = close_time.replace("Z", "").replace("+00:00", "")
                    ct_dt = datetime.datetime.fromisoformat(ct_str)
                except (ValueError, TypeError):
                    continue
                if ct_dt <= now or ct_dt > cutoff:
                    continue
                # _adapt_market_fields converts yes_bid_dollars -> yes_bid in cents
                # Divide by 100 to get 0-1 decimal
                yb = (m.get("yes_bid") or 0) / 100.0
                ya = (m.get("yes_ask") or 0) / 100.0
                nb = (m.get("no_bid") or 0) / 100.0
                na = (m.get("no_ask") or 0) / 100.0
                yes_price = (yb + ya) / 2 if yb > 0 and ya > 0 else (yb or ya)
                no_price  = (nb + na) / 2 if nb > 0 and na > 0 else (nb or na)
                if yes_price <= 0 and no_price <= 0:
                    continue

                seen.add(ticker)
                markets.append({
                    "market_id":    ticker,
                    "question":     m.get("title", ticker),
                    "venue":        "kalshi",
                    "yes_price":    yes_price,
                    "no_price":     no_price,
                    "yes_bid":      yb,
                    "yes_ask":      ya,
                    "event_ticker": evt_ticker,
                    "close_time":   close_time,
                    "category":     (m.get("category") or "").lower(),
                    "cap_strike":   m.get("cap_strike"),
                    "strike_type":  m.get("strike_type", ""),
                })

    return markets
