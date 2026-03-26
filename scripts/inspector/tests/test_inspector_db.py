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
