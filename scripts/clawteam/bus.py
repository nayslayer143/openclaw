#!/usr/bin/env python3
"""
ClawTeam SQLite bus.
Three ct_-prefixed tables in ~/.openclaw/clawmson.db.
WAL mode enabled for safe concurrent reads/writes from ThreadPoolExecutor.
"""
import os
import sqlite3
import datetime
from pathlib import Path
from typing import Optional, List

DB_PATH = Path(os.environ.get("CLAWMSON_DB_PATH",
               Path.home() / ".openclaw" / "clawmson.db"))

_conn: Optional[sqlite3.Connection] = None


def _get_conn() -> sqlite3.Connection:  # type: ignore[return]
    global _conn
    if _conn is None:
        path = str(DB_PATH)
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _init_db(_conn)
    return _conn


def _init_db(conn: sqlite3.Connection):
    c = conn
    c.executescript("""
        CREATE TABLE IF NOT EXISTS ct_swarms (
            id           TEXT PRIMARY KEY,
            task         TEXT NOT NULL,
            pattern      TEXT NOT NULL,
            status       TEXT NOT NULL DEFAULT 'pending',
            created_at   TEXT NOT NULL,
            completed_at TEXT,
            result       TEXT
        );
        CREATE TABLE IF NOT EXISTS ct_subtasks (
            id           TEXT PRIMARY KEY,
            swarm_id     TEXT NOT NULL REFERENCES ct_swarms(id),
            agent        TEXT NOT NULL,
            model        TEXT NOT NULL,
            prompt       TEXT NOT NULL,
            depends_on   TEXT,
            status       TEXT NOT NULL DEFAULT 'pending',
            result       TEXT,
            started_at   TEXT,
            completed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS ct_messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            swarm_id    TEXT NOT NULL,
            from_agent  TEXT NOT NULL,
            to_agent    TEXT,
            msg_type    TEXT NOT NULL,
            content     TEXT NOT NULL,
            timestamp   TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ct_subtasks_swarm ON ct_subtasks(swarm_id);
        CREATE INDEX IF NOT EXISTS idx_ct_messages_swarm ON ct_messages(swarm_id);
    """)


def _now() -> str:
    return datetime.datetime.utcnow().isoformat()


# ── Swarms ────────────────────────────────────────────────────────────────────

def create_swarm(swarm_id: str, task: str, pattern: str) -> None:
    conn = _get_conn()
    conn.execute(
        "INSERT INTO ct_swarms (id, task, pattern, status, created_at) VALUES (?,?,?,'pending',?)",
        (swarm_id, task, pattern, _now())
    )
    conn.commit()


def get_swarm(swarm_id: str) -> Optional[dict]:
    row = _get_conn().execute(
        "SELECT * FROM ct_swarms WHERE id=?", (swarm_id,)
    ).fetchone()
    return dict(row) if row else None


def update_swarm_status(swarm_id: str, status: str, result: Optional[str] = None) -> None:
    conn = _get_conn()
    completed_at = _now() if status in ("complete", "partial", "failed") else None
    conn.execute(
        "UPDATE ct_swarms SET status=?, result=?, completed_at=? WHERE id=?",
        (status, result, completed_at, swarm_id)
    )
    conn.commit()


def list_swarms(limit: int = 10) -> List[dict]:
    rows = _get_conn().execute(
        "SELECT id, task, pattern, status, created_at FROM ct_swarms ORDER BY created_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


# ── Subtasks ──────────────────────────────────────────────────────────────────

def insert_subtask(subtask_id: str, swarm_id: str, agent: str, model: str,
                   prompt: str, depends_on: Optional[str]) -> None:
    conn = _get_conn()
    conn.execute(
        "INSERT INTO ct_subtasks (id, swarm_id, agent, model, prompt, depends_on, status)"
        " VALUES (?,?,?,?,?,?,'pending')",
        (subtask_id, swarm_id, agent, model, prompt, depends_on)
    )
    conn.commit()


def get_subtask(subtask_id: str) -> Optional[dict]:
    row = _get_conn().execute(
        "SELECT * FROM ct_subtasks WHERE id=?", (subtask_id,)
    ).fetchone()
    return dict(row) if row else None


def list_subtasks(swarm_id: str) -> List[dict]:
    rows = _get_conn().execute(
        "SELECT * FROM ct_subtasks WHERE swarm_id=? ORDER BY id", (swarm_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def update_subtask_status(subtask_id: str, status: str) -> None:
    conn = _get_conn()
    started_at = _now() if status == "running" else None
    conn.execute(
        "UPDATE ct_subtasks SET status=?, started_at=COALESCE(started_at, ?) WHERE id=?",
        (status, started_at, subtask_id)
    )
    conn.commit()


def complete_subtask(subtask_id: str, result: str) -> None:
    conn = _get_conn()
    conn.execute(
        "UPDATE ct_subtasks SET status='complete', result=?, completed_at=? WHERE id=?",
        (result, _now(), subtask_id)
    )
    conn.commit()


def fail_subtask(subtask_id: str) -> None:
    conn = _get_conn()
    conn.execute(
        "UPDATE ct_subtasks SET status='failed', completed_at=? WHERE id=?",
        (_now(), subtask_id)
    )
    conn.commit()


def reset_running_subtasks(swarm_id: str) -> None:
    """Resume logic: reset any interrupted (running) subtasks back to pending."""
    conn = _get_conn()
    conn.execute(
        "UPDATE ct_subtasks SET status='pending', result=NULL, started_at=NULL"
        " WHERE swarm_id=? AND status='running'",
        (swarm_id,)
    )
    conn.commit()


# ── Messages ──────────────────────────────────────────────────────────────────

def post_message(swarm_id: str, from_agent: str, to_agent: Optional[str],
                 msg_type: str, content: str) -> None:
    conn = _get_conn()
    conn.execute(
        "INSERT INTO ct_messages (swarm_id, from_agent, to_agent, msg_type, content, timestamp)"
        " VALUES (?,?,?,?,?,?)",
        (swarm_id, from_agent, to_agent, msg_type, content, _now())
    )
    conn.commit()


def get_messages(swarm_id: str) -> List[dict]:
    rows = _get_conn().execute(
        "SELECT * FROM ct_messages WHERE swarm_id=? ORDER BY id", (swarm_id,)
    ).fetchall()
    return [dict(r) for r in rows]
