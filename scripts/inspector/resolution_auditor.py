"""
Inspector Gadget — Resolution Auditor (Task 4).

For every CLOSED paper trade in clawmson.db, verifies:
  1. Fetches actual Polymarket market resolution via the API
  2. Checks if the bot's claimed win/loss matches the actual market outcome
  3. Recalculates P&L from scratch: (exit_price - entry_price) * shares
  4. Compares recalculated P&L vs what the bot reported

Results written to resolution_audits table in inspector_gadget.db.

Match values (INTEGER):
  1  = resolution matches claim (VERIFIED)
  0  = resolution contradicts claim (MISMATCH — red flag)
 -1  = unverifiable (market not resolved yet, or not found)
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from inspector.inspector_db import InspectorDB
from inspector.kalshi_client import KalshiClient
from inspector.polymarket_client import PolymarketClient

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CLOSED_STATUSES = frozenset({"closed_win", "closed_loss", "expired"})


# ---------------------------------------------------------------------------
# Module-level resolution logic (pure function, easy to test in isolation)
# ---------------------------------------------------------------------------

def _resolution_matches(direction: str, bot_status: str, actual_resolution: str) -> bool:
    """
    Return True if the bot's claimed outcome matches the actual market resolution.

    Rules:
    - expired           → always True (expirations aren't resolution-dependent)
    - YES + closed_win  → matches if actual == "YES"
    - YES + closed_loss → matches if actual == "NO"
    - NO  + closed_win  → matches if actual == "NO"
    - NO  + closed_loss → matches if actual == "YES"
    - any other combo   → False
    """
    if bot_status == "expired":
        return True
    if direction == "YES" and bot_status == "closed_win":
        return actual_resolution == "YES"
    if direction == "YES" and bot_status == "closed_loss":
        return actual_resolution == "NO"
    if direction == "NO" and bot_status == "closed_win":
        return actual_resolution == "NO"
    if direction == "NO" and bot_status == "closed_loss":
        return actual_resolution == "YES"
    return False


# ---------------------------------------------------------------------------
# ResolutionAuditor
# ---------------------------------------------------------------------------

class ResolutionAuditor:
    def __init__(self, db: InspectorDB, poly: PolymarketClient, kalshi: Optional[KalshiClient] = None) -> None:
        self.db = db
        self.poly = poly
        self.kalshi = kalshi

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _recalc_pnl(self, trade: dict) -> Optional[float]:
        """Return (exit_price - entry_price) * shares, or None if any value is missing."""
        exit_price  = trade.get("exit_price")
        entry_price = trade.get("entry_price")
        shares      = trade.get("shares")
        if exit_price is None or entry_price is None or shares is None:
            return None
        return (exit_price - entry_price) * shares

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def audit_trade(self, trade: dict) -> Optional[dict]:
        """
        Audit a single trade's resolution claim.

        Returns None for open trades (status not in CLOSED_STATUSES).
        Returns a result dict ready for insertion into resolution_audits.
        """
        status = trade.get("status", "")
        if status not in CLOSED_STATUSES:
            return None

        market_id  = trade.get("market_id", "")
        direction  = trade.get("direction", "")
        claimed_pnl = trade.get("pnl")

        # Route to the correct exchange client
        if market_id.startswith("0x"):
            resolution_data = self.poly.get_resolution(market_id)
        elif market_id.startswith("KX") and self.kalshi is not None:
            resolution_data = self.kalshi.get_resolution(market_id)
        else:
            resolution_data = None

        if resolution_data is None:
            match = -1
            actual_resolution = "NOT_FOUND"
        else:
            actual_resolution = resolution_data.get("resolution")
            closed = resolution_data.get("closed", False)

            if not closed or actual_resolution is None:
                match = -1
                actual_resolution = "UNRESOLVED"
            elif actual_resolution not in ("YES", "NO"):
                # Unknown resolution (cancelled, N/A, etc.) — unverifiable, not a mismatch
                match = -1
                # actual_resolution already holds the raw value; preserve it
            else:
                match = 1 if _resolution_matches(direction, status, actual_resolution) else 0

        # Recalculate P&L independently
        recalculated_pnl = self._recalc_pnl(trade)

        # Compute delta only when both values are present
        pnl_delta: Optional[float] = None
        if recalculated_pnl is not None and claimed_pnl is not None:
            pnl_delta = abs(recalculated_pnl - claimed_pnl)

        checked_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        return {
            "trade_id":            str(trade.get("id", "")),
            "market_id":           market_id,
            "claimed_resolution":  status,
            "actual_resolution":   actual_resolution,
            "match":               match,
            "recalculated_pnl":    recalculated_pnl,
            "claimed_pnl":         claimed_pnl,
            "pnl_delta":           pnl_delta,
            "checked_at":          checked_at,
        }

    def run(self, clawmson_db_path: str) -> dict:
        """
        Read closed paper_trades from clawmson_db_path, audit each for resolution
        accuracy, write results to resolution_audits, and return a summary dict.
        """
        db_path = str(Path(clawmson_db_path).expanduser())
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            trades = conn.execute(
                "SELECT * FROM paper_trades WHERE status IN ('closed_win','closed_loss','expired')"
            ).fetchall()
        finally:
            conn.close()

        total_closed = len(trades)
        matched = 0
        mismatched = 0
        unverifiable = 0
        errors = 0

        for trade in trades:
            try:
                result = self.audit_trade(dict(trade))
                if result is None:
                    continue
                self.db.insert("resolution_audits", result)
                if result["match"] == 1:
                    matched += 1
                elif result["match"] == 0:
                    mismatched += 1
                else:
                    unverifiable += 1
            except Exception:
                errors += 1
                continue

        return {
            "total_closed": total_closed,
            "matched":      matched,
            "mismatched":   mismatched,
            "unverifiable": unverifiable,
            "errors":       errors,
        }
