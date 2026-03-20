#!/usr/bin/env python3
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


def _get_conn() -> sqlite3.Connection:
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
                media_type  TEXT
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
            CREATE INDEX IF NOT EXISTS idx_conv_chat ON conversations(chat_id);
            CREATE INDEX IF NOT EXISTS idx_ref_chat  ON refs(chat_id);
        """)


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
    """Return last `limit` messages as list of dicts, oldest first."""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT role, content, media_type FROM conversations"
            " WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
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
