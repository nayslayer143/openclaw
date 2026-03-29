"""
Inspector Gadget — Trade Verifier (Task 3).

For every paper trade in clawmson.db, verifies:
  1. Math consistency: shares * entry_price ≈ amount_usd
  2. Market existence on Polymarket
  3. Entry price against Polymarket historical data

Assigns status: VERIFIED, DISCREPANCY, IMPOSSIBLE, or UNVERIFIABLE.
Results written to verified_trades table in inspector_gadget.db.
"""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from inspector.inspector_db import InspectorDB
from inspector.kalshi_client import KalshiClient
from inspector.polymarket_client import PolymarketClient

# ---------------------------------------------------------------------------
# Tolerances
# ---------------------------------------------------------------------------

AMOUNT_TOL = 0.015   # 1.5% combined tolerance for shares*price vs amount_usd
PRICE_TOL  = 0.02    # ±2 cents price tolerance vs historical


# ---------------------------------------------------------------------------
# Status enum
# ---------------------------------------------------------------------------

class VerificationStatus(str, Enum):
    VERIFIED      = "VERIFIED"
    DISCREPANCY   = "DISCREPANCY"
    IMPOSSIBLE    = "IMPOSSIBLE"
    UNVERIFIABLE  = "UNVERIFIABLE"


# ---------------------------------------------------------------------------
# TradeVerifier
# ---------------------------------------------------------------------------

class TradeVerifier:
    def __init__(self, db: InspectorDB, poly: PolymarketClient, kalshi: Optional[KalshiClient] = None) -> None:
        self.db = db
        self.poly = poly
        self.kalshi = kalshi

    # ------------------------------------------------------------------
    # Internal checks
    # ------------------------------------------------------------------

    def _check_math(self, trade: dict) -> dict:
        """Verify shares * entry_price ≈ amount_usd."""
        shares      = trade.get("shares", 0) or 0
        entry_price = trade.get("entry_price", 0) or 0
        amount_usd  = trade.get("amount_usd", 0) or 0

        if shares <= 0:
            return {
                "status": VerificationStatus.IMPOSSIBLE,
                "detail": f"Negative/zero shares: {shares}",
            }

        if not (0.0 < entry_price <= 1.0):
            return {
                "status": VerificationStatus.IMPOSSIBLE,
                "detail": f"Price out of range: {entry_price}",
            }

        if amount_usd <= 0:
            return {
                "status": VerificationStatus.IMPOSSIBLE,
                "detail": f"Non-positive amount: {amount_usd}",
            }

        expected  = shares * entry_price
        delta_pct = abs(expected - amount_usd) / max(amount_usd, 0.001)

        if delta_pct > AMOUNT_TOL:
            return {
                "status": VerificationStatus.DISCREPANCY,
                "detail": (
                    f"Math mismatch: {shares}*{entry_price}={expected:.4f} "
                    f"vs claimed {amount_usd:.4f} ({delta_pct * 100:.1f}%)"
                ),
            }

        return {"status": VerificationStatus.VERIFIED, "detail": "Math OK"}

    def _check_price(self, trade: dict) -> dict:
        """Verify entry price against Polymarket historical data."""
        market_id   = trade.get("market_id", "")
        entry_price = trade.get("entry_price", 0) or 0
        opened_at   = trade.get("opened_at", "")

        # Route to the correct exchange client based on market ID prefix
        if market_id.startswith("0x"):
            client = self.poly
            exchange = "Polymarket"
        elif market_id.startswith("KX") and self.kalshi is not None:
            client = self.kalshi
            exchange = "Kalshi"
        else:
            return {
                "status": VerificationStatus.UNVERIFIABLE,
                "detail": f"Market {market_id} has no supported exchange client",
            }

        market = client.get_market(market_id)
        if market is None:
            return {
                "status": VerificationStatus.IMPOSSIBLE,
                "detail": f"Market {market_id} not found on {exchange}",
            }

        hist_price = client.get_price_at(market_id, opened_at)
        if hist_price is None:
            return {
                "status": VerificationStatus.UNVERIFIABLE,
                "detail": "No historical price data available",
            }

        delta = abs(hist_price - entry_price)
        if delta > PRICE_TOL:
            return {
                "status": VerificationStatus.DISCREPANCY,
                "detail": (
                    f"Price claim {entry_price} vs actual {hist_price:.4f} "
                    f"(Δ={delta:.4f})"
                ),
            }

        return {
            "status": VerificationStatus.VERIFIED,
            "detail": f"Price OK: claimed {entry_price}, actual {hist_price:.4f}",
            "verified_price": hist_price,
        }

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def verify_trade(self, trade: dict) -> dict:
        """
        Run math and price checks. Returns a result dict ready for
        insertion into the verified_trades table.

        Worst-status wins: IMPOSSIBLE > DISCREPANCY > UNVERIFIABLE > VERIFIED
        """
        math_result  = self._check_math(trade)
        price_result = self._check_price(trade)

        # Severity order: IMPOSSIBLE (3) > DISCREPANCY (2) > UNVERIFIABLE (1) > VERIFIED (0)
        # max() picks highest severity — worst status wins.
        priority = [
            VerificationStatus.VERIFIED,
            VerificationStatus.UNVERIFIABLE,
            VerificationStatus.DISCREPANCY,
            VerificationStatus.IMPOSSIBLE,
        ]
        final: VerificationStatus = max(
            math_result["status"],
            price_result["status"],
            key=lambda s: priority.index(s),
        )

        # Gather optional fields
        verified_entry: Optional[float] = price_result.get("verified_price")
        exit_price     = trade.get("exit_price")
        shares         = trade.get("shares")
        claimed_pnl    = trade.get("pnl")

        # Only compute verified_pnl when we have the actual verified entry price.
        # If price was DISCREPANCY or UNVERIFIABLE, leave verified_pnl as None
        # so discrepancy_amount reflects the unknown gap, not a false zero.
        verified_pnl: Optional[float] = None
        if exit_price is not None and shares is not None:
            if verified_entry is not None:
                verified_pnl = (exit_price - verified_entry) * shares

        discrepancy_amount: Optional[float] = None
        if claimed_pnl is not None and verified_pnl is not None:
            discrepancy_amount = abs(claimed_pnl - verified_pnl)

        discrepancy_detail = (
            f"Math: {math_result['detail']} | Price: {price_result['detail']}"
        )

        checked_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        return {
            "trade_id":           str(trade["id"]),
            "bot_source":         trade.get("strategy") or "unknown",
            "market_id":          trade.get("market_id"),
            "direction":          trade.get("direction"),
            "claimed_entry":      trade.get("entry_price"),
            "verified_entry":     verified_entry,
            "claimed_exit":       exit_price,
            "verified_exit":      None,          # resolution auditor handles this
            "claimed_pnl":        claimed_pnl,
            "verified_pnl":       verified_pnl,
            "claimed_amount":     trade.get("amount_usd"),
            "status":             final.value,
            "discrepancy_amount": discrepancy_amount,
            "discrepancy_detail": discrepancy_detail,
            "checked_at":         checked_at,
        }

    def run(self, clawmson_db_path: str, trade_query: Optional[str] = None) -> dict:
        """
        Read all paper_trades from clawmson_db_path, verify each, write
        results to verified_trades, and return a summary dict.
        """
        from pathlib import Path
        conn = sqlite3.connect(str(Path(clawmson_db_path).expanduser()))
        conn.row_factory = sqlite3.Row
        query = trade_query or "SELECT * FROM paper_trades"
        trades = conn.execute(query).fetchall()
        conn.close()

        counts = {s.value: 0 for s in VerificationStatus}
        errors = 0
        for trade in trades:
            try:
                result = self.verify_trade(dict(trade))
                self.db.insert("verified_trades", result)
                counts[result["status"]] += 1
                # Rate-limit API calls (Kalshi 429 protection)
                time.sleep(0.05)
            except Exception:
                errors += 1
                continue

        return {"total": len(trades), "counts": counts, "errors": errors}
