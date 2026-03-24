#!/usr/bin/env python3
"""
Mirofish backtester — replays historical market data through trading strategies
with simulated execution. Produces per-strategy P&L curves, drawdowns, Sharpe.

Data source: SQLite market_data table (historical snapshots from polymarket_feed).
Execution: uses paper_wallet's _simulate_execution for realistic fills.

CLI:
    python3 -m scripts.mirofish.backtester --from 2026-03-01 --to 2026-03-23
    python3 -m scripts.mirofish.backtester --from 2026-03-01 --strategies arb,price_lag
    python3 -m scripts.mirofish.backtester --from 2026-03-01 --report json

Python 3.9 compatible via __future__ annotations.
"""
from __future__ import annotations

import json
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

STARTING_BALANCE = float(os.environ.get("BACKTEST_STARTING_BALANCE", "1000.0"))
MAX_POSITION_PCT = float(os.environ.get("MIROFISH_MAX_POSITION_PCT", "0.10"))
STOP_LOSS_PCT = float(os.environ.get("MIROFISH_STOP_LOSS_PCT", "0.20"))
TAKE_PROFIT_PCT = float(os.environ.get("MIROFISH_TAKE_PROFIT_PCT", "0.50"))
SLIPPAGE_BPS = float(os.environ.get("BACKTEST_SLIPPAGE_BPS", "50"))
ARB_THRESHOLD = 0.03
PRICE_LAG_MIN_EDGE = float(os.environ.get("PRICE_LAG_MIN_EDGE", "0.05"))

ALL_STRATEGIES = ["arbitrage", "price_lag_arb", "momentum", "contrarian", "news_catalyst"]


# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------

def _get_conn() -> sqlite3.Connection:
    db_path = Path(os.environ.get("CLAWMSON_DB_PATH",
                                   Path.home() / ".openclaw" / "clawmson.db"))
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class BacktestTrade:
    trade_id: int
    market_id: str
    question: str
    direction: str
    strategy: str
    entry_price: float
    exit_price: float | None = None
    amount_usd: float = 0.0
    shares: float = 0.0
    pnl: float = 0.0
    status: str = "open"
    opened_at: str = ""
    closed_at: str = ""
    expected_edge: float = 0.0

    def to_dict(self) -> dict:
        return {
            "trade_id": self.trade_id,
            "market_id": self.market_id,
            "direction": self.direction,
            "strategy": self.strategy,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "amount_usd": self.amount_usd,
            "pnl": self.pnl,
            "status": self.status,
        }


@dataclass
class DailySnapshot:
    date: str
    balance: float
    open_positions: int
    realized_pnl: float
    unrealized_pnl: float
    trades_opened: int
    trades_closed: int


@dataclass
class StrategyResult:
    strategy: str
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    total_pnl: float
    roi_pct: float
    sharpe: float | None
    max_drawdown: float
    avg_trade_pnl: float
    best_trade: float
    worst_trade: float
    daily_snapshots: list[DailySnapshot] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "total_trades": self.total_trades,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": self.win_rate,
            "total_pnl": self.total_pnl,
            "roi_pct": self.roi_pct,
            "sharpe": self.sharpe,
            "max_drawdown": self.max_drawdown,
            "avg_trade_pnl": self.avg_trade_pnl,
            "best_trade": self.best_trade,
            "worst_trade": self.worst_trade,
        }


@dataclass
class BacktestResult:
    from_date: str
    to_date: str
    starting_balance: float
    ending_balance: float
    total_return_pct: float
    strategy_results: list[StrategyResult]
    all_trades: list[BacktestTrade]
    daily_snapshots: list[DailySnapshot]

    def to_dict(self) -> dict:
        return {
            "from_date": self.from_date,
            "to_date": self.to_date,
            "starting_balance": self.starting_balance,
            "ending_balance": self.ending_balance,
            "total_return_pct": self.total_return_pct,
            "strategies": [s.to_dict() for s in self.strategy_results],
            "total_trades": len(self.all_trades),
        }


# ---------------------------------------------------------------------------
# Historical data loader
# ---------------------------------------------------------------------------

def load_historical_snapshots(
    from_date: str,
    to_date: str,
) -> dict[str, list[dict]]:
    """
    Load market_data snapshots grouped by date (fetched_at date).
    Returns {date_str: [market_dicts]}.
    """
    with _get_conn() as conn:
        rows = conn.execute("""
            SELECT market_id, question, category, yes_price, no_price,
                   volume, end_date, fetched_at
            FROM market_data
            WHERE DATE(fetched_at) >= ? AND DATE(fetched_at) <= ?
            ORDER BY fetched_at ASC
        """, (from_date, to_date)).fetchall()

    # Group by date
    by_date: dict[str, list[dict]] = {}
    for r in rows:
        date_key = r["fetched_at"][:10]  # YYYY-MM-DD
        if date_key not in by_date:
            by_date[date_key] = []
        by_date[date_key].append(dict(r))

    # Deduplicate: keep latest snapshot per market per date
    for date_key in by_date:
        markets = by_date[date_key]
        latest: dict[str, dict] = {}
        for m in markets:
            mid = m["market_id"]
            if mid not in latest or m["fetched_at"] > latest[mid]["fetched_at"]:
                latest[mid] = m
        by_date[date_key] = list(latest.values())

    return by_date


def load_spot_prices(from_date: str, to_date: str) -> dict[str, dict[str, float]]:
    """
    Load historical spot prices grouped by date.
    Returns {date_str: {asset: price}}.
    """
    with _get_conn() as conn:
        rows = conn.execute("""
            SELECT ticker, amount_usd, fetched_at
            FROM spot_prices
            WHERE DATE(fetched_at) >= ? AND DATE(fetched_at) <= ?
            ORDER BY fetched_at ASC
        """, (from_date, to_date)).fetchall()

    by_date: dict[str, dict[str, float]] = {}
    for r in rows:
        date_key = r["fetched_at"][:10]
        if date_key not in by_date:
            by_date[date_key] = {}
        if r["amount_usd"] and r["amount_usd"] > 0:
            by_date[date_key][r["ticker"]] = r["amount_usd"]

    return by_date


# ---------------------------------------------------------------------------
# Simulated wallet for backtesting
# ---------------------------------------------------------------------------

class SimWallet:
    """Lightweight in-memory wallet for backtesting (no DB writes)."""

    def __init__(self, starting_balance: float = STARTING_BALANCE):
        self.starting_balance = starting_balance
        self.balance = starting_balance
        self.trades: list[BacktestTrade] = []
        self.open_trades: list[BacktestTrade] = []
        self.trade_counter = 0
        self.daily_pnls: list[float] = []

    def get_state(self) -> dict[str, Any]:
        return {
            "balance": self.balance,
            "open_positions": len(self.open_trades),
            "win_rate": self._win_rate(),
        }

    def execute(self, trade: BacktestTrade) -> bool:
        cap = self.balance * MAX_POSITION_PCT
        if trade.amount_usd > cap or trade.amount_usd <= 0:
            return False
        if self.balance - trade.amount_usd < 0:
            return False

        # Apply slippage
        slippage = trade.entry_price * (SLIPPAGE_BPS / 10000.0)
        trade.entry_price = min(0.99, trade.entry_price + slippage)
        trade.shares = trade.amount_usd / trade.entry_price if trade.entry_price > 0 else 0

        self.trade_counter += 1
        trade.trade_id = self.trade_counter
        trade.status = "open"
        self.open_trades.append(trade)
        self.trades.append(trade)
        return True

    def check_stops(self, prices: dict[str, dict], current_date: str) -> list[BacktestTrade]:
        closed = []
        still_open = []

        for t in self.open_trades:
            p = prices.get(t.market_id, {})
            if t.direction == "YES":
                current = p.get("yes_price", t.entry_price)
            else:
                current = p.get("no_price", t.entry_price)

            unrealized = t.shares * (current - t.entry_price)
            pnl_pct = unrealized / t.amount_usd if t.amount_usd > 0 else 0

            # Check expiry
            expired = False
            end_date = p.get("end_date")
            if end_date:
                try:
                    end = datetime.datetime.fromisoformat(str(end_date).replace("Z", ""))
                    now = datetime.datetime.fromisoformat(current_date)
                    expired = now > end
                except (ValueError, TypeError):
                    pass

            if pnl_pct <= -STOP_LOSS_PCT or pnl_pct >= TAKE_PROFIT_PCT or expired:
                t.exit_price = current
                t.pnl = unrealized
                t.status = "closed_win" if unrealized >= 0 else "closed_loss"
                t.closed_at = current_date
                self.balance += unrealized
                closed.append(t)
            else:
                still_open.append(t)

        self.open_trades = still_open
        return closed

    def mark_to_market(self, prices: dict[str, dict]) -> float:
        """Calculate unrealized PnL for open positions."""
        unrealized = 0.0
        for t in self.open_trades:
            p = prices.get(t.market_id, {})
            if t.direction == "YES":
                current = p.get("yes_price", t.entry_price)
            else:
                current = p.get("no_price", t.entry_price)
            unrealized += t.shares * (current - t.entry_price)
        return unrealized

    def _win_rate(self) -> float:
        closed = [t for t in self.trades if t.status != "open"]
        if not closed:
            return 0.0
        wins = sum(1 for t in closed if t.pnl > 0)
        return wins / len(closed)


# ---------------------------------------------------------------------------
# Strategy replay (reuses trading_brain logic)
# ---------------------------------------------------------------------------

def _replay_arbitrage(markets: list[dict], balance: float) -> list[BacktestTrade]:
    """Replay single-venue arb strategy."""
    trades = []
    for m in markets:
        yes_p = m.get("yes_price", 0) or 0
        no_p = m.get("no_price", 0) or 0
        gap = abs(yes_p + no_p - 1.0)
        if gap <= ARB_THRESHOLD:
            continue

        if no_p < 1 - yes_p:
            direction, entry_price = "NO", no_p
        else:
            direction, entry_price = "YES", yes_p

        if entry_price <= 0 or entry_price >= 1:
            continue

        amount = 0.05 * balance
        trades.append(BacktestTrade(
            trade_id=0,
            market_id=m.get("market_id", ""),
            question=m.get("question", ""),
            direction=direction,
            strategy="arbitrage",
            entry_price=entry_price,
            amount_usd=amount,
            shares=amount / entry_price,
            expected_edge=min(gap / 0.10, 1.0),
        ))
    return trades


def _replay_price_lag(
    markets: list[dict],
    spot_prices: dict[str, float],
    balance: float,
) -> list[BacktestTrade]:
    """Replay price-lag arb strategy using trading_brain logic."""
    try:
        from scripts.mirofish.trading_brain import _check_price_lag_arb
    except ImportError:
        return []

    trades = []
    for m in markets:
        decision = _check_price_lag_arb(m, spot_prices, balance)
        if decision:
            trades.append(BacktestTrade(
                trade_id=0,
                market_id=decision.market_id,
                question=decision.question,
                direction=decision.direction,
                strategy="price_lag_arb",
                entry_price=decision.entry_price,
                amount_usd=decision.amount_usd,
                shares=decision.shares,
                expected_edge=decision.confidence,
            ))
    return trades


# ---------------------------------------------------------------------------
# Main backtest engine
# ---------------------------------------------------------------------------

def run_backtest(
    from_date: str,
    to_date: str,
    strategies: list[str] | None = None,
    starting_balance: float = STARTING_BALANCE,
) -> BacktestResult:
    """
    Run a backtest over historical data.

    Replays each date's market snapshots through selected strategies,
    executes trades in a simulated wallet, checks stops daily.
    """
    if strategies is None:
        strategies = ALL_STRATEGIES

    print(f"[backtest] Loading data {from_date} → {to_date}")
    snapshots = load_historical_snapshots(from_date, to_date)
    spot_history = load_spot_prices(from_date, to_date)

    if not snapshots:
        print("[backtest] No historical data found")
        return BacktestResult(
            from_date=from_date, to_date=to_date,
            starting_balance=starting_balance, ending_balance=starting_balance,
            total_return_pct=0.0, strategy_results=[], all_trades=[],
            daily_snapshots=[],
        )

    wallet = SimWallet(starting_balance)
    daily_snaps: list[DailySnapshot] = []

    dates = sorted(snapshots.keys())
    print(f"[backtest] {len(dates)} trading days, "
          f"{sum(len(v) for v in snapshots.values())} market snapshots")

    for date_str in dates:
        markets = snapshots[date_str]
        spot = spot_history.get(date_str, {})
        balance = wallet.balance
        prices = {m["market_id"]: m for m in markets}

        # Generate trades for each strategy
        day_trades: list[BacktestTrade] = []

        if "arbitrage" in strategies:
            day_trades.extend(_replay_arbitrage(markets, balance))

        if "price_lag_arb" in strategies and spot:
            day_trades.extend(_replay_price_lag(markets, spot, balance))

        # Execute trades
        opened = 0
        for t in day_trades:
            t.opened_at = date_str
            if wallet.execute(t):
                opened += 1

        # Check stops
        closed_trades = wallet.check_stops(prices, date_str)

        # Daily snapshot
        unrealized = wallet.mark_to_market(prices)
        realized_today = sum(t.pnl for t in closed_trades)

        daily_snaps.append(DailySnapshot(
            date=date_str,
            balance=wallet.balance + unrealized,
            open_positions=len(wallet.open_trades),
            realized_pnl=realized_today,
            unrealized_pnl=unrealized,
            trades_opened=opened,
            trades_closed=len(closed_trades),
        ))

    # Force-close remaining open positions at last known prices
    if dates:
        last_markets = snapshots[dates[-1]]
        final_prices = {m["market_id"]: m for m in last_markets}
        remaining = wallet.check_stops(final_prices, dates[-1])
        # For anything still open, close at last price
        for t in list(wallet.open_trades):
            p = final_prices.get(t.market_id, {})
            price = p.get("yes_price" if t.direction == "YES" else "no_price", t.entry_price)
            t.exit_price = price
            t.pnl = t.shares * (price - t.entry_price)
            t.status = "closed_win" if t.pnl >= 0 else "closed_loss"
            t.closed_at = dates[-1]
            wallet.balance += t.pnl
        wallet.open_trades = []

    # Compute per-strategy results
    strategy_results = []
    for strat in strategies:
        strat_trades = [t for t in wallet.trades if t.strategy == strat]
        strategy_results.append(_compute_strategy_result(strat, strat_trades, starting_balance))

    ending_balance = wallet.balance
    total_return = ((ending_balance - starting_balance) / starting_balance * 100) if starting_balance > 0 else 0

    return BacktestResult(
        from_date=from_date,
        to_date=to_date,
        starting_balance=starting_balance,
        ending_balance=ending_balance,
        total_return_pct=total_return,
        strategy_results=strategy_results,
        all_trades=wallet.trades,
        daily_snapshots=daily_snaps,
    )


def _compute_strategy_result(
    strategy: str,
    trades: list[BacktestTrade],
    starting_balance: float,
) -> StrategyResult:
    """Compute aggregate stats for one strategy's trades."""
    if not trades:
        return StrategyResult(
            strategy=strategy, total_trades=0, wins=0, losses=0,
            win_rate=0.0, total_pnl=0.0, roi_pct=0.0, sharpe=None,
            max_drawdown=0.0, avg_trade_pnl=0.0, best_trade=0.0, worst_trade=0.0,
        )

    closed = [t for t in trades if t.status != "open"]
    pnls = [t.pnl for t in closed]
    wins = sum(1 for p in pnls if p > 0)
    losses = len(pnls) - wins
    total_pnl = sum(pnls)

    # Per-trade return percentages
    returns = []
    for t in closed:
        if t.amount_usd > 0:
            returns.append(t.pnl / t.amount_usd)

    sharpe = None
    if len(returns) > 1:
        s = stdev(returns)
        if s > 0:
            sharpe = mean(returns) / s

    # Max drawdown
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnls:
        cum += p
        peak = max(peak, cum)
        dd = (peak - cum) / peak if peak > 0 else 0.0
        max_dd = max(max_dd, dd)

    total_invested = sum(t.amount_usd for t in closed)
    roi = (total_pnl / total_invested * 100) if total_invested > 0 else 0.0

    return StrategyResult(
        strategy=strategy,
        total_trades=len(closed),
        wins=wins,
        losses=losses,
        win_rate=wins / len(closed) if closed else 0.0,
        total_pnl=total_pnl,
        roi_pct=roi,
        sharpe=sharpe,
        max_drawdown=max_dd,
        avg_trade_pnl=mean(pnls) if pnls else 0.0,
        best_trade=max(pnls) if pnls else 0.0,
        worst_trade=min(pnls) if pnls else 0.0,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Mirofish backtester")
    parser.add_argument("--from", dest="from_date", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--to", dest="to_date", default=datetime.date.today().isoformat(),
                        help="End date (YYYY-MM-DD)")
    parser.add_argument("--strategies", default=None,
                        help="Comma-separated strategies (default: all)")
    parser.add_argument("--balance", type=float, default=STARTING_BALANCE,
                        help="Starting balance")
    parser.add_argument("--report", choices=["text", "json"], default="text",
                        help="Output format")
    args = parser.parse_args()

    strategies = args.strategies.split(",") if args.strategies else None

    # Load .env
    env_file = Path.home() / "openclaw" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    result = run_backtest(args.from_date, args.to_date, strategies, args.balance)

    if args.report == "json":
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(f"\n{'='*60}")
        print(f"BACKTEST: {result.from_date} → {result.to_date}")
        print(f"{'='*60}")
        print(f"Starting: ${result.starting_balance:,.2f}")
        print(f"Ending:   ${result.ending_balance:,.2f}")
        print(f"Return:   {result.total_return_pct:+.2f}%")
        print(f"Trades:   {len(result.all_trades)}")

        for s in result.strategy_results:
            if s.total_trades > 0:
                print(f"\n  {s.strategy}:")
                print(f"    trades: {s.total_trades} (W:{s.wins} L:{s.losses})")
                print(f"    win_rate: {s.win_rate:.1%}")
                print(f"    PnL: ${s.total_pnl:+.2f} | ROI: {s.roi_pct:+.1f}%")
                if s.sharpe is not None:
                    print(f"    sharpe: {s.sharpe:.3f}")
                print(f"    max_dd: {s.max_drawdown:.1%}")
                print(f"    avg: ${s.avg_trade_pnl:+.2f} | "
                      f"best: ${s.best_trade:+.2f} | worst: ${s.worst_trade:+.2f}")

        if result.daily_snapshots:
            print(f"\n  Daily summary ({len(result.daily_snapshots)} days):")
            for snap in result.daily_snapshots[-5:]:
                print(f"    {snap.date}: ${snap.balance:,.2f} "
                      f"({snap.trades_opened} opened, {snap.trades_closed} closed)")
        print(f"\n{'='*60}")
