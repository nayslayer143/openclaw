"""Tests for high_freq_trader — startup, DB cleanup, wallet init."""
import sqlite3
import sys
import os
import datetime

# Ensure project root is importable
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
if _root not in sys.path:
    sys.path.insert(0, _root)

import pytest


def _make_db():
    """Create an in-memory SQLite DB with all required tables."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE paper_trades (
            id INTEGER PRIMARY KEY,
            market_id TEXT, question TEXT, direction TEXT,
            shares REAL, entry_price REAL, exit_price REAL,
            amount_usd REAL, pnl REAL, status TEXT,
            confidence REAL, reasoning TEXT, strategy TEXT,
            opened_at TEXT, closed_at TEXT,
            venue TEXT, expected_edge REAL, binary_outcome TEXT,
            resolved_price REAL, resolution_source TEXT,
            entry_fee REAL, exit_fee REAL
        );
        CREATE TABLE context (
            chat_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT,
            PRIMARY KEY (chat_id, key)
        );
        CREATE TABLE spot_prices (
            id INTEGER PRIMARY KEY,
            source TEXT, ticker TEXT, signal_type TEXT,
            direction TEXT, amount_usd REAL, description TEXT,
            fetched_at TEXT
        );
    """)
    return conn


def test_db_startup_wipes_open_trades():
    from scripts.mirofish.high_freq_trader import db_startup
    conn = _make_db()
    conn.execute(
        "INSERT INTO paper_trades (market_id, question, direction, shares, entry_price, "
        "amount_usd, status, confidence, reasoning, strategy, opened_at) "
        "VALUES ('KX-TEST', 'test?', 'YES', 10, 0.5, 100, 'open', 0.6, '', 'arb', '2026-03-27T00:00:00')"
    )
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM paper_trades WHERE status='open'").fetchone()[0] == 1

    db_startup(conn)

    assert conn.execute("SELECT COUNT(*) FROM paper_trades WHERE status='open'").fetchone()[0] == 0


def test_db_startup_clears_context_noise():
    from scripts.mirofish.high_freq_trader import db_startup
    conn = _make_db()
    for i in range(5):
        conn.execute(
            "INSERT INTO context (chat_id, key, value) VALUES ('mirofish', ?, '1000.00')",
            (f"wallet_reset_2026-03-24T{i:02d}:00:00",)
        )
    conn.commit()
    assert conn.execute(
        "SELECT COUNT(*) FROM context WHERE key LIKE 'wallet_reset_%'"
    ).fetchone()[0] == 5

    db_startup(conn)

    assert conn.execute(
        "SELECT COUNT(*) FROM context WHERE key LIKE 'wallet_reset_%'"
    ).fetchone()[0] == 0


def test_db_startup_sets_10k_balance():
    from scripts.mirofish.high_freq_trader import db_startup
    conn = _make_db()
    db_startup(conn)
    row = conn.execute(
        "SELECT value FROM context WHERE chat_id='mirofish' AND key='starting_balance'"
    ).fetchone()
    assert row is not None
    assert float(row["value"]) == 10000.0


def test_db_startup_adds_index():
    from scripts.mirofish.high_freq_trader import db_startup
    conn = _make_db()
    db_startup(conn)
    idx = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_pt_status_opened'"
    ).fetchone()
    assert idx is not None


def test_get_balance_reads_starting_plus_closed_pnl():
    from scripts.mirofish.high_freq_trader import get_balance
    conn = _make_db()
    conn.execute(
        "INSERT OR REPLACE INTO context (chat_id, key, value) VALUES ('mirofish', 'starting_balance', '10000.00')"
    )
    conn.execute(
        "INSERT INTO paper_trades (market_id, question, direction, shares, entry_price, "
        "amount_usd, pnl, status, confidence, reasoning, strategy, opened_at) "
        "VALUES ('KX-X', 'q', 'YES', 10, 0.5, 100, 250.0, 'closed_win', 1.0, '', 'arb', '2026-03-27T00:00:00')"
    )
    conn.commit()
    assert get_balance(conn) == 10250.0
