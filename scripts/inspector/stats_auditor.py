"""
Inspector Gadget — Statistical Auditor (Task 5).

Red flag detection on aggregate performance statistics.
Works entirely from clawmson.db data — no API calls.

Checks:
  1. Win rate: >80% sustained is suspicious
  2. Position sizing: >10% of balance violates Kelly cap
  3. Sharpe ratio: >3.5 is implausible; zero-variance is a critical flag
  4. No losing streaks: if >= 30 trades with no 3-streak → suspicious
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from math import sqrt
from pathlib import Path
from typing import List, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WIN_RATE_CEILING = 0.80   # >80% sustained = suspicious
SHARPE_CEILING   = 3.5    # >3.5 Sharpe = implausible
KELLY_CAP        = 0.10   # 10% max position
MIN_SAMPLE       = 20     # minimum closed trades for stats

_DEDUCTIONS = {"critical": 30, "high": 15, "medium": 5, "low": 1}
_CLOSED_STATUSES = frozenset({"closed_win", "closed_loss"})


# ---------------------------------------------------------------------------
# RedFlag dataclass
# ---------------------------------------------------------------------------

@dataclass
class RedFlag:
    check: str
    severity: str   # critical | high | medium | low
    message: str
    value: float = None


# ---------------------------------------------------------------------------
# StatsAuditor
# ---------------------------------------------------------------------------

class StatsAuditor:

    # ------------------------------------------------------------------
    # Individual checks (pure — no DB access)
    # ------------------------------------------------------------------

    def check_win_rate(self, trades: list) -> List[RedFlag]:
        """
        Flag if win rate > WIN_RATE_CEILING over a sample of >= MIN_SAMPLE
        closed trades.
        """
        closed = [t for t in trades if t.get("status") in _CLOSED_STATUSES]
        if len(closed) < MIN_SAMPLE:
            return []

        wins = sum(1 for t in closed if t.get("status") == "closed_win")
        win_rate = wins / len(closed)

        if win_rate > WIN_RATE_CEILING:
            return [RedFlag(
                check="win_rate",
                severity="critical",
                message=(
                    f"Win rate {win_rate:.1%} exceeds ceiling {WIN_RATE_CEILING:.0%} "
                    f"over {len(closed)} trades — statistically suspicious"
                ),
                value=win_rate,
            )]
        return []

    def check_position_size(self, trade: dict, balance: float) -> List[RedFlag]:
        """
        Flag if a single trade uses > KELLY_CAP * 1.05 of account balance.
        Critical if > 15%, high otherwise.
        """
        amount_usd = trade.get("amount_usd", 0) or 0
        if balance <= 0:
            return []

        size_pct = amount_usd / balance
        if size_pct <= KELLY_CAP * 1.05:
            return []

        severity = "critical" if size_pct > 0.15 else "high"
        return [RedFlag(
            check="position_size",
            severity=severity,
            message=(
                f"Position size {size_pct:.1%} exceeds Kelly cap "
                f"{KELLY_CAP:.0%} (grace: 5%) — over-leveraged"
            ),
            value=size_pct,
        )]

    def check_sharpe(self, daily_pnl_rows: list) -> List[RedFlag]:
        """
        Compute annualised Sharpe from daily roi_pct values.
        Flag zero-variance (critical) or Sharpe > SHARPE_CEILING (high).
        Requires >= 7 data points.
        """
        values = [
            r.get("roi_pct")
            for r in daily_pnl_rows
            if r.get("roi_pct") is not None
        ]
        if len(values) < 7:
            return []

        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        std = sqrt(variance)

        if std < 1e-10:
            return [RedFlag(
                check="sharpe",
                severity="critical",
                message=(
                    "Zero variance in daily returns — all returns identical, "
                    "which is statistically impossible in real markets"
                ),
                value=0.0,
            )]

        sharpe = (mean / std) * sqrt(365)
        if sharpe > SHARPE_CEILING:
            return [RedFlag(
                check="sharpe",
                severity="high",
                message=(
                    f"Annualised Sharpe {sharpe:.2f} exceeds plausibility ceiling "
                    f"{SHARPE_CEILING} — performance too consistent to be real"
                ),
                value=sharpe,
            )]
        return []

    def check_no_losing_streaks(self, trades: list) -> List[RedFlag]:
        """
        If >= 30 closed trades have no losing streak of >= 3, flag as medium.
        Real trading always produces clusters of losses.
        """
        closed = [t for t in trades if t.get("status") in _CLOSED_STATUSES]
        if len(closed) < 30:
            return []

        max_streak = 0
        current_streak = 0
        for t in closed:
            if t.get("status") == "closed_loss":
                current_streak += 1
                if current_streak > max_streak:
                    max_streak = current_streak
            else:
                current_streak = 0

        if max_streak < 3:
            return [RedFlag(
                check="losing_streaks",
                severity="medium",
                message=(
                    f"No losing streak >= 3 found over {len(closed)} closed trades "
                    f"(max streak: {max_streak}) — real trading always produces "
                    f"loss clusters"
                ),
                value=float(max_streak),
            )]
        return []

    # ------------------------------------------------------------------
    # Main runner
    # ------------------------------------------------------------------

    def run(self, clawmson_db_path: str, chat_id: str = "mirofish", trade_query: Optional[str] = None) -> dict:
        """
        Read paper_trades and daily_pnl from clawmson.db, run all 4 checks,
        compute trust score, and return a summary dict.
        """
        db_path = str(Path(clawmson_db_path).expanduser())
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            query = trade_query or "SELECT * FROM paper_trades"
            trades = [dict(r) for r in conn.execute(query).fetchall()]
            try:
                daily_pnl = [dict(r) for r in conn.execute("SELECT * FROM daily_pnl").fetchall()]
            except Exception:
                daily_pnl = []

            # Read starting balance from context table
            starting_balance = 1000.0
            try:
                # Try with chat_id first (openclaw/rivalclaw), then without (quantclaw)
                row = conn.execute(
                    "SELECT value FROM context WHERE chat_id=? AND key='starting_balance'",
                    (chat_id,),
                ).fetchone()
                if row is None:
                    row = conn.execute(
                        "SELECT value FROM context WHERE key='starting_balance'"
                    ).fetchone()
                if row is not None:
                    starting_balance = float(row["value"])
            except Exception:
                pass
        finally:
            conn.close()

        # Aggregate flags
        red_flags: List[RedFlag] = []

        # Check 1: win rate
        red_flags.extend(self.check_win_rate(trades))

        # Check 2: position sizing — collect all violations, collapse to one flag
        size_violations = []
        for trade in trades:
            try:
                flags = self.check_position_size(trade, starting_balance)
                size_violations.extend(flags)
            except Exception:
                continue

        if size_violations:
            worst = max(size_violations, key=lambda f: ["low","medium","high","critical"].index(f.severity))
            count = len(size_violations)
            red_flags.append(RedFlag(
                check="position_size",
                severity=worst.severity,
                message=f"{count} trade(s) exceeded {KELLY_CAP*100:.0f}% position cap. Worst: {worst.message}",
                value=worst.value,
            ))

        # Check 3: Sharpe
        red_flags.extend(self.check_sharpe(daily_pnl))

        # Check 4: losing streaks
        red_flags.extend(self.check_no_losing_streaks(trades))

        # Trust score
        trust_score = 100
        for flag in red_flags:
            trust_score -= _DEDUCTIONS.get(flag.severity, 0)
        trust_score = max(0, trust_score)

        closed_trades = sum(
            1 for t in trades if t.get("status") in _CLOSED_STATUSES
        )

        return {
            "trust_score": trust_score,
            "red_flags": [
                {
                    "check": f.check,
                    "severity": f.severity,
                    "message": f.message,
                    "value": f.value,
                }
                for f in red_flags
            ],
            "total_trades": len(trades),
            "closed_trades": closed_trades,
        }
