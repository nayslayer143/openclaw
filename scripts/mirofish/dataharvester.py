#!/usr/bin/env python3
"""
DataHarvester — high-volume non-LLM systematic bettor.
Places small paper bets across ALL available markets for data collection.
No Ollama. Pure math. Runs every 2 minutes via cron.
"""
import os, sys, sqlite3, time, json, requests
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(os.environ.get("CLAWMSON_DB_PATH", Path.home() / ".openclaw" / "clawmson.db"))

MAX_TRADES_PER_RUN = 50
BET_SIZE_USD = 4.0
MIN_ENTRY = 0.03
MAX_ENTRY = 0.97
MIN_HOURS_TO_CLOSE = 0.05
MAX_HOURS_TO_CLOSE = 168
FAIR_VALUE = 0.50
EDGE_THRESHOLD = 0.08
DASHBOARD_URL = "http://127.0.0.1:7080/api/trading/notify"


def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def get_open_ids(conn):
    rows = conn.execute("SELECT market_id FROM paper_trades WHERE status='open'").fetchall()
    return {r["market_id"] for r in rows}


def get_balance(conn):
    starting = 1000.0
    ctx = conn.execute(
        "SELECT value FROM context WHERE chat_id='mirofish' AND key='starting_balance'"
    ).fetchone()
    if ctx:
        starting = float(ctx[0])
    closed_pnl = conn.execute(
        "SELECT COALESCE(SUM(pnl), 0) FROM paper_trades WHERE status IN ('closed_win','closed_loss','expired')"
    ).fetchone()[0]
    return starting + closed_pnl


def fetch_kalshi_markets(conn):
    rows = conn.execute("""
        SELECT ticker, title, yes_bid, yes_ask, no_bid, no_ask,
               volume, close_time, event_ticker
        FROM kalshi_markets
        WHERE status='open' AND close_time IS NOT NULL
        ORDER BY close_time ASC
    """).fetchall()
    return [dict(r) for r in rows]


def fetch_polymarket_markets(conn):
    rows = conn.execute("""
        SELECT market_id, question, yes_price, no_price, volume, end_date
        FROM market_data
        WHERE end_date IS NOT NULL
        GROUP BY market_id
        HAVING fetched_at = MAX(fetched_at)
        ORDER BY end_date ASC
    """).fetchall()
    return [dict(r) for r in rows]


def hours_until(iso_str):
    try:
        if iso_str.endswith("Z"):
            iso_str = iso_str[:-1] + "+00:00"
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return (dt - now).total_seconds() / 3600
    except Exception:
        return None


def score_kalshi(m):
    ya = float(m.get("yes_ask") or 0)
    na = float(m.get("no_ask") or 0)
    yb = float(m.get("yes_bid") or 0)

    mid = (ya + yb) / 2 if ya > 0 and yb > 0 else ya if ya > 0 else 0.5
    deviation = abs(mid - FAIR_VALUE)

    if deviation >= EDGE_THRESHOLD:
        if mid < FAIR_VALUE - EDGE_THRESHOLD and ya > 0 and MIN_ENTRY <= ya <= MAX_ENTRY:
            conf = min(0.5 + deviation, 0.85)
            return ("YES", ya, conf, f"underpriced YES mid={mid:.3f}")
        elif mid > FAIR_VALUE + EDGE_THRESHOLD and na > 0 and MIN_ENTRY <= na <= MAX_ENTRY:
            conf = min(0.5 + deviation, 0.85)
            return ("NO", na, conf, f"overpriced YES mid={mid:.3f}")

    h = hours_until(m.get("close_time", ""))
    if h and h < 2:
        if mid > 0.75 and ya > 0 and ya <= MAX_ENTRY:
            return ("YES", ya, 0.65, f"near-expiry lean YES mid={mid:.3f} {h:.1f}h left")
        elif mid < 0.25 and na > 0 and na <= MAX_ENTRY:
            return ("NO", na, 0.65, f"near-expiry lean NO mid={mid:.3f} {h:.1f}h left")

    if ya > 0 and yb > 0:
        spread = ya - yb
        if spread > 0.10 and ya <= MAX_ENTRY:
            if ya < 0.5:
                return ("YES", ya, 0.50, f"spread capture YES spread={spread:.3f}")
            elif na > 0 and na <= MAX_ENTRY:
                return ("NO", na, 0.50, f"spread capture NO spread={spread:.3f}")

    return None


def score_polymarket(m):
    yp = float(m.get("yes_price") or 0.5)
    np = float(m.get("no_price") or 0.5)

    deviation = abs(yp - FAIR_VALUE)
    if deviation >= EDGE_THRESHOLD:
        if yp < FAIR_VALUE - EDGE_THRESHOLD and MIN_ENTRY <= yp <= MAX_ENTRY:
            return ("YES", yp, min(0.5 + deviation, 0.85), f"poly underpriced YES={yp:.3f}")
        elif yp > FAIR_VALUE + EDGE_THRESHOLD and MIN_ENTRY <= np <= MAX_ENTRY:
            return ("NO", np, min(0.5 + deviation, 0.85), f"poly overpriced YES={yp:.3f}")

    return None


def place_trade(conn, market_id, question, direction, entry, confidence, thesis, balance):
    amount = min(BET_SIZE_USD, balance * 0.05)
    if amount < 1:
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
        confidence, f"dataharvester: {thesis}", "dataharvester", ts,
    ))
    return True


def run():
    conn = get_conn()
    balance = get_balance(conn)
    open_ids = get_open_ids(conn)
    placed = 0
    now_utc = datetime.now(timezone.utc)

    print(f"[harvester] {now_utc.isoformat()} balance=${balance:.2f} open={len(open_ids)}")

    kalshi = fetch_kalshi_markets(conn)
    for m in kalshi:
        if placed >= MAX_TRADES_PER_RUN:
            break
        ticker = m.get("ticker", "")
        if ticker in open_ids:
            continue
        h = hours_until(m.get("close_time", ""))
        if h is None or h < MIN_HOURS_TO_CLOSE or h > MAX_HOURS_TO_CLOSE:
            continue
        result = score_kalshi(m)
        if result:
            direction, entry, conf, thesis = result
            if place_trade(conn, ticker, m.get("title", "")[:200], direction, entry, conf, thesis, balance):
                placed += 1
                open_ids.add(ticker)
                print(f"  [K] {direction} {entry:.3f} c={conf:.2f} | {m.get('title','')[:50]} | {thesis}")

    poly = fetch_polymarket_markets(conn)
    for m in poly:
        if placed >= MAX_TRADES_PER_RUN:
            break
        mid = m.get("market_id", "")
        if mid in open_ids:
            continue
        h = hours_until(m.get("end_date", ""))
        if h is None or h < MIN_HOURS_TO_CLOSE or h > MAX_HOURS_TO_CLOSE:
            continue
        result = score_polymarket(m)
        if result:
            direction, entry, conf, thesis = result
            if place_trade(conn, mid, m.get("question", "")[:200], direction, entry, conf, thesis, balance):
                placed += 1
                open_ids.add(mid)
                print(f"  [P] {direction} {entry:.3f} c={conf:.2f} | {m.get('question','')[:50]} | {thesis}")

    conn.commit()
    conn.close()

    print(f"[harvester] placed {placed} trades")

    if placed > 0:
        try:
            requests.post(DASHBOARD_URL, json={"source": "dataharvester", "trades": placed}, timeout=5)
        except Exception:
            pass


if __name__ == "__main__":
    run()
