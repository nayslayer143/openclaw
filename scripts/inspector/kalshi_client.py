"""
Kalshi API client for Inspector Gadget.

Authenticated HTTP wrapper around Kalshi's Trade API v2.
Mirrors the PolymarketClient interface: get_market, get_price_at,
get_resolution, close.  All methods return None on any failure.

Auth uses RSA-signed request headers (same pattern as rivalclaw/kalshi_feed.py).
"""

from __future__ import annotations

import base64
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROD_API = "https://api.elections.kalshi.com/trade-api/v2"
DEMO_API = "https://demo-api.kalshi.co/trade-api/v2"


def _validate_price(price: Any) -> bool:
    """Return True if price is a float in [0.0, 1.0]."""
    try:
        v = float(price)
        return 0.0 <= v <= 1.0
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# KalshiClient
# ---------------------------------------------------------------------------

class KalshiClient:
    """HTTP client for Kalshi Trade API v2 with RSA authentication."""

    def __init__(
        self,
        api_key_id: Optional[str] = None,
        private_key_path: Optional[str] = None,
        api_env: Optional[str] = None,
    ) -> None:
        self._api_key_id = api_key_id or os.environ.get("KALSHI_API_KEY_ID", "")
        pk_path = private_key_path or os.environ.get("KALSHI_PRIVATE_KEY_PATH", "")
        env = (api_env or os.environ.get("KALSHI_API_ENV", "demo")).lower()
        self._base_url = PROD_API if env == "prod" else DEMO_API
        self._private_key = self._load_key(pk_path)
        self._client = httpx.Client(timeout=30, follow_redirects=True)

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_key(path: str) -> Any:
        """Load RSA private key from PEM file. Returns None on failure."""
        if not path or not Path(path).exists():
            return None
        try:
            from cryptography.hazmat.primitives.serialization import load_pem_private_key

            with open(path, "rb") as f:
                return load_pem_private_key(f.read(), password=None)
        except Exception:
            return None

    def _sign_request(self, method: str, path: str) -> Optional[Dict[str, str]]:
        """Build auth headers for a Kalshi API request."""
        if not self._api_key_id or self._private_key is None:
            return None
        try:
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import padding

            timestamp_str = str(int(time.time() * 1000))
            message = (timestamp_str + method.upper() + path).encode("utf-8")
            signature = self._private_key.sign(
                message, padding.PKCS1v15(), hashes.SHA256()
            )
            return {
                "KALSHI-ACCESS-KEY": self._api_key_id,
                "KALSHI-ACCESS-TIMESTAMP": timestamp_str,
                "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode("utf-8"),
                "Content-Type": "application/json",
            }
        except Exception:
            return None

    # ------------------------------------------------------------------
    # HTTP helper
    # ------------------------------------------------------------------

    def _get(self, path: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Authenticated GET. Returns parsed JSON dict or None."""
        headers = self._sign_request("GET", path)
        if headers is None:
            return None
        try:
            resp = self._client.get(
                self._base_url + path, params=params, headers=headers
            )
            if resp.status_code != 200:
                return None
            return resp.json()
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Public API — mirrors PolymarketClient interface
    # ------------------------------------------------------------------

    def get_market(self, ticker: str) -> Optional[Dict]:
        """
        Fetch market metadata from Kalshi.

        GET /markets/{ticker}

        Returns the market dict, or None on 404 / auth failure / any error.
        """
        data = self._get(f"/markets/{ticker}")
        if data is None:
            return None
        # Kalshi wraps in {"market": {...}}
        if isinstance(data, dict) and "market" in data:
            return data["market"]
        return data

    def get_price_history(
        self, ticker: str, start_ts: int, end_ts: int
    ) -> Optional[List[Dict]]:
        """
        Fetch candlestick price history from Kalshi.

        GET /markets/{ticker}/candlesticks?start_ts=...&end_ts=...&period_interval=1

        Returns list of {"t": unix_ts, "p": float_price} dicts with prices
        normalised to [0.0, 1.0].  Returns None if no data or any error.
        """
        data = self._get(
            f"/markets/{ticker}/candlesticks",
            params={
                "start_ts": start_ts,
                "end_ts": end_ts,
                "period_interval": 1,
            },
        )
        if not data:
            return None

        candles = data.get("candlesticks", [])
        if not candles:
            return None

        result: List[Dict] = []
        for c in candles:
            ts = c.get("end_period_ts")
            # Kalshi v2 candlestick prices are in cents (0-100)
            raw_price = c.get("price") or c.get("yes_price")
            if ts is None or raw_price is None:
                continue
            try:
                price = float(raw_price) / 100.0
            except (TypeError, ValueError):
                continue
            if _validate_price(price):
                result.append({"t": int(ts), "p": price})

        return result if result else None

    def get_price_at(self, ticker: str, timestamp_iso: str) -> Optional[float]:
        """
        Return the market price at a given ISO timestamp.

        Fetches a ±1 hour window of candlestick data and returns the price
        from the closest data point.  Returns None if no history available.
        """
        try:
            ts_str = timestamp_iso.replace("Z", "+00:00")
            target_ts = int(datetime.fromisoformat(ts_str).timestamp())
        except Exception:
            return None

        window = 3600  # ±1 hour
        history = self.get_price_history(
            ticker,
            start_ts=target_ts - window,
            end_ts=target_ts + window,
        )
        if not history:
            return None

        try:
            closest = min(history, key=lambda pt: abs(pt["t"] - target_ts))
            price = closest["p"]
        except Exception:
            return None

        if not _validate_price(price):
            return None
        return float(price)

    def get_resolution(self, ticker: str) -> Optional[Dict]:
        """
        Return resolution metadata for a Kalshi market.

        Returns {"closed": bool, "resolution": str|None, "end_date": str|None,
                 "question": str|None} or None if market not found.
        """
        market = self.get_market(ticker)
        if market is None:
            return None

        status = (market.get("status") or "").lower()
        raw_result = market.get("result")

        # Map Kalshi result strings to Inspector format
        resolution: Optional[str] = None
        if raw_result is not None:
            r = str(raw_result).lower()
            if r == "yes":
                resolution = "YES"
            elif r == "no":
                resolution = "NO"
            # else: None (unknown, cancelled, etc.)

        return {
            "closed": status in ("closed", "settled", "finalized"),
            "resolution": resolution,
            "end_date": market.get("close_time") or market.get("expiration_time"),
            "question": market.get("title"),
        }

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._client.close()
