#!/usr/bin/env python3
"""
Data quality validator — checks market data freshness, detects price anomalies,
flags stale feeds. Integrated into simulator pre-execution to prevent trading
on bad data.

Phase 5B Step 4: stale-data and anomaly checks.

Python 3.9 compatible via __future__ annotations.
"""
from __future__ import annotations

import os
import sqlite3
import datetime
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Maximum age (minutes) before a feed is considered stale
STALE_THRESHOLD_MIN = int(os.environ.get("MIROFISH_STALE_THRESHOLD_MIN", "120"))

# Maximum allowed single-snapshot price change (30% = 0.30)
MAX_PRICE_JUMP = float(os.environ.get("MIROFISH_MAX_PRICE_JUMP", "0.30"))

# Minimum snapshots needed to check for stuck prices
MIN_SNAPSHOTS_FOR_STUCK = int(os.environ.get("MIROFISH_MIN_STUCK_SNAPSHOTS", "3"))

# Price must change by at least this much across MIN_SNAPSHOTS to not be "stuck"
STUCK_PRICE_EPSILON = float(os.environ.get("MIROFISH_STUCK_EPSILON", "0.001"))


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
class MarketAlert:
    market_id: str
    alert_type: str       # stale_price | price_jump | stuck_price | invalid_price | feed_stale
    severity: str         # warning | critical
    message: str
    value: float = 0.0    # the problematic value

    def to_dict(self) -> dict:
        return {
            "market_id": self.market_id,
            "alert_type": self.alert_type,
            "severity": self.severity,
            "message": self.message,
            "value": self.value,
        }


@dataclass
class DataQualityReport:
    checked_at: str
    total_markets: int
    alerts: list[MarketAlert] = field(default_factory=list)
    stale_feeds: list[str] = field(default_factory=list)
    markets_blocked: list[str] = field(default_factory=list)

    @property
    def has_critical(self) -> bool:
        return any(a.severity == "critical" for a in self.alerts)

    @property
    def blocked_ids(self) -> set[str]:
        return set(self.markets_blocked)

    def to_dict(self) -> dict:
        return {
            "checked_at": self.checked_at,
            "total_markets": self.total_markets,
            "alert_count": len(self.alerts),
            "critical_count": sum(1 for a in self.alerts if a.severity == "critical"),
            "stale_feeds": self.stale_feeds,
            "markets_blocked": self.markets_blocked,
            "alerts": [a.to_dict() for a in self.alerts],
        }


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

def check_invalid_prices(markets: list[dict]) -> list[MarketAlert]:
    """Check for impossible price values."""
    alerts = []
    for m in markets:
        mid = m.get("market_id", "unknown")
        yes_p = m.get("yes_price")
        no_p = m.get("no_price")

        if yes_p is not None:
            if yes_p < 0 or yes_p > 1:
                alerts.append(MarketAlert(
                    market_id=mid, alert_type="invalid_price", severity="critical",
                    message=f"yes_price={yes_p} outside [0,1]", value=yes_p,
                ))
        if no_p is not None:
            if no_p < 0 or no_p > 1:
                alerts.append(MarketAlert(
                    market_id=mid, alert_type="invalid_price", severity="critical",
                    message=f"no_price={no_p} outside [0,1]", value=no_p,
                ))

        # Check yes + no adds up (should be ~1.0 for binary)
        if yes_p is not None and no_p is not None and yes_p > 0 and no_p > 0:
            total = yes_p + no_p
            if total < 0.80 or total > 1.20:
                alerts.append(MarketAlert(
                    market_id=mid, alert_type="invalid_price", severity="warning",
                    message=f"yes+no={total:.3f} (expected ~1.0)", value=total,
                ))

    return alerts


def check_price_jumps(markets: list[dict]) -> list[MarketAlert]:
    """Check for sudden price jumps compared to previous snapshot."""
    alerts = []

    try:
        with _get_conn() as conn:
            for m in markets:
                mid = m.get("market_id", "")
                if not mid:
                    continue

                prev = conn.execute("""
                    SELECT yes_price, no_price FROM market_data
                    WHERE market_id = ?
                    ORDER BY fetched_at DESC LIMIT 1 OFFSET 1
                """, (mid,)).fetchone()

                if not prev:
                    continue

                for field_name in ("yes_price", "no_price"):
                    current = m.get(field_name)
                    previous = prev[field_name]
                    if current is None or previous is None or previous == 0:
                        continue
                    change = abs(current - previous) / previous
                    if change > MAX_PRICE_JUMP:
                        alerts.append(MarketAlert(
                            market_id=mid, alert_type="price_jump", severity="warning",
                            message=f"{field_name} jumped {change:.0%}: {previous:.3f}→{current:.3f}",
                            value=change,
                        ))
    except Exception:
        pass

    return alerts


def check_stuck_prices(markets: list[dict]) -> list[MarketAlert]:
    """Check for prices that haven't moved across recent snapshots."""
    alerts = []

    try:
        with _get_conn() as conn:
            for m in markets:
                mid = m.get("market_id", "")
                if not mid:
                    continue

                rows = conn.execute("""
                    SELECT yes_price FROM market_data
                    WHERE market_id = ?
                    ORDER BY fetched_at DESC LIMIT ?
                """, (mid, MIN_SNAPSHOTS_FOR_STUCK)).fetchall()

                if len(rows) < MIN_SNAPSHOTS_FOR_STUCK:
                    continue

                prices = [r["yes_price"] for r in rows if r["yes_price"] is not None]
                if len(prices) < MIN_SNAPSHOTS_FOR_STUCK:
                    continue

                price_range = max(prices) - min(prices)
                if price_range < STUCK_PRICE_EPSILON:
                    alerts.append(MarketAlert(
                        market_id=mid, alert_type="stuck_price", severity="warning",
                        message=f"yes_price unchanged across {len(prices)} snapshots ({prices[0]:.3f})",
                        value=price_range,
                    ))
    except Exception:
        pass

    return alerts


def check_feed_freshness() -> list[MarketAlert]:
    """Check if feeds have recent data."""
    alerts = []
    cutoff = (datetime.datetime.utcnow() -
              datetime.timedelta(minutes=STALE_THRESHOLD_MIN)).isoformat()

    feed_tables = {
        "polymarket": "market_data",
        "kalshi": "kalshi_markets",
    }

    try:
        with _get_conn() as conn:
            for feed_name, table in feed_tables.items():
                # Check table exists
                exists = conn.execute("""
                    SELECT name FROM sqlite_master
                    WHERE type='table' AND name=?
                """, (table,)).fetchone()
                if not exists:
                    continue

                latest = conn.execute(f"""
                    SELECT MAX(fetched_at) as latest FROM {table}
                """).fetchone()

                if not latest or not latest["latest"]:
                    alerts.append(MarketAlert(
                        market_id=feed_name, alert_type="feed_stale",
                        severity="warning",
                        message=f"{feed_name} feed has no data",
                    ))
                elif latest["latest"] < cutoff:
                    alerts.append(MarketAlert(
                        market_id=feed_name, alert_type="feed_stale",
                        severity="warning",
                        message=f"{feed_name} latest data is {latest['latest']} (>{STALE_THRESHOLD_MIN}min old)",
                    ))
    except Exception:
        pass

    return alerts


# ---------------------------------------------------------------------------
# Main validation
# ---------------------------------------------------------------------------

def validate_markets(markets: list[dict]) -> DataQualityReport:
    """
    Run all data quality checks on a list of markets.
    Returns a report with alerts and a list of markets blocked from trading.
    """
    now = datetime.datetime.utcnow().isoformat()
    alerts: list[MarketAlert] = []

    # Run all checks
    alerts.extend(check_invalid_prices(markets))
    alerts.extend(check_price_jumps(markets))
    alerts.extend(check_stuck_prices(markets))
    alerts.extend(check_feed_freshness())

    # Determine which markets to block
    blocked = set()
    stale_feeds = []

    for alert in alerts:
        if alert.severity == "critical":
            blocked.add(alert.market_id)
        if alert.alert_type == "feed_stale":
            stale_feeds.append(alert.market_id)

    return DataQualityReport(
        checked_at=now,
        total_markets=len(markets),
        alerts=alerts,
        stale_feeds=stale_feeds,
        markets_blocked=sorted(blocked),
    )


def filter_tradeable(
    markets: list[dict],
    report: DataQualityReport | None = None,
) -> list[dict]:
    """
    Filter markets to only those passing quality checks.
    If no report provided, generates one.
    """
    if report is None:
        report = validate_markets(markets)

    blocked = report.blocked_ids
    return [m for m in markets if m.get("market_id", "") not in blocked]
