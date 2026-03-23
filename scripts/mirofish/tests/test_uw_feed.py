# scripts/mirofish/tests/test_uw_feed.py
from __future__ import annotations
import os
import sqlite3
import datetime
import pytest
from unittest.mock import patch


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


def _uw(monkeypatch=None):
    """Re-import uw module with clean state."""
    import sys
    for mod in list(sys.modules.keys()):
        if "unusual_whales" in mod:
            del sys.modules[mod]
    import scripts.mirofish.unusual_whales_feed as uw
    return uw


# ── Test 1: no API key → returns [] immediately ────────────────────────────
def test_graceful_degrade_when_no_api_key(temp_db, monkeypatch):
    monkeypatch.delenv("UNUSUAL_WHALES_API_KEY", raising=False)
    uw = _uw()
    result = uw.fetch()
    assert result == []


# ── Test 2: options flow normalization ─────────────────────────────────────
def test_normalize_options_flow_call_is_bullish(temp_db):
    uw = _uw()
    raw = {
        "ticker": "NVDA",
        "type": "call",
        "has_sweep": True,
        "strike": "1000",
        "expiry": "2026-04-18",
        "total_premium": 2_500_000,
        "volume_oi_ratio": 3.2,
    }
    result = uw._normalize_options_flow(raw)
    assert result is not None
    assert result["ticker"] == "NVDA"
    assert result["source"] == "options_flow"
    assert result["signal_type"] == "call_sweep"
    assert result["direction"] == "bullish"
    assert result["amount_usd"] == pytest.approx(2_500_000)
    assert "NVDA" in result["description"]
    assert "fetched_at" in result


# ── Test 3: congressional normalization ────────────────────────────────────
def test_normalize_congressional_buy_bullish_sell_bearish(temp_db):
    uw = _uw()
    base = {
        "ticker": "TSLA",
        "name": "Sen. Test",
        "member_type": "senate",
        "amounts": "$15,001 - $50,000",
        "filed_at_date": "2026-03-20",
    }
    buy = uw._normalize_congressional({**base, "txn_type": "Buy"})
    sell = uw._normalize_congressional({**base, "txn_type": "Sale"})

    assert buy is not None and buy["direction"] == "bullish"
    assert buy["signal_type"] == "buy"
    assert sell is not None and sell["direction"] == "bearish"
    assert sell["signal_type"] == "sell"


# ── Test 4: fresh cache → no live fetch ────────────────────────────────────
def test_cache_returns_when_fresh(temp_db, monkeypatch):
    monkeypatch.setenv("UNUSUAL_WHALES_API_KEY", "test_key")
    uw = _uw()

    # Seed cache directly
    now = datetime.datetime.utcnow().isoformat()
    conn = sqlite3.connect(temp_db)
    conn.execute("""
        INSERT INTO uw_signals
        (source, ticker, signal_type, direction, amount_usd, description, fetched_at)
        VALUES ('options_flow', 'AAPL', 'call_sweep', 'bullish', 500000, 'AAPL sweep test', ?)
    """, (now,))
    conn.commit()
    conn.close()

    # _call_uw must NOT be called when cache is fresh
    with patch.object(uw, "_call_uw", side_effect=AssertionError("should not hit API")):
        result = uw.fetch()

    assert len(result) >= 1
    assert any(s["ticker"] == "AAPL" for s in result)


# ── Test 5: signals injected into Ollama prompt ────────────────────────────
def test_signals_injected_into_ollama_prompt(temp_db):
    import datetime as dt
    import scripts.mirofish.trading_brain as tb

    captured: list[str] = []

    def fake_ollama(prompt: str) -> str:
        captured.append(prompt)
        return "[]"

    sample_signal = {
        "source": "options_flow",
        "ticker": "NVDA",
        "signal_type": "call_sweep",
        "direction": "bullish",
        "amount_usd": 2_500_000,
        "description": "NVDA call_sweep 1000 exp 2026-04 — $2.5M premium",
        "fetched_at": dt.datetime.utcnow().isoformat(),
    }
    markets = [{
        "market_id": "m1",
        "question": "Will NVDA hit ATH in 2026?",
        "yes_price": 0.50,
        "no_price": 0.50,
        "volume": 50_000,
    }]
    wallet = {"balance": 1000.0, "open_positions": 0}

    with patch.object(tb, "_call_ollama", side_effect=fake_ollama):
        tb.analyze(markets, wallet, signals=[sample_signal])

    assert len(captured) == 1
    assert "Active market signals" in captured[0]
    assert "NVDA" in captured[0]
