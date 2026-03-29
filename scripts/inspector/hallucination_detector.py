"""
Inspector Gadget — Hallucination Detector (Task 6).

Detects when LLM trading decisions are based on hallucinated price data.
V1 scope: verify price/market-existence claims against Polymarket only
(no news API).

Grounding levels:
  GROUNDED           — claimed price within ±5 cents of actual
  PARTIALLY_GROUNDED — delta 5-15 cents
  HALLUCINATED       — delta > 15 cents
  UNVERIFIABLE       — no historical price data available
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from inspector.inspector_db import InspectorDB
from inspector.kalshi_client import KalshiClient
from inspector.polymarket_client import PolymarketClient

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PRICE_GROUNDED_TOL  = 0.05   # ±5 cents → GROUNDED
PRICE_PARTIAL_TOL   = 0.15   # 5-15 cents → PARTIALLY_GROUNDED; >15 → HALLUCINATED


# ---------------------------------------------------------------------------
# GroundingResult enum
# ---------------------------------------------------------------------------

class GroundingResult(str, Enum):
    GROUNDED           = "GROUNDED"
    PARTIALLY_GROUNDED = "PARTIALLY_GROUNDED"
    HALLUCINATED       = "HALLUCINATED"
    UNVERIFIABLE       = "UNVERIFIABLE"


# ---------------------------------------------------------------------------
# HallucinationDetector
# ---------------------------------------------------------------------------

class HallucinationDetector:
    def __init__(self, db: InspectorDB, poly: PolymarketClient, kalshi: Optional[KalshiClient] = None) -> None:
        self.db = db
        self.poly = poly
        self.kalshi = kalshi

    # ------------------------------------------------------------------
    # Core grounding checks (pure — no DB writes)
    # ------------------------------------------------------------------

    def _check_price_claim_with_value(
        self,
        market_id: str,
        claimed_price: float,
        timestamp_iso: str,
    ):
        """Returns (GroundingResult, actual_price_or_None)"""
        if market_id.startswith("KX") and self.kalshi is not None:
            actual = self.kalshi.get_price_at(market_id, timestamp_iso)
        else:
            actual = self.poly.get_price_at(market_id, timestamp_iso)
        if actual is None:
            return GroundingResult.UNVERIFIABLE, None

        delta = abs(actual - claimed_price)
        if delta <= PRICE_GROUNDED_TOL:
            return GroundingResult.GROUNDED, actual
        if delta <= PRICE_PARTIAL_TOL:
            return GroundingResult.PARTIALLY_GROUNDED, actual
        return GroundingResult.HALLUCINATED, actual

    def check_price_claim(
        self,
        market_id: str,
        claimed_price: float,
        timestamp_iso: str,
    ) -> GroundingResult:
        """
        Verify a claimed price against Polymarket historical data at the
        given timestamp.

        Returns:
          GROUNDED           if delta <= PRICE_GROUNDED_TOL
          PARTIALLY_GROUNDED if delta <= PRICE_PARTIAL_TOL
          HALLUCINATED       if delta > PRICE_PARTIAL_TOL
          UNVERIFIABLE       if no historical price is available
        """
        result, _ = self._check_price_claim_with_value(market_id, claimed_price, timestamp_iso)
        return result

    def check_market_existence(self, market_id: str) -> GroundingResult:
        """
        Verify that the referenced market exists on the relevant exchange.

        Returns GROUNDED if found, HALLUCINATED if not.
        """
        if market_id.startswith("KX") and self.kalshi is not None:
            info = self.kalshi.get_market(market_id)
        else:
            info = self.poly.get_market(market_id)
        if info is None:
            return GroundingResult.HALLUCINATED
        return GroundingResult.GROUNDED

    # ------------------------------------------------------------------
    # Scoring helper
    # ------------------------------------------------------------------

    @staticmethod
    def _score(result: GroundingResult) -> float:
        """Convert a GroundingResult to a numeric score."""
        _scores = {
            GroundingResult.GROUNDED:           1.0,
            GroundingResult.PARTIALLY_GROUNDED: 0.5,
            GroundingResult.HALLUCINATED:       0.0,
            GroundingResult.UNVERIFIABLE:      -1.0,
        }
        return _scores[result]

    # ------------------------------------------------------------------
    # Run methods
    # ------------------------------------------------------------------

    def run_on_signals(self, signals_json_path: str) -> dict:
        """
        Load a signals JSON file, check each signal's price claim, and
        insert results to hallucination_checks.

        Returns {"checked": N, "counts": {result_name: count}}.
        Returns {"error": "not found", "checked": 0} if file does not exist.
        """
        path = Path(signals_json_path).expanduser()
        if not path.exists():
            return {"error": "not found", "checked": 0}

        try:
            signals = json.loads(path.read_text())
        except Exception as exc:
            return {"error": str(exc), "checked": 0}

        if not isinstance(signals, list):
            signals = [signals]

        counts: Dict[str, int] = {}
        checked = 0

        for signal in signals:
            try:
                # Defensive field extraction
                market_id = (
                    signal.get("market_id")
                    or signal.get("id")
                    or ""
                )
                claimed_price = (
                    signal.get("current_yes_price")
                    if signal.get("current_yes_price") is not None
                    else signal.get("estimated_true_prob")
                )
                scan_time = (
                    signal.get("scan_time")
                    or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                )

                if not market_id or claimed_price is None:
                    continue

                result, actual_value = self._check_price_claim_with_value(market_id, float(claimed_price), scan_time)
                score = self._score(result)

                self.db.insert("hallucination_checks", {
                    "signal_id":           str(market_id),
                    "claim_type":          "price",
                    "claim_content":       str(claimed_price),
                    "verification_result": result.value,
                    "grounding_score":     score,
                    "actual_value":        actual_value,
                    "checked_at":          datetime.now(timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    ),
                })
                counts[result.value] = counts.get(result.value, 0) + 1
                checked += 1
            except Exception:
                continue

        return {"checked": checked, "counts": counts}

    def run_on_llm_trades(self, clawmson_db_path: str, trade_query: Optional[str] = None) -> dict:
        """
        Read paper_trades with LLM strategy or non-empty reasoning from
        clawmson.db, check each price claim, and insert to hallucination_checks.

        Uses try/finally for the DB connection and per-trade try/except in loop.
        """
        db_path = str(Path(clawmson_db_path).expanduser())
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            if trade_query:
                all_rows = conn.execute(trade_query).fetchall()
                trades = [t for t in all_rows
                          if (dict(t).get("strategy") or "").lower().find("llm") >= 0
                          or (dict(t).get("reasoning") or "")]
            else:
                trades = conn.execute(
                    "SELECT * FROM paper_trades "
                    "WHERE strategy LIKE '%llm%' OR (reasoning IS NOT NULL AND reasoning != '')"
                ).fetchall()
            trades = [dict(t) for t in trades]
        finally:
            conn.close()

        counts: Dict[str, int] = {}
        checked = 0
        errors = 0

        for trade in trades:
            try:
                market_id   = trade.get("market_id", "") or ""
                entry_price = trade.get("entry_price")
                opened_at   = trade.get("opened_at", "") or datetime.now(
                    timezone.utc
                ).strftime("%Y-%m-%dT%H:%M:%SZ")

                if not market_id or entry_price is None:
                    continue

                result, actual_value = self._check_price_claim_with_value(market_id, float(entry_price), opened_at)
                score = self._score(result)

                self.db.insert("hallucination_checks", {
                    "trade_id":            str(trade.get("id", "")),
                    "claim_type":          "entry_price",
                    "claim_content":       str(entry_price),
                    "verification_result": result.value,
                    "grounding_score":     score,
                    "actual_value":        actual_value,
                    "checked_at":          datetime.now(timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    ),
                })
                counts[result.value] = counts.get(result.value, 0) + 1
                checked += 1
            except Exception:
                errors += 1
                continue

        return {"checked": checked, "counts": counts, "errors": errors}
