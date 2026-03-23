"""Tests for bus.py — SQLite CRUD layer for ClawTeam swarm state."""
import sqlite3
import datetime
import pytest
from unittest.mock import patch
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

@pytest.fixture
def db():
    """In-memory SQLite bus for testing."""
    from clawteam import bus
    with patch.object(bus, 'DB_PATH', ':memory:'):
        bus._conn = None  # reset cached connection
        bus._get_conn()   # initialises tables lazily
        yield bus
        bus._conn.close()
        bus._conn = None


def test_wal_mode_enabled(db):
    conn = db._get_conn()
    result = conn.execute("PRAGMA journal_mode").fetchone()[0]
    # In-memory SQLite ignores WAL and returns 'memory'; file-backed returns 'wal'
    assert result in ("wal", "memory")


def test_indexes_exist(db):
    conn = db._get_conn()
    indexes = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'"
    ).fetchall()}
    assert "idx_ct_subtasks_swarm" in indexes
    assert "idx_ct_messages_swarm" in indexes


def test_create_swarm(db):
    db.create_swarm("swarm-111-test", "do a thing", "parallel")
    row = db.get_swarm("swarm-111-test")
    assert row["task"] == "do a thing"
    assert row["pattern"] == "parallel"
    assert row["status"] == "pending"


def test_get_swarm_missing_returns_none(db):
    assert db.get_swarm("no-such-id") is None


def test_update_swarm_status(db):
    db.create_swarm("swarm-222-test", "task", "sequential")
    db.update_swarm_status("swarm-222-test", "running")
    assert db.get_swarm("swarm-222-test")["status"] == "running"


def test_insert_subtask(db):
    db.create_swarm("swarm-333-test", "task", "sequential")
    db.insert_subtask("swarm-333-test_0", "swarm-333-test", "SCOUT", "qwen3:30b", "do research", None)
    row = db.get_subtask("swarm-333-test_0")
    assert row["agent"] == "SCOUT"
    assert row["status"] == "pending"
    assert row["result"] is None


def test_complete_subtask(db):
    db.create_swarm("swarm-444-test", "task", "parallel")
    db.insert_subtask("swarm-444-test_0", "swarm-444-test", "SCOUT", "qwen3:30b", "research", None)
    db.complete_subtask("swarm-444-test_0", "here are findings")
    row = db.get_subtask("swarm-444-test_0")
    assert row["status"] == "complete"
    assert row["result"] == "here are findings"
    assert row["completed_at"] is not None


def test_fail_subtask(db):
    db.create_swarm("swarm-555-test", "task", "parallel")
    db.insert_subtask("swarm-555-test_0", "swarm-555-test", "FORGE", "qwen3-coder-next", "build", None)
    db.fail_subtask("swarm-555-test_0")
    assert db.get_subtask("swarm-555-test_0")["status"] == "failed"


def test_list_subtasks_by_swarm(db):
    db.create_swarm("swarm-666-test", "task", "parallel")
    db.insert_subtask("swarm-666-test_0", "swarm-666-test", "SCOUT", "qwen3:30b", "p1", None)
    db.insert_subtask("swarm-666-test_1", "swarm-666-test", "AXIS", "qwen3:32b", "p2", None)
    rows = db.list_subtasks("swarm-666-test")
    assert len(rows) == 2


def test_reset_running_subtask(db):
    """Resume logic: running subtask must be reset to pending."""
    db.create_swarm("swarm-777-test", "task", "sequential")
    db.insert_subtask("swarm-777-test_0", "swarm-777-test", "SCOUT", "qwen3:30b", "do it", None)
    db.update_subtask_status("swarm-777-test_0", "running")
    db.reset_running_subtasks("swarm-777-test")
    row = db.get_subtask("swarm-777-test_0")
    assert row["status"] == "pending"
    assert row["result"] is None
    assert row["started_at"] is None


def test_post_message(db):
    db.create_swarm("swarm-888-test", "task", "debate")
    db.post_message("swarm-888-test", "SCOUT", "AXIS", "finding", "here is what I found")
    msgs = db.get_messages("swarm-888-test")
    assert len(msgs) == 1
    assert msgs[0]["content"] == "here is what I found"


def test_list_recent_swarms(db):
    db.create_swarm("swarm-aaa", "task a", "parallel")
    db.create_swarm("swarm-bbb", "task b", "sequential")
    rows = db.list_swarms(limit=10)
    assert len(rows) == 2
