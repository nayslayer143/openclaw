"""
Polymarket API client for Inspector Gadget.

Thin HTTP wrapper around two Polymarket endpoints:
- Gamma API (market metadata + resolution): https://gamma-api.polymarket.com
- CLOB API (price history): https://clob.polymarket.com

All methods return None on any failure — callers mark trades UNVERIFIABLE
rather than crashing. Never raises.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"


def _validate_price(price: Any) -> bool:
    """Return True if price is a float in [0.0, 1.0], False on any error."""
    try:
        v = float(price)
        return 0.0 <= v <= 1.0
    except (TypeError, ValueError):
        return False


class PolymarketClient:
    """HTTP client for Polymarket APIs used exclusively by Inspector Gadget."""

    def __init__(self) -> None:
        self._client = httpx.Client(timeout=15, follow_redirects=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_market(self, market_id: str) -> Optional[Dict]:
        """
        Fetch market metadata from Gamma API.

        GET /markets?id={market_id}

        Returns the first item if the response is a list, the dict itself
        if the response is an object, or None on 404 / empty / any error.
        """
        try:
            resp = self._client.get(
                f"{GAMMA_BASE}/markets",
                params={"id": market_id},
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                return data[0] if data else None
            if isinstance(data, dict):
                return data
            return None
        except Exception:
            return None

    def get_price_history(
        self, condition_id: str, start_ts: int, end_ts: int
    ) -> Optional[List[Dict]]:
        """
        Fetch price history from CLOB API.

        GET /prices-history?market={condition_id}&startTs={start_ts}&endTs={end_ts}&fidelity=60

        Returns list of {t: int, p: float} dicts from data["history"],
        or None if status != 200 or any error.
        """
        try:
            resp = self._client.get(
                f"{CLOB_BASE}/prices-history",
                params={
                    "market": condition_id,
                    "startTs": start_ts,
                    "endTs": end_ts,
                    "fidelity": 60,
                },
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            if not isinstance(data, dict):
                return None
            return data.get("history")
        except Exception:
            return None

    def get_price_at(self, condition_id: str, timestamp_iso: str) -> Optional[float]:
        """
        Return the market price at a given ISO timestamp.

        Converts the ISO timestamp to unix ts, fetches a ±1 hour window via
        get_price_history, and returns the price p from the closest {t, p}
        point to the target timestamp.

        Returns None if no history is available, or if the closest price is
        outside [0.0, 1.0].
        """
        try:
            # Normalise ISO string: strip trailing Z / handle +00:00
            ts_str = timestamp_iso.replace("Z", "+00:00")
            target_ts = int(datetime.fromisoformat(ts_str).timestamp())
        except Exception:
            return None

        window = 3600  # ±1 hour
        history = self.get_price_history(
            condition_id,
            start_ts=target_ts - window,
            end_ts=target_ts + window,
        )
        if not history:
            return None

        try:
            closest = min(history, key=lambda point: abs(point["t"] - target_ts))
            price = closest["p"]
        except Exception:
            return None

        if not _validate_price(price):
            return None
        return float(price)

    def close(self):
        """Close the underlying HTTP connection pool."""
        self._client.close()

    def get_resolution(self, condition_id: str) -> Optional[Dict]:
        """
        Return resolution metadata for a market.

        Calls get_market(condition_id) and returns a normalised dict:
            {"closed": bool, "resolution": str|None, "end_date": str|None, "question": str|None}

        Returns None if the market is not found.
        """
        market = self.get_market(condition_id)
        if market is None:
            return None

        return {
            "closed": bool(market.get("closed")),
            "resolution": market.get("resolution"),
            "end_date": market.get("endDate"),
            "question": market.get("question"),
        }
