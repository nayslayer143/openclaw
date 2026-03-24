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
MAX_TRADES_PER_RUN = int(os.environ.get("FAST_SCAN_MAX_TRADES", "5"))
MAX_PER_EVENT = int(os.environ.get("FAST_SCAN_MAX_PER_EVENT", "1"))
MIN_ENTRY_PRICE = 0.05   # skip penny contracts (<5 cents)
MAX_SPREAD_PCT = 0.30     # skip markets with >30% bid/ask spread

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


def _fetch_fresh_short_markets():
    """Fetch 15-min and hourly markets directly from Kalshi API (skip cache)."""
    try:
        from scripts.mirofish.kalshi_feed import _call_kalshi, _adapt_market_fields, _ensure_table, _get_conn as _kget_conn

        short_series = ["KXDOGE15M", "KXADA15M", "KXBNB15M", "KXBCH15M",
                         "INXI", "NASDAQ100I", "KXUSDJPYH"]
        markets = []
        now_iso = datetime.datetime.utcnow().isoformat()

        for series in short_series:
            data = _call_kalshi("GET", "/events", params={
                "series_ticker": series, "status": "open", "limit": 5,
            })
            if not data:
                continue
            for event in data.get("events", []):
                evt_ticker = event.get("event_ticker", "")
                if not evt_ticker:
                    continue
                mdata = _call_kalshi("GET", "/markets", params={
                    "event_ticker": evt_ticker, "status": "open", "limit": 50,
                })
                if not mdata:
                    continue
                for m in mdata.get("markets", []):
                    _adapt_market_fields(m)
                    if not m.get("mve_collection_ticker"):
                        markets.append(m)

        # Cache to DB for stop-check later
        if markets:
            with _kget_conn() as conn:
                _ensure_table(conn)
                for m in markets:
                    try:
                        conn.execute("""
                            INSERT OR REPLACE INTO kalshi_markets
                            (ticker, event_ticker, title, category, yes_bid, yes_ask,
                             no_bid, no_ask, last_price, volume, volume_24h, open_interest,
                             status, close_time, rules_primary, strike_type, cap_strike,
                             floor_strike, fetched_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            m.get("ticker", ""), m.get("event_ticker", ""),
                            m.get("title", ""), (m.get("category") or "").lower(),
                            m.get("yes_bid"), m.get("yes_ask"),
                            m.get("no_bid"), m.get("no_ask"),
                            m.get("last_price"),
                            float(m.get("volume", 0) or 0),
                            float(m.get("volume_24h", 0) or 0),
                            float(m.get("open_interest", 0) or 0),
                            m.get("status", ""),
                            m.get("close_time") or m.get("expiration_time", ""),
                            m.get("rules_primary", ""),
                            m.get("strike_type", ""),
                            m.get("cap_strike"), m.get("floor_strike"),
                            now_iso,
                        ))
                    except Exception:
                        pass

        print(f"[fast_scan] Fetched {len(markets)} fresh short-term markets")
        return markets
    except Exception as e:
        print(f"[fast_scan] Fresh fetch error: {e}")
        return []


def run():
    """Fast scan: find short-expiry Kalshi markets with spot-price edge."""
    now = datetime.datetime.utcnow()
    max_close = (now + datetime.timedelta(hours=MAX_EXPIRY_HOURS)).isoformat()

    # Fetch fresh 15-min/hourly markets directly from API
    fresh = _fetch_fresh_short_markets()

    conn = _get_conn()

    # Also grab any cached short-expiry markets
    try:
        cached = conn.execute("""
            SELECT km.* FROM kalshi_markets km
            INNER JOIN (
                SELECT ticker, MAX(fetched_at) AS latest
                FROM kalshi_markets GROUP BY ticker
            ) l ON km.ticker = l.ticker AND km.fetched_at = l.latest
            WHERE km.close_time != '' AND km.close_time < ?
            AND (km.yes_bid > 0 OR km.yes_ask > 0)
        """, (max_close,)).fetchall()
    except Exception:
        cached = []

    # Merge: use fresh data (dicts) + cached (rows), dedup by ticker
    seen = set()
    markets = []
    for m in fresh:
        t = m.get("ticker", "")
        if t and t not in seen:
            seen.add(t)
            markets.append(m)
    for m in cached:
        t = m["ticker"]
        if t not in seen:
            seen.add(t)
            markets.append(m)

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

    # Check for duplicate positions — by ticker AND by question prefix
    try:
        open_rows = conn.execute(
            "SELECT market_id, question FROM paper_trades WHERE status='open'"
        ).fetchall()
        open_ids = set(r[0] for r in open_rows)
        open_questions = set(r[1][:30] for r in open_rows if r[1])
    except Exception:
        open_ids = set()
        open_questions = set()

    trades_placed = 0
    events_traded: set[str] = set()  # limit 1 bracket per event

    def _g(row, key, default=None):
        """Get field from dict or sqlite3.Row."""
        try:
            v = row[key] if not isinstance(row, dict) else row.get(key, default)
            return v if v is not None else default
        except (KeyError, IndexError):
            return default

    for m in markets:
        if trades_placed >= MAX_TRADES_PER_RUN:
            break

        ticker = _g(m, "ticker", "")
        if not ticker or ticker in open_ids:
            continue

        title_str = _g(m, "title") or ticker

        # Skip if already traded this event or similar question
        event_ticker = _g(m, "event_ticker") or ticker[:20]
        if event_ticker in events_traded:
            continue
        question_prefix = title_str[:30]
        if question_prefix in open_questions:
            continue

        yes_bid = _g(m, "yes_bid", 0) or 0
        yes_ask = _g(m, "yes_ask", 0) or 0
        no_bid = _g(m, "no_bid", 0) or 0
        no_ask = _g(m, "no_ask", 0) or 0

        # Skip if no real prices
        if yes_bid <= 0 and yes_ask <= 0:
            continue

        yes_mid = (yes_bid + yes_ask) / 2 if yes_bid > 0 and yes_ask > 0 else (yes_bid or yes_ask)
        no_mid = (no_bid + no_ask) / 2 if no_bid > 0 and no_ask > 0 else (no_bid or no_ask)

        # Convert cents to decimal
        yes_p = yes_mid / 100.0 if yes_mid > 1 else yes_mid
        no_p = no_mid / 100.0 if no_mid > 1 else no_mid

        # Skip penny contracts and wide spreads
        if yes_p < MIN_ENTRY_PRICE and no_p < MIN_ENTRY_PRICE:
            continue
        if yes_bid > 0 and yes_ask > 0:
            spread = (yes_ask - yes_bid) / yes_mid if yes_mid > 0 else 1.0
            if spread > MAX_SPREAD_PCT:
                continue

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
                    open_questions.add(question_prefix)
                    events_traded.add(event_ticker)
                    continue

        # Strategy 2a: 15-min directional markets ("price up in next 15 min?")
        title = title_str.lower()
        if "price up" in title or "price down" in title:
            # Use recent spot trend to predict direction
            for asset, prefixes in CRYPTO_TICKERS.items():
                if not any(ticker.startswith(p) for p in prefixes):
                    continue
                if asset not in spot:
                    continue

                # Check recent price history for momentum
                try:
                    prices_rows = conn.execute("""
                        SELECT amount_usd FROM spot_prices
                        WHERE ticker = ? ORDER BY fetched_at DESC LIMIT 3
                    """, (f"SPOT:{asset}",)).fetchall()
                    if len(prices_rows) >= 2:
                        latest = prices_rows[0][0] or prices_rows[0]["amount_usd"]
                        prev = prices_rows[1][0] or prices_rows[1]["amount_usd"]
                        if latest and prev and prev > 0:
                            trend_pct = (latest - prev) / prev
                            if abs(trend_pct) > 0.001:  # any detectable trend
                                if "price up" in title:
                                    direction = "YES" if trend_pct > 0 else "NO"
                                else:
                                    direction = "YES" if trend_pct < 0 else "NO"
                                entry = yes_p if direction == "YES" else no_p
                                edge = min(abs(trend_pct), 0.10)  # cap edge at 10%
                                if entry >= MIN_ENTRY_PRICE and entry < 0.95 and edge > 0.001:
                                    amount = min(POSITION_PCT * balance, MAX_POSITION_PCT * balance)
                                    shares = amount / entry
                                    _place_trade(conn, ticker, title_str, direction,
                                                 entry, amount, shares, edge, "fast_15m_trend")
                                    trades_placed += 1
                                    open_ids.add(ticker)
                                    open_questions.add(question_prefix)
                                    events_traded.add(event_ticker)
                except Exception:
                    pass
                break
            if ticker in open_ids:
                continue

        # Strategy 2b: Price-lag vs spot (for crypto bracket/threshold markets)
        # Parse what the market is asking and compare to spot price
        import re
        for asset, prefixes in CRYPTO_TICKERS.items():
            if not any(ticker.startswith(p) for p in prefixes):
                continue
            if asset not in spot:
                continue

            spot_price = spot[asset]
            title_lower = title_str.lower()

            # Parse threshold from title
            threshold_match = re.search(r'\$?([\d,]+(?:\.\d+)?)', title_str)
            if not threshold_match:
                continue
            try:
                threshold = float(threshold_match.group(1).replace(",", ""))
            except ValueError:
                continue

            # Skip if threshold is wildly different from spot (extreme longshot)
            distance_pct = abs(spot_price - threshold) / spot_price if spot_price > 0 else 999
            if distance_pct > 0.10:
                # More than 10% away from spot — too speculative for short-term
                continue

            # Determine direction based on question semantics + spot vs threshold
            # "above X" / "over X" → YES if spot > threshold
            # "below X" / "under X" → YES if spot < threshold
            # "range" with threshold → check if spot is in range
            if "above" in title_lower or "over" in title_lower or ("-T" in ticker):
                # Threshold contract: resolves YES if price > threshold
                if spot_price > threshold * 1.01:
                    direction = "YES"
                elif spot_price < threshold * 0.99:
                    direction = "NO"
                else:
                    continue  # too close to call
            elif "below" in title_lower or "under" in title_lower:
                if spot_price < threshold * 0.99:
                    direction = "YES"
                elif spot_price > threshold * 1.01:
                    direction = "NO"
                else:
                    continue
            else:
                continue  # can't parse direction

            entry = yes_p if direction == "YES" else no_p
            edge = distance_pct

            # Only trade if entry price reflects actual edge (not 1-cent longshots)
            if entry >= MIN_ENTRY_PRICE and entry < 0.95 and edge > MIN_EDGE:
                amount = min(POSITION_PCT * balance, MAX_POSITION_PCT * balance)
                shares = amount / entry
                _place_trade(conn, ticker, title_str, direction,
                             entry, amount, shares, edge, "fast_spot_lag")
                trades_placed += 1
                open_ids.add(ticker)
                open_questions.add(question_prefix)
                events_traded.add(event_ticker)
            break

    # Resolve any expired Kalshi trades with actual results
    resolved = _resolve_expired(conn)
    conn.close()

    if trades_placed > 0 or resolved > 0:
        print(f"[fast_scan] Placed {trades_placed} trades, resolved {resolved}")
        _notify_dashboard()
    else:
        print(f"[fast_scan] No edge found in {len(markets)} short-expiry markets")


def _resolve_expired(conn) -> int:
    """Check Kalshi API for resolution on open expired trades."""
    try:
        from scripts.mirofish.kalshi_feed import _call_kalshi
    except ImportError:
        return 0

    open_kalshi = conn.execute(
        "SELECT id, market_id, direction, entry_price, shares FROM paper_trades WHERE status='open' AND market_id LIKE 'KX%'"
    ).fetchall()

    resolved = 0
    for t in open_kalshi:
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
        print(f"[fast_scan] Resolved: {t['market_id'][:30]} → {status} {sign}${pnl:.2f}")
        resolved += 1

    if resolved:
        conn.commit()
    return resolved


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
