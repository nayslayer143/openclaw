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


# ── Trade placement ───────────────────────────────────────────────────────────

def get_open_ids(conn: sqlite3.Connection) -> set:
    rows = conn.execute("SELECT market_id FROM paper_trades WHERE status='open'").fetchall()
    return {r["market_id"] for r in rows}


def load_spot_prices(conn: sqlite3.Connection) -> dict:
    spot = {}
    try:
        rows = conn.execute("""
            SELECT ticker, amount_usd FROM spot_prices
            WHERE ticker LIKE 'SPOT:%'
            ORDER BY fetched_at DESC
        """).fetchall()
        for r in rows:
            asset = r["ticker"].replace("SPOT:", "")
            if asset not in spot:
                spot[asset] = float(r["amount_usd"])
    except Exception:
        pass
    return spot


def place_trade(conn: sqlite3.Connection, sig, balance: float) -> object:
    """Insert a paper trade. Returns row ID or None if invalid."""
    if sig.shares <= 0:
        return None
    ts = datetime.datetime.utcnow().isoformat()
    try:
        cur = conn.execute("""
            INSERT INTO paper_trades
              (market_id, question, direction, shares, entry_price, amount_usd,
               status, confidence, reasoning, strategy, opened_at,
               venue, expected_edge, entry_fee)
            VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?, ?, ?)
        """, (
            sig.market_id, sig.question[:200], sig.direction, sig.shares,
            sig.entry_price, sig.amount_usd,
            min(sig.edge / 0.10, 1.0),
            f"{sig.strategy}: edge={sig.edge:.3f} entry={sig.entry_price:.3f}",
            sig.strategy, ts, sig.venue, sig.edge, sig.fee,
        ))
        conn.commit()
        return cur.lastrowid
    except Exception as e:
        print(f"[HFT] place_trade error: {e}")
        return None


# ── Resolution loop ───────────────────────────────────────────────────────────

def _fetch_result(venue: str, market_id: str) -> object:
    """Fetch resolution result. Returns 'yes', 'no', or None if still open."""
    if venue == "kalshi":
        data = _call_kalshi("GET", f"/markets/{market_id}")
        if not data:
            return None
        m = data.get("market", data)
        result = (m.get("result") or "").lower().strip()
        return result if result in ("yes", "no") else None
    # Polymarket
    try:
        resp = requests.get(GAMMA_API, params={"id": market_id, "closed": "true"}, timeout=15)
        resp.raise_for_status()
        raw = resp.json()
        markets = raw if isinstance(raw, list) else raw.get("markets", [raw])
        for m in markets:
            if not m.get("closed"):
                return None
            winner = (m.get("winningOutcome") or m.get("winning_side") or "").lower()
            if winner in ("yes", "no"):
                return winner
    except Exception:
        pass
    return None


def resolve_expired(conn: sqlite3.Connection) -> int:
    """Check open trades against venue APIs. Closes resolved ones. Returns count."""
    open_trades = conn.execute(
        "SELECT id, market_id, direction, entry_price, shares, venue "
        "FROM paper_trades WHERE status='open' ORDER BY opened_at ASC LIMIT 50"
    ).fetchall()

    resolved = 0
    for t in open_trades:
        result = _fetch_result(t["venue"], t["market_id"])
        if result is None:
            continue
        we_bet = t["direction"].lower()
        we_won = (result == "yes" and we_bet == "yes") or (result == "no" and we_bet == "no")
        exit_price = 1.0 if we_won else 0.0
        pnl = t["shares"] * (exit_price - t["entry_price"])
        status = "closed_win" if we_won else "closed_loss"
        now = datetime.datetime.utcnow().isoformat()
        conn.execute("""
            UPDATE paper_trades
            SET exit_price=?, pnl=?, status=?, closed_at=?, resolved_price=?
            WHERE id=?
        """, (exit_price, pnl, status, now, exit_price, t["id"]))
        sign = "+" if pnl >= 0 else ""
        print(f"[HFT] Resolved {t['market_id'][:35]} → {status} {sign}${pnl:.2f}")
        resolved += 1
    if resolved:
        conn.commit()
    return resolved


# ── Strategy weight evolution ─────────────────────────────────────────────────

_ALL_STRATEGIES = ("arb", "spot_lag", "momentum", "mean_reversion")


def evolve_weights(conn: sqlite3.Connection, weights: dict) -> dict:
    """
    Adjust Kelly multipliers from last 100 resolved trades per strategy.
    Win rate > 60% → weight × 1.1 (max 1.5)
    Win rate < 45% → weight × 0.9 (min 0.5)
    < 10 resolved → unchanged
    """
    new_weights = dict(weights)
    for strategy in _ALL_STRATEGIES:
        row = conn.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN status='closed_win' THEN 1 ELSE 0 END) as wins
            FROM paper_trades
            WHERE strategy=? AND status IN ('closed_win', 'closed_loss')
            ORDER BY closed_at DESC
            LIMIT 100
        """, (strategy,)).fetchone()
        total = row["total"] if row else 0
        wins  = row["wins"]  if row else 0
        if total < 10:
            new_weights.setdefault(strategy, 1.0)
            continue
        win_rate = wins / total
        current  = new_weights.get(strategy, 1.0)
        if win_rate > 0.60:
            new_weights[strategy] = min(current * 1.1, 1.5)
        elif win_rate < 0.45:
            new_weights[strategy] = max(current * 0.9, 0.5)
        else:
            new_weights[strategy] = current
    return new_weights


# ── Connectivity checks ───────────────────────────────────────────────────────

def _verify_connectivity() -> bool:
    ok = True
    data = _call_kalshi("GET", "/exchange/status")
    if data:
        print("[HFT] Kalshi prod API: connected")
    else:
        print("[HFT] WARNING: Kalshi API unreachable — Kalshi trades will be skipped")
        ok = False
    try:
        resp = requests.get(GAMMA_API, params={"limit": 1}, timeout=10)
        resp.raise_for_status()
        print("[HFT] Polymarket gamma API: connected")
    except Exception as e:
        print(f"[HFT] WARNING: Polymarket API unreachable: {e}")
        ok = False
    return ok


def _notify_dashboard():
    try:
        requests.post("http://127.0.0.1:7080/api/trading/notify", timeout=2)
    except Exception:
        pass


# ── Cycle ─────────────────────────────────────────────────────────────────────

def _run_cycle(conn: sqlite3.Connection, weights: dict, poly_cache: list, cycle_num: int) -> tuple:
    """One full trading cycle. Returns (trades_placed, trades_resolved)."""
    balance  = get_balance(conn)
    open_ids = get_open_ids(conn)
    spot_prices = load_spot_prices(conn)
    events_traded: set = set()

    kalshi_markets = fetch_kalshi_markets()

    if cycle_num % POLY_REFRESH_CYCLES == 1 or not poly_cache:
        fresh = fetch_polymarket_markets()
        poly_cache.clear()
        poly_cache.extend(fresh)

    all_markets = kalshi_markets + poly_cache
    placed = 0
    kalshi_placed = 0

    for market in all_markets:
        if market["venue"] == "kalshi" and kalshi_placed >= MAX_KALSHI_PER_CYCLE:
            continue
        sig = score_market(market, spot_prices, open_ids, events_traded, weights, balance)
        if sig is None:
            continue
        trade_id = place_trade(conn, sig, balance)
        if trade_id is not None:
            placed += 1
            open_ids.add(sig.market_id)
            events_traded.add(market["event_ticker"])
            if market["venue"] == "kalshi":
                kalshi_placed += 1

    resolved = resolve_expired(conn)
    return placed, resolved


# ── Main daemon ───────────────────────────────────────────────────────────────

_running = True


def _handle_signal(signum, frame):
    global _running
    print(f"\n[HFT] Signal {signum} — shutting down after this cycle...")
    _running = False


def run():
    """Main entry point. Daemon loop until SIGINT/SIGTERM."""
    global _running
    _running = True
    _load_env()

    print("=" * 60)
    print("[HFT] High-Frequency Paper Trader starting up")
    print(f"[HFT] Cycle: {CYCLE_SLEEP}s | Target: 100+ bets/hour")
    print("=" * 60)

    signal.signal(signal.SIGINT,  _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    conn = get_conn()
    db_startup(conn)
    _verify_connectivity()

    weights: dict = {s: 1.0 for s in _ALL_STRATEGIES}
    poly_cache: list = []
    session_placed   = 0
    session_resolved = 0
    session_start    = datetime.datetime.utcnow()
    cycle_num        = 0

    print(f"\n[HFT] Clean slate. Balance: $10,000.00. Starting loop...\n")

    while _running:
        cycle_num += 1
        cycle_start = time.time()
        try:
            placed, resolved = _run_cycle(conn, weights, poly_cache, cycle_num)
            weights = evolve_weights(conn, weights)
            session_placed   += placed
            session_resolved += resolved
            balance  = get_balance(conn)
            elapsed_min = (datetime.datetime.utcnow() - session_start).total_seconds() / 60
            rate = session_placed / elapsed_min if elapsed_min > 0 else 0
            open_count = conn.execute(
                "SELECT COUNT(*) FROM paper_trades WHERE status='open'"
            ).fetchone()[0]
            pnl = balance - 10000.0
            print(
                f"[HFT cycle {cycle_num:4d}] placed={placed:2d} resolved={resolved:2d} "
                f"open={open_count:3d} balance=${balance:,.2f} "
                f"({'+'if pnl>=0 else ''}{pnl:,.2f}) rate={rate:.1f}/min"
            )
            weight_str = " | ".join(
                f"{s}:{w:.2f}" for s, w in sorted(weights.items()) if w != 1.0
            )
            if weight_str:
                print(f"[HFT]       weights: {weight_str}")
            if placed > 0 or resolved > 0:
                _notify_dashboard()
        except Exception as e:
            print(f"[HFT] Cycle {cycle_num} error: {e}")
            import traceback; traceback.print_exc()
        elapsed = time.time() - cycle_start
        sleep_time = max(0, CYCLE_SLEEP - elapsed)
        if _running and sleep_time > 0:
            time.sleep(sleep_time)

    elapsed_total = (datetime.datetime.utcnow() - session_start).total_seconds()
    final_balance = get_balance(conn)
    final_pnl     = final_balance - 10000.0
    print("\n" + "=" * 60)
    print("[HFT] Session complete")
    print(f"  Runtime:   {elapsed_total/60:.1f} min ({cycle_num} cycles)")
    print(f"  Placed:    {session_placed} trades ({session_placed/(elapsed_total/3600):.0f}/hr)")
    print(f"  Resolved:  {session_resolved} trades")
    print(f"  Final P&L: {'+'if final_pnl>=0 else ''}{final_pnl:,.2f} ({final_pnl/10000*100:.2f}%)")
    print(f"  Balance:   ${final_balance:,.2f}")
    print("=" * 60)
    conn.close()


if __name__ == "__main__":
    run()
