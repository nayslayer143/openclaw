#!/usr/bin/env python3
"""
SentimentClaw — attention-gap prediction market trading.
Detects when public attention on a market spikes but price hasn't moved yet.

Uses Kalshi comment/volume data + market price velocity.
Runs every 5 minutes. No LLM.
"""
from __future__ import annotations

import os
import sqlite3
import datetime
import math
from pathlib import Path
from collections import defaultdict

def _load_env():
    env_file = Path.home() / "openclaw" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

# Config
MAX_TRADES_PER_RUN = 25       # was 6
POSITION_PCT = 0.03
MIN_ENTRY = 0.03              # was 0.08
MAX_ENTRY = 0.97              # was 0.92
VOLUME_SPIKE_MULT = 1.2       # was 1.5 (easier to trigger)
PRICE_STALE_THRESHOLD = 0.05  # was 0.02 (more permissive)


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
    """SentimentClaw's own $1000 virtual wallet — only counts its own trades."""
    try:
        pnl = conn.execute("SELECT COALESCE(SUM(pnl), 0) FROM paper_trades WHERE strategy='sentimentclaw' AND status IN ('closed_win','closed_loss','expired')").fetchone()[0]
        return 1000.0 + pnl
    except Exception:
        return 1000.0


def scan_volume_attention_gaps(conn, balance, open_ids) -> int:
    """
    Find markets where volume has spiked but price hasn't moved.
    The attention-price gap suggests the market is about to reprice.
    """
    now = datetime.datetime.utcnow()
    placed = 0
    events_seen = set()

    # Get all markets with volume history (need multiple snapshots)
    rows = conn.execute("""
        SELECT km.ticker, km.title, km.yes_bid, km.yes_ask, km.no_bid, km.no_ask,
               km.volume_24h, km.close_time, km.event_ticker
        FROM kalshi_markets km
        INNER JOIN (SELECT ticker, MAX(fetched_at) as latest FROM kalshi_markets GROUP BY ticker) l
        ON km.ticker = l.ticker AND km.fetched_at = l.latest
        WHERE km.volume_24h > 100 AND (km.yes_bid > 0 OR km.yes_ask > 0)
        AND km.close_time IS NOT NULL
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

        # Get volume history for this market
        vol_history = conn.execute("""
            SELECT volume_24h, yes_bid FROM kalshi_markets
            WHERE ticker = ? ORDER BY fetched_at DESC LIMIT 10
        """, (ticker,)).fetchall()

        if len(vol_history) < 1:
            continue

        # Compute volume baseline (average of older snapshots)
        volumes = [v["volume_24h"] or 0 for v in vol_history]
        current_vol = volumes[0]
        if len(volumes) > 1:
            baseline_vol = sum(volumes[1:]) / len(volumes[1:])
        else:
            baseline_vol = 5000  # single snapshot: use $5k as "normal" baseline

        if baseline_vol <= 0:
            continue

        vol_spike = current_vol / baseline_vol

        # Compute price change
        prices = [_norm(v["yes_bid"]) for v in vol_history if v["yes_bid"]]
        price_change = abs(prices[0] - prices[-1]) if len(prices) >= 2 else 0

        direction = None
        entry = None
        score = 0.0
        thesis = ""

        # ATTENTION-PRICE GAP: volume spiked but price barely moved
        if vol_spike >= VOLUME_SPIKE_MULT and price_change < PRICE_STALE_THRESHOLD:
            # Volume spike with stale price — something's brewing
            # Determine direction: if price is slightly trending, follow it
            ya = _norm(r["yes_ask"]) or _norm(r["yes_bid"])
            na = _norm(r["no_ask"]) or _norm(r["no_bid"])

            # Check expiry
            try:
                ct = datetime.datetime.fromisoformat(r["close_time"].replace("Z", "+00:00"))
                hours_left = (ct.replace(tzinfo=None) - now).total_seconds() / 3600
                if hours_left < 0.5 or hours_left > 168:
                    continue
            except Exception:
                continue

            # Direction heuristic: slight price drift + volume = continuation
            micro_drift = prices[0] - prices[1] if len(prices) >= 2 else 0
            if micro_drift > 0.005:
                direction = "YES"
                entry = ya
            elif micro_drift < -0.005:
                direction = "NO"
                entry = na
            else:
                # No drift — fade toward NO (status quo bias)
                direction = "NO"
                entry = na

            edge = min(vol_spike / 10.0, 0.20)  # normalize
            score = min(0.5 + edge, 0.85)
            thesis = f"sentimentclaw: vol_spike={vol_spike:.1f}x price_stale={price_change:.3f} drift={micro_drift:.4f}"

        # Fallback: extreme pricing strategy (no history needed)
        # Uses latest market row (r) for price data — vol_history only has volume_24h + yes_bid
        if len(vol_history) >= 1 and not direction:
            ya = _norm(r["yes_ask"]) or _norm(r["yes_bid"])
            na = _norm(r["no_ask"]) or _norm(r["no_bid"])
            if ya < 0.15 and ya >= MIN_ENTRY:
                direction = "YES"
                entry = ya
                score = 0.55
                thesis = f"extreme low price {ya:.2f} — mean-reversion bet"
            elif ya > 0.85 and na >= MIN_ENTRY:
                direction = "NO"
                entry = na
                score = 0.55
                thesis = f"extreme high price {ya:.2f} — fade to fair value"

        if not direction or entry is None:
            continue

        if entry < MIN_ENTRY or entry > MAX_ENTRY:
            continue

        # Spread filter
        ya_f = _norm(r["yes_ask"]) or _norm(r["yes_bid"])
        yb_f = _norm(r["yes_bid"])
        if yb_f > 0 and ya_f > 0:
            spread = (ya_f - yb_f) / ya_f
            if spread > 0.30:
                continue

        # Check expiry (for fallback path — vol-spike path already checked above)
        if vol_spike < VOLUME_SPIKE_MULT:
            try:
                ct = datetime.datetime.fromisoformat(r["close_time"].replace("Z", "+00:00"))
                hours_left = (ct.replace(tzinfo=None) - now).total_seconds() / 3600
                if hours_left < 0.5 or hours_left > 168:
                    continue
            except Exception:
                continue

        amount = min(POSITION_PCT * balance, balance * 0.10)
        if amount < 2:
            continue

        shares = amount / entry

        try:
            conn.execute("""
                INSERT INTO paper_trades
                (market_id, question, direction, shares, entry_price, amount_usd,
                 status, confidence, reasoning, strategy, opened_at)
                VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?)
            """, (
                ticker, (r["title"] or "")[:200], direction, shares, entry, amount,
                score, thesis, "sentimentclaw", now.isoformat(),
            ))
            conn.commit()
            placed += 1
            open_ids.add(ticker)
            events_seen.add(evt)
            print(f"[sentiment] {direction} ${amount:.0f} '{r['title'][:40]}' | {thesis[:60]}")
        except Exception as e:
            print(f"[sentiment] Error: {e}")

    return placed


def resolve_trades(conn) -> int:
    try:
        from scripts.mirofish.kalshi_feed import _call_kalshi
    except ImportError:
        return 0

    trades = conn.execute(
        "SELECT id, market_id, direction, entry_price, shares FROM paper_trades WHERE status='open' AND strategy='sentimentclaw'"
    ).fetchall()

    resolved = 0
    for t in trades:
        data = _call_kalshi("GET", f"/markets/{t['market_id']}")
        if not data: continue
        m = data.get("market", data)
        result = m.get("result", "")
        if not result: continue
        we_won = (result == t["direction"].lower())
        exit_price = 1.0 if we_won else 0.0
        pnl = t["shares"] * (exit_price - t["entry_price"])
        conn.execute("UPDATE paper_trades SET exit_price=?, pnl=?, status=?, closed_at=? WHERE id=?",
                     (exit_price, pnl, "closed_win" if we_won else "closed_loss", datetime.datetime.utcnow().isoformat(), t["id"]))
        sign = "+" if pnl >= 0 else ""
        print(f"[sentiment] Resolved: {'WIN' if we_won else 'LOSS'} {sign}${pnl:.2f}")
        resolved += 1

    if resolved: conn.commit()
    return resolved


def run():
    try:
        from scripts.mirofish.paper_wallet import check_circuit_breaker, reset_wallet
        breaker = check_circuit_breaker()
        if breaker:
            reset_wallet()
            _notify()
            return
    except Exception:
        pass

    conn = _get_conn()
    balance = _get_balance(conn)
    open_ids = set(r[0] for r in conn.execute("SELECT market_id FROM paper_trades WHERE status='open'").fetchall())

    placed = scan_volume_attention_gaps(conn, balance, open_ids)
    resolved = resolve_trades(conn)
    conn.close()

    if placed > 0 or resolved > 0:
        print(f"[sentiment] Placed {placed}, resolved {resolved}")
        _notify()
    else:
        print(f"[sentiment] No attention-price gaps found")


if __name__ == "__main__":
    _load_env()
    run()
