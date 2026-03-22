#!/usr/bin/env python3
"""
Mirofish simulator — cron orchestrator for paper trading.
CLI: python3 simulator.py --run | --migrate | --report
"""
from __future__ import annotations
import argparse
import os
import sqlite3
import datetime
from pathlib import Path


def _get_conn() -> sqlite3.Connection:
    db_path = Path(os.environ.get("CLAWMSON_DB_PATH", Path.home() / ".openclaw" / "clawmson.db"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS market_data (
    id           INTEGER PRIMARY KEY,
    market_id    TEXT NOT NULL,
    question     TEXT NOT NULL,
    category     TEXT,
    yes_price    REAL,
    no_price     REAL,
    volume       REAL,
    end_date     TEXT,
    fetched_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_market_data_market_time
    ON market_data(market_id, fetched_at);

CREATE TABLE IF NOT EXISTS paper_trades (
    id           INTEGER PRIMARY KEY,
    market_id    TEXT NOT NULL,
    question     TEXT NOT NULL,
    direction    TEXT NOT NULL,
    shares       REAL NOT NULL,
    entry_price  REAL NOT NULL,
    exit_price   REAL,
    amount_usd   REAL NOT NULL,
    pnl          REAL,
    status       TEXT NOT NULL,
    confidence   REAL NOT NULL DEFAULT 1.0,
    reasoning    TEXT NOT NULL DEFAULT '',
    strategy     TEXT NOT NULL DEFAULT 'manual',
    opened_at    TEXT NOT NULL,
    closed_at    TEXT
);

CREATE TABLE IF NOT EXISTS daily_pnl (
    id              INTEGER PRIMARY KEY,
    date            TEXT NOT NULL UNIQUE,
    balance         REAL NOT NULL,
    open_positions  INTEGER,
    realized_pnl    REAL,
    unrealized_pnl  REAL,
    total_trades    INTEGER,
    win_rate        REAL,
    roi_pct         REAL
);

CREATE TABLE IF NOT EXISTS context (
    chat_id  TEXT NOT NULL,
    key      TEXT NOT NULL,
    value    TEXT NOT NULL,
    PRIMARY KEY (chat_id, key)
);

INSERT OR IGNORE INTO context (chat_id, key, value)
VALUES ('mirofish', 'starting_balance', '1000.00');
"""


def migrate():
    """Create mirofish tables. Idempotent."""
    with _get_conn() as conn:
        conn.executescript(MIGRATION_SQL)
    db_path = Path(os.environ.get("CLAWMSON_DB_PATH", Path.home() / ".openclaw" / "clawmson.db"))
    print(f"[mirofish] Migration complete. DB: {db_path}")


def run_loop():
    """Full simulation loop: fetch → analyze → trade → stops → snapshot."""
    import scripts.mirofish.polymarket_feed as feed
    import scripts.mirofish.paper_wallet as wallet
    import scripts.mirofish.trading_brain as brain
    import scripts.mirofish.dashboard as dash

    print(f"[mirofish] Run loop starting — {datetime.datetime.utcnow().isoformat()}")

    # 1. Fetch market data
    markets = feed.fetch_markets()
    if not markets:
        print("[mirofish] No markets available (API down + cache stale). Skipping trades.")
    else:
        # 2. Get wallet state
        state = wallet.get_state()
        print(f"[mirofish] Wallet: ${state['balance']:.2f} | "
              f"Positions: {state['open_positions']} | "
              f"Win rate: {state['win_rate']*100:.0f}%")

        # 3. Analyze markets
        decisions = brain.analyze(markets, state)
        print(f"[mirofish] Brain returned {len(decisions)} trade decisions")

        # 4. Execute trades
        for d in decisions:
            result = wallet.execute_trade(d)
            if result:
                print(f"[mirofish] Executed: {d.direction} ${d.amount_usd:.0f} "
                      f"on '{d.question[:50]}' [{d.strategy}]")
            else:
                print(f"[mirofish] Rejected: {d.market_id} (cap or kelly)")

    # 5. Check stops (always runs, even if API is down)
    try:
        current_prices = feed.get_latest_prices()
        closed = wallet.check_stops(current_prices)
        for c in closed:
            sign = "+" if (c["pnl"] or 0) >= 0 else ""
            print(f"[mirofish] Stop closed: {c['market_id']} → {c['status']} "
                  f"{sign}${c['pnl']:.2f}")
    except Exception as exc:
        print(f"[mirofish] Stop check failed: {exc}")

    # 6. Daily snapshot (first run of the day only)
    snapshotted = dash.maybe_snapshot(chat_id_for_notify=os.environ.get("JORDAN_TELEGRAM_CHAT_ID") or None)
    if snapshotted:
        print("[mirofish] Daily snapshot written and digest sent")

    print(f"[mirofish] Run complete — {datetime.datetime.utcnow().isoformat()}")


def main():
    # Load .env
    env_file = Path.home() / "openclaw" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    parser = argparse.ArgumentParser(description="Mirofish paper trading simulator")
    parser.add_argument("--migrate", action="store_true", help="Create DB tables")
    parser.add_argument("--run", action="store_true", help="Run simulation loop")
    parser.add_argument("--report", action="store_true", help="Generate report only")
    args = parser.parse_args()

    if args.migrate:
        migrate()
    elif args.run:
        run_loop()
    elif args.report:
        import scripts.mirofish.dashboard as dash
        path = dash.generate_report("daily")
        print(f"[mirofish] Report: {path}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
