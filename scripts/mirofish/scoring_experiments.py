#!/usr/bin/env python3
"""
Scoring-weight experiments — A/B tests different tournament scoring formulas
and tracks which produces the best capital allocation.

Phase 5E Step 2.

Experiment configs define alternative scoring functions. The system runs
the tournament with each config and compares hypothetical allocations
against realized strategy performance.

Python 3.9 compatible via __future__ annotations.
"""
from __future__ import annotations

import os
import sqlite3
import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


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
            CREATE TABLE IF NOT EXISTS scoring_experiments (
                id              INTEGER PRIMARY KEY,
                experiment_name TEXT NOT NULL,
                scoring_formula TEXT NOT NULL,
                allocations_json TEXT NOT NULL,
                hypothetical_pnl REAL,
                actual_pnl      REAL,
                delta_pnl       REAL,
                snapshot_date   TEXT NOT NULL,
                UNIQUE(experiment_name, snapshot_date)
            );
        """)


# ---------------------------------------------------------------------------
# Scoring formulas
# ---------------------------------------------------------------------------

@dataclass
class ScoringConfig:
    name: str
    description: str
    score_fn: Callable  # (sharpe, capture_rate, win_rate, roi_pct) -> float


def _score_default(sharpe, capture, win_rate, roi) -> float:
    """Default: Sharpe * capture * win_rate (original tournament formula)."""
    return max(0, sharpe or 0) * max(0, capture) * win_rate


def _score_sharpe_heavy(sharpe, capture, win_rate, roi) -> float:
    """Heavily weight Sharpe ratio."""
    return max(0, sharpe or 0) ** 2 * max(0, capture) * win_rate


def _score_roi_weighted(sharpe, capture, win_rate, roi) -> float:
    """Include ROI in the scoring."""
    return max(0, sharpe or 0) * max(0, capture) * win_rate * max(0, 1 + roi / 100)


def _score_capture_focus(sharpe, capture, win_rate, roi) -> float:
    """Focus on edge capture rate above all else."""
    return max(0, capture) ** 2 * win_rate * (1 + max(0, sharpe or 0))


def _score_conservative(sharpe, capture, win_rate, roi) -> float:
    """Penalize drawdown risk via Sharpe floor."""
    s = max(0, sharpe or 0)
    if s < 0.5:
        s *= 0.1  # heavily penalize low Sharpe
    return s * max(0, capture) * win_rate


EXPERIMENT_CONFIGS = [
    ScoringConfig("default", "Sharpe * capture * win_rate", _score_default),
    ScoringConfig("sharpe_heavy", "Sharpe^2 * capture * win_rate", _score_sharpe_heavy),
    ScoringConfig("roi_weighted", "Sharpe * capture * WR * (1+ROI)", _score_roi_weighted),
    ScoringConfig("capture_focus", "capture^2 * WR * (1+Sharpe)", _score_capture_focus),
    ScoringConfig("conservative", "Sharpe-floor * capture * WR", _score_conservative),
]


# ---------------------------------------------------------------------------
# Experiment runner
# ---------------------------------------------------------------------------

@dataclass
class ExperimentResult:
    name: str
    allocations: dict[str, float]
    hypothetical_pnl: float
    formula: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "allocations": self.allocations,
            "hypothetical_pnl": self.hypothetical_pnl,
            "formula": self.formula,
        }


def run_experiments(
    window_days: int = 14,
    min_trades: int = 5,
) -> list[ExperimentResult]:
    """
    Run all scoring experiments against current strategy data.
    Returns allocation results for each scoring formula.
    """
    from scripts.mirofish.strategy_tracker import compute_all_reports, ALL_STRATEGIES

    reports = compute_all_reports(window_days)
    results = []

    for config in EXPERIMENT_CONFIGS:
        scores: dict[str, float] = {}
        explore: list[str] = []

        for r in reports:
            if r.total_trades < min_trades:
                explore.append(r.strategy)
                scores[r.strategy] = 0.0
                continue
            scores[r.strategy] = config.score_fn(
                r.sharpe, r.capture_rate, r.win_rate, r.roi_pct,
            )

        total = sum(scores.values())
        explore_total = 0.05 * len(explore)
        exploit_budget = max(0, 1.0 - explore_total)

        allocs: dict[str, float] = {}
        for s in ALL_STRATEGIES:
            if s in explore:
                allocs[s] = 0.05
            elif total > 0:
                allocs[s] = (scores.get(s, 0) / total) * exploit_budget
            else:
                allocs[s] = 0.0

        # Normalize
        total_alloc = sum(allocs.values())
        if total_alloc > 0:
            allocs = {k: v / total_alloc for k, v in allocs.items()}

        # Compute hypothetical PnL: sum(allocation * strategy_pnl)
        hypo_pnl = sum(
            allocs.get(r.strategy, 0) * r.total_pnl
            for r in reports if r.total_trades > 0
        )

        results.append(ExperimentResult(
            name=config.name,
            allocations=allocs,
            hypothetical_pnl=hypo_pnl,
            formula=config.description,
        ))

    return results


def snapshot_experiments(window_days: int = 14) -> None:
    """Persist experiment results to DB."""
    import json
    results = run_experiments(window_days)
    today = datetime.date.today().isoformat()

    with _get_conn() as conn:
        for r in results:
            conn.execute("""
                INSERT OR REPLACE INTO scoring_experiments
                (experiment_name, scoring_formula, allocations_json,
                 hypothetical_pnl, snapshot_date)
                VALUES (?, ?, ?, ?, ?)
            """, (
                r.name, r.formula, json.dumps(r.allocations),
                r.hypothetical_pnl, today,
            ))


def get_best_experiment(days: int = 7) -> str | None:
    """Return the experiment name with the highest hypothetical PnL over recent snapshots."""
    cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    with _get_conn() as conn:
        row = conn.execute("""
            SELECT experiment_name, SUM(hypothetical_pnl) as total
            FROM scoring_experiments
            WHERE snapshot_date > ?
            GROUP BY experiment_name
            ORDER BY total DESC LIMIT 1
        """, (cutoff,)).fetchone()
    return row["experiment_name"] if row else None
