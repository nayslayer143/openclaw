#!/usr/bin/env python3
from __future__ import annotations
"""
Clawmson conversation persistence layer.
SQLite store for messages, context, and references.
DB at ~/.openclaw/clawmson.db
"""

import os
import sqlite3
import datetime
from pathlib import Path

DB_PATH = Path(os.environ.get("CLAWMSON_DB_PATH", Path.home() / ".openclaw" / "clawmson.db"))
_SHARED_MEM_CONN = None  # For in-memory DB testing


def _get_conn() -> sqlite3.Connection:
    global _SHARED_MEM_CONN

    if str(DB_PATH) == ":memory:":
        # For in-memory testing, reuse the same connection
        if _SHARED_MEM_CONN is None:
            _SHARED_MEM_CONN = sqlite3.connect(":memory:", check_same_thread=False)
            _SHARED_MEM_CONN.row_factory = sqlite3.Row
        return _SHARED_MEM_CONN
    else:
        # For file-based DB, create a new connection each time
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        return conn


def _init_db():
    with _get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id     TEXT    NOT NULL,
                message_id  INTEGER,
                role        TEXT    NOT NULL,
                content     TEXT    NOT NULL,
                timestamp   TEXT    NOT NULL,
                media_type  TEXT,
                archived    INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS context (
                chat_id TEXT NOT NULL,
                key     TEXT NOT NULL,
                value   TEXT NOT NULL,
                PRIMARY KEY (chat_id, key)
            );
            CREATE TABLE IF NOT EXISTS refs (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id   TEXT NOT NULL,
                url       TEXT NOT NULL,
                title     TEXT,
                summary   TEXT,
                content   TEXT,
                timestamp TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS stm_summaries (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id   TEXT    NOT NULL,
                summary   TEXT    NOT NULL,
                from_ts   TEXT    NOT NULL,
                to_ts     TEXT    NOT NULL,
                timestamp TEXT    NOT NULL
            );
            CREATE TABLE IF NOT EXISTS episodic_memories (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id   TEXT    NOT NULL,
                content   TEXT    NOT NULL,
                summary   TEXT    NOT NULL,
                timestamp TEXT    NOT NULL,
                valence   TEXT    NOT NULL DEFAULT 'neutral',
                embedding BLOB
            );
            CREATE TABLE IF NOT EXISTS semantic_facts (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id    TEXT    NOT NULL,
                key        TEXT    NOT NULL,
                value      TEXT    NOT NULL,
                confidence REAL    NOT NULL DEFAULT 0.8,
                source     TEXT    NOT NULL DEFAULT 'inferred',
                timestamp  TEXT    NOT NULL,
                embedding  BLOB,
                UNIQUE(chat_id, key)
            );
            CREATE TABLE IF NOT EXISTS procedures (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id            TEXT    NOT NULL,
                trigger_pattern    TEXT    NOT NULL,
                action_description TEXT    NOT NULL,
                created_by         TEXT    NOT NULL DEFAULT 'explicit',
                status             TEXT    NOT NULL DEFAULT 'active',
                occurrence_count   INTEGER NOT NULL DEFAULT 1,
                last_triggered     TEXT,
                timestamp          TEXT    NOT NULL
            );
            CREATE TABLE IF NOT EXISTS procedure_candidates (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id        TEXT    NOT NULL,
                intent         TEXT    NOT NULL,
                action         TEXT    NOT NULL,
                trigger_phrase TEXT    NOT NULL,
                count          INTEGER NOT NULL DEFAULT 1,
                last_seen      TEXT    NOT NULL,
                UNIQUE(chat_id, intent, action)
            );
            CREATE TABLE IF NOT EXISTS sessions (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                session_key   TEXT NOT NULL,
                chat_id       TEXT NOT NULL,
                started_at    TEXT NOT NULL,
                ended_at      TEXT,
                message_count INTEGER NOT NULL DEFAULT 0,
                summary       TEXT,
                UNIQUE(session_key, chat_id)
            );
            CREATE INDEX IF NOT EXISTS idx_conv_chat      ON conversations(chat_id);
            CREATE INDEX IF NOT EXISTS idx_conv_archived  ON conversations(chat_id, archived);
            CREATE INDEX IF NOT EXISTS idx_ref_chat       ON refs(chat_id);
            CREATE INDEX IF NOT EXISTS idx_stm_chat       ON stm_summaries(chat_id);
            CREATE INDEX IF NOT EXISTS idx_episodic_chat  ON episodic_memories(chat_id);
            CREATE INDEX IF NOT EXISTS idx_semantic_chat  ON semantic_facts(chat_id);
            CREATE INDEX IF NOT EXISTS idx_procedures_chat ON procedures(chat_id, status);
            CREATE INDEX IF NOT EXISTS idx_candidates_chat ON procedure_candidates(chat_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_chat  ON sessions(chat_id, started_at DESC);
        """)
    # FTS5 creation is separate — not all SQLite builds support it
    try:
        with _get_conn() as conn:
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                    content,
                    source    UNINDEXED,
                    chat_id   UNINDEXED,
                    source_id UNINDEXED,
                    ts        UNINDEXED,
                    tokenize = 'porter unicode61'
                )
            """)
    except Exception as e:
        print(f"[db] FTS5 not available: {e}")


def save_message(chat_id: str, role: str, content: str,
                 message_id: int = None, media_type: str = None):
    ts = datetime.datetime.utcnow().isoformat()
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO conversations (chat_id, message_id, role, content, timestamp, media_type)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (chat_id, message_id, role, content, ts, media_type)
        )


def get_history(chat_id: str, limit: int = 50) -> list:
    """Return last `limit` non-archived messages as list of dicts, oldest first."""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT role, content, media_type FROM conversations"
            " WHERE chat_id = ? AND archived = 0 ORDER BY id DESC LIMIT ?",
            (chat_id, limit)
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def clear_history(chat_id: str):
    with _get_conn() as conn:
        conn.execute("DELETE FROM conversations WHERE chat_id = ?", (chat_id,))


def get_context(chat_id: str) -> dict:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT key, value FROM context WHERE chat_id = ?", (chat_id,)
        ).fetchall()
    return {r["key"]: r["value"] for r in rows}


def set_context(chat_id: str, key: str, value: str):
    with _get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO context (chat_id, key, value) VALUES (?, ?, ?)",
            (chat_id, key, value)
        )


def save_reference(chat_id: str, url: str, title: str, summary: str, content: str):
    ts = datetime.datetime.utcnow().isoformat()
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO refs (chat_id, url, title, summary, content, timestamp)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (chat_id, url, title or url, summary, content, ts)
        )


def fts_index(chat_id: str, source: str, source_id: int,
              content: str, ts: str, conn=None):
    """Insert one item into memory_fts. No-op if FTS5 unavailable.

    When conn is provided, INSERT runs inside the caller's existing transaction.
    When conn=None, a new connection is opened.
    """
    try:
        import clawmson_fts as _fts
        _fts.index(chat_id, source, source_id, content, ts, conn=conn)
    except ImportError:
        pass


def search_references(chat_id: str, keyword: str) -> list:
    pattern = f"%{keyword}%"
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT url, title, summary, timestamp FROM refs"
            " WHERE chat_id = ? AND (title LIKE ? OR summary LIKE ? OR content LIKE ?)"
            " ORDER BY id DESC LIMIT 10",
            (chat_id, pattern, pattern, pattern)
        ).fetchall()
    return [dict(r) for r in rows]


def list_references(chat_id: str, limit: int = 20) -> list:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT url, title, summary, timestamp FROM refs"
            " WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
            (chat_id, limit)
        ).fetchall()
    return [dict(r) for r in rows]


# Init on import
_init_db()
