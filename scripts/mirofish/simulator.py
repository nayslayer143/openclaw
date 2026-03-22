#!/usr/bin/env python3
"""
Mirofish simulator — cron orchestrator for paper trading.
CLI: python3 simulator.py --run | --migrate | --report
"""
from __future__ import annotations
import argparse
import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.environ.get("CLAWMSON_DB_PATH", Path.home() / ".openclaw" / "clawmson.db"))


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
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

-- Seed starting balance in context table if not already set
INSERT OR IGNORE INTO context (chat_id, key, value)
VALUES ('mirofish', 'starting_balance', '1000.00');
"""


def migrate():
    """Create mirofish tables. Idempotent."""
    with _get_conn() as conn:
        conn.executescript(MIGRATION_SQL)
    print(f"[mirofish] Migration complete. DB: {DB_PATH}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--migrate", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()

    if args.migrate:
        migrate()
    elif args.run:
        print("[mirofish] --run not yet implemented")
    elif args.report:
        print("[mirofish] --report not yet implemented")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
