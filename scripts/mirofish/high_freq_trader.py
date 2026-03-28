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


# ── Polymarket market fetcher ─────────────────────────────────────────────────

def fetch_polymarket_markets() -> list[dict]:
    """
    Fetch Polymarket markets closing within 24h via gamma API.
    Returns list of normalized market dicts (venue="polymarket", prices 0-1).
    """
    now = datetime.datetime.utcnow()
    cutoff = now + datetime.timedelta(hours=MAX_EXPIRY_HOURS)

    try:
        resp = requests.get(
            GAMMA_API,
            params={"active": "true", "closed": "false", "limit": 200},
            timeout=20,
        )
        resp.raise_for_status()
        raw = resp.json()
        raw_list = raw if isinstance(raw, list) else raw.get("data", raw.get("markets", []))
    except Exception as e:
        print(f"[HFT] Polymarket fetch error: {e}")
        return []

    markets: list[dict] = []
    for m in raw_list:
        try:
            volume = float(m.get("volume", 0) or 0)
        except (ValueError, TypeError):
            volume = 0.0
        if volume < MIN_POLY_VOLUME:
            continue

        end_date_str = m.get("endDate") or m.get("end_date") or ""
        if not end_date_str:
            continue
        try:
            end_dt_str = end_date_str.replace("Z", "").replace("+00:00", "")
            end_dt = datetime.datetime.fromisoformat(end_dt_str)
        except (ValueError, TypeError):
            continue
        if end_dt <= now or end_dt > cutoff:
            continue

        yes_price = no_price = None
        outcome_prices = m.get("outcomePrices", [])
        outcomes = m.get("outcomes", [])
        if isinstance(outcome_prices, str):
            import json as _json
            try: outcome_prices = _json.loads(outcome_prices)
            except Exception: outcome_prices = []
        if isinstance(outcomes, str):
            import json as _json
            try: outcomes = _json.loads(outcomes)
            except Exception: outcomes = []
        for label, price_str in zip(outcomes, outcome_prices):
            try:
                price = float(price_str)
            except (ValueError, TypeError):
                continue
            if (label or "").lower() == "yes":
                yes_price = price
            elif (label or "").lower() == "no":
                no_price = price

        if yes_price is None or no_price is None:
            for tok in (m.get("tokens") or []):
                outcome = (tok.get("outcome") or "").upper()
                try:
                    price = float(tok.get("price", 0) or 0)
                except (ValueError, TypeError):
                    continue
                if outcome == "YES":
                    yes_price = price
                elif outcome == "NO":
                    no_price = price

        if yes_price is None or no_price is None:
            continue

        market_id = m.get("conditionId") or m.get("id") or ""
        question  = m.get("question", "")
        if not market_id or not question:
            continue

        markets.append({
            "market_id":    market_id,
            "question":     question,
            "venue":        "polymarket",
            "yes_price":    float(yes_price),
            "no_price":     float(no_price),
            "yes_bid":      float(yes_price),
            "yes_ask":      float(yes_price),
            "event_ticker": market_id[:20],
            "close_time":   end_date_str,
            "category":     (m.get("category") or "").lower(),
            "cap_strike":   None,
            "strike_type":  "",
        })

    return markets


# ── Strategy scoring ──────────────────────────────────────────────────────────

_CRYPTO_TICKERS = {
    "BTC": ["KXBTC", "KXBTCUSD"],
    "ETH": ["KXETH", "KXETHUSD"],
    "SOL": ["KXSOL"],
    "DOGE": ["KXDOGE"],
    "ADA": ["KXADA"],
    "BNB": ["KXBNB"],
    "BCH": ["KXBCH"],
}


def _size_trade(balance: float, venue: str, weight: float) -> float:
    """Return position size in USD, Kelly-scaled by strategy weight."""
    base_pct = BASE_POS_POLY if venue == "polymarket" else BASE_POS_KALSHI
    sized = balance * base_pct * max(0.5, min(1.5, weight))
    return min(sized, balance * MAX_POS_PCT)


def _calc_fee(venue: str, shares: float, entry_price: float, amount_usd: float) -> float:
    if venue == "kalshi":
        return KALSHI_FEE_FACTOR * shares * entry_price * (1.0 - entry_price)
    return POLY_FEE_RATE * amount_usd


def _apply_slippage(price: float, direction: str) -> float:
    """Slip entry price against us by SLIPPAGE_BASE."""
    if direction == "YES":
        return min(price * (1.0 + SLIPPAGE_BASE), 0.99)
    return max(price * (1.0 - SLIPPAGE_BASE), 0.01)


def score_market(
    market: dict,
    spot_prices: dict,
    open_ids: set,
    events_traded: set,
    weights: dict,
    balance: float = 10000.0,
) -> object:
    """
    Score a market across 4 strategies. Returns TradeSignal or None.
    Priority: arb > spot_lag > momentum > mean_reversion.
    """
    mid   = market["market_id"]
    venue = market["venue"]
    yes_p = market["yes_price"]
    no_p  = market["no_price"]
    event = market["event_ticker"]

    if mid in open_ids or event in events_traded:
        return None
    if yes_p < MIN_ENTRY_PRICE and no_p < MIN_ENTRY_PRICE:
        return None
    if venue == "kalshi":
        yb, ya = market["yes_bid"], market["yes_ask"]
        if ya > 0 and yb > 0:
            spread = (ya - yb) / ((ya + yb) / 2)
            if spread > MAX_SPREAD_PCT:
                return None

    # ── Strategy 1: Arbitrage ─────────────────────────────────────────────────
    min_arb = MIN_EDGE_KALSHI_ARB if venue == "kalshi" else MIN_EDGE_POLY
    arb_gap = (yes_p + no_p) - 1.0
    if arb_gap > min_arb:
        direction = "NO" if no_p < (1.0 - yes_p) else "YES"
        entry_raw = no_p if direction == "NO" else yes_p
        entry  = _apply_slippage(entry_raw, direction)
        fill   = random.uniform(FILL_MIN, 1.0)
        amount = _size_trade(balance, venue, weights.get("arb", 1.0)) * fill
        shares = amount / entry if entry > 0 else 0
        fee    = _calc_fee(venue, shares, entry, amount)
        return TradeSignal(mid, market["question"], venue, direction,
                           arb_gap - min_arb, "arb", entry, amount, shares, fee)

    # ── Strategy 2: Spot-lag (Kalshi crypto brackets only) ───────────────────
    if venue == "kalshi" and market.get("cap_strike") and market.get("strike_type"):
        for asset, prefixes in _CRYPTO_TICKERS.items():
            if not any(mid.upper().startswith(p) for p in prefixes):
                continue
            spot = spot_prices.get(asset)
            if not spot or spot <= 0:
                break
            strike = float(market["cap_strike"])
            if strike <= 0:
                break
            dist = abs(spot - strike) / spot
            if dist < MIN_EDGE_KALSHI_SPOT:
                break
            stype = (market["strike_type"] or "").lower()
            if stype in ("greater", "above", "over", "t"):
                direction = "YES" if spot > strike else "NO"
            elif stype in ("lesser", "below", "under"):
                direction = "YES" if spot < strike else "NO"
            else:
                break
            entry_raw = yes_p if direction == "YES" else no_p
            if entry_raw < MIN_ENTRY_PRICE or entry_raw > 0.95:
                break
            entry  = _apply_slippage(entry_raw, direction)
            fill   = random.uniform(FILL_MIN, 1.0)
            amount = _size_trade(balance, venue, weights.get("spot_lag", 1.0)) * fill
            shares = amount / entry if entry > 0 else 0
            fee    = _calc_fee(venue, shares, entry, amount)
            return TradeSignal(mid, market["question"], venue, direction,
                               dist, "spot_lag", entry, amount, shares, fee)

    # ── Strategy 3: Momentum (Polymarket crypto) ─────────────────────────────
    if venue == "polymarket" and spot_prices:
        import re as _re
        for asset, prefixes in _CRYPTO_TICKERS.items():
            q_lower = market["question"].lower()
            if asset.lower() not in q_lower and not any(p.lower() in q_lower for p in prefixes):
                continue
            spot = spot_prices.get(asset)
            if not spot:
                continue
            thresh_match = _re.search(r"\$?([\d,]+(?:\.\d+)?)", market["question"])
            if not thresh_match:
                break
            try:
                threshold = float(thresh_match.group(1).replace(",", ""))
            except ValueError:
                break
            if threshold <= 0:
                break
            dist = abs(spot - threshold) / spot
            if dist < MIN_EDGE_POLY:
                break
            q = q_lower
            if "above" in q or "over" in q or "higher" in q:
                direction = "YES" if spot > threshold else "NO"
            elif "below" in q or "under" in q or "lower" in q:
                direction = "YES" if spot < threshold else "NO"
            else:
                break
            entry_raw = yes_p if direction == "YES" else no_p
            if entry_raw < MIN_ENTRY_PRICE or entry_raw > 0.95:
                break
            entry  = _apply_slippage(entry_raw, direction)
            fill   = random.uniform(FILL_MIN, 1.0)
            amount = _size_trade(balance, venue, weights.get("momentum", 1.0)) * fill
            shares = amount / entry if entry > 0 else 0
            fee    = _calc_fee(venue, shares, entry, amount)
            return TradeSignal(mid, market["question"], venue, direction,
                               dist, "momentum", entry, amount, shares, fee)

    # ── Strategy 4: Mean-reversion (Polymarket overpriced contracts) ─────────
    if venue == "polymarket":
        threshold = 0.15  # fires when yes_p > 0.85 or no_p > 0.85
        if yes_p > (1.0 - threshold):
            edge = yes_p - (1.0 - threshold)
            if edge >= MIN_EDGE_POLY:
                entry  = _apply_slippage(no_p, "NO")
                fill   = random.uniform(FILL_MIN, 1.0)
                amount = _size_trade(balance, venue, weights.get("mean_reversion", 1.0)) * fill
                shares = amount / entry if entry > 0 else 0
                fee    = _calc_fee(venue, shares, entry, amount)
                return TradeSignal(mid, market["question"], venue, "NO",
                                   edge, "mean_reversion", entry, amount, shares, fee)
        elif no_p > (1.0 - threshold):
            edge = no_p - (1.0 - threshold)
            if edge >= MIN_EDGE_POLY:
                entry  = _apply_slippage(yes_p, "YES")
                fill   = random.uniform(FILL_MIN, 1.0)
                amount = _size_trade(balance, venue, weights.get("mean_reversion", 1.0)) * fill
                shares = amount / entry if entry > 0 else 0
                fee    = _calc_fee(venue, shares, entry, amount)
                return TradeSignal(mid, market["question"], venue, "YES",
                                   edge, "mean_reversion", entry, amount, shares, fee)

    return None
