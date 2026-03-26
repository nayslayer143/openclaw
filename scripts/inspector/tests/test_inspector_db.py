import pytest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parents[2]))
from inspector.inspector_db import InspectorDB

def test_db_creates_tables(tmp_path):
    db = InspectorDB(db_path=str(tmp_path / "test.db"))
    db.init()
    tables = db.get_tables()
    assert "verified_trades" in tables
    assert "resolution_audits" in tables
    assert "code_findings" in tables
    assert "hallucination_checks" in tables
    assert "audit_reports" in tables

def test_db_idempotent(tmp_path):
    db = InspectorDB(db_path=str(tmp_path / "test.db"))
    db.init()
    db.init()  # second call must not raise
    assert len(db.get_tables()) == 5

def test_insert_and_fetch(tmp_path):
    db = InspectorDB(db_path=str(tmp_path / "test.db"))
    db.init()
    row_id = db.insert("code_findings", {
        "file_path": "/some/file.py",
        "line_number": 42,
        "finding_type": "logic_error",
        "severity": "high",
        "description": "Test finding",
        "snippet": "x = 1",
        "found_at": "2026-03-26T00:00:00Z",
    })
    assert row_id is not None and row_id > 0
    rows = db.fetch_all("code_findings")
    assert len(rows) == 1
    assert rows[0]["file_path"] == "/some/file.py"

def test_fetch_with_where(tmp_path):
    db = InspectorDB(db_path=str(tmp_path / "test.db"))
    db.init()
    db.insert("code_findings", {
        "file_path": "/a.py", "line_number": 1, "finding_type": "logic_error",
        "severity": "high", "description": "A", "snippet": None,
        "found_at": "2026-03-26T00:00:00Z",
    })
    db.insert("code_findings", {
        "file_path": "/b.py", "line_number": 2, "finding_type": "test_leak",
        "severity": "low", "description": "B", "snippet": None,
        "found_at": "2026-03-26T00:00:00Z",
    })
    rows = db.fetch_all("code_findings", where="severity = ?", params=("high",))
    assert len(rows) == 1
    assert rows[0]["file_path"] == "/a.py"

def test_invalid_table_raises(tmp_path):
    db = InspectorDB(db_path=str(tmp_path / "test.db"))
    db.init()
    with pytest.raises(ValueError, match="Unknown table"):
        db.insert("not_a_real_table", {"foo": "bar"})
