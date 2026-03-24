#!/usr/bin/env python3
"""
Telegram digest generator — produces formatted messages for strategy rankings,
arb opportunities, data quality alerts, and daily summaries.

Phase 5D Step 4 (Telegram surfaces) + Phase 5E Step 4 (ranking digests).

Does NOT send messages directly — produces formatted text that the existing
Telegram bot infrastructure can send. Keeps this module pure and testable.

Python 3.9 compatible via __future__ annotations.
"""
from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Digest formatters
# ---------------------------------------------------------------------------

def format_strategy_rankings(reports: list[Any]) -> str:
    """Format strategy tournament results as a Telegram message."""
    active = [r for r in reports if r.total_trades > 0 or r.allocation_pct > 0.01]
    if not active:
        return "📊 *Strategy Rankings*\nNo active strategies yet."

    active.sort(key=lambda r: r.allocation_pct, reverse=True)

    lines = ["📊 *Strategy Tournament Rankings*", ""]
    for i, r in enumerate(active, 1):
        medal = "🥇" if i == 1 else ("🥈" if i == 2 else ("🥉" if i == 3 else f" {i}."))
        alloc = f"{r.allocation_pct:.0%}" if r.allocation_pct > 0 else "0%"
        wr = f"{r.win_rate:.0%}" if r.total_trades > 0 else "n/a"
        sharpe = f"{r.sharpe:.2f}" if r.sharpe is not None else "n/a"
        pnl = f"${r.total_pnl:+.2f}" if r.total_trades > 0 else "$0"

        lines.append(
            f"{medal} *{r.strategy}* → {alloc}\n"
            f"   W/L: {r.wins}/{r.losses} ({wr}) | Sharpe: {sharpe} | PnL: {pnl}"
        )

    return "\n".join(lines)


def format_arb_opportunities(opportunities: list[Any]) -> str:
    """Format cross-venue arb opportunities as a Telegram message."""
    if not opportunities:
        return ""

    lines = ["⚡ *Cross-Venue Arb Opportunities*", ""]
    for opp in opportunities[:5]:
        lines.append(
            f"• Buy YES @{opp.buy_price:.3f} on {opp.buy_venue}\n"
            f"  Sell @{opp.sell_price:.3f} on {opp.sell_venue}\n"
            f"  Spread: {opp.spread:.3f} | Edge: {opp.estimated_edge:.3f}"
        )

    return "\n".join(lines)


def format_data_quality_alert(report: Any) -> str:
    """Format data quality alerts as a Telegram message."""
    if not report.alerts:
        return ""

    critical = [a for a in report.alerts if a.severity == "critical"]
    warnings = [a for a in report.alerts if a.severity == "warning"]

    lines = [f"🚨 *Data Quality Alert* ({len(report.alerts)} issues)", ""]

    if critical:
        lines.append(f"*Critical ({len(critical)}):*")
        for a in critical[:5]:
            lines.append(f"  ❌ {a.market_id}: {a.message}")

    if warnings:
        lines.append(f"*Warnings ({len(warnings)}):*")
        for a in warnings[:5]:
            lines.append(f"  ⚠️ {a.market_id}: {a.message}")

    if report.markets_blocked:
        lines.append(f"\n*Blocked from trading:* {', '.join(report.markets_blocked[:10])}")

    return "\n".join(lines)


def format_daily_summary(
    wallet_state: dict,
    strategy_reports: list[Any] | None = None,
    missed_summary: list[Any] | None = None,
) -> str:
    """Format daily trading summary as a Telegram message."""
    balance = wallet_state.get("balance", 0)
    starting = wallet_state.get("starting_balance", 1000)
    roi = ((balance - starting) / starting * 100) if starting > 0 else 0
    positions = wallet_state.get("open_positions", 0)
    win_rate = wallet_state.get("win_rate", 0)
    sharpe = wallet_state.get("sharpe_ratio")
    drawdown = wallet_state.get("max_drawdown", 0)

    lines = [
        "📋 *Daily MiroFish Summary*",
        "",
        f"💰 Balance: ${balance:,.2f} ({roi:+.1f}%)",
        f"📈 Open: {positions} | Win rate: {win_rate:.0%}",
    ]

    if sharpe is not None:
        lines.append(f"📊 Sharpe: {sharpe:.3f} | Max DD: {drawdown:.1%}")

    if strategy_reports:
        active = [r for r in strategy_reports if r.total_trades > 0]
        if active:
            lines.append("\n*Top strategies:*")
            for r in sorted(active, key=lambda x: x.total_pnl, reverse=True)[:3]:
                lines.append(f"  • {r.strategy}: ${r.total_pnl:+.2f} ({r.win_rate:.0%} WR)")

    if missed_summary:
        total_missed = sum(m.total_missed for m in missed_summary)
        total_opp_cost = sum(m.opportunity_cost for m in missed_summary)
        if total_missed > 0:
            lines.append(f"\n*Missed:* {total_missed} trades (${total_opp_cost:+.2f} opp cost)")

    return "\n".join(lines)


def format_edge_persistence(lifetimes: list[Any]) -> str:
    """Format edge persistence data as a Telegram message."""
    if not lifetimes:
        return ""

    lines = ["⏱ *Edge Persistence*", ""]
    for lt in sorted(lifetimes, key=lambda x: x.halflife_min):
        emoji = "🔴" if lt.urgency == "high" else ("🟡" if lt.urgency == "medium" else "🟢")
        lines.append(
            f"{emoji} *{lt.strategy}*: {lt.halflife_min:.0f}min half-life "
            f"({lt.urgency} urgency, n={lt.sample_count})"
        )

    return "\n".join(lines)
