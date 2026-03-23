#!/usr/bin/env python3
"""
skill_registry SQLite table — tracks installed skills, their hashes, and audit results.
Shares ~/.openclaw/clawmson.db with the rest of Clawmson.

IMPORTANT: set_approved() is a pure DB update. Hash re-verification before
approving a skill is the caller's responsibility (lives in auditor.py).
"""
from __future__ import annotations
import hashlib
import json
import sqlite3
import datetime
from pathlib import Path
import os

_DB_PATH: str = str(
    Path(os.environ.get("CLAWMSON_DB_PATH", Path.home() / ".openclaw" / "clawmson.db"))
)
_CONN: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    global _CONN, _DB_PATH
    if _DB_PATH == ":memory:":
        if _CONN is None:
            _CONN = sqlite3.connect(":memory:", check_same_thread=False)
            _CONN.row_factory = sqlite3.Row
        return _CONN
    path = Path(_DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    with _get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS skill_registry (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                skill_name    TEXT    NOT NULL UNIQUE,
                source_path   TEXT    NOT NULL,
                source_url    TEXT,
                install_date  TEXT    NOT NULL,
                hash_sha256   TEXT    NOT NULL,
                trust_score   INTEGER NOT NULL,
                category      TEXT    NOT NULL,
                audit_log     TEXT,
                approved_by   TEXT,
                last_verified TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_skill_registry_name
                ON skill_registry(skill_name);
        """)


def compute_hash(source_path: str) -> str:
    """
    Compute SHA256 of a skill file or directory.
    - Single file: hash of file contents.
    - Directory: sorted concatenation of all .py file contents.
    Returns hex digest string.
    """
    path = Path(source_path)
    h    = hashlib.sha256()

    if path.is_file():
        h.update(path.read_bytes())
    elif path.is_dir():
        for py_file in sorted(path.rglob("*.py")):
            h.update(py_file.read_bytes())
    # Missing path → empty hash (will differ from any real file)

    return h.hexdigest()


def register(
    skill_name: str,
    source_path: str,
    score: int,
    category: str,
    findings: list,
    source_url: str | None = None,
    approved_by: str | None = None,
) -> None:
    """Insert or replace a skill registry entry. Re-audit overwrites prior row."""
    now      = datetime.datetime.utcnow().isoformat()
    hash_val = compute_hash(source_path)
    log_json = json.dumps([
        {"category": f.category, "severity": f.severity,
         "line_no": f.line_no, "snippet": f.snippet}
        for f in findings
    ])
    if approved_by is None:
        approved_by = "auto" if category == "TRUSTED" else None

    with _get_conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO skill_registry
              (skill_name, source_path, source_url, install_date, hash_sha256,
               trust_score, category, audit_log, approved_by, last_verified)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (skill_name, source_path, source_url, now, hash_val,
              score, category, log_json, approved_by, now))


def get(skill_name: str) -> dict | None:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM skill_registry WHERE skill_name = ?", (skill_name,)
        ).fetchone()
    return dict(row) if row else None


def get_all() -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM skill_registry ORDER BY install_date DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def set_approved(skill_name: str, approved_by: str) -> None:
    """
    Pure DB update — sets approved_by field only.
    Hash re-verification before calling this is the caller's (auditor.py) responsibility.
    """
    with _get_conn() as conn:
        conn.execute(
            "UPDATE skill_registry SET approved_by = ? WHERE skill_name = ?",
            (approved_by, skill_name),
        )


def verify_all() -> list[tuple[str, str]]:
    """
    Recompute SHA256 for every registered skill.
    Returns list of (skill_name, status) where status is 'ok' or 'changed'.
    """
    results = []
    now     = datetime.datetime.utcnow().isoformat()
    for row in get_all():
        live_hash = compute_hash(row["source_path"])
        status    = "ok" if live_hash == row["hash_sha256"] else "changed"
        with _get_conn() as conn:
            conn.execute(
                "UPDATE skill_registry SET last_verified = ? WHERE skill_name = ?",
                (now, row["skill_name"]),
            )
        results.append((row["skill_name"], status))
    return results


# Init on import
_init_db()
