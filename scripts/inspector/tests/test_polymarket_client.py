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
    client = PolymarketClient()
    history = [{"t": 1000, "p": 0.45}, {"t": 2000, "p": 0.50}, {"t": 3000, "p": 0.55}]
    with patch.object(client, 'get_price_history', return_value=history):
        # Target ts will be somewhere near t=2000
        with patch('inspector.polymarket_client.datetime') as mock_dt:
            mock_dt.fromisoformat.return_value.timestamp.return_value = 1950
            result = client.get_price_at("0xABC", "2026-03-24T10:00:00")
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
