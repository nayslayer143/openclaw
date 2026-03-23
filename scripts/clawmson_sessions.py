#!/usr/bin/env python3
from __future__ import annotations
"""
Session lifecycle for Clawmson.
Sessions are restart-bounded: one UUID session_key per bot process run.
One DB record per (session_key, chat_id), created lazily on first message.
"""
import os
import uuid
import datetime
from pathlib import Path

# Import MemoryManager at module level so patch("clawmson_sessions.MemoryManager") works.
# Guarded by try/except in case clawmson_memory isn't importable in all environments.
try:
    from clawmson_memory import MemoryManager
except Exception:  # pragma: no cover
    MemoryManager = None  # type: ignore

SESSION_KEY_FILE = Path(os.environ.get(
    "CLAWMSON_SESSION_KEY_FILE", "/tmp/clawmson-session-key.txt"
))
RESUME_WINDOW_HOURS = int(os.environ.get("CLAWMSON_RESUME_WINDOW_HOURS", "24"))


def _now() -> str:
    return datetime.datetime.utcnow().isoformat()


def start_session() -> str:
    """
    Generate UUID session_key, write to SESSION_KEY_FILE.
    Returns session_key. Called once on dispatcher boot.
    """
    key = str(uuid.uuid4())
    SESSION_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_KEY_FILE.write_text(key)
    return key


def ensure_session(session_key: str, chat_id: str):
    """
    INSERT OR IGNORE session record for (session_key, chat_id).
    Increments message_count on every call (including the INSERT).
    Called per-message from dispatcher.
    """
    import clawmson_db as db
    ts = _now()
    with db._get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO sessions"
            " (session_key, chat_id, started_at, message_count)"
            " VALUES (?, ?, ?, 0)",
            (session_key, chat_id, ts)
        )
        conn.execute(
            "UPDATE sessions SET message_count = message_count + 1"
            " WHERE session_key=? AND chat_id=?",
            (session_key, chat_id)
        )


def end_all_sessions(session_key: str):
    """
    Called on SIGTERM/SIGINT. Sets ended_at = utcnow() for all open sessions
    under session_key. Queues fire-and-forget LLM summary tasks via executor.
    """
    import clawmson_db as db
    ts = _now()
    with db._get_conn() as conn:
        rows = conn.execute(
            "SELECT id, chat_id FROM sessions"
            " WHERE session_key=? AND ended_at IS NULL",
            (session_key,)
        ).fetchall()
        if not rows:
            return
        conn.execute(
            "UPDATE sessions SET ended_at=? WHERE session_key=? AND ended_at IS NULL",
            (ts, session_key)
        )

    # Fire-and-forget LLM summaries via MemoryManager executor
    try:
        _mm = MemoryManager()
        for row in rows:
            sid = row[0]
            cid = row[1]
            _mm._executor.submit(_generate_summary, sid, cid)
        _mm._executor.shutdown(wait=False)
    except Exception as e:
        print(f"[sessions] Could not queue summary tasks: {e}")


def _generate_summary(session_id: int, chat_id: str):
    """Background task: generate 3-sentence LLM summary for a session."""
    try:
        import clawmson_db as db
        from clawmson_memory import _llm_text

        with db._get_conn() as conn:
            msgs = conn.execute(
                "SELECT role, content FROM conversations"
                " WHERE chat_id=? ORDER BY id DESC LIMIT 20",
                (chat_id,)
            ).fetchall()

        if not msgs:
            return

        exchange = "\n".join(
            f"{r['role'].capitalize()}: {r['content'][:200]}"
            for r in reversed(msgs)
        )
        prompt = (
            f"Summarize the following conversation in exactly 3 sentences, "
            f"focusing on topics discussed, decisions made, and key information.\n\n"
            f"{exchange}"
        )
        summary = _llm_text(prompt)
        if not summary:
            return

        with db._get_conn() as conn:
            conn.execute(
                "UPDATE sessions SET summary=? WHERE id=?",
                (summary, session_id)
            )
    except Exception as e:
        print(f"[sessions] Summary generation failed for session {session_id}: {e}")


def get_resume_context(chat_id: str, current_session_key: str) -> str:
    """
    Find the most recent session for chat_id where session_key != current_session_key.

    Returns '### Previous Session\\n<summary>' if ALL of:
      - ended_at IS NOT NULL
      - ended_at is within RESUME_WINDOW_HOURS of utcnow()
      - summary IS NOT NULL and non-empty

    Returns "" in all other cases (no previous session, killed ungracefully,
    no summary, gap exceeds RESUME_WINDOW_HOURS).
    """
    import clawmson_db as db
    with db._get_conn() as conn:
        row = conn.execute(
            "SELECT ended_at, summary FROM sessions"
            " WHERE chat_id=? AND session_key != ?"
            " ORDER BY started_at DESC LIMIT 1",
            (chat_id, current_session_key)
        ).fetchone()

    if not row:
        return ""

    ended_at = row["ended_at"]
    summary = row["summary"]

    if not ended_at:
        return ""
    if not summary:
        return ""

    try:
        ended_dt = datetime.datetime.fromisoformat(ended_at)
        now_dt = datetime.datetime.utcnow()
        age_hours = (now_dt - ended_dt).total_seconds() / 3600
        if age_hours > RESUME_WINDOW_HOURS:
            return ""
    except Exception:
        return ""

    return f"### Previous Session\n{summary}"
