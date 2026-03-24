#!/usr/bin/env python3
"""
Edge persistence / lifetime tracker — measures how long edges persist
before decaying, tracks signal-to-fill latency, and computes half-life
per strategy. Informs trade urgency and tournament scoring.

Phase 5C Step 4.

Python 3.9 compatible via __future__ annotations.
"""
from __future__ import annotations

import math
import os
import sqlite3
import datetime
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean, median


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
            CREATE TABLE IF NOT EXISTS edge_observations (
                id              INTEGER PRIMARY KEY,
                market_id       TEXT NOT NULL,
                strategy        TEXT NOT NULL,
                initial_edge    REAL NOT NULL,
                observed_edge   REAL,
                elapsed_min     REAL NOT NULL,
                decay_pct       REAL,
                observed_at     TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_edge_obs_strategy
                ON edge_observations(strategy, observed_at);

            CREATE TABLE IF NOT EXISTS edge_halflife (
                id              INTEGER PRIMARY KEY,
                strategy        TEXT NOT NULL UNIQUE,
                halflife_min    REAL NOT NULL,
                sample_count    INTEGER NOT NULL,
                computed_at     TEXT NOT NULL
            );
        """)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class EdgeLifetime:
    strategy: str
    halflife_min: float          # minutes until edge decays to 50%
    avg_initial_edge: float
    avg_decay_rate: float        # edge lost per minute
    median_lifetime_min: float   # median time until edge < 1%
    sample_count: int
    urgency: str                 # "high" (<30min), "medium" (30-120), "low" (>120)

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "halflife_min": self.halflife_min,
            "avg_initial_edge": self.avg_initial_edge,
            "avg_decay_rate": self.avg_decay_rate,
            "median_lifetime_min": self.median_lifetime_min,
            "sample_count": self.sample_count,
            "urgency": self.urgency,
        }


# ---------------------------------------------------------------------------
# Recording observations
# ---------------------------------------------------------------------------

def record_edge_observation(
    market_id: str,
    strategy: str,
    initial_edge: float,
    observed_edge: float,
    elapsed_min: float,
) -> None:
    """Record a point-in-time edge observation for decay analysis."""
    decay_pct = 1.0 - (observed_edge / initial_edge) if initial_edge > 0 else 1.0
    with _get_conn() as conn:
        conn.execute("""
            INSERT INTO edge_observations
            (market_id, strategy, initial_edge, observed_edge, elapsed_min,
             decay_pct, observed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            market_id, strategy, initial_edge, observed_edge,
            elapsed_min, decay_pct,
            datetime.datetime.utcnow().isoformat(),
        ))


def compute_from_trades() -> int:
    """
    Infer edge decay from closed paper_trades by comparing expected_edge
    (at open) vs realized PnL ratio (at close).
    Returns count of observations generated.
    """
    count = 0
    with _get_conn() as conn:
        # Get closed trades with strategy_performance data
        rows = conn.execute("""
            SELECT sp.market_id, sp.strategy, sp.expected_edge,
                   sp.realized_pnl, sp.amount_usd, sp.opened_at, sp.closed_at
            FROM strategy_performance sp
            WHERE sp.status != 'open'
              AND sp.expected_edge > 0
              AND sp.realized_pnl IS NOT NULL
              AND sp.opened_at IS NOT NULL
              AND sp.closed_at IS NOT NULL
        """).fetchall()

    for r in rows:
        try:
            opened = datetime.datetime.fromisoformat(r["opened_at"])
            closed = datetime.datetime.fromisoformat(r["closed_at"])
            elapsed = (closed - opened).total_seconds() / 60.0

            if elapsed <= 0:
                continue

            # Realized edge = PnL / amount
            realized_edge = r["realized_pnl"] / r["amount_usd"] if r["amount_usd"] > 0 else 0

            record_edge_observation(
                market_id=r["market_id"],
                strategy=r["strategy"],
                initial_edge=r["expected_edge"],
                observed_edge=max(0, realized_edge),
                elapsed_min=elapsed,
            )
            count += 1
        except (ValueError, TypeError):
            pass

    return count


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def compute_halflife(strategy: str) -> EdgeLifetime | None:
    """
    Compute edge half-life for a strategy using exponential decay model.
    half-life = -elapsed / log2(1 - decay_pct) averaged over observations.
    """
    with _get_conn() as conn:
        rows = conn.execute("""
            SELECT initial_edge, observed_edge, elapsed_min, decay_pct
            FROM edge_observations
            WHERE strategy = ? AND initial_edge > 0 AND elapsed_min > 0
            ORDER BY observed_at DESC LIMIT 100
        """, (strategy,)).fetchall()

    if not rows or len(rows) < 3:
        return None

    initial_edges = [r["initial_edge"] for r in rows]
    decay_rates = []
    half_lives = []
    lifetimes = []

    for r in rows:
        if r["decay_pct"] is None or r["elapsed_min"] <= 0:
            continue

        decay = max(0.001, min(0.999, r["decay_pct"]))
        # Exponential decay: edge(t) = edge(0) * exp(-λt)
        # λ = -ln(1-decay) / t
        lam = -math.log(1.0 - decay) / r["elapsed_min"]
        if lam > 0:
            hl = math.log(2) / lam  # half-life in minutes
            half_lives.append(hl)
            decay_rates.append(r["initial_edge"] * lam)

            # Lifetime: time until edge < 1% of initial
            lifetime = -math.log(0.01) / lam
            lifetimes.append(lifetime)

    if not half_lives:
        return None

    avg_hl = mean(half_lives)
    urgency = "high" if avg_hl < 30 else ("medium" if avg_hl < 120 else "low")

    result = EdgeLifetime(
        strategy=strategy,
        halflife_min=avg_hl,
        avg_initial_edge=mean(initial_edges),
        avg_decay_rate=mean(decay_rates) if decay_rates else 0.0,
        median_lifetime_min=median(lifetimes) if lifetimes else avg_hl * 5,
        sample_count=len(rows),
        urgency=urgency,
    )

    # Persist
    with _get_conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO edge_halflife
            (strategy, halflife_min, sample_count, computed_at)
            VALUES (?, ?, ?, ?)
        """, (strategy, avg_hl, len(rows), datetime.datetime.utcnow().isoformat()))

    return result


def compute_all_halflives() -> list[EdgeLifetime]:
    """Compute half-lives for all strategies with data."""
    from scripts.mirofish.strategy_tracker import ALL_STRATEGIES
    results = []
    for s in ALL_STRATEGIES:
        hl = compute_halflife(s)
        if hl:
            results.append(hl)
    return results


def get_urgency(strategy: str) -> str:
    """Quick lookup: how urgent is execution for this strategy?"""
    try:
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT halflife_min FROM edge_halflife WHERE strategy = ?",
                (strategy,),
            ).fetchone()
        if row:
            hl = row["halflife_min"]
            return "high" if hl < 30 else ("medium" if hl < 120 else "low")
    except Exception:
        pass
    return "medium"  # default
