#!/usr/bin/env python3
"""Tests for session lifecycle module."""
from __future__ import annotations
import os
import sys
import datetime
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

os.environ["CLAWMSON_DB_PATH"] = ":memory:"
os.environ["CLAWMSON_SESSION_KEY_FILE"] = "/tmp/test-clawmson-session-key.txt"

_SCRIPTS = Path(__file__).parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import clawmson_db as db
db._init_db()


def _now_offset(hours: float) -> str:
    """Return UTC ISO timestamp offset by `hours` from now."""
    return (datetime.datetime.utcnow() +
            datetime.timedelta(hours=hours)).isoformat()


class TestSessions(unittest.TestCase):
    def setUp(self):
        import importlib
        import clawmson_db
        importlib.reload(clawmson_db)
        # Clean sessions table
        with clawmson_db._get_conn() as conn:
            conn.execute("DELETE FROM sessions")
        import clawmson_sessions
        importlib.reload(clawmson_sessions)
        # Remove stale key file
        key_file = Path(os.environ["CLAWMSON_SESSION_KEY_FILE"])
        if key_file.exists():
            key_file.unlink()

    def test_start_session_writes_key_file(self):
        """start_session() creates key file containing a valid UUID."""
        import uuid
        import clawmson_sessions as sessions
        key = sessions.start_session()
        key_file = Path(os.environ["CLAWMSON_SESSION_KEY_FILE"])
        self.assertTrue(key_file.exists())
        written = key_file.read_text().strip()
        self.assertEqual(written, key)
        # Validate UUID format
        uuid.UUID(key)  # raises if invalid

    def test_ensure_session_creates_record(self):
        """First ensure_session() call creates row; second increments message_count."""
        import clawmson_sessions as sessions
        import clawmson_db as db
        key = "test-key-001"
        sessions.ensure_session(key, "chat1")
        with db._get_conn() as conn:
            row = conn.execute(
                "SELECT message_count FROM sessions WHERE session_key=? AND chat_id=?",
                (key, "chat1")
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 1)

        sessions.ensure_session(key, "chat1")
        with db._get_conn() as conn:
            row2 = conn.execute(
                "SELECT message_count FROM sessions WHERE session_key=? AND chat_id=?",
                (key, "chat1")
            ).fetchone()
        self.assertEqual(row2[0], 2)

    def test_end_all_sessions_sets_ended_at(self):
        """end_all_sessions() sets ended_at for all open sessions."""
        import clawmson_sessions as sessions
        import clawmson_db as db
        key = "test-key-002"
        sessions.ensure_session(key, "chatA")
        sessions.ensure_session(key, "chatB")
        # Mock MemoryManager to avoid Ollama calls
        with patch("clawmson_sessions.MemoryManager") as MockMM:
            mock_mm = MagicMock()
            mock_mm._executor = MagicMock()
            MockMM.return_value = mock_mm
            sessions.end_all_sessions(key)
        with db._get_conn() as conn:
            rows = conn.execute(
                "SELECT ended_at FROM sessions WHERE session_key=?", (key,)
            ).fetchall()
        self.assertEqual(len(rows), 2)
        for r in rows:
            self.assertIsNotNone(r[0])

    def test_get_resume_context_recent(self):
        """Session ended <24h ago with summary returns ### Previous Session block."""
        import clawmson_sessions as sessions
        import clawmson_db as db
        old_key = "old-key-001"
        new_key = "new-key-001"
        ended = _now_offset(-1)  # 1 hour ago
        with db._get_conn() as conn:
            conn.execute(
                "INSERT INTO sessions (session_key, chat_id, started_at, ended_at,"
                " message_count, summary) VALUES (?,?,?,?,?,?)",
                (old_key, "chat1", _now_offset(-2), ended, 5,
                 "Jordan was debugging the FTS module.")
            )
        result = sessions.get_resume_context("chat1", new_key)
        self.assertIn("### Previous Session", result)
        self.assertIn("FTS module", result)

    def test_get_resume_context_stale(self):
        """Session ended >24h ago returns empty string."""
        import clawmson_sessions as sessions
        import clawmson_db as db
        old_key = "old-key-002"
        new_key = "new-key-002"
        ended = _now_offset(-25)  # 25 hours ago
        with db._get_conn() as conn:
            conn.execute(
                "INSERT INTO sessions (session_key, chat_id, started_at, ended_at,"
                " message_count, summary) VALUES (?,?,?,?,?,?)",
                (old_key, "chat2", _now_offset(-26), ended, 3, "Some old session.")
            )
        result = sessions.get_resume_context("chat2", new_key)
        self.assertEqual(result, "")

    def test_get_resume_context_null_ended_at(self):
        """Session with ended_at=NULL (kill -9 case) returns empty string."""
        import clawmson_sessions as sessions
        import clawmson_db as db
        old_key = "old-key-003"
        new_key = "new-key-003"
        with db._get_conn() as conn:
            conn.execute(
                "INSERT INTO sessions (session_key, chat_id, started_at,"
                " message_count, summary) VALUES (?,?,?,?,?)",
                (old_key, "chat3", _now_offset(-1), 5, "Killed without SIGTERM.")
            )
        result = sessions.get_resume_context("chat3", new_key)
        self.assertEqual(result, "")


if __name__ == "__main__":
    unittest.main()
