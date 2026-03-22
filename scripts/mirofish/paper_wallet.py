#!/usr/bin/env python3
"""
Mirofish paper wallet — fake wallet manager for prediction market simulation.
DB: ~/.openclaw/clawmson.db (tables: paper_trades, daily_pnl, context)
"""
from __future__ import annotations
import os
import sqlite3
import datetime
from pathlib import Path
from statistics import mean, stdev
from typing import Any

STOP_LOSS_PCT    = float(os.environ.get("MIROFISH_STOP_LOSS_PCT",    "0.20"))
TAKE_PROFIT_PCT  = float(os.environ.get("MIROFISH_TAKE_PROFIT_PCT",  "0.50"))
MAX_POSITION_PCT = float(os.environ.get("MIROFISH_MAX_POSITION_PCT", "0.10"))
MIN_HISTORY_DAYS = int(os.environ.get("MIROFISH_MIN_HISTORY_DAYS", "14"))


def _get_conn() -> sqlite3.Connection:
    db_path = Path(os.environ.get("CLAWMSON_DB_PATH", Path.home() / ".openclaw" / "clawmson.db"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _get_starting_balance() -> float:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT value FROM context WHERE chat_id='mirofish' AND key='starting_balance'"
        ).fetchone()
    return float(row["value"]) if row else 1000.0


def _get_latest_prices() -> dict[str, dict]:
    """Return {market_id: {yes_price, no_price}} from most recent snapshot per market."""
    with _get_conn() as conn:
        rows = conn.execute("""
            SELECT md.market_id, md.yes_price, md.no_price
            FROM market_data md
            INNER JOIN (
                SELECT market_id, MAX(fetched_at) AS latest
                FROM market_data GROUP BY market_id
            ) latest ON md.market_id = latest.market_id AND md.fetched_at = latest.latest
        """).fetchall()
    return {r["market_id"]: {"yes_price": r["yes_price"], "no_price": r["no_price"]} for r in rows}


def _compute_balance(starting: float, prices: dict[str, dict]) -> float:
    """Derive current balance from trade history + mark-to-market open positions."""
    with _get_conn() as conn:
        # Includes closed_win, closed_loss, and expired — all have their final pnl stored at close time
        closed = conn.execute(
            "SELECT COALESCE(SUM(pnl), 0) as total FROM paper_trades WHERE status != 'open'"
        ).fetchone()["total"]
        open_trades = conn.execute(
            "SELECT market_id, direction, shares, entry_price FROM paper_trades WHERE status='open'"
        ).fetchall()

    unrealized = 0.0
    for t in open_trades:
        p = prices.get(t["market_id"], {})
        if t["direction"] == "YES":
            price = p.get("yes_price", t["entry_price"])
        else:
            price = p.get("no_price", t["entry_price"])
        unrealized += t["shares"] * (price - t["entry_price"])

    return starting + closed + unrealized


def get_state() -> dict[str, Any]:
    """Return full wallet state. Balance is always derived, never cached."""
    starting = _get_starting_balance()
    prices = _get_latest_prices()
    balance = _compute_balance(starting, prices)

    with _get_conn() as conn:
        closed_trades = conn.execute(
            "SELECT status FROM paper_trades WHERE status != 'open'"
        ).fetchall()
        open_positions = conn.execute(
            "SELECT COUNT(*) as cnt FROM paper_trades WHERE status='open'"
        ).fetchone()["cnt"]
        daily_rows = conn.execute(
            "SELECT balance, roi_pct FROM daily_pnl ORDER BY date ASC"
        ).fetchall()

    total_closed = len(closed_trades)
    wins = sum(1 for t in closed_trades if t["status"] == "closed_win")
    win_rate = wins / total_closed if total_closed > 0 else 0.0

    # Sharpe: mean/std of daily roi_pct (unannualized)
    returns = [r["roi_pct"] for r in daily_rows if r["roi_pct"] is not None]
    sharpe = None
    if len(returns) >= MIN_HISTORY_DAYS:
        s = stdev(returns)
        if s > 0:
            sharpe = mean(returns) / s

    # Max drawdown: peak-to-trough over all daily balances
    balances = [r["balance"] for r in daily_rows]
    max_dd = 0.0
    if balances:
        peak = balances[0]
        for b in balances:
            peak = max(peak, b)
            dd = (peak - b) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, dd)

    return {
        "balance": balance,
        "starting_balance": starting,
        "open_positions": open_positions,
        "win_rate": win_rate,
        "sharpe_ratio": sharpe,
        "max_drawdown": max_dd,
        "total_trades": total_closed,
    }


def execute_trade(decision: Any) -> dict | None:
    """
    Execute a paper trade. Returns trade dict or None if rejected.
    Rejects if: amount_usd > 10% of balance.
    Manual /bet trades: pass decision with strategy='manual', confidence=1.0.
    """
    state = get_state()
    cap = state["balance"] * MAX_POSITION_PCT

    if decision.amount_usd > cap:
        return None  # position cap breached

    ts = datetime.datetime.utcnow().isoformat()
    with _get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO paper_trades
            (market_id, question, direction, shares, entry_price, amount_usd,
             status, confidence, reasoning, strategy, opened_at)
            VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?)
        """, (
            decision.market_id, decision.question, decision.direction,
            decision.shares, decision.entry_price, decision.amount_usd,
            getattr(decision, "confidence", 1.0),
            getattr(decision, "reasoning", "manual via /bet"),
            getattr(decision, "strategy", "manual"),
            ts,
        ))
        trade_id = cur.lastrowid

    return {"id": trade_id, "status": "open", "amount_usd": decision.amount_usd,
            "market_id": decision.market_id, "direction": decision.direction}


def check_stops(current_prices: dict[str, dict]) -> list[dict]:
    """
    Check all open positions for stop-loss (-20%) and take-profit (+50%).
    Also closes positions in markets whose end_date has passed.
    Returns list of closed trade dicts.
    """
    now = datetime.datetime.utcnow()
    closed = []
    closed_updates = []

    with _get_conn() as conn:
        open_trades = conn.execute("""
            SELECT pt.*, md.end_date
            FROM paper_trades pt
            LEFT JOIN (
                SELECT market_id, end_date, MAX(fetched_at) AS latest
                FROM market_data GROUP BY market_id
            ) md ON pt.market_id = md.market_id
            WHERE pt.status = 'open'
        """).fetchall()

    for t in open_trades:
        p = current_prices.get(t["market_id"], {})
        if t["direction"] == "YES":
            current_price = p.get("yes_price", t["entry_price"])
        else:
            current_price = p.get("no_price", t["entry_price"])

        unrealized_pnl = t["shares"] * (current_price - t["entry_price"])
        # Round to 10 decimal places to avoid floating-point drift at boundary conditions
        pnl_pct = round(unrealized_pnl / t["amount_usd"], 10) if t["amount_usd"] > 0 else 0.0

        # Check expiry
        expired = False
        if t["end_date"]:
            try:
                end = datetime.datetime.fromisoformat(t["end_date"].replace("Z", ""))
                expired = now > end
            except (ValueError, AttributeError):
                pass

        should_close = (
            pnl_pct <= -STOP_LOSS_PCT or
            pnl_pct >= TAKE_PROFIT_PCT or
            expired
        )

        if should_close:
            status = "expired" if expired else ("closed_win" if unrealized_pnl >= 0 else "closed_loss")
            ts = now.isoformat()
            closed_updates.append((current_price, unrealized_pnl, status, ts, t["id"]))
            closed.append({
                "id": t["id"], "market_id": t["market_id"],
                "status": status, "exit_price": current_price, "pnl": unrealized_pnl,
            })

    if closed_updates:
        with _get_conn() as conn:
            conn.executemany("""
                UPDATE paper_trades SET exit_price=?, pnl=?, status=?, closed_at=? WHERE id=?
            """, closed_updates)

    return closed


def get_open_positions() -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM paper_trades WHERE status='open' ORDER BY opened_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_pnl_summary(days: int = 7) -> dict:
    with _get_conn() as conn:
        rows = conn.execute("""
            SELECT date, balance, roi_pct, win_rate
            FROM daily_pnl ORDER BY date DESC LIMIT ?
        """, (days,)).fetchall()
    return {"rows": [dict(r) for r in rows], "days": days}
