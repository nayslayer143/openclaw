#!/usr/bin/env python3
"""
LotteryClaw — ultra-cheap contract strategy.
Buys contracts priced $0.01-$0.15 with $50-100 bets.
Low win rate (10-15%), massive payoff ratio (7-10x).
Inspired by RivalClaw's $54K success. Our own implementation.
"""
import os
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from scripts.mirofish.bot_config import get_param as _p, is_trading_hours

DB_PATH = Path(os.environ.get("CLAWMSON_DB_PATH", Path.home() / ".openclaw" / "clawmson.db"))

MAX_TRADES_PER_RUN = _p("lotteryclaw", "MAX_TRADES_PER_RUN", 30)
BET_SIZE_USD       = _p("lotteryclaw", "BET_SIZE_USD", 75.0)
MAX_ENTRY          = 0.15   # only ultra-cheap contracts
MIN_ENTRY          = 0.01   # not literally zero
MIN_HOURS_TO_CLOSE = 0.25   # at least 15 min left
MAX_HOURS_TO_CLOSE = 48     # not too far out (RivalClaw sweet spot)
DASHBOARD_URL      = "http://127.0.0.1:7080/api/trading/notify"


def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def get_balance(conn):
    """LotteryClaw's own $1000 virtual wallet — only counts its own trades."""
    pnl = conn.execute(
        "SELECT COALESCE(SUM(pnl), 0) FROM paper_trades "
        "WHERE strategy='lotteryclaw' AND status IN ('closed_win','closed_loss','expired')"
    ).fetchone()[0]
    return 1000.0 + pnl


def get_open_ids(conn):
    rows = conn.execute(
        "SELECT market_id FROM paper_trades WHERE strategy='lotteryclaw' AND status='open'"
    ).fetchall()
    return {r["market_id"] for r in rows}


def hours_until(iso_str):
    try:
        if not iso_str:
            return None
        if iso_str.endswith("Z"):
            iso_str = iso_str[:-1] + "+00:00"
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (dt - datetime.now(timezone.utc)).total_seconds() / 3600
    except Exception:
        return None


def score_market(m):
    """Score a Kalshi market for lottery potential.
    Returns (direction, entry, confidence, thesis) or None.

    Strategy: buy whichever side is ultra-cheap ($0.01-$0.15).
    The market is saying "this almost certainly won't happen."
    We're betting it sometimes does.
    """
    ya = float(m.get("yes_ask") or 0)
    na = float(m.get("no_ask") or 0)

    candidates = []

    # Check YES side — is it ultra-cheap?
    if MIN_ENTRY <= ya <= MAX_ENTRY and ya > 0:
        payoff = (1.0 - ya) / ya
        if payoff >= 5:  # at least 5:1 payoff
            candidates.append(("YES", ya, payoff, f"YES ultra-cheap {ya:.3f}, payoff {payoff:.0f}:1"))

    # Check NO side — is it ultra-cheap?
    if MIN_ENTRY <= na <= MAX_ENTRY and na > 0:
        payoff = (1.0 - na) / na
        if payoff >= 5:
            candidates.append(("NO", na, payoff, f"NO ultra-cheap {na:.3f}, payoff {payoff:.0f}:1"))

    if not candidates:
        return None

    # Pick the one with better payoff ratio
    candidates.sort(key=lambda x: x[2], reverse=True)
    direction, entry, payoff, thesis = candidates[0]
    confidence = min(0.15 + (payoff - 5) * 0.01, 0.30)  # low confidence by design
    return (direction, entry, confidence, thesis)


def place_trade(conn, market_id, question, direction, entry, confidence, thesis, balance):
    """Place a lottery trade."""
    amount = min(BET_SIZE_USD, balance * 0.15)  # max 15% of wallet per trade
    if amount < 10:
        return False
    shares = amount / entry if entry > 0 else 0
    if shares <= 0:
        return False

    ts = datetime.now(timezone.utc).isoformat()
    conn.execute("""
        INSERT INTO paper_trades
        (market_id, question, direction, shares, entry_price, amount_usd,
         status, confidence, reasoning, strategy, opened_at)
        VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?)
    """, (
        market_id, question[:200], direction, shares, entry, amount,
        confidence, f"lotteryclaw: {thesis}", "lotteryclaw", ts,
    ))
    return True


def run():
    if not is_trading_hours():
        print("[lottery] Outside trading hours (00-06 UTC) — skipping")
        return

    conn = get_conn()
    balance = get_balance(conn)
    open_ids = get_open_ids(conn)
    placed = 0
    now_utc = datetime.now(timezone.utc)

    print(f"[lottery] {now_utc.isoformat()} balance=${balance:.2f} open_ids={len(open_ids)}")

    if balance < 100:
        print("[lottery] Balance too low (<$100), skipping")
        conn.close()
        return

    # Scan Kalshi markets for ultra-cheap contracts
    markets = conn.execute("""
        SELECT ticker, title, yes_bid, yes_ask, no_bid, no_ask,
               volume, close_time, event_ticker
        FROM kalshi_markets
        WHERE status IN ('open','active') AND close_time IS NOT NULL
        ORDER BY close_time ASC
    """).fetchall()

    seen_events = set()  # one trade per event to diversify

    for m in markets:
        if placed >= MAX_TRADES_PER_RUN:
            break

        ticker = m["ticker"] or ""
        if ticker in open_ids:
            continue

        # One trade per event ticker (diversification)
        evt = m["event_ticker"] or ticker[:20]
        if evt in seen_events:
            continue

        h = hours_until(m["close_time"])
        if h is None or h < MIN_HOURS_TO_CLOSE or h > MAX_HOURS_TO_CLOSE:
            continue

        result = score_market(dict(m))
        if result:
            direction, entry, conf, thesis = result
            if place_trade(conn, ticker, m["title"] or "", direction, entry, conf, thesis, balance):
                placed += 1
                open_ids.add(ticker)
                seen_events.add(evt)
                print(f"  [L] {direction} {entry:.3f} ${BET_SIZE_USD:.0f} | {(m['title'] or '')[:45]} | {thesis}")

    conn.commit()
    conn.close()

    print(f"[lottery] placed {placed} trades")

    if placed > 0:
        try:
            import requests
            requests.post(DASHBOARD_URL, json={"source": "lotteryclaw", "trades": placed}, timeout=5)
        except Exception:
            pass


if __name__ == "__main__":
    run()
