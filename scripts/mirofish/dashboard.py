#!/usr/bin/env python3
"""
Mirofish dashboard — graduation checks, report generation, Telegram message formatting.
"""
from __future__ import annotations
import os
import sqlite3
import datetime
from pathlib import Path
from statistics import mean, stdev
from typing import Any

REPORTS_DIR = Path(os.environ.get("MIROFISH_REPORTS_DIR",
                                   Path.home() / "openclaw" / "mirofish" / "reports"))
MIN_HISTORY_DAYS = int(os.environ.get("MIROFISH_MIN_HISTORY_DAYS", "14"))

WIN_RATE_THRESHOLD  = 0.55
SHARPE_THRESHOLD    = 1.0
MAX_DRAWDOWN_LIMIT  = 0.25
ROI_7D_THRESHOLD    = 0.0


def _get_conn() -> sqlite3.Connection:
    db_path = Path(os.environ.get("CLAWMSON_DB_PATH", Path.home() / ".openclaw" / "clawmson.db"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def check_graduation() -> dict[str, Any]:
    """Evaluate all 4 graduation criteria. Returns status dict."""
    with _get_conn() as conn:
        all_pnl = conn.execute(
            "SELECT date, balance, roi_pct FROM daily_pnl ORDER BY date ASC"
        ).fetchall()
        closed = conn.execute(
            "SELECT status FROM paper_trades WHERE status != 'open'"
        ).fetchall()

    history_days = len(all_pnl)
    has_min_history = history_days >= MIN_HISTORY_DAYS

    last7 = all_pnl[-7:] if len(all_pnl) >= 7 else all_pnl
    roi_7d = sum(r["roi_pct"] for r in last7 if r["roi_pct"] is not None)

    total_closed = len(closed)
    wins = sum(1 for t in closed if t["status"] == "closed_win")
    win_rate = wins / total_closed if total_closed > 0 else 0.0

    returns = [r["roi_pct"] for r in all_pnl if r["roi_pct"] is not None]
    sharpe = None
    if len(returns) >= MIN_HISTORY_DAYS:
        s = stdev(returns)
        if s > 0:
            sharpe = mean(returns) / s

    balances = [r["balance"] for r in all_pnl]
    max_dd = 0.0
    if balances:
        peak = balances[0]
        for b in balances:
            peak = max(peak, b)
            if peak > 0:
                max_dd = max(max_dd, (peak - b) / peak)

    criteria = {
        "min_history": has_min_history,
        "roi_7d_positive": roi_7d > ROI_7D_THRESHOLD,
        "win_rate_55pct": win_rate > WIN_RATE_THRESHOLD,
        "sharpe_above_1": sharpe is not None and sharpe > SHARPE_THRESHOLD,
        "drawdown_below_25pct": max_dd < MAX_DRAWDOWN_LIMIT,
    }
    ready = has_min_history and all(criteria.values())

    return {
        "ready": ready,
        "has_minimum_history": has_min_history,
        "history_days": history_days,
        "roi_7d": roi_7d,
        "win_rate": win_rate,
        "sharpe_all_time": sharpe,
        "max_drawdown": max_dd,
        "criteria": criteria,
    }


def maybe_snapshot(chat_id_for_notify: str | None = None) -> bool:
    """Write daily_pnl row if not written today. Returns True if snapshot written."""
    today = datetime.date.today().isoformat()
    with _get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM daily_pnl WHERE date=?", (today,)
        ).fetchone()

    if existing:
        return False

    import scripts.mirofish.paper_wallet as pw
    import scripts.mirofish.polymarket_feed as feed

    prices = feed.get_latest_prices()
    state = pw.get_state()

    with _get_conn() as conn:
        prev_row = conn.execute(
            "SELECT balance FROM daily_pnl ORDER BY date DESC LIMIT 1"
        ).fetchone()
    prev_balance = prev_row["balance"] if prev_row else state["starting_balance"]
    roi_pct = (state["balance"] - prev_balance) / prev_balance if prev_balance > 0 else 0.0

    with _get_conn() as conn:
        open_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM paper_trades WHERE status='open'"
        ).fetchone()["cnt"]
        total_trades = conn.execute(
            "SELECT COUNT(*) as cnt FROM paper_trades WHERE status != 'open'"
        ).fetchone()["cnt"]
        realized_pnl = conn.execute(
            "SELECT COALESCE(SUM(pnl), 0) as s FROM paper_trades WHERE status != 'open'"
        ).fetchone()["s"]
        unrealized_pnl = state["balance"] - state["starting_balance"] - realized_pnl
        conn.execute("""
            INSERT OR IGNORE INTO daily_pnl
            (date, balance, open_positions, realized_pnl, unrealized_pnl,
             total_trades, win_rate, roi_pct)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (today, state["balance"], open_count, realized_pnl,
              unrealized_pnl, total_trades, state["win_rate"], roi_pct))

    generate_report("daily")

    grad = check_graduation()
    if grad["ready"]:
        with _get_conn() as conn:
            already_notified = conn.execute(
                "SELECT value FROM context WHERE chat_id='mirofish' AND key='graduation_notified'"
            ).fetchone()
        if not already_notified:
            with _get_conn() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO context (chat_id, key, value)
                    VALUES ('mirofish', 'graduation_notified', '1')
                """)
            if chat_id_for_notify:
                _send_telegram(chat_id_for_notify,
                    "MIROFISH: READY FOR LIVE TRADING\n"
                    f"7d ROI: {grad['roi_7d']*100:.1f}% | "
                    f"Win: {grad['win_rate']*100:.0f}% | "
                    f"Sharpe: {grad['sharpe_all_time']:.2f} | "
                    f"MaxDD: {grad['max_drawdown']*100:.1f}%")

    if chat_id_for_notify:
        pnl_today = state["balance"] - prev_balance
        pct_today = roi_pct * 100
        sign = "+" if pnl_today >= 0 else ""
        msg = (
            f"Mirofish Daily — {today}\n"
            f"P&L today: {sign}${pnl_today:.2f} ({sign}{pct_today:.1f}%)\n"
            f"Open positions: {open_count}\n"
            f"Win rate: {state['win_rate']*100:.0f}%\n"
            f"Portfolio: ${state['balance']:.2f}"
        )
        if grad["ready"]:
            msg = "READY FOR LIVE TRADING\n\n" + msg
        _send_telegram(chat_id_for_notify, msg)

    return True


def _send_telegram(chat_id: str, message: str) -> None:
    """Send a Telegram message via notify-telegram.sh."""
    import subprocess
    script = Path.home() / "openclaw" / "scripts" / "notify-telegram.sh"
    if script.exists():
        subprocess.run([str(script), message], timeout=30, capture_output=True)


def generate_report(period: str = "daily") -> Path:
    """Write markdown report to REPORTS_DIR. Returns path."""
    # Re-read REPORTS_DIR from env at call time to support test isolation
    reports_dir = Path(os.environ.get("MIROFISH_REPORTS_DIR",
                                      Path.home() / "openclaw" / "mirofish" / "reports"))
    reports_dir.mkdir(parents=True, exist_ok=True)

    import scripts.mirofish.paper_wallet as pw
    state = pw.get_state()
    grad = check_graduation()
    today = datetime.date.today().isoformat()

    with _get_conn() as conn:
        recent_trades = conn.execute("""
            SELECT market_id, question, direction, amount_usd, pnl, status, strategy,
                   opened_at, closed_at
            FROM paper_trades ORDER BY opened_at DESC LIMIT 10
        """).fetchall()
        last7_pnl = conn.execute("""
            SELECT date, balance, roi_pct FROM daily_pnl
            ORDER BY date DESC LIMIT 7
        """).fetchall()

    lines = []
    if grad["ready"]:
        lines.append("# READY FOR LIVE TRADING\n")
    lines.append(f"# Mirofish {period.title()} Report — {today}\n")
    lines.append(f"**Portfolio:** ${state['balance']:.2f} "
                 f"(started ${state['starting_balance']:.2f})\n")
    lines.append(f"**Win rate:** {state['win_rate']*100:.0f}%  |  "
                 f"**Open positions:** {state['open_positions']}\n")

    if state["sharpe_ratio"] is not None:
        lines.append(f"**Sharpe:** {state['sharpe_ratio']:.2f}  |  "
                     f"**Max drawdown:** {state['max_drawdown']*100:.1f}%\n")

    lines.append("\n## Graduation Status\n")
    lines.append(f"- Min history (14d): {'✓' if grad['criteria']['min_history'] else '✗'} "
                 f"({grad['history_days']} days)\n")
    lines.append(f"- ROI 7d > 0%: {'✓' if grad['criteria']['roi_7d_positive'] else '✗'} "
                 f"({grad['roi_7d']*100:.2f}%)\n")
    lines.append(f"- Win rate > 55%: {'✓' if grad['criteria']['win_rate_55pct'] else '✗'} "
                 f"({grad['win_rate']*100:.0f}%)\n")
    sharpe_str = f"{grad['sharpe_all_time']:.2f}" if grad["sharpe_all_time"] is not None else "N/A"
    lines.append(f"- Sharpe > 1.0: {'✓' if grad['criteria']['sharpe_above_1'] else '✗'} "
                 f"({sharpe_str})\n")
    lines.append(f"- Drawdown < 25%: {'✓' if grad['criteria']['drawdown_below_25pct'] else '✗'} "
                 f"({grad['max_drawdown']*100:.1f}%)\n")

    if last7_pnl:
        lines.append("\n## 7-Day P&L\n")
        for row in reversed(last7_pnl):
            r = row["roi_pct"] or 0
            sign = "+" if r >= 0 else ""
            lines.append(f"- {row['date']}: ${row['balance']:.2f} ({sign}{r*100:.2f}%)\n")

    if recent_trades:
        lines.append("\n## Recent Trades\n")
        for t in recent_trades:
            pnl_str = f"+${t['pnl']:.2f}" if (t['pnl'] or 0) >= 0 else f"-${abs(t['pnl'] or 0):.2f}"
            lines.append(f"- [{t['status']}] {t['direction']} ${t['amount_usd']:.0f} "
                         f"on {t['question'][:50]}  {pnl_str}  [{t['strategy']}]\n")

    report_path = reports_dir / f"mirofish-{period}-{today}.md"
    report_path.write_text("".join(lines))
    return report_path


def format_portfolio_message() -> str:
    """Telegram-ready portfolio snapshot."""
    import scripts.mirofish.paper_wallet as pw
    state = pw.get_state()
    positions = pw.get_open_positions()
    lines = [f"Portfolio: ${state['balance']:.2f}"]
    lines.append(f"Open positions: {len(positions)}")
    for p in positions[:5]:
        lines.append(f"  {p['direction']} ${p['amount_usd']:.0f} — {p['question'][:40]}")
    if len(positions) > 5:
        lines.append(f"  ...and {len(positions)-5} more")
    return "\n".join(lines)


def format_pnl_message() -> str:
    """Telegram-ready 7d ROI, win rate, graduation status."""
    import scripts.mirofish.paper_wallet as pw
    state = pw.get_state()
    grad = check_graduation()
    roi_7d = grad["roi_7d"]
    sign = "+" if roi_7d >= 0 else ""
    lines = [
        f"7d ROI: {sign}{roi_7d*100:.2f}%",
        f"Win rate: {state['win_rate']*100:.0f}% ({state['total_trades']} closed trades)",
        f"Balance: ${state['balance']:.2f}",
    ]
    if state["sharpe_ratio"]:
        lines.append(f"Sharpe: {state['sharpe_ratio']:.2f}  |  Drawdown: {state['max_drawdown']*100:.1f}%")
    if grad["ready"]:
        lines.insert(0, "READY FOR LIVE TRADING")
    elif grad["has_minimum_history"]:
        failing = [k for k, v in grad["criteria"].items() if not v]
        lines.append(f"Graduation: failing {', '.join(failing)}")
    else:
        lines.append(f"Graduation: {grad['history_days']}/{MIN_HISTORY_DAYS} days history")
    return "\n".join(lines)


def format_trades_message(limit: int = 10) -> str:
    """Telegram-ready recent trades list."""
    with _get_conn() as conn:
        trades = conn.execute("""
            SELECT direction, amount_usd, question, pnl, status, strategy, opened_at
            FROM paper_trades ORDER BY opened_at DESC LIMIT ?
        """, (limit,)).fetchall()
    if not trades:
        return "No trades yet."
    lines = []
    for t in trades:
        pnl_str = ""
        if t["pnl"] is not None:
            sign = "+" if t["pnl"] >= 0 else ""
            pnl_str = f" {sign}${t['pnl']:.2f}"
        lines.append(f"[{t['status']}] {t['direction']} ${t['amount_usd']:.0f}{pnl_str} "
                     f"— {t['question'][:45]} [{t['strategy']}]")
    return "\n".join(lines)
