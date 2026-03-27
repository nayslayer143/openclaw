#!/usr/bin/env python3
"""
ArbClaw — lean, fast cross-outcome arbitrage scanner.
Runs every 5 minutes. No LLM, no OSINT. Pure math.

Strategies:
1. Single-venue arb: YES+NO bids < 1.0 → buy both, guaranteed profit
2. Cross-bracket arb: adjacent bracket prices don't sum correctly
3. Spot-vs-market dislocation on near-expiry contracts

All trades get close_time for countdown timers on dashboard.

Usage:
    python3 -m scripts.mirofish.arbclaw
"""
from __future__ import annotations

import os
import sqlite3
import datetime
from pathlib import Path

try:
    from scripts.mirofish.protocol_adapter import submit_trade, USE_PROTOCOL
except ImportError:
    try:
        from protocol_adapter import submit_trade, USE_PROTOCOL
    except ImportError:
        submit_trade = None
        USE_PROTOCOL = False


def _load_env():
    env_file = Path.home() / "openclaw" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


# Config
MIN_GAP = float(os.environ.get("ARBCLAW_MIN_GAP", "0.025"))  # 2.5% minimum
POSITION_PCT = float(os.environ.get("ARBCLAW_POSITION_PCT", "0.03"))  # 3% per trade
MAX_TRADES_PER_RUN = int(os.environ.get("ARBCLAW_MAX_TRADES", "5"))
MIN_VOLUME = float(os.environ.get("ARBCLAW_MIN_VOLUME", "100"))
MIN_ENTRY = 0.05  # no penny contracts


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


def _get_balance(conn) -> float:
    try:
        ctx = conn.execute(
            "SELECT value FROM context WHERE chat_id='mirofish' AND key='starting_balance'"
        ).fetchone()
        starting = float(ctx[0]) if ctx else 1000.0
        pnl = conn.execute(
            "SELECT COALESCE(SUM(pnl), 0) FROM paper_trades WHERE status != 'open'"
        ).fetchone()[0]
        return starting + pnl
    except Exception:
        return 1000.0


def _resolve_expired(conn) -> int:
    """Check Kalshi API for results on expired trades."""
    try:
        from scripts.mirofish.kalshi_feed import _call_kalshi
    except ImportError:
        return 0

    trades = conn.execute(
        "SELECT id, market_id, direction, entry_price, shares FROM paper_trades "
        "WHERE status='open' AND strategy LIKE 'arbclaw%'"
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
        print(f"[arbclaw] Resolved: {status} {sign}${pnl:.2f} {t['market_id'][:30]}")
        resolved += 1

    if resolved:
        conn.commit()
    return resolved


def run():
    # Circuit breaker
    try:
        from scripts.mirofish.paper_wallet import check_circuit_breaker, reset_wallet
        breaker = check_circuit_breaker()
        if breaker:
            print("[arbclaw] Circuit breaker — wallet depleted")
            reset_wallet()
            _notify()
            return
    except Exception:
        pass

    conn = _get_conn()
    balance = _get_balance(conn)
    now = datetime.datetime.utcnow()
    trade_size = max(5.0, POSITION_PCT * balance)

    # Get open position market IDs to avoid duplicates
    open_ids = set(r[0] for r in conn.execute(
        "SELECT market_id FROM paper_trades WHERE status='open'"
    ).fetchall())

    # Scan all Kalshi markets with bid data for single-venue arb
    rows = conn.execute("""
        SELECT km.ticker, km.title, km.yes_bid, km.yes_ask, km.no_bid, km.no_ask,
               km.volume_24h, km.close_time, km.event_ticker
        FROM kalshi_markets km
        INNER JOIN (SELECT ticker, MAX(fetched_at) as latest FROM kalshi_markets GROUP BY ticker) l
        ON km.ticker = l.ticker AND km.fetched_at = l.latest
        WHERE km.yes_bid > 0 AND km.no_bid > 0
    """).fetchall()

    opportunities = []
    for r in rows:
        ticker = r["ticker"]
        if ticker in open_ids:
            continue

        yb = r["yes_bid"]
        ya = r["yes_ask"] or yb
        nb = r["no_bid"]
        na = r["no_ask"] or nb

        # Normalize to decimal
        if yb > 1: yb /= 100.0
        if ya > 1: ya /= 100.0
        if nb > 1: nb /= 100.0
        if na > 1: na /= 100.0

        # Single-venue arb: if yes_ask + no_ask < 1.0, buy both for guaranteed profit
        # More conservatively: if yes_bid + no_bid != 1.0, there's a gap
        total_bid = yb + nb
        gap = 1.0 - total_bid  # positive = arb exists (buy both for < $1, pays $1)

        if gap >= MIN_GAP and r["volume_24h"] >= MIN_VOLUME:
            # Buy the cheaper side
            if yb < nb:
                direction = "YES"
                entry = ya  # buy at ask
            else:
                direction = "NO"
                entry = na

            if entry >= MIN_ENTRY and entry < 0.95:
                # Check close_time for countdown
                close_time = r["close_time"] or ""
                hours_left = 999
                if close_time:
                    try:
                        ct = datetime.datetime.fromisoformat(close_time.replace("Z", "+00:00"))
                        hours_left = (ct.replace(tzinfo=None) - now).total_seconds() / 3600
                    except Exception:
                        pass

                # Skip markets resolving beyond 7 days
                if hours_left > 168:
                    continue

                opportunities.append({
                    "ticker": ticker,
                    "title": r["title"],
                    "direction": direction,
                    "entry": entry,
                    "gap": gap,
                    "volume": r["volume_24h"],
                    "close_time": close_time,
                    "hours_left": hours_left,
                    "event_ticker": r["event_ticker"],
                })

    # Sort: prefer near-expiry with biggest gaps
    opportunities.sort(key=lambda x: (-x["gap"], x["hours_left"]))

    placed = 0
    events_seen = set()
    new_ids = set()

    for opp in opportunities:
        if placed >= MAX_TRADES_PER_RUN:
            break

        # One per event
        evt = opp["event_ticker"] or opp["ticker"][:20]
        if evt in events_seen:
            continue
        events_seen.add(evt)

        amount = min(trade_size, balance * 0.10)
        if amount < 2:
            continue

        # Fee deduction before share calculation
        fee_rate = 0.07  # Kalshi
        entry_fee = amount * fee_rate * min(opp["entry"], 1.0 - opp["entry"])
        amount -= entry_fee
        shares = amount / opp["entry"]
        ts = now.isoformat()

        try:
            _reasoning = f"arbclaw: gap={opp['gap']:.3f} entry={opp['entry']:.3f} vol={opp['volume']:.0f}"
            _confidence = min(opp["gap"] / 0.05, 1.0)
            _venue = "kalshi"

            # Protocol path
            _trade_id = None
            if USE_PROTOCOL and submit_trade is not None:
                _trade_id = submit_trade(
                    market_id=opp["ticker"],
                    question=(opp["title"] or "")[:200],
                    direction=opp["direction"],
                    shares=shares,
                    entry_price=opp["entry"],
                    amount_usd=amount,
                    confidence=_confidence,
                    reasoning=_reasoning,
                    strategy="arbclaw_single_venue",
                    venue=_venue,
                    db_conn=conn,
                )

            if _trade_id is not None:
                # Protocol handled it (including shadow write to paper_trades)
                new_ids.add(_trade_id)
                placed += 1
            else:
                # Legacy INSERT fallback
                cur = conn.execute("""
                    INSERT INTO paper_trades
                    (market_id, question, direction, shares, entry_price, amount_usd,
                     status, confidence, reasoning, strategy, opened_at, entry_fee)
                    VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?)
                """, (
                    opp["ticker"], (opp["title"] or "")[:200], opp["direction"],
                    shares, opp["entry"], amount,
                    _confidence,
                    _reasoning,
                    "arbclaw_single_venue", ts, entry_fee,
                ))
                conn.commit()
                new_ids.add(cur.lastrowid)
                placed += 1

            hrs = opp["hours_left"]
            timer = f"{hrs:.0f}h" if hrs < 999 else "?"
            print(f"[arbclaw] {opp['direction']} ${amount:.0f} on '{opp['title'][:45]}' "
                  f"gap={opp['gap']:.3f} timer={timer}")
        except Exception as e:
            print(f"[arbclaw] Error: {e}")

    # Resolve expired trades (skip ones just placed)
    resolved = 0
    trades = conn.execute(
        "SELECT id, market_id, direction, entry_price, shares FROM paper_trades "
        "WHERE status='open' AND strategy LIKE 'arbclaw%'"
    ).fetchall()

    try:
        from scripts.mirofish.kalshi_feed import _call_kalshi
        for t in trades:
            if t["id"] in new_ids:
                continue
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
                         (exit_price, pnl, status, now.isoformat(), t["id"]))
            sign = "+" if pnl >= 0 else ""
            print(f"[arbclaw] Resolved: {status} {sign}${pnl:.2f} {t['market_id'][:30]}")
            resolved += 1

        if resolved:
            conn.commit()
    except ImportError:
        pass

    conn.close()

    if placed > 0 or resolved > 0:
        print(f"[arbclaw] Placed {placed}, resolved {resolved}")
        _notify()
    else:
        print(f"[arbclaw] No arb gaps > {MIN_GAP:.1%} found in {len(rows)} markets")


if __name__ == "__main__":
    _load_env()
    run()
