from __future__ import annotations
import sqlite3
import datetime
import pytest


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    db = str(tmp_path / "test.db")
    monkeypatch.setenv("CLAWMSON_DB_PATH", db)
    import sys
    for mod in list(sys.modules.keys()):
        if "mirofish" in mod:
            del sys.modules[mod]
    import scripts.mirofish.simulator as sim
    sim.migrate()
    yield db


def _sa():
    import sys
    for mod in list(sys.modules.keys()):
        if "security_auditor" in mod:
            del sys.modules[mod]
    import scripts.mirofish.security_auditor as sa
    return sa


def test_valid_trade_approved(temp_db):
    sa = _sa()
    result = sa.audit_trade("mkt-1", "YES", 0.50, 50.0, 1000.0)
    assert result.approved is True
    assert len(result.checks_failed) == 0


def test_oversized_trade_rejected(temp_db):
    sa = _sa()
    result = sa.audit_trade("mkt-1", "YES", 0.50, 200.0, 1000.0)  # 20% > 10% cap
    assert result.approved is False
    assert "cap" in result.reason


def test_zero_amount_rejected(temp_db):
    sa = _sa()
    result = sa.audit_trade("mkt-1", "YES", 0.50, 0.0, 1000.0)
    assert result.approved is False


def test_insufficient_balance_rejected(temp_db):
    sa = _sa()
    # 8.0 is within 10% cap of 100, but balance is only 5
    result = sa.audit_trade("mkt-1", "YES", 0.50, 8.0, 5.0)
    assert result.approved is False
    assert any("balance" in f for f in result.checks_failed)


def test_invalid_price_rejected(temp_db):
    sa = _sa()
    result = sa.audit_trade("mkt-1", "YES", 1.50, 50.0, 1000.0)
    assert result.approved is False
    assert "price" in result.reason


def test_very_low_price_rejected(temp_db):
    sa = _sa()
    result = sa.audit_trade("mkt-1", "YES", 0.005, 50.0, 1000.0)
    assert result.approved is False


def test_duplicate_trade_rejected(temp_db):
    sa = _sa()
    # Seed an existing open trade
    conn = sqlite3.connect(temp_db)
    conn.execute("""
        INSERT INTO paper_trades
        (market_id, question, direction, shares, entry_price, amount_usd,
         status, confidence, reasoning, strategy, opened_at)
        VALUES ('mkt-1', 'Test?', 'YES', 100, 0.50, 50.0, 'open', 0.7, '', 'test', ?)
    """, (datetime.datetime.utcnow().isoformat(),))
    conn.commit()
    conn.close()

    result = sa.audit_trade("mkt-1", "YES", 0.50, 50.0, 1000.0)
    assert result.approved is False
    assert "duplicate" in result.reason


def test_result_to_dict(temp_db):
    sa = _sa()
    result = sa.audit_trade("mkt-1", "YES", 0.50, 50.0, 1000.0)
    d = result.to_dict()
    assert "approved" in d
    assert "checks_passed" in d
