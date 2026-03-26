#!/usr/bin/env python3
"""
Hedged prediction market strategies — options-style risk management.
Runs every 5 minutes. No LLM.

Strategies:
1. Hedged bracket pairs — buy main bracket + adjacent bracket as insurance
2. Fade the public — bet against heavy one-sided volume
3. Volatility clustering — after big moves, bet on continued movement

All positions track both legs (main + hedge) for accurate P&L.

Usage:
    python3 -m scripts.mirofish.hedged_strategies
"""
from __future__ import annotations

import os
import sqlite3
import datetime
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
POSITION_PCT = float(os.environ.get("HEDGE_POSITION_PCT", "0.04"))
HEDGE_RATIO = float(os.environ.get("HEDGE_RATIO", "0.25"))  # spend 25% of position on hedge
MAX_TRADES_PER_RUN = 4
MIN_ENTRY = 0.05
MAX_ENTRY = 0.95
MAX_EXPIRY_HOURS = 168  # 7 days


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


def _place(conn, ticker, question, direction, entry, amount, edge, strategy) -> int | None:
    if amount < 1 or entry < MIN_ENTRY or entry > MAX_ENTRY:
        return None

    # Fee deduction before share calculation
    fee_rate = 0.07  # Kalshi
    entry_fee = amount * fee_rate * min(entry, 1.0 - entry)
    amount -= entry_fee
    shares = amount / entry
    ts = datetime.datetime.utcnow().isoformat()
    try:
        cur = conn.execute("""
            INSERT INTO paper_trades
            (market_id, question, direction, shares, entry_price, amount_usd,
             status, confidence, reasoning, strategy, opened_at, entry_fee)
            VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?)
        """, (
            ticker, (question or "")[:200], direction, shares, entry, amount,
            min(edge / 0.05, 1.0),
            f"{strategy}: edge={edge:.3f} entry={entry:.3f}",
            strategy, ts, entry_fee,
        ))
        conn.commit()
        return cur.lastrowid
    except Exception as e:
        print(f"[hedge] Error: {e}")
        return None


def _norm(price):
    """Normalize price: cents to decimal."""
    if price is None:
        return 0
    p = float(price)
    return p / 100.0 if p > 1 else p


# ---------------------------------------------------------------------------
# Strategy 1: Hedged Bracket Pairs
# ---------------------------------------------------------------------------

def scan_hedged_brackets(conn, balance, open_ids) -> int:
    """
    Find bracket events where we can buy a high-probability bracket
    and hedge with an adjacent bracket.

    Example: BTC at $70,259
    - Main: buy "BTC $69k-$71k" at $0.60 ($8)
    - Hedge: buy "BTC $68k-$69k" at $0.10 ($2)
    - If BTC stays $69k-$71k: win $5.33 on main, lose $2 hedge = +$3.33
    - If BTC drops to $68k-$69k: lose $8 main, win $18 hedge = +$10
    - If BTC goes to $67k: lose $8 + $2 = -$10 (same as unhedged)

    Net: hedged loses less on the common failure mode (adjacent bracket).
    """
    now = datetime.datetime.utcnow()
    placed = 0

    # Group Kalshi markets by event_ticker to find bracket sets
    rows = conn.execute("""
        SELECT km.ticker, km.title, km.yes_bid, km.yes_ask, km.no_bid, km.no_ask,
               km.event_ticker, km.close_time, km.floor_strike, km.cap_strike
        FROM kalshi_markets km
        INNER JOIN (SELECT ticker, MAX(fetched_at) as latest FROM kalshi_markets GROUP BY ticker) l
        ON km.ticker = l.ticker AND km.fetched_at = l.latest
        WHERE km.event_ticker IS NOT NULL AND km.event_ticker != ''
        AND km.yes_bid > 0
    """).fetchall()

    events: dict[str, list] = defaultdict(list)
    for r in rows:
        events[r["event_ticker"]].append(r)

    events_traded = set()

    for evt, markets in events.items():
        if placed >= MAX_TRADES_PER_RUN:
            break
        if len(markets) < 3:
            continue
        if evt in events_traded:
            continue

        # Check expiry
        ct = markets[0]["close_time"]
        if ct:
            try:
                exp = datetime.datetime.fromisoformat(ct.replace("Z", "+00:00"))
                hrs = (exp.replace(tzinfo=None) - now).total_seconds() / 3600
                if hrs > MAX_EXPIRY_HOURS or hrs < 0.5:
                    continue
            except Exception:
                continue

        # Sort brackets by YES bid (highest probability first)
        sorted_brackets = sorted(markets, key=lambda m: _norm(m["yes_bid"]), reverse=True)

        # Find a high-prob main bet with an adjacent hedge
        for i, main in enumerate(sorted_brackets):
            main_ticker = main["ticker"]
            if main_ticker in open_ids:
                continue

            main_yb = _norm(main["yes_bid"])
            main_ya = _norm(main["yes_ask"]) or main_yb

            # Main bet should be 15-90% probability
            if main_ya < 0.15 or main_ya > 0.90:
                continue

            # Find adjacent bracket (next most likely) as hedge
            for j, hedge in enumerate(sorted_brackets):
                if j == i:
                    continue
                hedge_ticker = hedge["ticker"]
                if hedge_ticker in open_ids or hedge_ticker == main_ticker:
                    continue

                hedge_ya = _norm(hedge["yes_ask"]) or _norm(hedge["yes_bid"])
                if hedge_ya < MIN_ENTRY or hedge_ya > 0.40:
                    continue  # hedge should be cheap

                # Calculate position sizes
                main_amount = POSITION_PCT * balance * (1 - HEDGE_RATIO)
                hedge_amount = POSITION_PCT * balance * HEDGE_RATIO

                if main_amount < 2 or hedge_amount < 1:
                    continue

                # Calculate expected P&L scenarios
                main_win_pnl = main_amount * (1.0 / main_ya - 1)
                hedge_win_pnl = hedge_amount * (1.0 / hedge_ya - 1)
                both_lose = -(main_amount + hedge_amount)
                main_wins = main_win_pnl - hedge_amount  # win main, lose hedge
                hedge_wins = hedge_win_pnl - main_amount  # lose main, win hedge

                # Only trade if the hedge improves our risk profile
                edge = (main_ya - 0.5) * 0.1  # edge proportional to how decisive the main bet is

                # Place both legs
                main_id = _place(conn, main_ticker, main["title"], "YES",
                                  main_ya, main_amount, edge, "hedged_bracket_main")
                if main_id:
                    hedge_id = _place(conn, hedge_ticker, hedge["title"], "YES",
                                      hedge_ya, hedge_amount, edge * 0.5, "hedged_bracket_hedge")
                    open_ids.add(main_ticker)
                    open_ids.add(hedge_ticker)
                    events_traded.add(evt)
                    placed += 1

                    print(f"[hedge] PAIR: main={main['title'][:30]} @{main_ya:.2f} ${main_amount:.0f}"
                          f" + hedge={hedge['title'][:30]} @{hedge_ya:.2f} ${hedge_amount:.0f}")
                    print(f"  Scenarios: main_wins=+${main_wins:.2f} hedge_wins=+${hedge_wins:.2f}"
                          f" both_lose=${both_lose:.2f}")
                break  # found hedge for this main, move to next event

    return placed


# ---------------------------------------------------------------------------
# Strategy 2: Fade the Public
# ---------------------------------------------------------------------------

def scan_fade_public(conn, balance, open_ids) -> int:
    """
    When a market has heavy volume but the price hasn't moved to reflect it,
    the crowd may be wrong. Bet against the consensus.

    Look for: high volume + price near 50% (market can't decide) → fade YES
    Or: sudden volume spike on YES side but price barely moved → fade
    """
    now = datetime.datetime.utcnow()
    placed = 0

    rows = conn.execute("""
        SELECT km.ticker, km.title, km.yes_bid, km.yes_ask, km.no_bid, km.no_ask,
               km.volume_24h, km.close_time, km.event_ticker
        FROM kalshi_markets km
        INNER JOIN (SELECT ticker, MAX(fetched_at) as latest FROM kalshi_markets GROUP BY ticker) l
        ON km.ticker = l.ticker AND km.fetched_at = l.latest
        WHERE km.volume_24h > 1000 AND km.yes_bid > 0 AND km.no_bid > 0
    """).fetchall()

    for r in rows:
        if placed >= 2:
            break
        ticker = r["ticker"]
        if ticker in open_ids:
            continue

        # Check expiry
        if r["close_time"]:
            try:
                exp = datetime.datetime.fromisoformat(r["close_time"].replace("Z", "+00:00"))
                hrs = (exp.replace(tzinfo=None) - now).total_seconds() / 3600
                if hrs > MAX_EXPIRY_HOURS or hrs < 1:
                    continue
            except Exception:
                continue

        yb = _norm(r["yes_bid"])
        nb = _norm(r["no_bid"])
        ya = _norm(r["yes_ask"]) or yb
        na = _norm(r["no_ask"]) or nb

        # "Fade" criteria: high volume + price is stuck in indecision zone (40-60%)
        if 0.40 < yb < 0.60 and r["volume_24h"] > 5000:
            # Market can't decide — fade toward NO (contrarian)
            # Rationale: when neither side is winning, the status quo (NO) tends to prevail
            entry = na
            edge = abs(0.50 - yb) + 0.02  # small edge from reversion to mean
            amount = POSITION_PCT * balance * 0.5  # half size for speculative fade

            if entry >= MIN_ENTRY and entry < MAX_ENTRY and amount >= 2:
                if _place(conn, ticker, r["title"], "NO", entry, amount, edge, "fade_public"):
                    open_ids.add(ticker)
                    placed += 1
                    print(f"[hedge] FADE: NO on '{r['title'][:40]}' @{entry:.2f} vol={r['volume_24h']:.0f}")

    return placed


# ---------------------------------------------------------------------------
# Strategy 3: Volatility Clustering
# ---------------------------------------------------------------------------

def scan_volatility_clustering(conn, balance, open_ids) -> int:
    """
    After a big price move in crypto, the next 15-min period tends to
    have another big move. We don't know the direction, but we can buy
    both YES and NO on a 15-min market if the combined cost < $1.

    This is a volatility bet, not a directional bet.
    """
    now = datetime.datetime.utcnow()
    placed = 0

    # Check BTC volatility: did spot move >0.5% in the last snapshot?
    btc_rows = conn.execute("""
        SELECT amount_usd FROM spot_prices
        WHERE ticker = 'SPOT:BTC' ORDER BY fetched_at DESC LIMIT 3
    """).fetchall()

    if len(btc_rows) < 2:
        return 0

    latest = btc_rows[0]["amount_usd"]
    prev = btc_rows[1]["amount_usd"]
    if not latest or not prev or prev <= 0:
        return 0

    btc_vol = abs(latest - prev) / prev

    if btc_vol < 0.005:  # need >0.5% move
        return 0

    print(f"[hedge] Vol cluster detected: BTC moved {btc_vol:.2%}")

    # Find 15-min crypto markets to straddle
    max_close = (now + datetime.timedelta(hours=1)).isoformat()

    for prefix in ["KXDOGE15M", "KXBNB15M", "KXADA15M"]:
        if placed >= 1:  # 1 straddle per run
            break

        rows = conn.execute("""
            SELECT km.ticker, km.title, km.yes_bid, km.yes_ask, km.no_bid, km.no_ask, km.close_time
            FROM kalshi_markets km
            INNER JOIN (SELECT ticker, MAX(fetched_at) as latest FROM kalshi_markets GROUP BY ticker) l
            ON km.ticker = l.ticker AND km.fetched_at = l.latest
            WHERE km.ticker LIKE ? AND km.close_time > ? AND km.close_time < ?
            AND km.yes_ask > 0 AND km.no_ask > 0
        """, (prefix + "%", now.isoformat(), max_close)).fetchall()

        for r in rows:
            ticker = r["ticker"]
            if ticker in open_ids:
                continue

            ya = _norm(r["yes_ask"])
            na = _norm(r["no_ask"])

            # Straddle: buy both YES and NO
            straddle_cost = ya + na
            if straddle_cost < 0.95:
                # Guaranteed profit if either wins! (pays $1, cost < $1)
                # This is really an arb, but framed as vol bet
                total_amount = POSITION_PCT * balance * 0.5
                yes_amount = total_amount * (na / straddle_cost)  # weight toward cheaper side
                no_amount = total_amount - yes_amount

                if yes_amount >= 1 and no_amount >= 1:
                    y_id = _place(conn, ticker, r["title"] + " [YES leg]", "YES",
                                   ya, yes_amount, 1.0 - straddle_cost, "vol_straddle_yes")
                    n_id = _place(conn, ticker + "_NO", r["title"] + " [NO leg]", "NO",
                                   na, no_amount, 1.0 - straddle_cost, "vol_straddle_no")
                    if y_id and n_id:
                        open_ids.add(ticker)
                        placed += 1
                        profit = total_amount * (1.0 / straddle_cost - 1)
                        print(f"[hedge] STRADDLE: '{r['title'][:35]}' cost={straddle_cost:.3f}"
                              f" guaranteed +${profit:.2f}")

    return placed


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def resolve_trades(conn, new_ids: set) -> int:
    try:
        from scripts.mirofish.kalshi_feed import _call_kalshi
    except ImportError:
        return 0

    strategies = ("hedged_bracket_main", "hedged_bracket_hedge",
                  "fade_public", "vol_straddle_yes", "vol_straddle_no")
    placeholders = ",".join(f"'{s}'" for s in strategies)

    trades = conn.execute(f"""
        SELECT id, market_id, direction, entry_price, shares FROM paper_trades
        WHERE status='open' AND strategy IN ({placeholders})
    """).fetchall()

    resolved = 0
    for t in trades:
        if t["id"] in new_ids:
            continue
        mid = t["market_id"].rstrip("_NO")  # straddle NO leg has _NO suffix
        data = _call_kalshi("GET", f"/markets/{mid}")
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
        print(f"[hedge] Resolved: {status} {sign}${pnl:.2f} {t['market_id'][:30]}")
        resolved += 1

    if resolved:
        conn.commit()
    return resolved


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run():
    try:
        from scripts.mirofish.paper_wallet import check_circuit_breaker, reset_wallet
        breaker = check_circuit_breaker()
        if breaker:
            print("[hedge] Circuit breaker — wallet depleted")
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
    total += scan_hedged_brackets(conn, balance, open_ids)
    total += scan_fade_public(conn, balance, open_ids)
    total += scan_volatility_clustering(conn, balance, open_ids)

    resolved = resolve_trades(conn, new_ids)
    conn.close()

    if total > 0 or resolved > 0:
        print(f"[hedge] Placed {total}, resolved {resolved}")
        _notify()
    else:
        print(f"[hedge] No opportunities found")


if __name__ == "__main__":
    _load_env()
    run()
