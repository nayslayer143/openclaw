"""
Tests for Inspector Gadget — Kalshi API Client.
All tests use mocks — no live API calls or real credentials.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, mock_open

from inspector.kalshi_client import KalshiClient, _validate_price


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_client_with_mock_http():
    """Create a KalshiClient with mocked HTTP and fake auth."""
    client = KalshiClient.__new__(KalshiClient)
    client._api_key_id = "test-key-id"
    client._private_key = MagicMock()  # mock RSA key
    client._base_url = "https://test-api.kalshi.com/trade-api/v2"
    client._client = MagicMock()
    # Make _sign_request return valid headers
    client._private_key.sign = MagicMock(return_value=b"fakesignature")
    return client


# ---------------------------------------------------------------------------
# _validate_price tests
# ---------------------------------------------------------------------------

def test_validate_price_valid():
    assert _validate_price(0.5) is True
    assert _validate_price(0.0) is True
    assert _validate_price(1.0) is True


def test_validate_price_invalid():
    assert _validate_price(-0.1) is False
    assert _validate_price(1.1) is False
    assert _validate_price(None) is False
    assert _validate_price("abc") is False


# ---------------------------------------------------------------------------
# get_market tests
# ---------------------------------------------------------------------------

def test_get_market_returns_market_dict():
    client = _make_client_with_mock_http()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "market": {
            "ticker": "KXBTC-26MAR2817-B66425",
            "title": "Will Bitcoin be above $66,425?",
            "status": "open",
            "result": None,
            "close_time": "2026-03-28T17:00:00Z",
        }
    }
    client._client.get.return_value = mock_resp

    result = client.get_market("KXBTC-26MAR2817-B66425")
    assert result is not None
    assert result["ticker"] == "KXBTC-26MAR2817-B66425"
    assert result["status"] == "open"


def test_get_market_returns_none_on_404():
    client = _make_client_with_mock_http()
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    client._client.get.return_value = mock_resp

    result = client.get_market("KXFAKE-NONEXIST")
    assert result is None


def test_get_market_returns_none_when_no_credentials():
    client = KalshiClient.__new__(KalshiClient)
    client._api_key_id = ""
    client._private_key = None
    client._base_url = "https://test-api.kalshi.com/trade-api/v2"
    client._client = MagicMock()

    result = client.get_market("KXBTC-26MAR2817-B66425")
    assert result is None
    # HTTP client should NOT have been called
    client._client.get.assert_not_called()


def test_get_market_returns_none_on_exception():
    client = _make_client_with_mock_http()
    client._client.get.side_effect = Exception("connection timeout")

    result = client.get_market("KXBTC-26MAR2817-B66425")
    assert result is None


# ---------------------------------------------------------------------------
# get_price_history tests
# ---------------------------------------------------------------------------

def test_price_history_normalizes_cents_to_float():
    """Kalshi candlestick prices are in cents (0-100), should normalize to [0, 1]."""
    client = _make_client_with_mock_http()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "candlesticks": [
            {"end_period_ts": 1711296000, "price": 65, "volume": 100},
            {"end_period_ts": 1711296060, "price": 70, "volume": 50},
        ]
    }
    client._client.get.return_value = mock_resp

    result = client.get_price_history("KXBTC-TEST", 1711295000, 1711297000)
    assert result is not None
    assert len(result) == 2
    assert result[0]["p"] == 0.65
    assert result[1]["p"] == 0.70
    assert result[0]["t"] == 1711296000


def test_price_history_returns_none_on_empty():
    client = _make_client_with_mock_http()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"candlesticks": []}
    client._client.get.return_value = mock_resp

    result = client.get_price_history("KXBTC-TEST", 1711295000, 1711297000)
    assert result is None


# ---------------------------------------------------------------------------
# get_price_at tests
# ---------------------------------------------------------------------------

def test_get_price_at_returns_closest_price():
    client = _make_client_with_mock_http()

    target_ts = 1711296100
    # Mock get_price_history to return two points
    client.get_price_history = MagicMock(return_value=[
        {"t": 1711296000, "p": 0.65},   # 100s before target
        {"t": 1711296060, "p": 0.70},   # 40s before target (closer)
    ])

    result = client.get_price_at("KXBTC-TEST", "2026-03-24T18:01:40Z")
    assert result is not None
    assert result == 0.70  # closest to target


def test_get_price_at_returns_none_when_no_history():
    client = _make_client_with_mock_http()
    client.get_price_history = MagicMock(return_value=None)

    result = client.get_price_at("KXBTC-TEST", "2026-03-24T18:00:00Z")
    assert result is None


def test_get_price_at_returns_none_on_bad_timestamp():
    client = _make_client_with_mock_http()

    result = client.get_price_at("KXBTC-TEST", "not-a-timestamp")
    assert result is None


# ---------------------------------------------------------------------------
# get_resolution tests
# ---------------------------------------------------------------------------

def test_get_resolution_maps_yes():
    client = _make_client_with_mock_http()
    client.get_market = MagicMock(return_value={
        "ticker": "KXBTC-26MAR2817-B66425",
        "title": "Will Bitcoin be above $66,425?",
        "status": "finalized",
        "result": "yes",
        "close_time": "2026-03-28T17:00:00Z",
    })

    result = client.get_resolution("KXBTC-26MAR2817-B66425")
    assert result is not None
    assert result["closed"] is True
    assert result["resolution"] == "YES"
    assert result["question"] == "Will Bitcoin be above $66,425?"


def test_get_resolution_maps_no():
    client = _make_client_with_mock_http()
    client.get_market = MagicMock(return_value={
        "ticker": "KXBTC-TEST",
        "title": "Test market",
        "status": "finalized",
        "result": "no",
        "close_time": "2026-03-28T17:00:00Z",
    })

    result = client.get_resolution("KXBTC-TEST")
    assert result is not None
    assert result["closed"] is True
    assert result["resolution"] == "NO"


def test_get_resolution_unresolved():
    client = _make_client_with_mock_http()
    client.get_market = MagicMock(return_value={
        "ticker": "KXBTC-TEST",
        "title": "Test market",
        "status": "open",
        "result": None,
        "close_time": "2026-03-28T17:00:00Z",
    })

    result = client.get_resolution("KXBTC-TEST")
    assert result is not None
    assert result["closed"] is False
    assert result["resolution"] is None


def test_get_resolution_returns_none_when_market_missing():
    client = _make_client_with_mock_http()
    client.get_market = MagicMock(return_value=None)

    result = client.get_resolution("KXFAKE-NONEXIST")
    assert result is None


# ---------------------------------------------------------------------------
# Auth header tests
# ---------------------------------------------------------------------------

def test_sign_request_produces_valid_headers():
    client = _make_client_with_mock_http()

    headers = client._sign_request("GET", "/markets/KXBTC-TEST")
    assert headers is not None
    assert "KALSHI-ACCESS-KEY" in headers
    assert headers["KALSHI-ACCESS-KEY"] == "test-key-id"
    assert "KALSHI-ACCESS-TIMESTAMP" in headers
    assert "KALSHI-ACCESS-SIGNATURE" in headers
    assert headers["Content-Type"] == "application/json"
    # Timestamp should be a numeric string
    assert headers["KALSHI-ACCESS-TIMESTAMP"].isdigit()


def test_sign_request_returns_none_without_credentials():
    client = KalshiClient.__new__(KalshiClient)
    client._api_key_id = ""
    client._private_key = None

    headers = client._sign_request("GET", "/markets/KXBTC-TEST")
    assert headers is None
