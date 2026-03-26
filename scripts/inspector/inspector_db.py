"""
Inspector Gadget — SQLite persistence layer.
Manages five audit tables for independent trading verification.
"""

import sqlite3
from pathlib import Path
from typing import List, Dict, Any


class InspectorDB:
    DEFAULT_DB_PATH = "~/.openclaw/inspector_gadget.db"

    def __init__(self, db_path: str = None):
        raw_path = db_path if db_path is not None else self.DEFAULT_DB_PATH
        self.db_path = str(Path(raw_path).expanduser())
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def init(self) -> None:
        """Create all five audit tables. Idempotent — safe to call multiple times."""
        ddl = [
            """
            CREATE TABLE IF NOT EXISTS verified_trades (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id         TEXT,
                bot_source       TEXT,
                market_id        TEXT,
                direction        TEXT,
                claimed_entry    REAL,
                verified_entry   REAL,
                claimed_exit     REAL,
                verified_exit    REAL,
                claimed_pnl      REAL,
                verified_pnl     REAL,
                claimed_amount   REAL,
                status           TEXT CHECK(status IN ('VERIFIED','DISCREPANCY','IMPOSSIBLE','UNVERIFIABLE')),
                discrepancy_amount  REAL,
                discrepancy_detail  TEXT,
                checked_at       TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS resolution_audits (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id            TEXT,
                market_id           TEXT,
                claimed_resolution  TEXT,
                actual_resolution   TEXT,
                match               INTEGER CHECK(match IN (1, 0, -1)),
                recalculated_pnl    REAL,
                claimed_pnl         REAL,
                pnl_delta           REAL,
                checked_at          TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS code_findings (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path    TEXT,
                line_number  INTEGER,
                finding_type TEXT,
                severity     TEXT CHECK(severity IN ('critical','high','medium','low')),
                description  TEXT,
                snippet      TEXT,
                found_at     TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS hallucination_checks (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id            TEXT,
                signal_id           TEXT,
                claim_type          TEXT,
                claim_content       TEXT,
                verification_result TEXT CHECK(verification_result IN (
                                        'GROUNDED','PARTIALLY_GROUNDED','HALLUCINATED','UNVERIFIABLE'
                                    )),
                grounding_score     REAL,
                actual_value        TEXT,
                checked_at          TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS audit_reports (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id               TEXT UNIQUE,
                generated_at            TEXT,
                summary                 TEXT,
                total_trades_checked    INTEGER,
                verified_count          INTEGER,
                discrepancy_count       INTEGER,
                impossible_count        INTEGER,
                unverifiable_count      INTEGER,
                trust_scores_json       TEXT,
                red_flags_json          TEXT,
                report_path             TEXT
            )
            """,
        ]
        with self._connect() as conn:
            for statement in ddl:
                conn.execute(statement)
            conn.commit()

    def get_tables(self) -> List[str]:
        """Return the names of all user-created tables in the database."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        return [row["name"] for row in rows]

    def insert(self, table: str, row: Dict[str, Any]) -> int:
        """Insert a row dict into the named table. Returns the lastrowid."""
        columns = ", ".join(row.keys())
        placeholders = ", ".join(["?"] * len(row))
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        with self._connect() as conn:
            cursor = conn.execute(sql, list(row.values()))
            conn.commit()
            return cursor.lastrowid

    def fetch_all(self, table: str, where: str = "", params: tuple = ()) -> List[Dict[str, Any]]:
        """SELECT all rows from table with an optional WHERE clause."""
        sql = f"SELECT * FROM {table}"
        if where:
            sql += f" WHERE {where}"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
