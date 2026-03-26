"""Tests for Inspector Gadget Polymarket API client."""
from unittest.mock import patch, MagicMock

from inspector.polymarket_client import PolymarketClient, _validate_price


def test_validate_price_in_range():
    assert _validate_price(0.5) is True
    assert _validate_price(0.0) is True
    assert _validate_price(1.0) is True


def test_validate_price_out_of_range():
    assert _validate_price(1.1) is False
    assert _validate_price(-0.1) is False
    assert _validate_price("bad") is False


def test_get_market_returns_none_on_404():
    client = PolymarketClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.raise_for_status.side_effect = Exception("404")
    with patch.object(client._client, 'get', return_value=mock_resp):
        result = client.get_market("0xDEAD")
    assert result is None


def test_get_market_returns_first_item_from_list():
    client = PolymarketClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = [{"id": "0xABC", "question": "Will X?", "closed": False}]
    with patch.object(client._client, 'get', return_value=mock_resp):
        result = client.get_market("0xABC")
    assert result["id"] == "0xABC"


def test_get_price_at_returns_none_when_no_history():
    client = PolymarketClient()
    with patch.object(client, 'get_price_history', return_value=None):
        result = client.get_price_at("0xABC", "2026-03-24T10:00:00")
    assert result is None


def test_get_price_at_returns_closest_price():
    from datetime import datetime, timezone
    client = PolymarketClient()
    # Use a real ISO timestamp and real unix timestamps near it
    target = datetime(2026, 3, 24, 10, 0, 0, tzinfo=timezone.utc)
    target_ts = int(target.timestamp())
    history = [
        {"t": target_ts - 600, "p": 0.45},   # 10 min before
        {"t": target_ts + 60,  "p": 0.50},   # 1 min after — closest
        {"t": target_ts + 900, "p": 0.55},   # 15 min after
    ]
    with patch.object(client, 'get_price_history', return_value=history):
        result = client.get_price_at("0xABC", "2026-03-24T10:00:00Z")
    assert result == 0.50


def test_get_resolution_wraps_market():
    client = PolymarketClient()
    with patch.object(client, 'get_market', return_value={
        "closed": True, "resolution": "YES", "endDate": "2026-03-25", "question": "Will X?"
    }):
        result = client.get_resolution("0xABC")
    assert result["closed"] is True
    assert result["resolution"] == "YES"


def test_get_resolution_returns_none_when_market_missing():
    client = PolymarketClient()
    with patch.object(client, 'get_market', return_value=None):
        result = client.get_resolution("0xDEAD")
    assert result is None


def test_get_price_at_returns_none_when_price_out_of_range():
    from datetime import datetime, timezone
    client = PolymarketClient()
    target = datetime(2026, 3, 24, 10, 0, 0, tzinfo=timezone.utc)
    target_ts = int(target.timestamp())
    # Price is 1.5 — out of [0, 1] range
    history = [{"t": target_ts + 30, "p": 1.5}]
    with patch.object(client, 'get_price_history', return_value=history):
        result = client.get_price_at("0xABC", "2026-03-24T10:00:00Z")
    assert result is None


def test_get_price_at_returns_none_on_malformed_history():
    client = PolymarketClient()
    # History entries missing required 't' and 'p' keys
    history = [{"wrong_key": 0}, {"also_wrong": "bad"}]
    with patch.object(client, 'get_price_history', return_value=history):
        result = client.get_price_at("0xABC", "2026-03-24T10:00:00Z")
    assert result is None


def test_get_market_returns_dict_directly():
    client = PolymarketClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"id": "0xABC", "question": "Will Y?", "closed": True}
    with patch.object(client._client, 'get', return_value=mock_resp):
        result = client.get_market("0xABC")
    assert result["question"] == "Will Y?"
