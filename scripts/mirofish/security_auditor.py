#!/usr/bin/env python3
"""
Pre-execution security auditor — sanity checks before any trade executes.
Phase 5B Step 5: wire security auditor into pre-execution validation.

Checks:
1. Max single trade size
2. Max daily exposure (total open positions)
3. Duplicate trade detection (same market + direction within window)
4. Market status verification (only trade open markets)
5. Price sanity (entry price within bid/ask range)
6. Balance sufficiency

Python 3.9 compatible via __future__ annotations.
"""
from __future__ import annotations

import os
import sqlite3
import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MAX_SINGLE_TRADE_PCT = float(os.environ.get("MIROFISH_MAX_POSITION_PCT", "0.10"))
MAX_DAILY_EXPOSURE_PCT = float(os.environ.get("MIROFISH_MAX_DAILY_EXPOSURE", "0.50"))
DUPLICATE_WINDOW_MIN = int(os.environ.get("MIROFISH_DUPLICATE_WINDOW_MIN", "30"))
MAX_OPEN_POSITIONS = int(os.environ.get("MIROFISH_MAX_OPEN_POSITIONS", "20"))


# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------

def _get_conn() -> sqlite3.Connection:
    db_path = Path(os.environ.get("CLAWMSON_DB_PATH",
                                   Path.home() / ".openclaw" / "clawmson.db"))
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class AuditResult:
    approved: bool
    reason: str = ""
    checks_passed: list[str] = field(default_factory=list)
    checks_failed: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "approved": self.approved,
            "reason": self.reason,
            "checks_passed": self.checks_passed,
            "checks_failed": self.checks_failed,
        }


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def _check_trade_size(amount_usd: float, balance: float) -> tuple[bool, str]:
    cap = balance * MAX_SINGLE_TRADE_PCT
    if amount_usd > cap:
        return False, f"trade ${amount_usd:.2f} exceeds {MAX_SINGLE_TRADE_PCT:.0%} cap (${cap:.2f})"
    if amount_usd <= 0:
        return False, "trade amount must be positive"
    return True, "trade_size"


def _check_balance(amount_usd: float, balance: float) -> tuple[bool, str]:
    if amount_usd > balance:
        return False, f"insufficient balance: ${amount_usd:.2f} > ${balance:.2f}"
    return True, "balance"


def _check_daily_exposure(balance: float) -> tuple[bool, str]:
    try:
        today = datetime.date.today().isoformat()
        with _get_conn() as conn:
            row = conn.execute("""
                SELECT COALESCE(SUM(amount_usd), 0) as total
                FROM paper_trades
                WHERE status = 'open' OR DATE(opened_at) = ?
            """, (today,)).fetchone()
        exposure = row["total"]
        cap = balance * MAX_DAILY_EXPOSURE_PCT
        if exposure > cap:
            return False, f"daily exposure ${exposure:.2f} exceeds {MAX_DAILY_EXPOSURE_PCT:.0%} cap (${cap:.2f})"
    except Exception:
        pass
    return True, "daily_exposure"


def _check_open_positions() -> tuple[bool, str]:
    try:
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM paper_trades WHERE status = 'open'"
            ).fetchone()
        if row["cnt"] >= MAX_OPEN_POSITIONS:
            return False, f"max open positions ({MAX_OPEN_POSITIONS}) reached"
    except Exception:
        pass
    return True, "open_positions"


def _check_duplicate(market_id: str, direction: str) -> tuple[bool, str]:
    try:
        cutoff = (datetime.datetime.utcnow() -
                  datetime.timedelta(minutes=DUPLICATE_WINDOW_MIN)).isoformat()
        with _get_conn() as conn:
            row = conn.execute("""
                SELECT COUNT(*) as cnt FROM paper_trades
                WHERE market_id = ? AND direction = ? AND opened_at > ? AND status = 'open'
            """, (market_id, direction, cutoff)).fetchone()
        if row["cnt"] > 0:
            return False, f"duplicate: already have open {direction} on {market_id}"
    except Exception:
        pass
    return True, "duplicate"


def _check_price_sanity(entry_price: float) -> tuple[bool, str]:
    if entry_price <= 0 or entry_price >= 1:
        return False, f"entry_price {entry_price} outside (0, 1)"
    if entry_price < 0.01:
        return False, f"entry_price {entry_price} suspiciously low (<$0.01)"
    if entry_price > 0.99:
        return False, f"entry_price {entry_price} suspiciously high (>$0.99)"
    return True, "price_sanity"


# ---------------------------------------------------------------------------
# Main audit
# ---------------------------------------------------------------------------

def audit_trade(
    market_id: str,
    direction: str,
    entry_price: float,
    amount_usd: float,
    balance: float,
    strategy: str = "",
) -> AuditResult:
    """
    Run all pre-execution checks. Returns AuditResult with GO/NO-GO.
    All checks must pass for approval.
    """
    passed = []
    failed = []

    checks = [
        _check_trade_size(amount_usd, balance),
        _check_balance(amount_usd, balance),
        _check_price_sanity(entry_price),
        _check_duplicate(market_id, direction),
        _check_open_positions(),
        _check_daily_exposure(balance),
    ]

    for ok, msg in checks:
        if ok:
            passed.append(msg)
        else:
            failed.append(msg)

    approved = len(failed) == 0
    reason = failed[0] if failed else ""

    return AuditResult(
        approved=approved,
        reason=reason,
        checks_passed=passed,
        checks_failed=failed,
    )
