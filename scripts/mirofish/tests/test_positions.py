# scripts/mirofish/tests/test_positions.py
from __future__ import annotations
import os
import pytest
import sqlite3
import tempfile
from pathlib import Path


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


def _brain():
    import sys
    for mod in list(sys.modules.keys()):
        if "trading_brain" in mod:
            del sys.modules[mod]
    import scripts.mirofish.trading_brain as tb
    return tb


def _wallet():
    import sys
    for mod in list(sys.modules.keys()):
        if "paper_wallet" in mod:
            del sys.modules[mod]
    import scripts.mirofish.paper_wallet as pw
    return pw


# ── Arbitrage detection ────────────────────────────────────────────────────
def test_arbitrage_detected_when_gap_exceeds_threshold():
    tb = _brain()
    # yes=0.60 + no=0.45 → gap = 0.05 > 0.03 → flagged
    market = {"market_id": "m1", "question": "test", "yes_price": 0.60, "no_price": 0.45,
              "volume": 50000, "end_date": None, "category": "crypto"}
    result = tb._check_arbitrage(market)
    assert result is not None
    assert result.strategy == "arbitrage"
    # Should buy the underpriced side (NO at 0.45 < 0.50)
    assert result.direction == "NO"


def test_arbitrage_detected_buy_yes_when_yes_underpriced():
    tb = _brain()
    # yes=0.45 + no=0.60 → gap=0.05; yes is underpriced (< 0.50)
    market = {"market_id": "m2", "question": "test", "yes_price": 0.45, "no_price": 0.60,
              "volume": 50000, "end_date": None, "category": "crypto"}
    result = tb._check_arbitrage(market)
    assert result is not None
    assert result.direction == "YES"


def test_arbitrage_not_detected_below_threshold():
    tb = _brain()
    # yes=0.60 + no=0.41 → gap=0.01 ≤ 0.03 → not flagged
    market = {"market_id": "m3", "question": "test", "yes_price": 0.60, "no_price": 0.41,
              "volume": 50000, "end_date": None, "category": "crypto"}
    result = tb._check_arbitrage(market)
    assert result is None


# ── Kelly sizing ───────────────────────────────────────────────────────────
def test_kelly_positive_returns_within_cap():
    tb = _brain()
    # confidence=0.70, entry=0.30 → b=2.33, kelly=(0.70*2.33 - 0.30)/2.33 ≈ 0.57
    # position_size = min(0.57 * 1000, 0.10 * 1000) = 100
    size = tb._kelly_size(confidence=0.70, entry_price=0.30, balance=1000.0)
    assert size is not None
    assert size <= 100.0  # capped at 10%
    assert size > 0


def test_kelly_negative_returns_none():
    tb = _brain()
    # confidence=0.20, entry=0.80 → b=0.25, kelly=(0.20*0.25 - 0.80)/0.25 < 0
    size = tb._kelly_size(confidence=0.20, entry_price=0.80, balance=1000.0)
    assert size is None


def test_kelly_cap_never_exceeded():
    tb = _brain()
    # Even extremely high confidence should not exceed 10% cap
    size = tb._kelly_size(confidence=0.99, entry_price=0.10, balance=1000.0)
    assert size is not None
    assert size <= 100.0


# ── Graduation (needs dashboard.py — skip with marker) ─────────────────────
# (Graduation tests are in test_positions.py but require dashboard.py which is Task 5.
#  They will be run after Task 5 is complete. For now, these are the core brain tests.)


# ── Manual /bet position cap ────────────────────────────────────────────────
def test_manual_bet_enforces_position_cap(temp_db):
    pw = _wallet()
    from types import SimpleNamespace
    decision = SimpleNamespace(
        market_id="manual1", question="manual bet", direction="YES",
        amount_usd=150.0,  # 15% — over cap
        entry_price=0.50, shares=300.0,
        confidence=1.0, reasoning="manual via /bet", strategy="manual"
    )
    result = pw.execute_trade(decision)
    assert result is None  # Rejected even for manual trades
