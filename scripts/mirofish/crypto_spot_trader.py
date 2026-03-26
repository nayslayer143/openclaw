#!/usr/bin/env python3
"""
Crypto spot paper trader — simulates BTC/ETH spot trades using mean-reversion
and momentum strategies against live exchange prices.

Runs every 10 minutes alongside fast_scanner. No LLM needed.
Uses simple technical signals: price vs moving average, RSI-like overbought/oversold.

Stores trades in paper_trades with strategy='crypto_spot_mean_rev' or 'crypto_spot_momentum'.

Usage:
    python3 -m scripts.mirofish.crypto_spot_trader
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


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ASSETS = ["BTC", "ETH"]
LOOKBACK_HOURS = int(os.environ.get("CRYPTO_SPOT_LOOKBACK", "6"))
MEAN_REV_THRESHOLD = float(os.environ.get("CRYPTO_SPOT_MEAN_REV_PCT", "1.5"))  # 1.5% from SMA
MOMENTUM_THRESHOLD = float(os.environ.get("CRYPTO_SPOT_MOMENTUM_PCT", "2.0"))  # 2% move
POSITION_PCT = float(os.environ.get("CRYPTO_SPOT_POSITION_PCT", "0.05"))
MAX_POSITION_PCT = float(os.environ.get("MIROFISH_MAX_POSITION_PCT", "0.10"))
STOP_LOSS_PCT = float(os.environ.get("CRYPTO_SPOT_STOP_LOSS", "0.03"))   # 3% stop
TAKE_PROFIT_PCT = float(os.environ.get("CRYPTO_SPOT_TAKE_PROFIT", "0.05"))  # 5% TP
MAX_OPEN_PER_ASSET = 1


def _get_conn():
    db_path = Path(os.environ.get("CLAWMSON_DB_PATH",
                                   Path.home() / ".openclaw" / "clawmson.db"))
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _notify_dashboard():
    try:
        import requests
        requests.post("http://127.0.0.1:7080/api/trading/notify", timeout=2)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Price history
# ---------------------------------------------------------------------------

def _get_price_history(conn, asset: str, hours: int = LOOKBACK_HOURS) -> list[float]:
    """Get recent spot prices from DB."""
    cutoff = (datetime.datetime.utcnow() -
              datetime.timedelta(hours=hours)).isoformat()
    rows = conn.execute("""
        SELECT amount_usd FROM spot_prices
        WHERE ticker = ? AND fetched_at > ?
        ORDER BY fetched_at ASC
    """, (f"SPOT:{asset}", cutoff)).fetchall()
    return [r["amount_usd"] for r in rows if r["amount_usd"] and r["amount_usd"] > 0]


def _get_current_price(conn, asset: str) -> float | None:
    """Get latest spot price."""
    row = conn.execute("""
        SELECT amount_usd FROM spot_prices
        WHERE ticker = ? ORDER BY fetched_at DESC LIMIT 1
    """, (f"SPOT:{asset}",)).fetchone()
    return row["amount_usd"] if row and row["amount_usd"] else None


def _sma(prices: list[float]) -> float:
    return sum(prices) / len(prices) if prices else 0


def _rsi_like(prices: list[float], period: int = 14) -> float | None:
    """Simple RSI approximation from price changes."""
    if len(prices) < period + 1:
        return None
    changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    recent = changes[-period:]
    gains = [c for c in recent if c > 0]
    losses = [-c for c in recent if c < 0]
    avg_gain = sum(gains) / period if gains else 0.001
    avg_loss = sum(losses) / period if losses else 0.001
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

def _check_mean_reversion(asset: str, current: float, prices: list[float]) -> dict | None:
    """Buy when price is significantly below SMA, sell when above."""
    if len(prices) < 5:
        return None

    avg = _sma(prices)
    deviation_pct = (current - avg) / avg * 100

    if deviation_pct < -MEAN_REV_THRESHOLD:
        # Price below SMA — expect reversion up → BUY
        return {
            "direction": "BUY",
            "edge": abs(deviation_pct) / 100,
            "reasoning": f"{asset} spot ${current:,.0f} is {deviation_pct:.1f}% below SMA ${avg:,.0f} — mean reversion buy",
        }
    elif deviation_pct > MEAN_REV_THRESHOLD:
        # Price above SMA — expect reversion down → SELL (short)
        return {
            "direction": "SELL",
            "edge": abs(deviation_pct) / 100,
            "reasoning": f"{asset} spot ${current:,.0f} is +{deviation_pct:.1f}% above SMA ${avg:,.0f} — mean reversion sell",
        }
    return None


def _check_momentum(asset: str, current: float, prices: list[float]) -> dict | None:
    """Ride strong trends — buy into upward momentum, sell into downward."""
    if len(prices) < 10:
        return None

    # Compare current to price 1 hour ago (approx 6 data points at 10-min intervals)
    lookback = min(6, len(prices) - 1)
    old_price = prices[-(lookback + 1)]
    change_pct = (current - old_price) / old_price * 100

    rsi = _rsi_like(prices)

    if change_pct > MOMENTUM_THRESHOLD and (rsi is None or rsi < 75):
        return {
            "direction": "BUY",
            "edge": abs(change_pct) / 100,
            "reasoning": f"{asset} momentum +{change_pct:.1f}% in {lookback * 10}min, RSI={rsi:.0f if rsi else '?'} — trend follow buy",
        }
    elif change_pct < -MOMENTUM_THRESHOLD and (rsi is None or rsi > 25):
        return {
            "direction": "SELL",
            "edge": abs(change_pct) / 100,
            "reasoning": f"{asset} momentum {change_pct:.1f}% in {lookback * 10}min, RSI={rsi:.0f if rsi else '?'} — trend follow sell",
        }
    return None


# ---------------------------------------------------------------------------
# Trade execution
# ---------------------------------------------------------------------------

def _get_open_crypto_positions(conn, asset: str) -> list:
    rows = conn.execute("""
        SELECT * FROM paper_trades
        WHERE market_id = ? AND status = 'open'
        AND strategy LIKE 'crypto_spot_%'
    """, (f"SPOT:{asset}",)).fetchall()
    return list(rows)


def _place_crypto_trade(conn, asset: str, direction: str, price: float,
                         edge: float, reasoning: str, strategy: str, balance: float) -> bool:
    amount = min(POSITION_PCT * balance, MAX_POSITION_PCT * balance)
    if amount <= 0 or price <= 0:
        return False

    # Fee deduction before share calculation
    fee_rate = 0.07  # Kalshi crypto
    entry_fee = amount * fee_rate * min(price, 1.0 - price) if price < 1.0 else 0.0
    amount -= entry_fee

    shares = amount / price
    ts = datetime.datetime.utcnow().isoformat()

    # For crypto spot: direction is BUY/SELL, map to YES/NO for paper_trades compatibility
    paper_direction = "YES" if direction == "BUY" else "NO"

    conn.execute("""
        INSERT INTO paper_trades
        (market_id, question, direction, shares, entry_price, amount_usd,
         status, confidence, reasoning, strategy, opened_at, entry_fee)
        VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?)
    """, (
        f"SPOT:{asset}",
        f"{asset} spot trade @ ${price:,.2f}",
        paper_direction, shares, price, amount,
        min(edge / 0.05, 1.0), reasoning, strategy, ts, entry_fee,
    ))
    conn.commit()
    print(f"[crypto_spot] {direction} {shares:.6f} {asset} @ ${price:,.2f} (${amount:.0f}) [{strategy}]")
    return True


def _check_crypto_stops(conn, asset: str, current_price: float) -> int:
    """Check stop-loss and take-profit for open crypto positions."""
    positions = _get_open_crypto_positions(conn, asset)
    closed = 0

    for p in positions:
        entry = p["entry_price"]
        direction = p["direction"]  # YES = long, NO = short

        if direction == "YES":  # long
            pnl_pct = (current_price - entry) / entry
        else:  # short
            pnl_pct = (entry - current_price) / entry

        if pnl_pct <= -STOP_LOSS_PCT or pnl_pct >= TAKE_PROFIT_PCT:
            pnl_usd = p["shares"] * abs(current_price - entry)
            if pnl_pct < 0:
                pnl_usd = -pnl_usd

            status = "closed_win" if pnl_usd >= 0 else "closed_loss"
            ts = datetime.datetime.utcnow().isoformat()

            conn.execute("""
                UPDATE paper_trades SET exit_price=?, pnl=?, status=?, closed_at=?
                WHERE id=?
            """, (current_price, pnl_usd, status, ts, p["id"]))

            sign = "+" if pnl_usd >= 0 else ""
            print(f"[crypto_spot] {asset} {status}: {sign}${pnl_usd:.2f} ({pnl_pct:+.1%})")
            closed += 1

    if closed:
        conn.commit()
    return closed


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run():
    conn = _get_conn()
    notified = False

    # Get balance
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

    for asset in ASSETS:
        current = _get_current_price(conn, asset)
        if not current:
            continue

        prices = _get_price_history(conn, asset)

        # Check stops first
        closed = _check_crypto_stops(conn, asset, current)
        if closed:
            notified = True

        # Check if we already have an open position
        open_pos = _get_open_crypto_positions(conn, asset)
        if len(open_pos) >= MAX_OPEN_PER_ASSET:
            continue

        # Try mean reversion first
        signal = _check_mean_reversion(asset, current, prices)
        if signal:
            placed = _place_crypto_trade(
                conn, asset, signal["direction"], current,
                signal["edge"], signal["reasoning"],
                "crypto_spot_mean_rev", balance,
            )
            if placed:
                notified = True
                continue

        # Try momentum
        signal = _check_momentum(asset, current, prices)
        if signal:
            placed = _place_crypto_trade(
                conn, asset, signal["direction"], current,
                signal["edge"], signal["reasoning"],
                "crypto_spot_momentum", balance,
            )
            if placed:
                notified = True

    conn.close()

    if notified:
        _notify_dashboard()


if __name__ == "__main__":
    _load_env()
    run()
