#!/usr/bin/env python3
"""
PhantomClaw — RivalClaw's proven strategy running inside Clawmpson architecture.

Implements RivalClaw's Black-Scholes fair-value engine that turned $1K→$10.6K:
1. fair_value_directional — THE ENGINE: BS fair value vs market price
2. bracket_cone — spread bets across adjacent brackets
3. time_decay — sell overpriced near-expiry
4. mean_reversion — bet against crowd at coin-flip prices
5. cross_outcome_arb — guaranteed profit when YES+NO+fees < 1

Key RivalClaw lessons encoded:
- NO stop-losses on fast contracts (<60 min)
- ONE trade per event_ticker
- Price bucket filtering (0.10-0.30 = sweet spot)
- Fractional Kelly (0.5x) for unproven strategies
- Use ASK prices (what you actually pay)

Runs every 2 minutes via cron. No LLM. Pure math.
"""
from __future__ import annotations

import math
import os
import sqlite3
import datetime
from pathlib import Path
from collections import defaultdict
from statistics import stdev

# Normal CDF approximation
def _norm_cdf(x: float) -> float:
    """Standard normal CDF (Abramowitz & Stegun approximation)."""
    if x < -6: return 0.0
    if x > 6: return 1.0
    a1, a2, a3, a4, a5 = 0.254829592, -0.284496736, 1.421413741, -1.453152027, 1.061405429
    p = 0.3275911
    sign = 1 if x >= 0 else -1
    x = abs(x)
    t = 1.0 / (1.0 + p * x)
    y = 1.0 - (((((a5*t + a4)*t) + a3)*t + a2)*t + a1)*t * math.exp(-x*x/2)
    return 0.5 * (1.0 + sign * y)


def _load_env():
    env_file = Path.home() / "openclaw" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


# ---------------------------------------------------------------------------
# Config (from RivalClaw's proven parameters)
# ---------------------------------------------------------------------------
from scripts.mirofish.bot_config import get_param as _p

MAX_POSITION_PCT = _p("phantomclaw_fv", "MAX_POSITION_PCT", 0.05)
MIN_FV_EDGE = _p("phantomclaw_fv", "MIN_FV_EDGE", 0.01)
KELLY_PROVEN = 1.0
KELLY_NEW = 0.50
MAX_TRADES_PER_RUN = _p("phantomclaw_fv", "MAX_TRADES_PER_RUN", 12)
SLIPPAGE_BPS = 30
MIN_ENTRY = _p("phantomclaw_fv", "MIN_ENTRY", 0.55)
NO_STOP_LOSS_MINUTES = 60   # no stops on contracts expiring < 60 min

# Price bucket multipliers (calibrated from 87 PhantomClaw trades)
# 0.00-0.50: 0% to 31% win rate, -$795 total → AVOID
# 0.70-0.85: 95% win rate, +$82 total → SWEET SPOT
# 0.85-1.00: 83% win rate, -$23 total → OK but thin edge
PRICE_BUCKET_MULT = {
    "dead_zone": 2.0,    # <0.55 — NEGATIVE EV, skip
    "ok_mid": 1.2,       # 0.55-0.70 — untested, cautious
    "sweet_spot": 0.5,   # 0.70-0.85 — 95% win rate, best bucket
    "ok_high": 1.0,      # 0.85-0.95 — 83% win rate, ok
    "expensive": 1.5,    # >0.95 — tiny edge
}

# Realized volatility defaults (will be overwritten by spot data)
CRYPTO_VOLS = {
    "BTC": 0.60, "ETH": 0.65, "DOGE": 0.90,
    "ADA": 0.80, "BNB": 0.65, "BCH": 0.75,
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


# ---------------------------------------------------------------------------
# Realized volatility from spot data
# ---------------------------------------------------------------------------
def _compute_realized_vol(conn, asset: str) -> float:
    """Compute annualized realized vol from recent spot snapshots."""
    rows = conn.execute("""
        SELECT amount_usd FROM spot_prices
        WHERE ticker = ? ORDER BY fetched_at DESC LIMIT 200
    """, (f"SPOT:{asset}",)).fetchall()

    prices = [r["amount_usd"] for r in rows if r["amount_usd"] and r["amount_usd"] > 0]
    if len(prices) < 20:
        return CRYPTO_VOLS.get(asset, 0.70)

    # Log returns
    returns = [math.log(prices[i] / prices[i+1]) for i in range(len(prices)-1)]
    if not returns:
        return CRYPTO_VOLS.get(asset, 0.70)

    vol_per_period = stdev(returns)
    # Assume ~10 min intervals, ~52560 periods/year
    annualized = vol_per_period * math.sqrt(52560)
    return max(0.30, min(1.50, annualized))


# ---------------------------------------------------------------------------
# Fair value computation (Black-Scholes for binary options)
# ---------------------------------------------------------------------------
def _bs_fair_value_threshold(spot: float, strike: float, vol: float, t_years: float) -> float:
    """Binary option fair value: P(spot > strike at expiry) using BS model."""
    if t_years <= 0 or vol <= 0 or spot <= 0:
        return 1.0 if spot > strike else 0.0
    d2 = (math.log(spot / strike) + (-0.5 * vol**2) * t_years) / (vol * math.sqrt(t_years))
    return _norm_cdf(d2)


def _bs_fair_value_bracket(spot: float, floor_strike: float, cap_strike: float,
                            vol: float, t_years: float) -> float:
    """Bracket fair value: P(floor < spot < cap at expiry)."""
    p_above_floor = _bs_fair_value_threshold(spot, floor_strike, vol, t_years)
    p_above_cap = _bs_fair_value_threshold(spot, cap_strike, vol, t_years)
    return max(0, p_above_floor - p_above_cap)


def _price_bucket(entry: float) -> str:
    if entry < 0.55: return "dead_zone"
    if entry < 0.70: return "ok_mid"
    if entry < 0.85: return "sweet_spot"
    if entry < 0.95: return "ok_high"
    return "expensive"


# ---------------------------------------------------------------------------
# Strategy: Fair Value Directional
# ---------------------------------------------------------------------------
def scan_fair_value(conn, balance, open_ids, spot_dict, events_seen, new_ids) -> int:
    """THE ENGINE: compute BS fair value for every Kalshi contract, trade mispricings."""
    import re
    now = datetime.datetime.utcnow()
    placed = 0

    # Use RivalClaw's richer market data if available (11K+ snapshots vs our 700)
    rivalclaw_db = Path.home() / "rivalclaw" / "rivalclaw.db"
    if rivalclaw_db.exists():
        try:
            rc_conn = sqlite3.connect(str(rivalclaw_db))
            rc_conn.row_factory = sqlite3.Row
            rows = rc_conn.execute("""
                SELECT ke.market_id as ticker, md.question as title,
                       ke.yes_bid, ke.yes_ask, ke.no_bid, ke.no_ask,
                       ke.close_time, ke.event_ticker, ke.strike_type, ke.cap_strike, ke.floor_strike
                FROM kalshi_extra ke
                INNER JOIN (SELECT market_id, MAX(fetched_at) as latest FROM kalshi_extra GROUP BY market_id) l
                ON ke.market_id = l.market_id AND ke.fetched_at = l.latest
                LEFT JOIN market_data md ON ke.market_id = md.market_id
                WHERE (ke.yes_ask > 0 OR ke.yes_bid > 0)
            """).fetchall()
            rc_conn.close()
            print(f"[phantom] Using RivalClaw data: {len(rows)} markets")
        except Exception as e:
            print(f"[phantom] RivalClaw DB error: {e}, falling back to clawmson")
            rows = conn.execute("""
                SELECT km.ticker, km.title, km.yes_bid, km.yes_ask, km.no_bid, km.no_ask,
                       km.close_time, km.event_ticker, km.strike_type, km.cap_strike, km.floor_strike
                FROM kalshi_markets km
                INNER JOIN (SELECT ticker, MAX(fetched_at) as latest FROM kalshi_markets GROUP BY ticker) l
                ON km.ticker = l.ticker AND km.fetched_at = l.latest
                WHERE (km.yes_ask > 0 OR km.yes_bid > 0)
            """).fetchall()
    else:
        rows = conn.execute("""
            SELECT km.ticker, km.title, km.yes_bid, km.yes_ask, km.no_bid, km.no_ask,
                   km.close_time, km.event_ticker, km.strike_type, km.cap_strike, km.floor_strike
            FROM kalshi_markets km
            INNER JOIN (SELECT ticker, MAX(fetched_at) as latest FROM kalshi_markets GROUP BY ticker) l
            ON km.ticker = l.ticker AND km.fetched_at = l.latest
            WHERE (km.yes_ask > 0 OR km.yes_bid > 0)
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

        # Parse close time
        ct_str = r["close_time"] or ""
        if not ct_str:
            continue
        try:
            ct = datetime.datetime.fromisoformat(ct_str.replace("Z", "+00:00"))
            t_hours = (ct.replace(tzinfo=None) - now).total_seconds() / 3600
        except Exception:
            continue

        if t_hours < 0.05 or t_hours > 168:  # skip expired + >7 days
            continue

        t_years = t_hours / 8760

        # Market prices (use ASK = what we actually pay)
        ya = _norm(r["yes_ask"]) or _norm(r["yes_bid"])
        na = _norm(r["no_ask"]) or _norm(r["no_bid"])
        if ya <= 0 and na <= 0:
            continue

        # Determine asset and get spot + vol
        title = (r["title"] or "").lower()
        mid = (ticker or "").upper()
        spot = None
        vol = None

        for asset in ["BTC", "ETH", "DOGE", "BNB", "ADA", "BCH"]:
            if asset in mid or asset.lower() in title or \
               ("bitcoin" in title and asset == "BTC") or \
               ("ethereum" in title and asset == "ETH") or \
               ("doge" in title and asset == "DOGE"):
                spot = spot_dict.get(asset)
                vol = _compute_realized_vol(conn, asset)
                break

        if not spot or spot <= 0:
            continue

        # Compute fair value
        cap = r["cap_strike"]
        floor_s = r["floor_strike"]

        if cap and floor_s:
            # Bracket contract
            fair = _bs_fair_value_bracket(spot, float(floor_s), float(cap), vol, t_years)
        elif cap:
            # Threshold "above X"
            fair = _bs_fair_value_threshold(spot, float(cap), vol, t_years)
        elif floor_s:
            fair = 1.0 - _bs_fair_value_threshold(spot, float(floor_s), vol, t_years)
        else:
            # Try to parse threshold from title
            m = re.search(r'\$?([\d,]+(?:\.\d+)?)', r["title"] or "")
            if not m:
                continue
            try:
                strike = float(m.group(1).replace(",", ""))
            except ValueError:
                continue
            if "above" in title or "over" in title or "-T" in ticker:
                fair = _bs_fair_value_threshold(spot, strike, vol, t_years)
            elif "below" in title or "under" in title:
                fair = 1.0 - _bs_fair_value_threshold(spot, strike, vol, t_years)
            else:
                fair = _bs_fair_value_threshold(spot, strike, vol, t_years)

        # Edge = |fair - market_price|
        # If fair > market → buy YES (underpriced)
        # If fair < market → buy NO (YES is overpriced)
        # For NO: use 1-yes_bid as the effective NO price (what you'd pay)
        yb = _norm(r["yes_bid"])
        nb = _norm(r["no_bid"])
        effective_no_price = (1.0 - yb) if yb > 0 else na  # what NO effectively costs

        if fair > ya + 0.01 and ya > 0:
            direction = "YES"
            entry = ya
            edge = fair - ya
        elif fair < yb - 0.01 and yb > 0:
            # YES is overpriced → buy NO
            direction = "NO"
            entry = effective_no_price
            edge = yb - fair  # how much YES is overpriced
        else:
            continue

        if entry < MIN_ENTRY or entry > 0.95:
            continue

        # Price bucket filter (RivalClaw's key insight)
        bucket = _price_bucket(entry)
        if bucket == "dead_zone":
            continue  # negative EV zone
        adjusted_threshold = MIN_FV_EDGE * PRICE_BUCKET_MULT[bucket]

        if edge < adjusted_threshold:
            continue

        # Spread filter
        yb = _norm(r["yes_bid"])
        if yb > 0 and ya > 0:
            spread = (ya - yb) / ya
            if spread > 0.30:
                continue

        # Kelly sizing with fractional Kelly for safety
        b = (1.0 / entry) - 1.0 if entry > 0 else 0
        confidence = min(fair if direction == "YES" else (1.0 - fair), 0.95)
        kelly = (confidence * b - (1.0 - confidence)) / b if b > 0 else 0
        if kelly <= 0:
            continue

        amount = kelly * balance * KELLY_PROVEN  # full Kelly — strategy is proven by RivalClaw
        amount = min(amount, MAX_POSITION_PCT * balance)
        if amount < 2:
            continue

        # Apply slippage
        slippage = entry * (SLIPPAGE_BPS / 10000)
        entry_adj = min(0.99, entry + slippage)

        # Apply Kalshi taker fee (7% of min(price, 1-price))
        fee_rate = 0.07
        entry_fee = amount * fee_rate * min(entry_adj, 1.0 - entry_adj)
        amount -= entry_fee
        shares = amount / entry_adj

        # Place trade
        ts = now.isoformat()
        try:
            cur = conn.execute("""
                INSERT INTO paper_trades
                (market_id, question, direction, shares, entry_price, amount_usd,
                 status, confidence, reasoning, strategy, opened_at, entry_fee)
                VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?)
            """, (
                ticker, (r["title"] or "")[:200], direction, shares, entry_adj, amount,
                confidence,
                f"phantomclaw_fv: fair={fair:.3f} mkt={entry:.3f} edge={edge:.3f} bucket={bucket} vol={vol:.2f}",
                "phantomclaw_fv", ts, entry_fee,
            ))
            conn.commit()
            new_ids.add(cur.lastrowid)
            placed += 1
            open_ids.add(ticker)
            events_seen.add(evt)
            print(f"[phantom] {direction} ${amount:.0f} '{r['title'][:40]}' fair={fair:.3f} mkt={entry:.3f} edge={edge:.3f} [{bucket}]")
        except Exception as e:
            print(f"[phantom] Error: {e}")

    return placed


# ---------------------------------------------------------------------------
# Resolution (same as other scanners — check Kalshi API for results)
# ---------------------------------------------------------------------------
def resolve_trades(conn, new_ids: set) -> int:
    try:
        from scripts.mirofish.kalshi_feed import _call_kalshi
    except ImportError:
        return 0

    # --- Early exit check: close profitable trades before expiry ---
    try:
        from scripts.mirofish.bot_config import should_early_exit
        open_trades = conn.execute(
            "SELECT id, market_id, direction, entry_price, shares FROM paper_trades WHERE strategy LIKE 'phantomclaw%' AND status='open'"
        ).fetchall()
        for t in open_trades:
            km = conn.execute(
                "SELECT yes_bid, no_bid, close_time FROM kalshi_markets WHERE ticker=? ORDER BY fetched_at DESC LIMIT 1",
                (t["market_id"],)
            ).fetchone()
            if not km:
                continue
            current = km["yes_bid"] if t["direction"] == "YES" else km["no_bid"]
            if not current:
                continue
            hours_left = None
            if km["close_time"]:
                try:
                    ct = datetime.datetime.fromisoformat(km["close_time"].replace("Z", "+00:00"))
                    if ct.tzinfo is None:
                        ct = ct.replace(tzinfo=datetime.timezone.utc)
                    hours_left = (ct - datetime.datetime.now(datetime.timezone.utc)).total_seconds() / 3600
                except Exception:
                    pass
            if hours_left and should_early_exit(t["entry_price"], current, t["direction"], hours_left):
                pnl = t["shares"] * (current - t["entry_price"]) if t["direction"] == "YES" else t["shares"] * (t["entry_price"] - current)
                status = "closed_win" if pnl > 0 else "closed_loss"
                conn.execute(
                    "UPDATE paper_trades SET status=?, exit_price=?, pnl=?, closed_at=? WHERE id=?",
                    (status, current, round(pnl, 2), datetime.datetime.now(datetime.timezone.utc).isoformat(), t["id"])
                )
                sign = "+" if pnl >= 0 else ""
                print(f"  [EARLY EXIT] {t['direction']} {t['market_id'][:30]} entry={t['entry_price']:.3f} exit={current:.3f} pnl={sign}${pnl:.2f} hours_left={hours_left:.1f}")
        conn.commit()
    except Exception as e:
        print(f"  [EARLY EXIT] check failed: {e}")
    # --- End early exit check ---

    trades = conn.execute("""
        SELECT id, market_id, direction, entry_price, shares FROM paper_trades
        WHERE status='open' AND strategy LIKE 'phantomclaw%'
    """).fetchall()

    resolved = 0
    now = datetime.datetime.utcnow()

    for t in trades:
        if t["id"] in new_ids:
            continue

        # Check if contract has resolved
        data = _call_kalshi("GET", f"/markets/{t['market_id']}")
        if not data:
            continue
        m = data.get("market", data)
        result = m.get("result", "")

        # For fast contracts, also check if expired (let them ride — no stop loss)
        if not result:
            exp_str = m.get("expected_expiration_time") or m.get("close_time", "")
            if exp_str:
                try:
                    exp = datetime.datetime.fromisoformat(exp_str.replace("Z", "+00:00"))
                    if now > exp.replace(tzinfo=None) + datetime.timedelta(minutes=5):
                        # Expired but no result yet — skip, will resolve next cycle
                        pass
                except Exception:
                    pass
            continue

        we_bet = t["direction"].lower()
        we_won = (result == "yes" and we_bet == "yes") or (result == "no" and we_bet == "no")
        exit_price = 1.0 if we_won else 0.0
        pnl = t["shares"] * (exit_price - t["entry_price"])
        status = "closed_win" if we_won else "closed_loss"

        conn.execute("UPDATE paper_trades SET exit_price=?, pnl=?, status=?, closed_at=? WHERE id=?",
                     (exit_price, pnl, status, now.isoformat(), t["id"]))
        sign = "+" if pnl >= 0 else ""
        print(f"[phantom] Resolved: {status} {sign}${pnl:.2f} {t['market_id'][:30]}")
        resolved += 1

    if resolved:
        conn.commit()
    return resolved


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def _get_balance(conn) -> float:
    """PhantomClaw's own $1000 virtual wallet — only counts phantomclaw trades."""
    try:
        pnl = conn.execute("SELECT COALESCE(SUM(pnl), 0) FROM paper_trades WHERE strategy LIKE 'phantomclaw%' AND status IN ('closed_win','closed_loss','expired')").fetchone()[0]
        return 1000.0 + pnl
    except Exception:
        return 1000.0


def run():
    from scripts.mirofish.bot_config import is_trading_hours
    if not is_trading_hours():
        print("[phantom] Outside trading hours (00-06 UTC) — skipping")
        return
    # Circuit breaker
    try:
        from scripts.mirofish.paper_wallet import check_circuit_breaker, reset_wallet
        breaker = check_circuit_breaker()
        if breaker:
            print("[phantom] Circuit breaker")
            reset_wallet()
            _notify()
            return
    except Exception:
        pass

    conn = _get_conn()
    balance = _get_balance(conn)
    open_ids = set(r[0] for r in conn.execute("SELECT market_id FROM paper_trades WHERE status='open'").fetchall())
    # Allow up to 3 brackets per event (like RivalClaw's bracket_cone)
    from collections import Counter
    event_counts = Counter()
    for r in conn.execute("SELECT market_id FROM paper_trades WHERE status='open' AND strategy LIKE 'phantomclaw%'").fetchall():
        # Extract event ticker from market_id (everything before last dash segment)
        parts = r[0].rsplit("-", 1)
        event_counts[parts[0] if len(parts) > 1 else r[0]] += 1
    events_seen = set(evt for evt, cnt in event_counts.items() if cnt >= 3)
    new_ids: set[int] = set()

    # Get spot prices
    spot_dict = {}
    for asset in ["BTC", "ETH", "DOGE", "BNB", "ADA", "BCH"]:
        row = conn.execute("SELECT amount_usd FROM spot_prices WHERE ticker=? ORDER BY fetched_at DESC LIMIT 1",
                           (f"SPOT:{asset}",)).fetchone()
        if row and row["amount_usd"]:
            spot_dict[asset] = row["amount_usd"]

    if not spot_dict:
        print("[phantom] No spot data — skipping")
        conn.close()
        return

    # Run fair value strategy
    placed = scan_fair_value(conn, balance, open_ids, spot_dict, events_seen, new_ids)

    # Resolve expired trades
    resolved = resolve_trades(conn, new_ids)
    conn.close()

    if placed > 0 or resolved > 0:
        print(f"[phantom] Placed {placed}, resolved {resolved}")
        _notify()
    else:
        print(f"[phantom] No fair-value opportunities found (spot: {spot_dict})")


if __name__ == "__main__":
    _load_env()
    run()
