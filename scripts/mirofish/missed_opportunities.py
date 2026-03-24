#!/usr/bin/env python3
"""
Missed opportunity tracker — records signals that were generated but not
acted on (rejected by Kelly, cap, data-quality, or audit), then measures
counterfactual PnL. Feeds into tournament scoring.

Phase 5C Step 3.

Python 3.9 compatible via __future__ annotations.
"""
from __future__ import annotations

import json
import os
import sqlite3
import datetime
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean


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
            CREATE TABLE IF NOT EXISTS missed_opportunities (
                id              INTEGER PRIMARY KEY,
                market_id       TEXT NOT NULL,
                direction       TEXT NOT NULL,
                strategy        TEXT NOT NULL,
                entry_price     REAL NOT NULL,
                expected_edge   REAL NOT NULL,
                amount_usd      REAL NOT NULL,
                reject_reason   TEXT NOT NULL,
                counterfactual_exit REAL,
                counterfactual_pnl  REAL,
                status          TEXT NOT NULL DEFAULT 'pending',
                detected_at     TEXT NOT NULL,
                resolved_at     TEXT,
                metadata_json   TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_missed_opp_strategy
                ON missed_opportunities(strategy, detected_at);
            CREATE INDEX IF NOT EXISTS idx_missed_opp_market
                ON missed_opportunities(market_id);
        """)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class MissedOppSummary:
    strategy: str
    total_missed: int
    total_counterfactual_pnl: float
    avg_counterfactual_pnl: float
    would_have_won: int
    would_have_lost: int
    opportunity_cost: float        # positive = we missed profit

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "total_missed": self.total_missed,
            "total_counterfactual_pnl": self.total_counterfactual_pnl,
            "avg_counterfactual_pnl": self.avg_counterfactual_pnl,
            "would_have_won": self.would_have_won,
            "would_have_lost": self.would_have_lost,
            "opportunity_cost": self.opportunity_cost,
        }


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------

def record_missed(
    market_id: str,
    direction: str,
    strategy: str,
    entry_price: float,
    expected_edge: float,
    amount_usd: float,
    reject_reason: str,
    metadata: dict | None = None,
) -> None:
    """Record a trade that was generated but rejected."""
    with _get_conn() as conn:
        conn.execute("""
            INSERT INTO missed_opportunities
            (market_id, direction, strategy, entry_price, expected_edge,
             amount_usd, reject_reason, detected_at, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            market_id, direction, strategy, entry_price, expected_edge,
            amount_usd, reject_reason,
            datetime.datetime.utcnow().isoformat(),
            json.dumps(metadata) if metadata else None,
        ))


def resolve_missed_opportunities() -> int:
    """
    Check pending missed opportunities against current market prices
    to compute counterfactual PnL. Returns count resolved.
    """
    resolved = 0
    with _get_conn() as conn:
        pending = conn.execute("""
            SELECT mo.id, mo.market_id, mo.direction, mo.entry_price, mo.amount_usd
            FROM missed_opportunities mo
            WHERE mo.status = 'pending'
        """).fetchall()

        for row in pending:
            # Get latest price
            price_row = conn.execute("""
                SELECT yes_price, no_price FROM market_data
                WHERE market_id = ?
                ORDER BY fetched_at DESC LIMIT 1
            """, (row["market_id"],)).fetchone()

            if not price_row:
                continue

            if row["direction"] == "YES":
                current = price_row["yes_price"]
            else:
                current = price_row["no_price"]

            if current is None:
                continue

            shares = row["amount_usd"] / row["entry_price"] if row["entry_price"] > 0 else 0
            counterfactual_pnl = shares * (current - row["entry_price"])

            conn.execute("""
                UPDATE missed_opportunities
                SET counterfactual_exit = ?, counterfactual_pnl = ?,
                    status = 'resolved', resolved_at = ?
                WHERE id = ?
            """, (
                current, counterfactual_pnl,
                datetime.datetime.utcnow().isoformat(),
                row["id"],
            ))
            resolved += 1

    return resolved


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def get_summary(
    strategy: str | None = None,
    days: int = 14,
) -> list[MissedOppSummary]:
    """Get missed opportunity summary per strategy."""
    cutoff = (datetime.datetime.utcnow() -
              datetime.timedelta(days=days)).isoformat()

    with _get_conn() as conn:
        if strategy:
            rows = conn.execute("""
                SELECT * FROM missed_opportunities
                WHERE strategy = ? AND detected_at > ? AND status = 'resolved'
            """, (strategy, cutoff)).fetchall()
            strategies = [strategy]
        else:
            rows = conn.execute("""
                SELECT * FROM missed_opportunities
                WHERE detected_at > ? AND status = 'resolved'
            """, (cutoff,)).fetchall()
            strategies = list(set(r["strategy"] for r in rows))

    summaries = []
    for strat in strategies:
        strat_rows = [r for r in rows if r["strategy"] == strat]
        if not strat_rows:
            continue

        pnls = [r["counterfactual_pnl"] for r in strat_rows
                if r["counterfactual_pnl"] is not None]
        wins = sum(1 for p in pnls if p > 0)
        losses = len(pnls) - wins
        total_pnl = sum(pnls)
        opportunity_cost = max(0, total_pnl)  # only count missed profit

        summaries.append(MissedOppSummary(
            strategy=strat,
            total_missed=len(strat_rows),
            total_counterfactual_pnl=total_pnl,
            avg_counterfactual_pnl=mean(pnls) if pnls else 0.0,
            would_have_won=wins,
            would_have_lost=losses,
            opportunity_cost=opportunity_cost,
        ))

    return summaries
