#!/usr/bin/env python3
"""
Strategy performance tracker — tracks expected vs realized PnL per strategy,
computes edge capture rates, and provides the data foundation for the
strategy tournament / capital allocator.

Tables:
    strategy_performance — per-trade expected vs realized tracking
    strategy_stats       — rolling aggregate stats per strategy (daily snapshots)

Python 3.9 compatible via __future__ annotations.
"""
from __future__ import annotations

import os
import sqlite3
import datetime
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean, stdev
from typing import Any


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ROLLING_WINDOW_DAYS = int(os.environ.get("MIROFISH_ROLLING_WINDOW", "7"))
MIN_TRADES_FOR_STATS = int(os.environ.get("MIROFISH_MIN_TRADES_STATS", "5"))

ALL_STRATEGIES = [
    "arbitrage",
    "cross_venue_arb",
    "price_lag_arb",
    "momentum",
    "contrarian",
    "news_catalyst",
    "manual",
]


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _get_conn() -> sqlite3.Connection:
    db_path = Path(os.environ.get("CLAWMSON_DB_PATH",
                                   Path.home() / ".openclaw" / "clawmson.db"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def migrate() -> None:
    """Create strategy tracking tables. Idempotent."""
    with _get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS strategy_performance (
                id              INTEGER PRIMARY KEY,
                trade_id        INTEGER NOT NULL,
                strategy        TEXT NOT NULL,
                market_id       TEXT NOT NULL,
                direction       TEXT NOT NULL,
                entry_price     REAL NOT NULL,
                exit_price      REAL,
                expected_edge   REAL NOT NULL,
                realized_pnl    REAL,
                amount_usd      REAL NOT NULL,
                confidence      REAL NOT NULL,
                status          TEXT NOT NULL DEFAULT 'open',
                opened_at       TEXT NOT NULL,
                closed_at       TEXT,
                metadata_json   TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_strat_perf_strategy
                ON strategy_performance(strategy, opened_at);
            CREATE INDEX IF NOT EXISTS idx_strat_perf_trade
                ON strategy_performance(trade_id);

            CREATE TABLE IF NOT EXISTS strategy_stats (
                id              INTEGER PRIMARY KEY,
                strategy        TEXT NOT NULL,
                snapshot_date   TEXT NOT NULL,
                total_trades    INTEGER NOT NULL DEFAULT 0,
                wins            INTEGER NOT NULL DEFAULT 0,
                losses          INTEGER NOT NULL DEFAULT 0,
                win_rate        REAL,
                avg_expected_edge REAL,
                avg_realized_pnl REAL,
                capture_rate    REAL,
                total_pnl       REAL NOT NULL DEFAULT 0,
                sharpe          REAL,
                max_drawdown    REAL,
                roi_pct         REAL,
                allocation_pct  REAL,
                UNIQUE(strategy, snapshot_date)
            );
            CREATE INDEX IF NOT EXISTS idx_strat_stats_date
                ON strategy_stats(snapshot_date, strategy);
        """)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class StrategyReport:
    strategy: str
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    avg_expected_edge: float
    avg_realized_pnl: float
    capture_rate: float          # realized / expected (1.0 = perfect capture)
    total_pnl: float
    sharpe: float | None
    max_drawdown: float
    roi_pct: float
    allocation_pct: float = 0.0  # set by tournament

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "total_trades": self.total_trades,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": self.win_rate,
            "avg_expected_edge": self.avg_expected_edge,
            "avg_realized_pnl": self.avg_realized_pnl,
            "capture_rate": self.capture_rate,
            "total_pnl": self.total_pnl,
            "sharpe": self.sharpe,
            "max_drawdown": self.max_drawdown,
            "roi_pct": self.roi_pct,
            "allocation_pct": self.allocation_pct,
        }


# ---------------------------------------------------------------------------
# Recording trades
# ---------------------------------------------------------------------------

def record_trade_open(
    trade_id: int,
    strategy: str,
    market_id: str,
    direction: str,
    entry_price: float,
    expected_edge: float,
    amount_usd: float,
    confidence: float,
    metadata: dict | None = None,
) -> None:
    """Record a trade opening for strategy tracking."""
    import json
    with _get_conn() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO strategy_performance
            (trade_id, strategy, market_id, direction, entry_price,
             expected_edge, amount_usd, confidence, status, opened_at, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)
        """, (
            trade_id, strategy, market_id, direction, entry_price,
            expected_edge, amount_usd, confidence,
            datetime.datetime.utcnow().isoformat(),
            json.dumps(metadata) if metadata else None,
        ))


def record_trade_close(
    trade_id: int,
    exit_price: float,
    realized_pnl: float,
    status: str,
) -> None:
    """Record a trade closure with realized PnL."""
    with _get_conn() as conn:
        conn.execute("""
            UPDATE strategy_performance
            SET exit_price = ?, realized_pnl = ?, status = ?, closed_at = ?
            WHERE trade_id = ?
        """, (
            exit_price, realized_pnl, status,
            datetime.datetime.utcnow().isoformat(),
            trade_id,
        ))


def sync_from_paper_trades() -> int:
    """
    Backfill strategy_performance from paper_trades for any trades
    not yet tracked. Returns count of newly synced trades.
    """
    with _get_conn() as conn:
        # Find paper_trades not yet in strategy_performance
        rows = conn.execute("""
            SELECT pt.id, pt.strategy, pt.market_id, pt.direction,
                   pt.entry_price, pt.exit_price, pt.amount_usd,
                   pt.confidence, pt.pnl, pt.status, pt.opened_at, pt.closed_at
            FROM paper_trades pt
            LEFT JOIN strategy_performance sp ON sp.trade_id = pt.id
            WHERE sp.id IS NULL
        """).fetchall()

    synced = 0
    for r in rows:
        # Estimate expected edge from confidence
        # For arb strategies, confidence IS the edge
        # For LLM strategies, expected_edge ≈ confidence * (1/entry_price - 1)
        strategy = r["strategy"]
        confidence = r["confidence"] or 0.5
        entry_price = r["entry_price"] or 0.5

        if strategy in ("arbitrage", "cross_venue_arb", "price_lag_arb"):
            expected_edge = confidence  # confidence = edge for arb strategies
        else:
            # For LLM strategies: expected profit per dollar
            payout_ratio = (1.0 / entry_price) - 1.0 if entry_price > 0 and entry_price < 1 else 0
            expected_edge = confidence * payout_ratio - (1 - confidence)

        record_trade_open(
            trade_id=r["id"],
            strategy=strategy,
            market_id=r["market_id"],
            direction=r["direction"],
            entry_price=entry_price,
            expected_edge=expected_edge,
            amount_usd=r["amount_usd"],
            confidence=confidence,
        )

        if r["status"] != "open" and r["pnl"] is not None:
            record_trade_close(
                trade_id=r["id"],
                exit_price=r["exit_price"] or entry_price,
                realized_pnl=r["pnl"],
                status=r["status"],
            )
        synced += 1

    return synced


# ---------------------------------------------------------------------------
# Computing strategy stats
# ---------------------------------------------------------------------------

def compute_strategy_report(
    strategy: str,
    window_days: int = ROLLING_WINDOW_DAYS,
) -> StrategyReport:
    """Compute performance stats for a single strategy over the rolling window."""
    cutoff = (datetime.datetime.utcnow() -
              datetime.timedelta(days=window_days)).isoformat()

    with _get_conn() as conn:
        rows = conn.execute("""
            SELECT * FROM strategy_performance
            WHERE strategy = ? AND opened_at > ?
            ORDER BY opened_at ASC
        """, (strategy, cutoff)).fetchall()

    if not rows:
        return StrategyReport(
            strategy=strategy, total_trades=0, wins=0, losses=0,
            win_rate=0.0, avg_expected_edge=0.0, avg_realized_pnl=0.0,
            capture_rate=0.0, total_pnl=0.0, sharpe=None,
            max_drawdown=0.0, roi_pct=0.0,
        )

    closed = [r for r in rows if r["status"] != "open"]
    total = len(closed)
    wins = sum(1 for r in closed if (r["realized_pnl"] or 0) > 0)
    losses = total - wins
    win_rate = wins / total if total > 0 else 0.0

    expected_edges = [r["expected_edge"] for r in closed if r["expected_edge"] is not None]
    realized_pnls = [r["realized_pnl"] for r in closed if r["realized_pnl"] is not None]

    avg_expected = mean(expected_edges) if expected_edges else 0.0
    avg_realized = mean(realized_pnls) if realized_pnls else 0.0
    total_pnl = sum(realized_pnls) if realized_pnls else 0.0

    # Capture rate: how much of expected edge we actually capture
    total_expected_pnl = sum(
        r["expected_edge"] * r["amount_usd"]
        for r in closed
        if r["expected_edge"] is not None
    )
    capture_rate = total_pnl / total_expected_pnl if total_expected_pnl > 0 else 0.0

    # Sharpe: mean/stdev of per-trade PnL normalized by amount
    returns = []
    for r in closed:
        if r["realized_pnl"] is not None and r["amount_usd"] > 0:
            returns.append(r["realized_pnl"] / r["amount_usd"])

    sharpe = None
    if len(returns) >= MIN_TRADES_FOR_STATS:
        s = stdev(returns) if len(returns) > 1 else 0
        if s > 0:
            sharpe = mean(returns) / s

    # Max drawdown over cumulative PnL
    cum_pnl = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in closed:
        cum_pnl += r["realized_pnl"] or 0
        peak = max(peak, cum_pnl)
        dd = (peak - cum_pnl) / peak if peak > 0 else 0.0
        max_dd = max(max_dd, dd)

    # ROI
    total_invested = sum(r["amount_usd"] for r in closed)
    roi_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0.0

    return StrategyReport(
        strategy=strategy,
        total_trades=total,
        wins=wins,
        losses=losses,
        win_rate=win_rate,
        avg_expected_edge=avg_expected,
        avg_realized_pnl=avg_realized,
        capture_rate=capture_rate,
        total_pnl=total_pnl,
        sharpe=sharpe,
        max_drawdown=max_dd,
        roi_pct=roi_pct,
    )


def compute_all_reports(
    window_days: int = ROLLING_WINDOW_DAYS,
) -> list[StrategyReport]:
    """Compute performance reports for all strategies."""
    return [compute_strategy_report(s, window_days) for s in ALL_STRATEGIES]


def snapshot_stats(window_days: int = ROLLING_WINDOW_DAYS) -> None:
    """Write daily strategy stats snapshot to DB."""
    today = datetime.date.today().isoformat()
    reports = compute_all_reports(window_days)

    with _get_conn() as conn:
        for r in reports:
            if r.total_trades == 0:
                continue
            conn.execute("""
                INSERT OR REPLACE INTO strategy_stats
                (strategy, snapshot_date, total_trades, wins, losses, win_rate,
                 avg_expected_edge, avg_realized_pnl, capture_rate, total_pnl,
                 sharpe, max_drawdown, roi_pct, allocation_pct)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r.strategy, today, r.total_trades, r.wins, r.losses,
                r.win_rate, r.avg_expected_edge, r.avg_realized_pnl,
                r.capture_rate, r.total_pnl, r.sharpe, r.max_drawdown,
                r.roi_pct, r.allocation_pct,
            ))


# ---------------------------------------------------------------------------
# Strategy tournament / capital allocator
# ---------------------------------------------------------------------------

def run_tournament(
    window_days: int = ROLLING_WINDOW_DAYS,
    min_trades: int = MIN_TRADES_FOR_STATS,
) -> list[StrategyReport]:
    """
    Compete strategies and allocate capital proportional to
    Sharpe-weighted edge capture rate.

    Allocation formula per strategy:
        score = max(0, sharpe) * max(0, capture_rate) * win_rate
        allocation = score / sum(all_scores)

    Strategies with < min_trades get a minimum 5% exploration allocation.
    """
    reports = compute_all_reports(window_days)
    active = [r for r in reports if r.total_trades > 0]

    if not active:
        # Equal allocation across all strategies
        for r in reports:
            r.allocation_pct = 1.0 / len(reports) if reports else 0
        return reports

    # Compute scores
    scores: dict[str, float] = {}
    explore_strategies: list[str] = []

    for r in active:
        if r.total_trades < min_trades:
            # Not enough data — give exploration allocation
            explore_strategies.append(r.strategy)
            scores[r.strategy] = 0.0
            continue

        sharpe = max(0.0, r.sharpe or 0.0)
        capture = max(0.0, r.capture_rate)
        score = sharpe * capture * r.win_rate
        scores[r.strategy] = score

    total_score = sum(scores.values())

    # Exploration budget: 5% per under-sampled strategy
    explore_total = 0.05 * len(explore_strategies)
    exploit_budget = max(0.0, 1.0 - explore_total)

    for r in reports:
        if r.strategy in explore_strategies:
            r.allocation_pct = 0.05
        elif r.total_trades > 0 and total_score > 0:
            r.allocation_pct = (scores.get(r.strategy, 0) / total_score) * exploit_budget
        else:
            r.allocation_pct = 0.0

    # Normalize to sum to 1.0
    total_alloc = sum(r.allocation_pct for r in reports)
    if total_alloc > 0:
        for r in reports:
            r.allocation_pct /= total_alloc

    return reports


def get_strategy_allocation() -> dict[str, float]:
    """
    Return {strategy: allocation_pct} from the latest tournament.
    Used by trading_brain to dynamically size positions.
    """
    reports = run_tournament()
    return {r.strategy: r.allocation_pct for r in reports}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Mirofish strategy tracker")
    parser.add_argument("--migrate", action="store_true", help="Create tracking tables")
    parser.add_argument("--sync", action="store_true", help="Sync from paper_trades")
    parser.add_argument("--report", action="store_true", help="Print strategy reports")
    parser.add_argument("--tournament", action="store_true", help="Run tournament + allocation")
    parser.add_argument("--snapshot", action="store_true", help="Write daily stats snapshot")
    parser.add_argument("--window", type=int, default=ROLLING_WINDOW_DAYS, help="Rolling window days")
    args = parser.parse_args()

    if args.migrate:
        migrate()
        print("[strategy_tracker] Tables created")
    elif args.sync:
        n = sync_from_paper_trades()
        print(f"[strategy_tracker] Synced {n} trades")
    elif args.report:
        reports = compute_all_reports(args.window)
        for r in reports:
            if r.total_trades > 0:
                print(f"\n{r.strategy}:")
                print(f"  trades: {r.total_trades} (W:{r.wins} L:{r.losses})")
                print(f"  win_rate: {r.win_rate:.1%}")
                print(f"  avg_edge: {r.avg_expected_edge:.4f} expected, {r.avg_realized_pnl:.4f} realized")
                print(f"  capture: {r.capture_rate:.1%}")
                print(f"  PnL: ${r.total_pnl:.2f} | ROI: {r.roi_pct:.1f}%")
                print(f"  sharpe: {r.sharpe:.3f}" if r.sharpe else "  sharpe: n/a")
                print(f"  max_dd: {r.max_drawdown:.1%}")
    elif args.tournament:
        reports = run_tournament(args.window)
        print("\nStrategy Tournament Results:")
        print("-" * 60)
        for r in sorted(reports, key=lambda x: x.allocation_pct, reverse=True):
            if r.total_trades > 0 or r.allocation_pct > 0:
                print(f"  {r.strategy:20s} → {r.allocation_pct:6.1%} "
                      f"(trades={r.total_trades}, capture={r.capture_rate:.0%}, "
                      f"sharpe={r.sharpe:.2f})" if r.sharpe else
                      f"  {r.strategy:20s} → {r.allocation_pct:6.1%} "
                      f"(trades={r.total_trades}, exploring)")
    elif args.snapshot:
        snapshot_stats(args.window)
        print("[strategy_tracker] Daily snapshot written")
    else:
        parser.print_help()
