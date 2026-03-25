#!/usr/bin/env python3
"""
CalendarClaw — scheduled-catalyst prediction market trading.
Exploits predictable market behavior around known event times.

Strategies:
A. Pre-event positioning: enter when indecision is mispriced before catalyst
B. Post-release momentum: enter after event if repricing incomplete
C. Uncertainty collapse: sell rich uncertainty premium near resolution

Target events: CPI, Fed, sports game times, daily crypto closes.
Runs every 5 minutes. No LLM.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import datetime
from pathlib import Path
from dataclasses import dataclass

def _load_env():
    env_file = Path.home() / "openclaw" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

# Config
MAX_TRADES_PER_RUN = 30
POSITION_PCT = 0.03
MIN_ENTRY = 0.03
MAX_ENTRY = 0.97
MIN_EDGE_SCORE = 0.35

# Event families and their typical windows
EVENT_FAMILIES = {
    "cpi": {
        "keywords": ["cpi", "inflation", "consumer price"],
        "pre_window_hours": 4, "post_window_hours": 1,
        "typical_move": 0.08, "confidence_boost": 0.15,
    },
    "fed": {
        "keywords": ["fed", "fomc", "federal reserve", "rate"],
        "pre_window_hours": 6, "post_window_hours": 2,
        "typical_move": 0.10, "confidence_boost": 0.20,
    },
    "sports_nba": {
        "keywords": ["nba", "basketball"],
        "pre_window_hours": 4, "post_window_hours": 0.5,
        "typical_move": 0.05, "confidence_boost": 0.10,
    },
    "sports_mlb": {
        "keywords": ["mlb", "baseball"],
        "pre_window_hours": 4, "post_window_hours": 0.5,
        "typical_move": 0.05, "confidence_boost": 0.10,
    },
    "crypto_daily": {
        "keywords": ["bitcoin price range", "ethereum price", "btc", "eth", "bnb", "doge", "solana"],
        "pre_window_hours": 72, "post_window_hours": 0.25,
        "typical_move": 0.06, "confidence_boost": 0.10,
    },
    "weather": {
        "keywords": ["temperature", "weather", "max temp"],
        "pre_window_hours": 48, "post_window_hours": 1,
        "typical_move": 0.12, "confidence_boost": 0.15,
    },
    "treasury": {
        "keywords": ["treasury", "yield", "10-year", "10y"],
        "pre_window_hours": 2, "post_window_hours": 0.5,
        "typical_move": 0.05, "confidence_boost": 0.10,
    },
}


def _get_conn():
    db_path = Path(os.environ.get("CLAWMSON_DB_PATH",
                                   Path.home() / ".openclaw" / "clawmson.db"))
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _notify():
    try:
        import requests
        requests.post("http://127.0.0.1:7080/api/trading/notify", timeout=2)
    except Exception:
        pass


def _norm(v):
    if v is None: return 0
    f = float(v)
    return f / 100.0 if f > 1 else f


def _get_balance(conn) -> float:
    """CalendarClaw's own $1000 virtual wallet — only counts its own trades."""
    try:
        pnl = conn.execute("SELECT COALESCE(SUM(pnl), 0) FROM paper_trades WHERE strategy='calendarclaw' AND status IN ('closed_win','closed_loss','expired')").fetchone()[0]
        return 1000.0 + pnl
    except Exception:
        return 1000.0


def _classify_event(title: str, ticker: str) -> str | None:
    """Match market to event family."""
    combined = (title + " " + ticker).lower()
    for family, config in EVENT_FAMILIES.items():
        if any(kw in combined for kw in config["keywords"]):
            return family
    return None


def _get_price_history(conn, ticker: str, hours: int = 12) -> list[float]:
    """Get recent YES bid prices for pattern analysis."""
    cutoff = (datetime.datetime.utcnow() - datetime.timedelta(hours=hours)).isoformat()
    rows = conn.execute("""
        SELECT yes_bid FROM kalshi_markets WHERE ticker=? AND fetched_at > ?
        ORDER BY fetched_at ASC
    """, (ticker, cutoff)).fetchall()
    return [_norm(r["yes_bid"]) for r in rows if r["yes_bid"]]


def scan_calendar_setups(conn, balance, open_ids) -> int:
    """Find markets approaching known catalysts with tradeable setups."""
    now = datetime.datetime.utcnow()
    placed = 0
    events_seen = set()

    rows = conn.execute("""
        SELECT km.ticker, km.title, km.yes_bid, km.yes_ask, km.no_bid, km.no_ask,
               km.close_time, km.event_ticker, km.volume_24h
        FROM kalshi_markets km
        INNER JOIN (SELECT ticker, MAX(fetched_at) as latest FROM kalshi_markets GROUP BY ticker) l
        ON km.ticker = l.ticker AND km.fetched_at = l.latest
        WHERE km.close_time IS NOT NULL AND km.close_time != ''
        AND (km.yes_bid > 0 OR km.yes_ask > 0)
    """).fetchall()

    for r in rows:
        if placed >= MAX_TRADES_PER_RUN:
            break

        ticker = r["ticker"]
        if ticker in open_ids:
            continue

        evt = r["event_ticker"] or ticker[:20]
        if evt in events_seen:
            continue

        title = r["title"] or ""
        family = _classify_event(title, ticker)
        if not family:
            continue

        config = EVENT_FAMILIES[family]

        # Parse close time
        try:
            ct = datetime.datetime.fromisoformat(r["close_time"].replace("Z", "+00:00"))
            hours_to_close = (ct.replace(tzinfo=None) - now).total_seconds() / 3600
        except Exception:
            continue

        if hours_to_close < 0.05 or hours_to_close > 168:
            continue

        ya = _norm(r["yes_ask"]) or _norm(r["yes_bid"])
        na = _norm(r["no_ask"]) or _norm(r["no_bid"])
        yb = _norm(r["yes_bid"])

        if ya <= 0 and na <= 0:
            continue

        # Spread filter
        if yb > 0 and ya > 0:
            spread = (ya - yb) / ya
            if spread > 0.30:
                continue

        # Score the setup
        score = 0.0
        direction = None
        entry = None
        thesis = ""

        # Strategy A: Pre-event positioning
        # In the window before a catalyst, prices tend to drift toward extremes
        if hours_to_close <= config["pre_window_hours"] and hours_to_close > 0.5:
            # Get price history to detect drift
            history = _get_price_history(conn, ticker)

            if len(history) >= 3:
                recent_avg = sum(history[-3:]) / 3
                older_avg = sum(history[:3]) / 3 if len(history) >= 6 else recent_avg

                drift = recent_avg - older_avg

                if drift > 0.01:
                    # Price drifting up → momentum into catalyst
                    direction = "YES"
                    entry = ya
                    score = 0.5 + config["confidence_boost"]
                    thesis = f"pre-event momentum: {family}, {hours_to_close:.1f}h to close, price drifting up"
                elif drift < -0.01:
                    direction = "NO"
                    entry = na
                    score = 0.5 + config["confidence_boost"]
                    thesis = f"pre-event momentum: {family}, {hours_to_close:.1f}h to close, price drifting down"

            # Indecision pricing: if price near 50%, there's uncertainty premium
            if not direction and 0.40 < ya < 0.60 and hours_to_close < config["pre_window_hours"] / 2:
                # Near-expiry indecision — fade toward NO (status quo bias)
                direction = "NO"
                entry = na
                score = 0.45 + config["confidence_boost"]
                thesis = f"pre-event indecision: {family}, {hours_to_close:.1f}h, price at {ya:.2f} (coin flip → fade)"

            # Cold-start lean: no history but strong price lean away from 50%
            if not direction and len(history) < 3:
                if ya > 0 and ya < 0.30:
                    direction = "NO"
                    entry = na if na > 0 else (1 - ya)
                    score = 0.40 + config["confidence_boost"]
                    thesis = f"pre-event cold-start lean: {family}, {hours_to_close:.1f}h, YES at {ya:.2f} (low → NO)"
                elif ya > 0.70:
                    direction = "YES"
                    entry = ya
                    score = 0.40 + config["confidence_boost"]
                    thesis = f"pre-event cold-start lean: {family}, {hours_to_close:.1f}h, YES at {ya:.2f} (high → YES)"

        # Strategy B: Near-expiry convergence (within 1 hour)
        if not direction and hours_to_close < 1.0 and hours_to_close > 0.1:
            # Strong lean → bet on continuation
            if ya > 0.75:
                direction = "YES"
                entry = ya
                score = 0.55 + config["confidence_boost"]
                thesis = f"near-expiry lean: {family}, {hours_to_close*60:.0f}min, YES at {ya:.2f}"
            elif ya < 0.25:
                direction = "NO"
                entry = na
                score = 0.55 + config["confidence_boost"]
                thesis = f"near-expiry lean: {family}, {hours_to_close*60:.0f}min, YES at {ya:.2f} (low → NO)"

        if not direction or not entry or score < MIN_EDGE_SCORE:
            continue

        if entry < MIN_ENTRY or entry > MAX_ENTRY:
            continue

        # Size
        amount = min(POSITION_PCT * balance, balance * 0.10)
        if amount < 2:
            continue

        shares = amount / entry
        edge = score - 0.50  # edge above coin flip

        # Place trade
        ts = now.isoformat()
        try:
            conn.execute("""
                INSERT INTO paper_trades
                (market_id, question, direction, shares, entry_price, amount_usd,
                 status, confidence, reasoning, strategy, opened_at)
                VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?)
            """, (
                ticker, title[:200], direction, shares, entry, amount,
                score,
                f"calendarclaw: {thesis}",
                "calendarclaw", ts,
            ))
            conn.commit()
            placed += 1
            open_ids.add(ticker)
            events_seen.add(evt)
            print(f"[calendar] {direction} ${amount:.0f} '{title[:40]}' score={score:.2f} [{family}] {hours_to_close:.1f}h")
        except Exception as e:
            print(f"[calendar] Error: {e}")

    return placed


def resolve_trades(conn) -> int:
    try:
        from scripts.mirofish.kalshi_feed import _call_kalshi
    except ImportError:
        return 0

    trades = conn.execute(
        "SELECT id, market_id, direction, entry_price, shares FROM paper_trades WHERE status='open' AND strategy='calendarclaw'"
    ).fetchall()

    resolved = 0
    for t in trades:
        data = _call_kalshi("GET", f"/markets/{t['market_id']}")
        if not data:
            continue
        m = data.get("market", data)
        result = m.get("result", "")
        if not result:
            continue

        we_bet = t["direction"].lower()
        we_won = (result == "yes" and we_bet == "yes") or (result == "no" and we_bet == "no")
        exit_price = 1.0 if we_won else 0.0
        pnl = t["shares"] * (exit_price - t["entry_price"])
        status = "closed_win" if we_won else "closed_loss"

        conn.execute("UPDATE paper_trades SET exit_price=?, pnl=?, status=?, closed_at=? WHERE id=?",
                     (exit_price, pnl, status, datetime.datetime.utcnow().isoformat(), t["id"]))
        sign = "+" if pnl >= 0 else ""
        print(f"[calendar] Resolved: {status} {sign}${pnl:.2f} {t['market_id'][:30]}")
        resolved += 1

    if resolved:
        conn.commit()
    return resolved


def run():
    try:
        from scripts.mirofish.paper_wallet import check_circuit_breaker, reset_wallet
        breaker = check_circuit_breaker()
        if breaker:
            print("[calendar] Circuit breaker")
            reset_wallet()
            _notify()
            return
    except Exception:
        pass

    conn = _get_conn()
    balance = _get_balance(conn)
    open_ids = set(r[0] for r in conn.execute("SELECT market_id FROM paper_trades WHERE status='open'").fetchall())

    placed = scan_calendar_setups(conn, balance, open_ids)
    resolved = resolve_trades(conn)
    conn.close()

    if placed > 0 or resolved > 0:
        print(f"[calendar] Placed {placed}, resolved {resolved}")
        _notify()
    else:
        print(f"[calendar] No calendar setups found")


if __name__ == "__main__":
    _load_env()
    run()
