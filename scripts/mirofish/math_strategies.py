#!/usr/bin/env python3
"""
Math-only trading strategies — no LLM, pure price/math signals.
Runs every 5 minutes alongside ArbClaw.

Strategies:
1. Expiry convergence — bet on near-expiry contracts that should be 0 or 1
2. Cross-bracket consistency — bracket probabilities must sum to ~100%
3. Correlation arb — if BTC moves, DOGE/ADA/BNB 15-min markets lag behind
4. Mean reversion — sudden price spikes revert in thin markets

Usage:
    python3 -m scripts.mirofish.math_strategies
"""
from __future__ import annotations

import os
import sqlite3
import datetime
import math
from pathlib import Path


def _load_env():
    env_file = Path.home() / "openclaw" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


# Config
POSITION_PCT = float(os.environ.get("MATH_STRAT_POSITION_PCT", "0.03"))
MAX_TRADES_PER_RUN = int(os.environ.get("MATH_STRAT_MAX_TRADES", "5"))
MIN_ENTRY = 0.05
MAX_ENTRY = 0.95


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


def _get_open_ids(conn) -> set:
    return set(r[0] for r in conn.execute(
        "SELECT market_id FROM paper_trades WHERE status='open'"
    ).fetchall())


def _place(conn, ticker, question, direction, entry, amount, edge, strategy, new_ids) -> bool:
    if amount < 2 or entry < MIN_ENTRY or entry > MAX_ENTRY:
        return False
    shares = amount / entry
    ts = datetime.datetime.utcnow().isoformat()
    try:
        cur = conn.execute("""
            INSERT INTO paper_trades
            (market_id, question, direction, shares, entry_price, amount_usd,
             status, confidence, reasoning, strategy, opened_at)
            VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?)
        """, (
            ticker, (question or "")[:200], direction, shares, entry, amount,
            min(edge / 0.05, 1.0),
            f"{strategy}: edge={edge:.3f} entry={entry:.3f}",
            strategy, ts,
        ))
        conn.commit()
        new_ids.add(cur.lastrowid)
        timer = ""
        # Get close_time for logging
        km = conn.execute("SELECT close_time FROM kalshi_markets WHERE ticker=? ORDER BY fetched_at DESC LIMIT 1",
                          (ticker,)).fetchone()
        if km and km["close_time"]:
            try:
                ct = datetime.datetime.fromisoformat(km["close_time"].replace("Z", "+00:00"))
                mins = (ct.replace(tzinfo=None) - datetime.datetime.utcnow()).total_seconds() / 60
                timer = f" [{mins:.0f}min]"
            except Exception:
                pass
        print(f"[math] {direction} ${amount:.0f} '{question[:40]}' [{strategy}] edge={edge:.3f}{timer}")
        return True
    except Exception as e:
        print(f"[math] Error: {e}")
        return False


# ---------------------------------------------------------------------------
# Strategy 1: Expiry Convergence
# ---------------------------------------------------------------------------

def scan_expiry_convergence(conn, balance, open_ids, new_ids) -> int:
    """
    Near-expiry contracts should converge to 0 or 1.
    If a contract is at 0.30 with 30 min left and spot is clearly
    above/below the strike, it's mispriced.
    """
    now = datetime.datetime.utcnow()
    max_close = (now + datetime.timedelta(hours=2)).isoformat()
    min_close = now.isoformat()

    rows = conn.execute("""
        SELECT km.ticker, km.title, km.yes_bid, km.yes_ask, km.no_bid, km.no_ask,
               km.close_time, km.event_ticker
        FROM kalshi_markets km
        INNER JOIN (SELECT ticker, MAX(fetched_at) as latest FROM kalshi_markets GROUP BY ticker) l
        ON km.ticker = l.ticker AND km.fetched_at = l.latest
        WHERE km.close_time > ? AND km.close_time < ?
        AND (km.yes_bid > 0 OR km.no_bid > 0)
    """, (min_close, max_close)).fetchall()

    placed = 0
    events_seen = set()

    for r in rows:
        if placed >= 2:  # max 2 per strategy per run
            break
        ticker = r["ticker"]
        if ticker in open_ids:
            continue
        evt = r["event_ticker"] or ticker[:20]
        if evt in events_seen:
            continue

        yb = (r["yes_bid"] or 0)
        nb = (r["no_bid"] or 0)
        if yb > 1: yb /= 100.0
        if nb > 1: nb /= 100.0

        # Look for contracts in the "should be resolved" zone
        # If yes_bid is between 0.15-0.40 or 0.60-0.85 near expiry, it's indecisive
        # We want contracts that SHOULD be near 0 or 1 but aren't
        try:
            ct = datetime.datetime.fromisoformat(r["close_time"].replace("Z", "+00:00"))
            mins_left = (ct.replace(tzinfo=None) - now).total_seconds() / 60
        except Exception:
            continue

        if mins_left < 5 or mins_left > 120:
            continue

        # Contracts near expiry should be decisive
        # If YES is 0.20-0.40 with <30 min left, bet NO (likely resolves NO)
        # If YES is 0.60-0.80 with <30 min left, bet YES (likely resolves YES)
        ya = (r["yes_ask"] or yb)
        if ya > 1: ya /= 100.0
        na = (r["no_ask"] or nb)
        if na > 1: na /= 100.0

        if mins_left < 60:
            if 0.10 < yb < 0.35:
                # Leaning NO — bet NO
                edge = (1.0 - yb - nb) if nb > 0 else 0.0
                entry = na if na > 0 else (1.0 - yb)
                if edge > 0.02 and _place(conn, ticker, r["title"], "NO", entry,
                                           POSITION_PCT * balance, abs(0.5 - yb), "expiry_convergence", new_ids):
                    placed += 1
                    open_ids.add(ticker)
                    events_seen.add(evt)
            elif 0.65 < yb < 0.90:
                # Leaning YES — bet YES
                entry = ya if ya > 0 else yb
                if _place(conn, ticker, r["title"], "YES", entry,
                          POSITION_PCT * balance, abs(yb - 0.5), "expiry_convergence", new_ids):
                    placed += 1
                    open_ids.add(ticker)
                    events_seen.add(evt)

    return placed


# ---------------------------------------------------------------------------
# Strategy 2: Cross-Bracket Consistency
# ---------------------------------------------------------------------------

def scan_cross_bracket(conn, balance, open_ids, new_ids) -> int:
    """
    Brackets within the same event must sum to ~100%.
    If they sum to <95% or >105%, there's an arb.
    """
    # Group markets by event_ticker
    rows = conn.execute("""
        SELECT km.ticker, km.title, km.yes_bid, km.yes_ask, km.no_bid, km.no_ask,
               km.event_ticker, km.close_time
        FROM kalshi_markets km
        INNER JOIN (SELECT ticker, MAX(fetched_at) as latest FROM kalshi_markets GROUP BY ticker) l
        ON km.ticker = l.ticker AND km.fetched_at = l.latest
        WHERE km.event_ticker IS NOT NULL AND km.event_ticker != ''
        AND km.yes_bid > 0
    """).fetchall()

    events: dict[str, list] = {}
    for r in rows:
        evt = r["event_ticker"]
        if evt not in events:
            events[evt] = []
        events[evt].append(r)

    placed = 0
    for evt, markets in events.items():
        if placed >= 2:
            break
        if len(markets) < 3:  # need multiple brackets
            continue

        # Sum all YES bids
        total_yes = 0
        for m in markets:
            yb = m["yes_bid"] or 0
            if yb > 1: yb /= 100.0
            total_yes += yb

        # Should sum to ~1.0
        gap = 1.0 - total_yes
        if abs(gap) < 0.05:
            continue  # close enough, no arb

        # Check expiry — skip events beyond 7 days
        close_times = [m["close_time"] for m in markets if m["close_time"]]
        if close_times:
            try:
                ct = datetime.datetime.fromisoformat(close_times[0].replace("Z", "+00:00"))
                if (ct.replace(tzinfo=None) - now).total_seconds() / 3600 > 168:
                    continue
            except Exception:
                pass

        if gap > 0.05:
            # Total < 95% — brackets are underpriced, buy the cheapest
            cheapest = min(markets, key=lambda m: (m["yes_bid"] or 999))
            ticker = cheapest["ticker"]
            if ticker in open_ids:
                continue
            yb = cheapest["yes_bid"]
            if yb > 1: yb /= 100.0
            ya = (cheapest["yes_ask"] or yb)
            if ya > 1: ya /= 100.0
            if ya >= MIN_ENTRY and ya < MAX_ENTRY:
                if _place(conn, ticker, cheapest["title"], "YES", ya,
                          POSITION_PCT * balance, gap, "cross_bracket_arb", new_ids):
                    placed += 1
                    open_ids.add(ticker)

    return placed


# ---------------------------------------------------------------------------
# Strategy 3: Correlation Arb (crypto lag)
# ---------------------------------------------------------------------------

def scan_correlation_arb(conn, balance, open_ids, new_ids) -> int:
    """
    If BTC moves, smaller cryptos (DOGE, BNB, ADA) follow with a lag.
    If BTC is up 1%+ in last 30 min but DOGE 15-min market hasn't repriced,
    bet on DOGE following.
    """
    # Get BTC trend
    btc_rows = conn.execute("""
        SELECT amount_usd, fetched_at FROM spot_prices
        WHERE ticker = 'SPOT:BTC' ORDER BY fetched_at DESC LIMIT 5
    """).fetchall()

    if len(btc_rows) < 2:
        return 0

    btc_latest = btc_rows[0]["amount_usd"]
    btc_prev = btc_rows[-1]["amount_usd"]
    if not btc_latest or not btc_prev or btc_prev <= 0:
        return 0

    btc_change = (btc_latest - btc_prev) / btc_prev

    if abs(btc_change) < 0.005:  # need >0.5% BTC move
        return 0

    btc_direction = "up" if btc_change > 0 else "down"

    # Find 15-min "price up" markets for correlated assets
    now = datetime.datetime.utcnow()
    max_close = (now + datetime.timedelta(hours=1)).isoformat()

    placed = 0
    for prefix in ["KXDOGE15M", "KXADA15M", "KXBNB15M", "KXBCH15M"]:
        if placed >= 2:
            break

        rows = conn.execute("""
            SELECT km.ticker, km.title, km.yes_bid, km.yes_ask, km.no_bid, km.no_ask, km.close_time
            FROM kalshi_markets km
            INNER JOIN (SELECT ticker, MAX(fetched_at) as latest FROM kalshi_markets GROUP BY ticker) l
            ON km.ticker = l.ticker AND km.fetched_at = l.latest
            WHERE km.ticker LIKE ? AND km.close_time > ? AND km.close_time < ?
            AND (km.yes_bid > 0 OR km.yes_ask > 0)
        """, (prefix + "%", now.isoformat(), max_close)).fetchall()

        for r in rows:
            ticker = r["ticker"]
            if ticker in open_ids:
                continue

            yb = (r["yes_bid"] or 0)
            ya = (r["yes_ask"] or yb)
            nb = (r["no_bid"] or 0)
            na = (r["no_ask"] or nb)
            if yb > 1: yb /= 100.0
            if ya > 1: ya /= 100.0
            if nb > 1: nb /= 100.0
            if na > 1: na /= 100.0

            title_lower = (r["title"] or "").lower()

            # BTC up → correlated alts likely up too
            if btc_direction == "up" and "price up" in title_lower:
                entry = ya if ya > 0 else 0.5
                if entry >= MIN_ENTRY and entry < MAX_ENTRY:
                    if _place(conn, ticker, r["title"], "YES", entry,
                              POSITION_PCT * balance, abs(btc_change), "correlation_arb", new_ids):
                        placed += 1
                        open_ids.add(ticker)
                        break
            elif btc_direction == "down" and "price up" in title_lower:
                entry = na if na > 0 else 0.5
                if entry >= MIN_ENTRY and entry < MAX_ENTRY:
                    if _place(conn, ticker, r["title"], "NO", entry,
                              POSITION_PCT * balance, abs(btc_change), "correlation_arb", new_ids):
                        placed += 1
                        open_ids.add(ticker)
                        break

    return placed


# ---------------------------------------------------------------------------
# Strategy 4: Mean Reversion
# ---------------------------------------------------------------------------

def scan_mean_reversion(conn, balance, open_ids, new_ids) -> int:
    """
    When a market's YES price moves >15% in the last few snapshots,
    bet on reversion. Thin markets overreact.
    """
    rows = conn.execute("""
        SELECT km.ticker, km.title, km.yes_bid, km.yes_ask, km.no_bid, km.no_ask,
               km.close_time, km.event_ticker
        FROM kalshi_markets km
        INNER JOIN (SELECT ticker, MAX(fetched_at) as latest FROM kalshi_markets GROUP BY ticker) l
        ON km.ticker = l.ticker AND km.fetched_at = l.latest
        WHERE km.yes_bid > 0 AND km.volume_24h > 500
    """).fetchall()

    placed = 0
    now = datetime.datetime.utcnow()

    for r in rows:
        if placed >= 1:  # conservative — 1 mean-rev per run
            break
        ticker = r["ticker"]
        if ticker in open_ids:
            continue

        # Check close_time within 7 days
        if r["close_time"]:
            try:
                ct = datetime.datetime.fromisoformat(r["close_time"].replace("Z", "+00:00"))
                if (ct.replace(tzinfo=None) - now).total_seconds() / 3600 > 168:
                    continue
            except Exception:
                continue

        # Get price history for this market
        history = conn.execute("""
            SELECT yes_bid FROM kalshi_markets
            WHERE ticker = ? ORDER BY fetched_at DESC LIMIT 5
        """, (ticker,)).fetchall()

        if len(history) < 3:
            continue

        prices = [(h["yes_bid"] / 100.0 if h["yes_bid"] > 1 else h["yes_bid"]) for h in history if h["yes_bid"]]
        if len(prices) < 3:
            continue

        latest = prices[0]
        avg = sum(prices[1:]) / len(prices[1:])
        if avg <= 0:
            continue

        move_pct = (latest - avg) / avg

        if abs(move_pct) > 0.15:  # >15% move from recent average
            # Bet on reversion
            if move_pct > 0:
                # Price spiked up — bet NO (revert down)
                na = (r["no_ask"] or r["no_bid"] or 0)
                if na > 1: na /= 100.0
                entry = na
                direction = "NO"
            else:
                # Price crashed — bet YES (revert up)
                ya = (r["yes_ask"] or r["yes_bid"] or 0)
                if ya > 1: ya /= 100.0
                entry = ya
                direction = "YES"

            if entry >= MIN_ENTRY and entry < MAX_ENTRY:
                if _place(conn, ticker, r["title"], direction, entry,
                          POSITION_PCT * balance, abs(move_pct), "mean_reversion", new_ids):
                    placed += 1
                    open_ids.add(ticker)

    return placed


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def resolve_trades(conn, new_ids: set) -> int:
    try:
        from scripts.mirofish.kalshi_feed import _call_kalshi
    except ImportError:
        return 0

    strategies = ("expiry_convergence", "cross_bracket_arb", "correlation_arb", "mean_reversion")
    placeholders = ",".join(f"'{s}'" for s in strategies)

    trades = conn.execute(f"""
        SELECT id, market_id, direction, entry_price, shares FROM paper_trades
        WHERE status='open' AND strategy IN ({placeholders})
    """).fetchall()

    resolved = 0
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
                     (exit_price, pnl, status, datetime.datetime.utcnow().isoformat(), t["id"]))
        sign = "+" if pnl >= 0 else ""
        print(f"[math] Resolved: {status} {sign}${pnl:.2f} {t['market_id'][:30]}")
        resolved += 1

    if resolved:
        conn.commit()
    return resolved


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run():
    # Circuit breaker
    try:
        from scripts.mirofish.paper_wallet import check_circuit_breaker, reset_wallet
        breaker = check_circuit_breaker()
        if breaker:
            print("[math] Circuit breaker — wallet depleted")
            reset_wallet()
            _notify()
            return
    except Exception:
        pass

    conn = _get_conn()
    balance = _get_balance(conn)
    open_ids = _get_open_ids(conn)
    new_ids: set[int] = set()

    total = 0
    total += scan_expiry_convergence(conn, balance, open_ids, new_ids)
    total += scan_cross_bracket(conn, balance, open_ids, new_ids)
    total += scan_correlation_arb(conn, balance, open_ids, new_ids)
    total += scan_mean_reversion(conn, balance, open_ids, new_ids)

    resolved = resolve_trades(conn, new_ids)
    conn.close()

    if total > 0 or resolved > 0:
        print(f"[math] Placed {total}, resolved {resolved}")
        _notify()
    else:
        print(f"[math] No opportunities found")


if __name__ == "__main__":
    _load_env()
    run()
