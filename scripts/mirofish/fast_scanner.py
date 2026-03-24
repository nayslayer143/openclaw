#!/usr/bin/env python3
"""
Fast scanner — runs every 10 minutes, targets 15-min and hourly Kalshi markets
using pure-math strategies (no LLM). Spot-price-vs-market dislocation only.

This is separate from the main simulator loop to avoid Ollama latency.
Executes in <5 seconds.

Usage:
    python3 -m scripts.mirofish.fast_scanner
    # or via cron: */10 * * * *
"""
from __future__ import annotations

import os
import sys
import math
import datetime
import sqlite3
from pathlib import Path


def _load_env():
    env_file = Path.home() / "openclaw" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def _get_conn():
    db_path = Path(os.environ.get("CLAWMSON_DB_PATH",
                                   Path.home() / ".openclaw" / "clawmson.db"))
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MAX_EXPIRY_HOURS = float(os.environ.get("FAST_SCAN_MAX_HOURS", "2.0"))
MIN_EDGE = float(os.environ.get("FAST_SCAN_MIN_EDGE", "0.04"))
POSITION_PCT = float(os.environ.get("FAST_SCAN_POSITION_PCT", "0.05"))
MAX_POSITION_PCT = float(os.environ.get("MIROFISH_MAX_POSITION_PCT", "0.10"))
ARB_THRESHOLD = 0.03
MAX_TRADES_PER_RUN = int(os.environ.get("FAST_SCAN_MAX_TRADES", "10"))
MAX_PER_EVENT = int(os.environ.get("FAST_SCAN_MAX_PER_EVENT", "1"))  # 1 bracket per event

# Crypto assets we can price-check against spot
CRYPTO_TICKERS = {
    "DOGE": ["KXDOGE15M", "KXDOGE"],
    "ADA": ["KXADA15M", "KXADA"],
    "BNB": ["KXBNB15M", "KXBNB"],
    "BCH": ["KXBCH15M", "KXBCH"],
    "BTC": ["KXBTC"],
    "ETH": ["KXETH"],
}

# Index tickers for hourly S&P/Nasdaq
INDEX_SERIES = {
    "SPX": ["INXI", "KXINXSPX"],
    "NDX": ["NASDAQ100I", "KXINXNDX"],
}


def _notify_dashboard():
    try:
        import requests
        requests.post("http://127.0.0.1:7080/api/trading/notify", timeout=2)
    except Exception:
        pass


def run():
    """Fast scan: find short-expiry Kalshi markets with spot-price edge."""
    now = datetime.datetime.utcnow()
    max_close = (now + datetime.timedelta(hours=MAX_EXPIRY_HOURS)).isoformat()

    conn = _get_conn()

    # Get latest Kalshi markets expiring soon
    try:
        markets = conn.execute("""
            SELECT km.* FROM kalshi_markets km
            INNER JOIN (
                SELECT ticker, MAX(fetched_at) AS latest
                FROM kalshi_markets GROUP BY ticker
            ) l ON km.ticker = l.ticker AND km.fetched_at = l.latest
            WHERE km.close_time != '' AND km.close_time < ?
            AND (km.yes_bid > 0 OR km.yes_ask > 0)
        """, (max_close,)).fetchall()
    except Exception as e:
        print(f"[fast_scan] DB error: {e}")
        conn.close()
        return

    if not markets:
        print(f"[fast_scan] No markets expiring within {MAX_EXPIRY_HOURS}h")
        conn.close()
        return

    print(f"[fast_scan] {len(markets)} markets expiring within {MAX_EXPIRY_HOURS}h")

    # Get spot prices
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
                spot[asset] = r["amount_usd"]
    except Exception:
        pass

    # Get wallet balance
    try:
        ctx = conn.execute(
            "SELECT value FROM context WHERE chat_id='mirofish' AND key='starting_balance'"
        ).fetchone()
        starting = float(ctx[0]) if ctx else 1000.0
        closed_pnl = conn.execute(
            "SELECT COALESCE(SUM(pnl), 0) FROM paper_trades WHERE status != 'open'"
        ).fetchone()[0]
        balance = starting + closed_pnl
    except Exception:
        balance = 1000.0

    # Check for duplicate positions
    try:
        open_ids = set(
            r[0] for r in conn.execute(
                "SELECT market_id FROM paper_trades WHERE status='open'"
            ).fetchall()
        )
    except Exception:
        open_ids = set()

    trades_placed = 0
    events_traded: set[str] = set()  # limit 1 bracket per event

    for m in markets:
        if trades_placed >= MAX_TRADES_PER_RUN:
            break

        # Skip if already traded this event (avoid spamming every bracket)
        event_ticker = m["event_ticker"] if m["event_ticker"] else m["ticker"][:20]
        if event_ticker in events_traded:
            continue
        ticker = m["ticker"]
        if ticker in open_ids:
            continue

        yes_bid = m["yes_bid"] or 0
        yes_ask = m["yes_ask"] or 0
        no_bid = m["no_bid"] or 0
        no_ask = m["no_ask"] or 0
        title_str = m["title"] or ticker

        # Skip if no real prices
        if yes_bid <= 0 and yes_ask <= 0:
            continue

        yes_mid = (yes_bid + yes_ask) / 2 if yes_bid > 0 and yes_ask > 0 else (yes_bid or yes_ask)
        no_mid = (no_bid + no_ask) / 2 if no_bid > 0 and no_ask > 0 else (no_bid or no_ask)

        # Convert cents to decimal
        yes_p = yes_mid / 100.0 if yes_mid > 1 else yes_mid
        no_p = no_mid / 100.0 if no_mid > 1 else no_mid

        # Strategy 1: Single-venue arb (yes + no != 1.0)
        if yes_p > 0 and no_p > 0:
            gap = abs(yes_p + no_p - 1.0)
            if gap > ARB_THRESHOLD:
                direction = "NO" if no_p < (1 - yes_p) else "YES"
                entry = no_p if direction == "NO" else yes_p
                if entry > 0 and entry < 1:
                    amount = min(POSITION_PCT * balance, MAX_POSITION_PCT * balance)
                    shares = amount / entry
                    _place_trade(conn, ticker, title_str, direction,
                                 entry, amount, shares, gap, "fast_arb")
                    trades_placed += 1
                    open_ids.add(ticker)
                    events_traded.add(event_ticker)
                    continue

        # Strategy 2: Price-lag vs spot (for crypto markets)
        title = title_str.lower()
        for asset, prefixes in CRYPTO_TICKERS.items():
            if not any(ticker.startswith(p) for p in prefixes):
                continue
            if asset not in spot:
                continue

            spot_price = spot[asset]
            # Parse threshold from title (e.g. "Bitcoin above $70,500?")
            import re
            threshold_match = re.search(r'\$?([\d,]+(?:\.\d+)?)', title_str)
            if not threshold_match:
                continue
            try:
                threshold = float(threshold_match.group(1).replace(",", ""))
            except ValueError:
                continue

            # Is spot clearly above or below the threshold?
            distance_pct = abs(spot_price - threshold) / spot_price if spot_price > 0 else 0

            if distance_pct > MIN_EDGE:
                if spot_price > threshold:
                    # Spot above threshold → YES more likely
                    direction = "YES"
                    entry = yes_p if yes_p > 0 else 0.5
                else:
                    direction = "NO"
                    entry = no_p if no_p > 0 else 0.5

                if entry > 0 and entry < 1:
                    amount = min(POSITION_PCT * balance, MAX_POSITION_PCT * balance)
                    shares = amount / entry
                    _place_trade(conn, ticker, title_str, direction,
                                 entry, amount, shares, distance_pct, "fast_spot_lag")
                    trades_placed += 1
                    open_ids.add(ticker)
                    events_traded.add(event_ticker)
            break

    conn.close()

    if trades_placed > 0:
        print(f"[fast_scan] Placed {trades_placed} trades")
        _notify_dashboard()
    else:
        print(f"[fast_scan] No edge found in {len(markets)} short-expiry markets")


def _place_trade(conn, market_id, question, direction, entry_price, amount, shares, edge, strategy):
    """Insert a paper trade directly (bypasses wallet for speed)."""
    ts = datetime.datetime.utcnow().isoformat()
    try:
        conn.execute("""
            INSERT INTO paper_trades
            (market_id, question, direction, shares, entry_price, amount_usd,
             status, confidence, reasoning, strategy, opened_at)
            VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?)
        """, (
            market_id, question[:200], direction, shares, entry_price, amount,
            min(edge / 0.10, 1.0),
            f"{strategy}: edge={edge:.3f} entry={entry_price:.3f}",
            strategy, ts,
        ))
        conn.commit()
        print(f"[fast_scan] {direction} ${amount:.0f} on '{question[:50]}' [{strategy}] edge={edge:.3f}")
    except Exception as e:
        print(f"[fast_scan] Trade error: {e}")


if __name__ == "__main__":
    _load_env()
    run()
