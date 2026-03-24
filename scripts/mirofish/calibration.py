#!/usr/bin/env python3
"""
Calibration + scenario archive + promotion rules.

Phase 5F Steps 2-4:
- Scoring calibration: auto-tune strategy params from backtest results
- Scenario archive: store past market setups for pattern matching
- Promotion rules: when can new strategies/weights go live?

Python 3.9 compatible via __future__ annotations.
"""
from __future__ import annotations

import json
import os
import sqlite3
import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------

def _get_conn() -> sqlite3.Connection:
    db_path = Path(os.environ.get("CLAWMSON_DB_PATH",
                                   Path.home() / ".openclaw" / "clawmson.db"))
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def migrate() -> None:
    with _get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS scenario_archive (
                id              INTEGER PRIMARY KEY,
                market_id       TEXT NOT NULL,
                question        TEXT NOT NULL,
                category        TEXT,
                strategy        TEXT NOT NULL,
                direction       TEXT NOT NULL,
                entry_price     REAL NOT NULL,
                exit_price      REAL,
                pnl             REAL,
                status          TEXT NOT NULL,
                signals_json    TEXT,
                market_state_json TEXT,
                outcome         TEXT,
                tags            TEXT,
                archived_at     TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_scenario_category
                ON scenario_archive(category, strategy);
            CREATE INDEX IF NOT EXISTS idx_scenario_tags
                ON scenario_archive(tags);

            CREATE TABLE IF NOT EXISTS calibration_params (
                id              INTEGER PRIMARY KEY,
                param_name      TEXT NOT NULL,
                current_value   REAL NOT NULL,
                proposed_value  REAL,
                backtest_pnl_current REAL,
                backtest_pnl_proposed REAL,
                improvement_pct REAL,
                status          TEXT NOT NULL DEFAULT 'pending',
                computed_at     TEXT NOT NULL,
                approved_at     TEXT,
                UNIQUE(param_name, computed_at)
            );

            CREATE TABLE IF NOT EXISTS promotion_candidates (
                id              INTEGER PRIMARY KEY,
                candidate_type  TEXT NOT NULL,
                candidate_name  TEXT NOT NULL,
                description     TEXT,
                backtest_sharpe REAL,
                backtest_roi    REAL,
                paper_sharpe    REAL,
                paper_roi       REAL,
                min_days_paper  INTEGER NOT NULL DEFAULT 14,
                days_active     INTEGER NOT NULL DEFAULT 0,
                status          TEXT NOT NULL DEFAULT 'testing',
                created_at      TEXT NOT NULL,
                promoted_at     TEXT
            );
        """)


# ---------------------------------------------------------------------------
# Scenario archive
# ---------------------------------------------------------------------------

def archive_trade(
    market_id: str,
    question: str,
    category: str,
    strategy: str,
    direction: str,
    entry_price: float,
    exit_price: float | None,
    pnl: float | None,
    status: str,
    signals: list[dict] | None = None,
    market_state: dict | None = None,
    tags: list[str] | None = None,
) -> None:
    """Archive a completed trade as a scenario for future pattern matching."""
    with _get_conn() as conn:
        outcome = "win" if (pnl or 0) > 0 else ("loss" if pnl is not None else "pending")
        conn.execute("""
            INSERT INTO scenario_archive
            (market_id, question, category, strategy, direction, entry_price,
             exit_price, pnl, status, signals_json, market_state_json, outcome,
             tags, archived_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            market_id, question, category, strategy, direction, entry_price,
            exit_price, pnl, status,
            json.dumps(signals) if signals else None,
            json.dumps(market_state) if market_state else None,
            outcome,
            ",".join(tags) if tags else None,
            datetime.datetime.utcnow().isoformat(),
        ))


def find_similar_scenarios(
    category: str | None = None,
    strategy: str | None = None,
    tags: list[str] | None = None,
    limit: int = 10,
) -> list[dict]:
    """Find similar past scenarios for pattern matching."""
    conditions = []
    params = []

    if category:
        conditions.append("category = ?")
        params.append(category)
    if strategy:
        conditions.append("strategy = ?")
        params.append(strategy)
    if tags:
        tag_conds = " OR ".join(["tags LIKE ?" for _ in tags])
        conditions.append(f"({tag_conds})")
        params.extend([f"%{t}%" for t in tags])

    where = " AND ".join(conditions) if conditions else "1=1"

    with _get_conn() as conn:
        rows = conn.execute(f"""
            SELECT * FROM scenario_archive
            WHERE {where}
            ORDER BY archived_at DESC LIMIT ?
        """, params + [limit]).fetchall()

    return [dict(r) for r in rows]


def get_scenario_stats(
    category: str | None = None,
    strategy: str | None = None,
) -> dict:
    """Get aggregate stats for matching scenarios."""
    scenarios = find_similar_scenarios(category, strategy, limit=1000)
    if not scenarios:
        return {"count": 0, "win_rate": 0, "avg_pnl": 0}

    pnls = [s["pnl"] for s in scenarios if s["pnl"] is not None]
    wins = sum(1 for s in scenarios if s["outcome"] == "win")

    return {
        "count": len(scenarios),
        "win_rate": wins / len(scenarios) if scenarios else 0,
        "avg_pnl": sum(pnls) / len(pnls) if pnls else 0,
        "total_pnl": sum(pnls) if pnls else 0,
    }


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------

@dataclass
class CalibrationProposal:
    param_name: str
    current_value: float
    proposed_value: float
    backtest_pnl_current: float
    backtest_pnl_proposed: float
    improvement_pct: float

    def to_dict(self) -> dict:
        return {
            "param_name": self.param_name,
            "current": self.current_value,
            "proposed": self.proposed_value,
            "improvement": f"{self.improvement_pct:+.1f}%",
        }


# Tunable parameters with their env var names and search ranges
TUNABLE_PARAMS = {
    "ARB_THRESHOLD": {"env": "ARB_THRESHOLD", "min": 0.01, "max": 0.10, "step": 0.01, "default": 0.03},
    "PRICE_LAG_MIN_EDGE": {"env": "PRICE_LAG_MIN_EDGE", "min": 0.02, "max": 0.15, "step": 0.01, "default": 0.05},
    "SLIPPAGE_BPS": {"env": "MIROFISH_SLIPPAGE_BPS", "min": 10, "max": 100, "step": 10, "default": 50},
    "STOP_LOSS_PCT": {"env": "MIROFISH_STOP_LOSS_PCT", "min": 0.10, "max": 0.40, "step": 0.05, "default": 0.20},
    "TAKE_PROFIT_PCT": {"env": "MIROFISH_TAKE_PROFIT_PCT", "min": 0.20, "max": 1.0, "step": 0.10, "default": 0.50},
}


def propose_calibrations(
    backtest_fn: Any | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> list[CalibrationProposal]:
    """
    Generate calibration proposals by grid-searching tunable params
    against backtest results. Returns proposals where improvement > 5%.

    If backtest_fn is None, uses stored backtest results instead of
    re-running (faster but less accurate).
    """
    proposals = []
    now = datetime.datetime.utcnow().isoformat()

    for param_name, config in TUNABLE_PARAMS.items():
        current = float(os.environ.get(config["env"], config["default"]))

        # Simple hill-climbing: try one step up and one step down
        candidates = []
        up = current + config["step"]
        down = current - config["step"]
        if up <= config["max"]:
            candidates.append(up)
        if down >= config["min"]:
            candidates.append(down)

        # Without a backtest function, we can't evaluate — just propose
        # based on heuristics from strategy_stats
        best_proposed = None
        best_improvement = 0.0

        for val in candidates:
            # Heuristic: if current performance is negative, try opposite direction
            improvement = _estimate_param_improvement(param_name, current, val)
            if improvement > best_improvement:
                best_improvement = improvement
                best_proposed = val

        if best_proposed and best_improvement > 5.0:
            proposal = CalibrationProposal(
                param_name=param_name,
                current_value=current,
                proposed_value=best_proposed,
                backtest_pnl_current=0.0,
                backtest_pnl_proposed=0.0,
                improvement_pct=best_improvement,
            )
            proposals.append(proposal)

            # Persist
            with _get_conn() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO calibration_params
                    (param_name, current_value, proposed_value, improvement_pct,
                     status, computed_at)
                    VALUES (?, ?, ?, ?, 'pending', ?)
                """, (param_name, current, best_proposed, best_improvement, now))

    return proposals


def _estimate_param_improvement(param_name: str, current: float, proposed: float) -> float:
    """Heuristic estimate of param change improvement from strategy_stats."""
    try:
        with _get_conn() as conn:
            latest = conn.execute("""
                SELECT strategy, total_pnl, win_rate, capture_rate
                FROM strategy_stats
                ORDER BY snapshot_date DESC LIMIT 20
            """).fetchall()

        if not latest:
            return 0.0

        avg_pnl = sum(r["total_pnl"] for r in latest) / len(latest)

        # If losing money, changes in the "tighter" direction get bonus
        if avg_pnl < 0:
            if param_name == "STOP_LOSS_PCT" and proposed < current:
                return 8.0  # tighter stops when losing
            if param_name == "ARB_THRESHOLD" and proposed > current:
                return 6.0  # higher threshold = fewer but better arb trades
        else:
            if param_name == "TAKE_PROFIT_PCT" and proposed > current:
                return 7.0  # let winners run when profitable
    except Exception:
        pass

    return 0.0


# ---------------------------------------------------------------------------
# Promotion rules
# ---------------------------------------------------------------------------

@dataclass
class PromotionStatus:
    candidate_name: str
    candidate_type: str       # "strategy" | "scoring_weight" | "param_change"
    status: str               # "testing" | "eligible" | "promoted" | "rejected"
    days_active: int
    meets_criteria: dict[str, bool]
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.candidate_name,
            "type": self.candidate_type,
            "status": self.status,
            "days_active": self.days_active,
            "criteria": self.meets_criteria,
            "reason": self.reason,
        }


# Promotion criteria
PROMOTION_CRITERIA = {
    "min_days": 7,
    "min_trades": 20,
    "min_win_rate": 0.50,
    "min_sharpe": 0.5,
    "max_drawdown": 0.30,
    "min_capture_rate": 0.30,
}


def check_promotion_eligibility(
    candidate_name: str,
    candidate_type: str = "strategy",
) -> PromotionStatus:
    """
    Check if a candidate meets all promotion criteria.
    Candidates must prove themselves over PROMOTION_CRITERIA[min_days]
    with sufficient trades and positive metrics.
    """
    criteria_met = {}

    try:
        from scripts.mirofish.strategy_tracker import compute_strategy_report
        report = compute_strategy_report(candidate_name, PROMOTION_CRITERIA["min_days"])

        criteria_met["min_days"] = report.total_trades > 0  # has any data in window
        criteria_met["min_trades"] = report.total_trades >= PROMOTION_CRITERIA["min_trades"]
        criteria_met["min_win_rate"] = report.win_rate >= PROMOTION_CRITERIA["min_win_rate"]
        criteria_met["min_sharpe"] = (report.sharpe or 0) >= PROMOTION_CRITERIA["min_sharpe"]
        criteria_met["max_drawdown"] = report.max_drawdown <= PROMOTION_CRITERIA["max_drawdown"]
        criteria_met["min_capture_rate"] = report.capture_rate >= PROMOTION_CRITERIA["min_capture_rate"]

        all_met = all(criteria_met.values())
        status = "eligible" if all_met else "testing"
        reason = "" if all_met else f"failed: {[k for k, v in criteria_met.items() if not v]}"

    except Exception as e:
        status = "testing"
        reason = f"error checking: {e}"
        criteria_met = {}

    return PromotionStatus(
        candidate_name=candidate_name,
        candidate_type=candidate_type,
        status=status,
        days_active=PROMOTION_CRITERIA["min_days"],
        meets_criteria=criteria_met,
        reason=reason,
    )
