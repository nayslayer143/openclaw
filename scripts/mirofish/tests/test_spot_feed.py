# tests/test_spot_feed.py
from __future__ import annotations
import datetime
import sqlite3
import requests
import pytest
from unittest.mock import patch, MagicMock


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


def test_spot_prices_table_exists(temp_db):
    conn = sqlite3.connect(temp_db)
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='spot_prices'"
    ).fetchone()
    conn.close()
    assert row is not None


def test_price_lag_trades_table_exists(temp_db):
    conn = sqlite3.connect(temp_db)
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='price_lag_trades'"
    ).fetchone()
    conn.close()
    assert row is not None


def _sf():
    """Re-import spot_feed with clean state."""
    import sys
    for mod in list(sys.modules.keys()):
        if "spot_feed" in mod:
            del sys.modules[mod]
    import scripts.mirofish.spot_feed as sf
    return sf


def _mock_binance(btc_price="42340.00", eth_price="2848.00"):
    """Return a side_effect function for requests.get that mocks Binance."""
    def side_effect(url, **kwargs):
        mock = MagicMock()
        mock.raise_for_status.return_value = None
        if "BTCUSDT" in url:
            mock.json.return_value = {"symbol": "BTCUSDT", "price": btc_price}
        elif "ETHUSDT" in url:
            mock.json.return_value = {"symbol": "ETHUSDT", "price": eth_price}
        elif "BTC-USD" in url:
            mock.json.return_value = {"data": {"amount": "42360.00"}}
        elif "ETH-USD" in url:
            mock.json.return_value = {"data": {"amount": "2852.00"}}
        return mock
    return side_effect


def test_module_interface(temp_db):
    sf = _sf()
    assert sf.source_name == "spot_prices"
    assert callable(sf.fetch)
    assert callable(sf.get_cached)
    assert callable(sf.get_spot_dict)


def test_fetch_binance_and_coinbase(temp_db):
    sf = _sf()
    with patch("requests.get", side_effect=_mock_binance()):
        signals = sf.fetch()
    assert len(signals) >= 2  # BTC + ETH at minimum, up to 6 with DOGE/BNB/ADA/BCH
    btc = [s for s in signals if s["ticker"] == "SPOT:BTC"]
    eth = [s for s in signals if s["ticker"] == "SPOT:ETH"]
    assert len(btc) == 1
    assert len(eth) == 1
    # Averaged: (42340 + 42360) / 2 = 42350
    assert btc[0]["amount_usd"] == pytest.approx(42350.0)
    assert btc[0]["source"] == "spot_prices"
    assert btc[0]["signal_type"] == "spot_price"
    assert btc[0]["direction"] == "neutral"


def test_fetch_one_exchange_down(temp_db):
    sf = _sf()
    call_count = [0]
    def side_effect(url, **kwargs):
        call_count[0] += 1
        if "binance" in url:
            raise requests.exceptions.ConnectionError("binance down")
        mock = MagicMock()
        mock.raise_for_status.return_value = None
        if "BTC-USD" in url:
            mock.json.return_value = {"data": {"amount": "42360.00"}}
        elif "ETH-USD" in url:
            mock.json.return_value = {"data": {"amount": "2852.00"}}
        return mock
    with patch("requests.get", side_effect=side_effect):
        signals = sf.fetch()
    btc = [s for s in signals if s["ticker"] == "SPOT:BTC"]
    assert len(btc) == 1
    assert btc[0]["amount_usd"] == pytest.approx(42360.0)  # Coinbase only


def test_get_spot_dict(temp_db):
    sf = _sf()
    with patch("requests.get", side_effect=_mock_binance()):
        sf.fetch()  # populate cache
    result = sf.get_spot_dict()
    assert "BTC" in result
    assert "ETH" in result
    assert isinstance(result["BTC"], float)
    assert result["BTC"] > 0


def test_cache_freshness(temp_db):
    sf = _sf()
    # Seed cache via fetch
    with patch("requests.get", side_effect=_mock_binance()):
        sf.fetch()
    # Second fetch should use cache (no HTTP)
    with patch("requests.get", side_effect=AssertionError("should not hit API")):
        signals = sf.fetch()
    assert len(signals) >= 2


def test_signal_dict_shape(temp_db):
    sf = _sf()
    with patch("requests.get", side_effect=_mock_binance()):
        signals = sf.fetch()
    required = {"source", "ticker", "signal_type", "direction", "amount_usd", "description", "fetched_at"}
    for s in signals:
        assert required.issubset(s.keys()), f"Missing keys: {required - set(s.keys())}"
