# High-Frequency Paper Trader — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a continuous daemon (`high_freq_trader.py`) that paper-trades Kalshi and Polymarket at 100+ bets/hour using pure-math strategies with realistic fee/slippage simulation.

**Architecture:** Single new file `scripts/mirofish/high_freq_trader.py` owns the full loop. Imports `_call_kalshi` and `_adapt_market_fields` from `kalshi_feed.py`. Reads/writes `paper_trades`, `context`, and `spot_prices` tables directly via SQLite. No modifications to any existing module.

**Tech Stack:** Python 3.11, sqlite3 (stdlib), requests, existing `kalshi_feed._call_kalshi` for auth, gamma-api.polymarket.com for Polymarket data.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| CREATE | `scripts/mirofish/high_freq_trader.py` | Full daemon: startup, loop, all strategies |
| CREATE | `scripts/mirofish/tests/test_high_freq_trader.py` | Unit tests for all components |

No existing files modified.

---

## Shared Types / Constants (defined in Task 1, used throughout)

```python
# Normalized market dict passed between all functions:
# {
#   "market_id": str,       # Kalshi ticker or Polymarket conditionId
#   "question": str,        # market title/question
#   "venue": str,           # "kalshi" | "polymarket"
#   "yes_price": float,     # 0.0–1.0 decimal midpoint
#   "no_price": float,      # 0.0–1.0 decimal midpoint
#   "yes_bid": float,       # 0.0–1.0 (Kalshi only, else == yes_price)
#   "yes_ask": float,       # 0.0–1.0 (Kalshi only, else == yes_price)
#   "event_ticker": str,    # for dedup (Kalshi event; Polymarket uses market_id[:20])
#   "close_time": str,      # ISO timestamp
#   "category": str,        # "crypto", "politics", etc.
#   "cap_strike": float,    # numeric threshold (Kalshi bracket markets)
#   "strike_type": str,     # "greater" | "lesser" | "" (Kalshi bracket semantics)
# }

# TradeSignal namedtuple returned by score_market():
# TradeSignal(market_id, question, venue, direction, edge, strategy, entry_price, amount_usd, shares, fee)
```

---

## Task 1: DB Startup — Clean Slate + $10k Wallet

**Files:**
- Create: `scripts/mirofish/high_freq_trader.py` (initial scaffold + startup functions)
- Create: `scripts/mirofish/tests/test_high_freq_trader.py` (initial scaffold + startup tests)

- [ ] **Step 1.1: Write failing tests for startup functions**

File: `scripts/mirofish/tests/test_high_freq_trader.py`

```python
"""Tests for high_freq_trader — startup, DB cleanup, wallet init."""
import sqlite3
import sys
import os

# Ensure project root is importable
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
if _root not in sys.path:
    sys.path.insert(0, _root)

import pytest


def _make_db():
    """Create an in-memory SQLite DB with all required tables."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE paper_trades (
            id INTEGER PRIMARY KEY,
            market_id TEXT, question TEXT, direction TEXT,
            shares REAL, entry_price REAL, exit_price REAL,
            amount_usd REAL, pnl REAL, status TEXT,
            confidence REAL, reasoning TEXT, strategy TEXT,
            opened_at TEXT, closed_at TEXT,
            venue TEXT, expected_edge REAL, binary_outcome TEXT,
            resolved_price REAL, resolution_source TEXT,
            entry_fee REAL, exit_fee REAL
        );
        CREATE TABLE context (
            chat_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT,
            PRIMARY KEY (chat_id, key)
        );
        CREATE TABLE spot_prices (
            id INTEGER PRIMARY KEY,
            source TEXT, ticker TEXT, signal_type TEXT,
            direction TEXT, amount_usd REAL, description TEXT,
            fetched_at TEXT
        );
    """)
    return conn


def test_db_startup_wipes_open_trades():
    from scripts.mirofish.high_freq_trader import db_startup
    conn = _make_db()
    # Insert some stale open trades
    conn.execute(
        "INSERT INTO paper_trades (market_id, question, direction, shares, entry_price, "
        "amount_usd, status, confidence, reasoning, strategy, opened_at) "
        "VALUES ('KX-TEST', 'test?', 'YES', 10, 0.5, 100, 'open', 0.6, '', 'arb', '2026-03-27T00:00:00')"
    )
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM paper_trades WHERE status='open'").fetchone()[0] == 1

    db_startup(conn)

    assert conn.execute("SELECT COUNT(*) FROM paper_trades WHERE status='open'").fetchone()[0] == 0


def test_db_startup_clears_context_noise():
    from scripts.mirofish.high_freq_trader import db_startup
    conn = _make_db()
    # Insert noise reset rows
    for i in range(5):
        conn.execute(
            "INSERT INTO context (chat_id, key, value) VALUES ('mirofish', ?, '1000.00')",
            (f"wallet_reset_2026-03-24T{i:02d}:00:00",)
        )
    conn.commit()
    assert conn.execute(
        "SELECT COUNT(*) FROM context WHERE key LIKE 'wallet_reset_%'"
    ).fetchone()[0] == 5

    db_startup(conn)

    assert conn.execute(
        "SELECT COUNT(*) FROM context WHERE key LIKE 'wallet_reset_%'"
    ).fetchone()[0] == 0


def test_db_startup_sets_10k_balance():
    from scripts.mirofish.high_freq_trader import db_startup
    conn = _make_db()
    db_startup(conn)
    row = conn.execute(
        "SELECT value FROM context WHERE chat_id='mirofish' AND key='starting_balance'"
    ).fetchone()
    assert row is not None
    assert float(row["value"]) == 10000.0


def test_db_startup_adds_index():
    from scripts.mirofish.high_freq_trader import db_startup
    conn = _make_db()
    db_startup(conn)
    idx = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_pt_status_opened'"
    ).fetchone()
    assert idx is not None


def test_get_balance_reads_starting_plus_closed_pnl():
    from scripts.mirofish.high_freq_trader import get_balance
    conn = _make_db()
    conn.execute(
        "INSERT OR REPLACE INTO context (chat_id, key, value) VALUES ('mirofish', 'starting_balance', '10000.00')"
    )
    conn.execute(
        "INSERT INTO paper_trades (market_id, question, direction, shares, entry_price, "
        "amount_usd, pnl, status, confidence, reasoning, strategy, opened_at) "
        "VALUES ('KX-X', 'q', 'YES', 10, 0.5, 100, 250.0, 'closed_win', 1.0, '', 'arb', '2026-03-27T00:00:00')"
    )
    conn.commit()
    assert get_balance(conn) == 10250.0
```

- [ ] **Step 1.2: Run tests to confirm they fail**

```bash
cd /Users/nayslayer/openclaw
python3 -m pytest scripts/mirofish/tests/test_high_freq_trader.py -v 2>&1 | head -30
```
Expected: `ModuleNotFoundError` or `ImportError` — `high_freq_trader` doesn't exist yet.

- [ ] **Step 1.3: Create `high_freq_trader.py` with startup functions**

File: `scripts/mirofish/high_freq_trader.py`

```python
#!/usr/bin/env python3
"""
High-frequency paper trader daemon.
Loops every 30s: fetch markets → score → place → resolve → evolve.
Target: 100+ paper bets/hour across Kalshi (prod) and Polymarket.

Usage:
    python3 -m scripts.mirofish.high_freq_trader
"""
from __future__ import annotations

import os
import sys
import math
import signal
import time
import random
import datetime
import sqlite3
import requests
from collections import namedtuple
from pathlib import Path

# ── project root on sys.path ─────────────────────────────────────────────────
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

# ── Config ────────────────────────────────────────────────────────────────────
CYCLE_SLEEP         = int(os.environ.get("HFT_CYCLE_SLEEP", "30"))
MIN_EDGE_POLY       = float(os.environ.get("HFT_MIN_EDGE_POLY", "0.003"))   # 0.3%
MIN_EDGE_KALSHI_ARB = float(os.environ.get("HFT_MIN_EDGE_KALSHI_ARB", "0.020"))  # 2.0%
MIN_EDGE_KALSHI_SPOT= float(os.environ.get("HFT_MIN_EDGE_KALSHI_SPOT", "0.025")) # 2.5%
BASE_POS_POLY       = float(os.environ.get("HFT_BASE_POS_POLY", "0.015"))   # 1.5%
BASE_POS_KALSHI     = float(os.environ.get("HFT_BASE_POS_KALSHI", "0.030")) # 3%
MAX_POS_PCT         = float(os.environ.get("HFT_MAX_POS_PCT", "0.05"))      # 5% hard cap
MAX_KALSHI_PER_CYCLE= int(os.environ.get("HFT_MAX_KALSHI_PER_CYCLE", "15"))
MIN_ENTRY_PRICE     = 0.05
MAX_SPREAD_PCT      = 0.25
POLY_REFRESH_CYCLES = 5
MIN_POLY_VOLUME     = 1000.0
MAX_EXPIRY_HOURS    = 24.0

# Fee / execution
KALSHI_FEE_FACTOR   = 0.07
POLY_FEE_RATE       = 0.001   # 10 bps
SLIPPAGE_BASE       = 0.003   # 0.3%
FILL_MIN            = 0.85

KALSHI_SHORT_SERIES = [
    "KXDOGE15M", "KXADA15M", "KXBNB15M", "KXBCH15M",
    "KXBTC15M",  "KXETH15M",
    "INXI", "NASDAQ100I", "KXUSDJPYH",
    "KXBTCUSD", "KXETHUSD",
    "KXBTC", "KXETH", "KXSOL",
]

GAMMA_API = "https://gamma-api.polymarket.com/markets"

# TradeSignal: output of score_market()
TradeSignal = namedtuple(
    "TradeSignal",
    ["market_id", "question", "venue", "direction", "edge",
     "strategy", "entry_price", "amount_usd", "shares", "fee"],
)


# ── DB helpers ────────────────────────────────────────────────────────────────

def _load_env():
    env_file = Path.home() / "openclaw" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def get_conn() -> sqlite3.Connection:
    db_path = Path(os.environ.get("CLAWMSON_DB_PATH",
                                   Path.home() / ".openclaw" / "clawmson.db"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def get_balance(conn: sqlite3.Connection) -> float:
    """Balance = starting_balance + sum of all closed P&L."""
    row = conn.execute(
        "SELECT value FROM context WHERE chat_id='mirofish' AND key='starting_balance'"
    ).fetchone()
    starting = float(row["value"]) if row else 10000.0
    closed_pnl = conn.execute(
        "SELECT COALESCE(SUM(pnl), 0) FROM paper_trades WHERE status != 'open'"
    ).fetchone()[0] or 0.0
    return starting + closed_pnl


# ── Startup ───────────────────────────────────────────────────────────────────

def db_startup(conn: sqlite3.Connection) -> None:
    """
    One-time startup: wipe stale open positions, clear context noise,
    set $10k starting balance, add performance index.
    """
    # 1. Wipe all stale open trades
    conn.execute("DELETE FROM paper_trades WHERE status = 'open'")

    # 2. Clear wallet-reset noise rows
    conn.execute("DELETE FROM context WHERE key LIKE 'wallet_reset_%'")

    # 3. Set fresh $10k starting balance
    conn.execute(
        "INSERT OR REPLACE INTO context (chat_id, key, value) "
        "VALUES ('mirofish', 'starting_balance', '10000.00')"
    )
    conn.execute(
        "INSERT OR REPLACE INTO context (chat_id, key, value) "
        "VALUES ('mirofish', 'trading_status', 'active')"
    )

    # 4. Performance index
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_pt_status_opened "
        "ON paper_trades(status, opened_at)"
    )

    conn.commit()
    print("[HFT] DB startup complete — clean slate, $10,000 balance")
```

- [ ] **Step 1.4: Run tests — expect pass**

```bash
cd /Users/nayslayer/openclaw
python3 -m pytest scripts/mirofish/tests/test_high_freq_trader.py -v 2>&1 | tail -20
```
Expected: 5 tests PASS.

- [ ] **Step 1.5: Commit**

```bash
cd /Users/nayslayer/openclaw
git add scripts/mirofish/high_freq_trader.py scripts/mirofish/tests/test_high_freq_trader.py
git commit -m "feat: scaffold high_freq_trader with db_startup and get_balance"
```

---

## Task 2: Kalshi Market Fetcher

**Files:**
- Modify: `scripts/mirofish/high_freq_trader.py` (add `fetch_kalshi_markets`)
- Modify: `scripts/mirofish/tests/test_high_freq_trader.py` (add Kalshi fetch tests)

- [ ] **Step 2.1: Write failing tests**

Append to `scripts/mirofish/tests/test_high_freq_trader.py`:

```python
from unittest.mock import patch, MagicMock


def test_fetch_kalshi_markets_filters_beyond_24h():
    """Markets closing more than 24h from now are excluded."""
    from scripts.mirofish.high_freq_trader import fetch_kalshi_markets

    now = datetime.datetime.utcnow()
    close_soon = (now + datetime.timedelta(hours=1)).isoformat()
    close_far  = (now + datetime.timedelta(hours=48)).isoformat()

    fake_event = {"event_ticker": "KXBTC-TEST"}
    fake_market_soon = {
        "ticker": "KXBTC-NEAR", "event_ticker": "KXBTC-TEST",
        "title": "BTC above $70k?", "category": "crypto",
        "yes_bid_dollars": "0.45", "yes_ask_dollars": "0.47",
        "no_bid_dollars": "0.53", "no_ask_dollars": "0.55",
        "volume_fp": "1000", "close_time": close_soon,
        "strike_type": "greater", "cap_strike": 70000.0,
    }
    fake_market_far = {
        "ticker": "KXBTC-FAR", "event_ticker": "KXBTC-TEST",
        "title": "BTC above $80k?", "category": "crypto",
        "yes_bid_dollars": "0.20", "yes_ask_dollars": "0.22",
        "no_bid_dollars": "0.78", "no_ask_dollars": "0.80",
        "volume_fp": "500", "close_time": close_far,
        "strike_type": "greater", "cap_strike": 80000.0,
    }

    def mock_call_kalshi(method, path, params=None):
        if "/events" in path or (params and params.get("series_ticker")):
            return {"events": [fake_event]}
        if "/markets" in path and params and params.get("event_ticker"):
            return {"markets": [fake_market_soon, fake_market_far]}
        return None

    with patch("scripts.mirofish.high_freq_trader._call_kalshi", side_effect=mock_call_kalshi):
        markets = fetch_kalshi_markets()

    tickers = [m["market_id"] for m in markets]
    assert "KXBTC-NEAR" in tickers
    assert "KXBTC-FAR" not in tickers


def test_fetch_kalshi_markets_normalizes_prices():
    """yes_price and no_price are 0–1 decimals, not cents."""
    from scripts.mirofish.high_freq_trader import fetch_kalshi_markets

    now = datetime.datetime.utcnow()
    close_soon = (now + datetime.timedelta(hours=2)).isoformat()

    fake_event = {"event_ticker": "KXBTC-TEST"}
    fake_market = {
        "ticker": "KXBTC-NORM", "event_ticker": "KXBTC-TEST",
        "title": "BTC above $70k?", "category": "crypto",
        "yes_bid_dollars": "0.40", "yes_ask_dollars": "0.44",
        "no_bid_dollars": "0.56", "no_ask_dollars": "0.60",
        "volume_fp": "2000", "close_time": close_soon,
        "strike_type": "greater", "cap_strike": 70000.0,
    }

    def mock_call_kalshi(method, path, params=None):
        if params and params.get("series_ticker"):
            return {"events": [fake_event]}
        if params and params.get("event_ticker"):
            return {"markets": [fake_market]}
        return None

    with patch("scripts.mirofish.high_freq_trader._call_kalshi", side_effect=mock_call_kalshi):
        markets = fetch_kalshi_markets()

    assert len(markets) == 1
    m = markets[0]
    assert m["venue"] == "kalshi"
    assert 0.0 < m["yes_price"] < 1.0   # should be ~0.42, not 42
    assert 0.0 < m["no_price"] < 1.0    # should be ~0.58, not 58
    assert m["yes_bid"] < m["yes_ask"]
```

Note: `import datetime` must be at the top of the test file — add it now if not already present.

- [ ] **Step 2.2: Run tests to confirm failure**

```bash
cd /Users/nayslayer/openclaw
python3 -m pytest scripts/mirofish/tests/test_high_freq_trader.py::test_fetch_kalshi_markets_filters_beyond_24h -v 2>&1 | tail -10
```
Expected: FAIL — `fetch_kalshi_markets` not defined.

- [ ] **Step 2.3: Implement `fetch_kalshi_markets`**

Append to `scripts/mirofish/high_freq_trader.py` (after the startup section):

```python
# ── Kalshi market fetcher ─────────────────────────────────────────────────────

try:
    from scripts.mirofish.kalshi_feed import _call_kalshi, _adapt_market_fields
except ImportError:
    from kalshi_feed import _call_kalshi, _adapt_market_fields


def fetch_kalshi_markets() -> list[dict]:
    """
    Fetch all open Kalshi markets across target series that close within 24h.
    Returns list of normalized market dicts (venue="kalshi", prices 0–1 decimal).
    """
    now = datetime.datetime.utcnow()
    cutoff = now + datetime.timedelta(hours=MAX_EXPIRY_HOURS)
    cutoff_iso = cutoff.isoformat()

    seen: set[str] = set()
    markets: list[dict] = []

    for series in KALSHI_SHORT_SERIES:
        data = _call_kalshi("GET", "/events", params={
            "series_ticker": series, "status": "open", "limit": 10,
        })
        if not data:
            continue
        for event in data.get("events", []):
            evt_ticker = event.get("event_ticker", "")
            if not evt_ticker:
                continue
            mdata = _call_kalshi("GET", "/markets", params={
                "event_ticker": evt_ticker, "status": "open", "limit": 100,
            })
            if not mdata:
                continue
            for m in mdata.get("markets", []):
                _adapt_market_fields(m)
                ticker = m.get("ticker", "")
                if not ticker or ticker in seen:
                    continue
                # Skip MVE combo markets
                if m.get("mve_collection_ticker") or "KXMVE" in ticker:
                    continue
                # Filter to <24hr closing
                close_time = m.get("close_time") or m.get("expiration_time", "")
                if not close_time or close_time > cutoff_iso:
                    continue
                # Normalize prices: Kalshi returns cents (0–100), convert to 0–1
                yb = (m.get("yes_bid") or 0) / 100.0
                ya = (m.get("yes_ask") or 0) / 100.0
                nb = (m.get("no_bid") or 0) / 100.0
                na = (m.get("no_ask") or 0) / 100.0
                yes_price = (yb + ya) / 2 if yb > 0 and ya > 0 else (yb or ya)
                no_price  = (nb + na) / 2 if nb > 0 and na > 0 else (nb or na)
                if yes_price <= 0 and no_price <= 0:
                    continue

                seen.add(ticker)
                markets.append({
                    "market_id":    ticker,
                    "question":     m.get("title", ticker),
                    "venue":        "kalshi",
                    "yes_price":    yes_price,
                    "no_price":     no_price,
                    "yes_bid":      yb,
                    "yes_ask":      ya,
                    "event_ticker": evt_ticker,
                    "close_time":   close_time,
                    "category":     (m.get("category") or "").lower(),
                    "cap_strike":   m.get("cap_strike"),
                    "strike_type":  m.get("strike_type", ""),
                })

    return markets
```

- [ ] **Step 2.4: Run tests — expect pass**

```bash
cd /Users/nayslayer/openclaw
python3 -m pytest scripts/mirofish/tests/test_high_freq_trader.py -v 2>&1 | tail -15
```
Expected: all 7 tests PASS.

- [ ] **Step 2.5: Commit**

```bash
cd /Users/nayslayer/openclaw
git add scripts/mirofish/high_freq_trader.py scripts/mirofish/tests/test_high_freq_trader.py
git commit -m "feat: add fetch_kalshi_markets with 24hr filter and price normalization"
```

---

## Task 3: Polymarket Market Fetcher

**Files:**
- Modify: `scripts/mirofish/high_freq_trader.py` (add `fetch_polymarket_markets`)
- Modify: `scripts/mirofish/tests/test_high_freq_trader.py`

- [ ] **Step 3.1: Write failing tests**

Append to test file:

```python
def test_fetch_polymarket_markets_filters_beyond_24h():
    """Polymarket markets closing > 24h from now are excluded."""
    from scripts.mirofish.high_freq_trader import fetch_polymarket_markets

    now = datetime.datetime.utcnow()
    close_soon = (now + datetime.timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
    close_far  = (now + datetime.timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")

    fake_response = [
        {
            "conditionId": "0xabc", "question": "Will it rain?",
            "category": "weather", "volume": "5000",
            "endDate": close_soon, "active": True, "closed": False,
            "outcomePrices": ["0.65", "0.35"], "outcomes": ["Yes", "No"],
        },
        {
            "conditionId": "0xdef", "question": "Election winner?",
            "category": "politics", "volume": "50000",
            "endDate": close_far, "active": True, "closed": False,
            "outcomePrices": ["0.55", "0.45"], "outcomes": ["Yes", "No"],
        },
    ]

    with patch("scripts.mirofish.high_freq_trader.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = fake_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        markets = fetch_polymarket_markets()

    ids = [m["market_id"] for m in markets]
    assert "0xabc" in ids
    assert "0xdef" not in ids


def test_fetch_polymarket_markets_normalizes_fields():
    """Polymarket markets have correct venue and price fields."""
    from scripts.mirofish.high_freq_trader import fetch_polymarket_markets

    now = datetime.datetime.utcnow()
    close_soon = (now + datetime.timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")

    fake_response = [{
        "conditionId": "0x123", "question": "BTC above $70k today?",
        "category": "crypto", "volume": "20000",
        "endDate": close_soon, "active": True, "closed": False,
        "outcomePrices": ["0.72", "0.28"], "outcomes": ["Yes", "No"],
    }]

    with patch("scripts.mirofish.high_freq_trader.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.json.return_value = fake_response
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        markets = fetch_polymarket_markets()

    assert len(markets) == 1
    m = markets[0]
    assert m["venue"] == "polymarket"
    assert abs(m["yes_price"] - 0.72) < 0.001
    assert abs(m["no_price"] - 0.28) < 0.001
    assert m["event_ticker"] == "0x123"[:20]
```

- [ ] **Step 3.2: Run to confirm failure**

```bash
cd /Users/nayslayer/openclaw
python3 -m pytest scripts/mirofish/tests/test_high_freq_trader.py::test_fetch_polymarket_markets_filters_beyond_24h -v 2>&1 | tail -10
```
Expected: FAIL — `fetch_polymarket_markets` not defined.

- [ ] **Step 3.3: Implement `fetch_polymarket_markets`**

Append to `high_freq_trader.py`:

```python
# ── Polymarket market fetcher ─────────────────────────────────────────────────

def fetch_polymarket_markets() -> list[dict]:
    """
    Fetch Polymarket markets closing within 24h via gamma API.
    Returns list of normalized market dicts (venue="polymarket", prices 0–1).
    """
    now = datetime.datetime.utcnow()
    cutoff = now + datetime.timedelta(hours=MAX_EXPIRY_HOURS)

    try:
        resp = requests.get(
            GAMMA_API,
            params={"active": "true", "closed": "false", "limit": 200},
            timeout=20,
        )
        resp.raise_for_status()
        raw = resp.json()
        raw_list = raw if isinstance(raw, list) else raw.get("data", raw.get("markets", []))
    except Exception as e:
        print(f"[HFT] Polymarket fetch error: {e}")
        return []

    markets: list[dict] = []
    for m in raw_list:
        # Volume filter
        try:
            volume = float(m.get("volume", 0) or 0)
        except (ValueError, TypeError):
            volume = 0.0
        if volume < MIN_POLY_VOLUME:
            continue

        # End-date filter: must close within 24h
        end_date_str = m.get("endDate") or m.get("end_date") or ""
        if not end_date_str:
            continue
        try:
            # Strip trailing Z or timezone
            end_dt_str = end_date_str.replace("Z", "").replace("+00:00", "")
            end_dt = datetime.datetime.fromisoformat(end_dt_str)
        except (ValueError, TypeError):
            continue
        if end_dt <= now or end_dt > cutoff:
            continue

        # Parse yes/no prices
        yes_price = no_price = None
        outcome_prices = m.get("outcomePrices", [])
        outcomes = m.get("outcomes", [])
        if isinstance(outcome_prices, str):
            import json as _json
            try: outcome_prices = _json.loads(outcome_prices)
            except Exception: outcome_prices = []
        if isinstance(outcomes, str):
            import json as _json
            try: outcomes = _json.loads(outcomes)
            except Exception: outcomes = []
        for label, price_str in zip(outcomes, outcome_prices):
            try:
                price = float(price_str)
            except (ValueError, TypeError):
                continue
            if (label or "").lower() == "yes":
                yes_price = price
            elif (label or "").lower() == "no":
                no_price = price

        # Fallback: tokens array
        if yes_price is None or no_price is None:
            for tok in (m.get("tokens") or []):
                outcome = (tok.get("outcome") or "").upper()
                try:
                    price = float(tok.get("price", 0) or 0)
                except (ValueError, TypeError):
                    continue
                if outcome == "YES":
                    yes_price = price
                elif outcome == "NO":
                    no_price = price

        if yes_price is None or no_price is None:
            continue

        market_id = m.get("conditionId") or m.get("id") or ""
        question  = m.get("question", "")
        if not market_id or not question:
            continue

        markets.append({
            "market_id":    market_id,
            "question":     question,
            "venue":        "polymarket",
            "yes_price":    float(yes_price),
            "no_price":     float(no_price),
            "yes_bid":      float(yes_price),
            "yes_ask":      float(yes_price),
            "event_ticker": market_id[:20],
            "close_time":   end_date_str,
            "category":     (m.get("category") or "").lower(),
            "cap_strike":   None,
            "strike_type":  "",
        })

    return markets
```

- [ ] **Step 3.4: Run all tests — expect pass**

```bash
cd /Users/nayslayer/openclaw
python3 -m pytest scripts/mirofish/tests/test_high_freq_trader.py -v 2>&1 | tail -15
```
Expected: all 9 tests PASS.

- [ ] **Step 3.5: Commit**

```bash
cd /Users/nayslayer/openclaw
git add scripts/mirofish/high_freq_trader.py scripts/mirofish/tests/test_high_freq_trader.py
git commit -m "feat: add fetch_polymarket_markets with 24hr filter"
```

---

## Task 4: Strategy Scoring Engine

**Files:**
- Modify: `scripts/mirofish/high_freq_trader.py` (add 4 strategy functions + `score_market`)
- Modify: `scripts/mirofish/tests/test_high_freq_trader.py`

- [ ] **Step 4.1: Write failing tests**

Append to test file:

```python
def _make_kalshi_market(yes_price=0.45, no_price=0.57, strike=70000.0, strike_type="greater",
                        ticker="KXBTC-T", event="KXBTC-E"):
    return {
        "market_id": ticker, "question": "BTC above $70k?", "venue": "kalshi",
        "yes_price": yes_price, "no_price": no_price,
        "yes_bid": yes_price - 0.02, "yes_ask": yes_price + 0.02,
        "event_ticker": event, "close_time": "2099-01-01T00:00:00",
        "category": "crypto", "cap_strike": strike, "strike_type": strike_type,
    }


def _make_poly_market(yes_price=0.65, no_price=0.35, mid="0xABC", question="Will it rain?"):
    return {
        "market_id": mid, "question": question, "venue": "polymarket",
        "yes_price": yes_price, "no_price": no_price,
        "yes_bid": yes_price, "yes_ask": yes_price,
        "event_ticker": mid[:20], "close_time": "2099-01-01T00:00:00",
        "category": "weather", "cap_strike": None, "strike_type": "",
    }


def test_score_market_arb_kalshi_detects_gap():
    """arb strategy fires when yes+no > 1 + min_edge on Kalshi."""
    from scripts.mirofish.high_freq_trader import score_market
    # yes=0.45, no=0.57 → sum=1.02, gap=0.02 which is >= MIN_EDGE_KALSHI_ARB=0.02
    m = _make_kalshi_market(yes_price=0.45, no_price=0.57)
    sig = score_market(m, spot_prices={}, open_ids=set(), events_traded=set(), weights={})
    assert sig is not None
    assert sig.strategy == "arb"
    assert sig.venue == "kalshi"


def test_score_market_arb_polymarket_lower_threshold():
    """arb strategy fires at lower edge threshold on Polymarket."""
    from scripts.mirofish.high_freq_trader import score_market
    # yes=0.48, no=0.53 → gap=0.01, above MIN_EDGE_POLY=0.003 but below MIN_EDGE_KALSHI_ARB=0.02
    m = _make_poly_market(yes_price=0.48, no_price=0.53)
    sig = score_market(m, spot_prices={}, open_ids=set(), events_traded=set(), weights={})
    assert sig is not None
    assert sig.strategy == "arb"
    assert sig.venue == "polymarket"


def test_score_market_skips_already_open():
    """Returns None if market_id is already in open_ids."""
    from scripts.mirofish.high_freq_trader import score_market
    m = _make_kalshi_market(yes_price=0.45, no_price=0.57)
    sig = score_market(m, spot_prices={}, open_ids={"KXBTC-T"}, events_traded=set(), weights={})
    assert sig is None


def test_score_market_skips_duplicate_event():
    """Returns None if event_ticker already traded this cycle."""
    from scripts.mirofish.high_freq_trader import score_market
    m = _make_kalshi_market(yes_price=0.45, no_price=0.57)
    sig = score_market(m, spot_prices={}, open_ids=set(), events_traded={"KXBTC-E"}, weights={})
    assert sig is None


def test_score_market_spot_lag_yes_when_spot_above_strike():
    """spot_lag fires YES when spot clearly above strike and market underprices YES."""
    from scripts.mirofish.high_freq_trader import score_market
    # Spot BTC = 75000, strike = 70000 → clearly above → YES
    # Market only prices YES at 0.45 — underpriced, take YES
    m = _make_kalshi_market(yes_price=0.45, no_price=0.53, strike=70000.0, strike_type="greater")
    sig = score_market(
        m, spot_prices={"BTC": 75000.0},
        open_ids=set(), events_traded=set(), weights={}
    )
    assert sig is not None
    assert sig.direction == "YES"
    assert sig.strategy == "spot_lag"


def test_score_market_mean_reversion_poly():
    """mean_reversion fires on Polymarket when YES is dramatically overpriced."""
    from scripts.mirofish.high_freq_trader import score_market
    # YES priced at 0.92 — fade it, bet NO
    m = _make_poly_market(yes_price=0.92, no_price=0.08)
    sig = score_market(m, spot_prices={}, open_ids=set(), events_traded=set(), weights={})
    assert sig is not None
    assert sig.direction == "NO"
    assert sig.strategy == "mean_reversion"


def test_score_market_no_edge_returns_none():
    """Returns None when no strategy finds sufficient edge."""
    from scripts.mirofish.high_freq_trader import score_market
    # Perfectly priced, no gap, no spot data
    m = _make_poly_market(yes_price=0.50, no_price=0.50)
    sig = score_market(m, spot_prices={}, open_ids=set(), events_traded=set(), weights={})
    assert sig is None
```

- [ ] **Step 4.2: Run to confirm failure**

```bash
cd /Users/nayslayer/openclaw
python3 -m pytest scripts/mirofish/tests/test_high_freq_trader.py -k "score_market" -v 2>&1 | tail -15
```
Expected: all 6 score_market tests FAIL.

- [ ] **Step 4.3: Implement scoring engine**

Append to `high_freq_trader.py`:

```python
# ── Strategy scoring ──────────────────────────────────────────────────────────

# Crypto ticker mapping: asset symbol → Kalshi ticker prefix substrings
_CRYPTO_TICKERS = {
    "BTC": ["KXBTC", "KXBTCUSD"],
    "ETH": ["KXETH", "KXETHUSD"],
    "SOL": ["KXSOL"],
    "DOGE": ["KXDOGE"],
    "ADA": ["KXADA"],
    "BNB": ["KXBNB"],
    "BCH": ["KXBCH"],
}


def _size_trade(balance: float, venue: str, weight: float) -> float:
    """Return position size in USD, Kelly-scaled."""
    base_pct = BASE_POS_POLY if venue == "polymarket" else BASE_POS_KALSHI
    sized = balance * base_pct * max(0.5, min(1.5, weight))
    return min(sized, balance * MAX_POS_PCT)


def _calc_fee(venue: str, shares: float, entry_price: float, amount_usd: float) -> float:
    if venue == "kalshi":
        return KALSHI_FEE_FACTOR * shares * entry_price * (1.0 - entry_price)
    return POLY_FEE_RATE * amount_usd


def _apply_slippage(price: float, direction: str) -> float:
    """Slip the entry price slightly against us."""
    slip = SLIPPAGE_BASE
    if direction == "YES":
        return min(price * (1.0 + slip), 0.99)
    return max(price * (1.0 - slip), 0.01)


def score_market(
    market: dict,
    spot_prices: dict[str, float],
    open_ids: set[str],
    events_traded: set[str],
    weights: dict[str, float],
    balance: float = 10000.0,
) -> "TradeSignal | None":
    """
    Score a single market against all applicable strategies.
    Returns the best TradeSignal or None if no edge found.
    Priority: arb > spot_lag > momentum > mean_reversion.
    """
    mid = market["market_id"]
    venue = market["venue"]
    yes_p = market["yes_price"]
    no_p  = market["no_price"]
    event = market["event_ticker"]

    # Guard: skip if already open or event already traded this cycle
    if mid in open_ids or event in events_traded:
        return None

    # Guard: skip penny contracts
    if yes_p < MIN_ENTRY_PRICE and no_p < MIN_ENTRY_PRICE:
        return None

    # Guard: skip wide spread (Kalshi only — Polymarket has no bid/ask spread)
    if venue == "kalshi":
        yb, ya = market["yes_bid"], market["yes_ask"]
        if ya > 0 and yb > 0:
            spread = (ya - yb) / ((ya + yb) / 2)
            if spread > MAX_SPREAD_PCT:
                return None

    # ── Strategy 1: Arbitrage ─────────────────────────────────────────────────
    min_arb = MIN_EDGE_KALSHI_ARB if venue == "kalshi" else MIN_EDGE_POLY
    arb_gap = (yes_p + no_p) - 1.0
    if arb_gap > min_arb:
        # Buy the underpriced side
        direction = "NO" if no_p < (1.0 - yes_p) else "YES"
        entry_raw = no_p if direction == "NO" else yes_p
        entry = _apply_slippage(entry_raw, direction)
        fill  = random.uniform(FILL_MIN, 1.0)
        amount = _size_trade(balance, venue, weights.get("arb", 1.0)) * fill
        shares = amount / entry if entry > 0 else 0
        fee = _calc_fee(venue, shares, entry, amount)
        return TradeSignal(mid, market["question"], venue, direction,
                           arb_gap - min_arb, "arb", entry, amount, shares, fee)

    # ── Strategy 2: Spot-lag (Kalshi crypto brackets only) ───────────────────
    if venue == "kalshi" and market.get("cap_strike") and market.get("strike_type"):
        for asset, prefixes in _CRYPTO_TICKERS.items():
            if not any(mid.upper().startswith(p) for p in prefixes):
                continue
            spot = spot_prices.get(asset)
            if not spot or spot <= 0:
                break
            strike = float(market["cap_strike"])
            if strike <= 0:
                break
            dist = abs(spot - strike) / spot
            if dist < MIN_EDGE_KALSHI_SPOT:
                break  # too close to call
            stype = (market["strike_type"] or "").lower()
            if stype in ("greater", "above", "over", "t"):
                direction = "YES" if spot > strike else "NO"
            elif stype in ("lesser", "below", "under"):
                direction = "YES" if spot < strike else "NO"
            else:
                break
            entry_raw = yes_p if direction == "YES" else no_p
            if entry_raw < MIN_ENTRY_PRICE or entry_raw > 0.95:
                break
            entry = _apply_slippage(entry_raw, direction)
            fill  = random.uniform(FILL_MIN, 1.0)
            amount = _size_trade(balance, venue, weights.get("spot_lag", 1.0)) * fill
            shares = amount / entry if entry > 0 else 0
            fee = _calc_fee(venue, shares, entry, amount)
            return TradeSignal(mid, market["question"], venue, direction,
                               dist, "spot_lag", entry, amount, shares, fee)

    # ── Strategy 3: Momentum (Polymarket, crypto) ────────────────────────────
    if venue == "polymarket" and spot_prices:
        for asset, prefixes in _CRYPTO_TICKERS.items():
            q_lower = market["question"].lower()
            if asset.lower() not in q_lower and not any(p.lower() in q_lower for p in prefixes):
                continue
            spot = spot_prices.get(asset)
            if not spot:
                continue
            # Momentum: if "above X" in question, check spot trend
            import re as _re
            thresh_match = _re.search(r"\$?([\d,]+(?:\.\d+)?)", market["question"])
            if not thresh_match:
                break
            try:
                threshold = float(thresh_match.group(1).replace(",", ""))
            except ValueError:
                break
            if threshold <= 0:
                break
            dist = abs(spot - threshold) / spot
            if dist < MIN_EDGE_POLY:
                break
            q = q_lower
            if "above" in q or "over" in q or "higher" in q:
                direction = "YES" if spot > threshold else "NO"
            elif "below" in q or "under" in q or "lower" in q:
                direction = "YES" if spot < threshold else "NO"
            else:
                break
            entry_raw = yes_p if direction == "YES" else no_p
            if entry_raw < MIN_ENTRY_PRICE or entry_raw > 0.95:
                break
            entry = _apply_slippage(entry_raw, direction)
            fill  = random.uniform(FILL_MIN, 1.0)
            amount = _size_trade(balance, venue, weights.get("momentum", 1.0)) * fill
            shares = amount / entry if entry > 0 else 0
            fee = _calc_fee(venue, shares, entry, amount)
            return TradeSignal(mid, market["question"], venue, direction,
                               dist, "momentum", entry, amount, shares, fee)

    # ── Strategy 4: Mean-reversion (Polymarket, overpriced contracts) ────────
    if venue == "polymarket":
        mean_rev_threshold = 0.35  # contract priced > 0.85 or < 0.15
        if yes_p > (1.0 - mean_rev_threshold):
            # YES is overpriced — fade it, bet NO
            edge = yes_p - (1.0 - mean_rev_threshold)
            if edge >= MIN_EDGE_POLY:
                direction = "NO"
                entry_raw = no_p
                entry = _apply_slippage(entry_raw, direction)
                fill  = random.uniform(FILL_MIN, 1.0)
                amount = _size_trade(balance, venue, weights.get("mean_reversion", 1.0)) * fill
                shares = amount / entry if entry > 0 else 0
                fee = _calc_fee(venue, shares, entry, amount)
                return TradeSignal(mid, market["question"], venue, direction,
                                   edge, "mean_reversion", entry, amount, shares, fee)
        elif no_p > (1.0 - mean_rev_threshold):
            # NO is overpriced — bet YES
            edge = no_p - (1.0 - mean_rev_threshold)
            if edge >= MIN_EDGE_POLY:
                direction = "YES"
                entry_raw = yes_p
                entry = _apply_slippage(entry_raw, direction)
                fill  = random.uniform(FILL_MIN, 1.0)
                amount = _size_trade(balance, venue, weights.get("mean_reversion", 1.0)) * fill
                shares = amount / entry if entry > 0 else 0
                fee = _calc_fee(venue, shares, entry, amount)
                return TradeSignal(mid, market["question"], venue, direction,
                                   edge, "mean_reversion", entry, amount, shares, fee)

    return None
```

- [ ] **Step 4.4: Run all tests — expect pass**

```bash
cd /Users/nayslayer/openclaw
python3 -m pytest scripts/mirofish/tests/test_high_freq_trader.py -v 2>&1 | tail -20
```
Expected: all 15 tests PASS.

- [ ] **Step 4.5: Commit**

```bash
cd /Users/nayslayer/openclaw
git add scripts/mirofish/high_freq_trader.py scripts/mirofish/tests/test_high_freq_trader.py
git commit -m "feat: add 4-strategy scoring engine with arb, spot_lag, momentum, mean_reversion"
```

---

## Task 5: Trade Placement

**Files:**
- Modify: `scripts/mirofish/high_freq_trader.py` (add `place_trade`, `load_spot_prices`, `get_open_ids`)
- Modify: `scripts/mirofish/tests/test_high_freq_trader.py`

- [ ] **Step 5.1: Write failing tests**

Append to test file:

```python
def test_place_trade_inserts_to_db():
    """place_trade inserts a row into paper_trades with correct fields."""
    from scripts.mirofish.high_freq_trader import place_trade, TradeSignal
    conn = _make_db()
    conn.execute(
        "INSERT OR REPLACE INTO context (chat_id, key, value) VALUES ('mirofish', 'starting_balance', '10000.00')"
    )
    conn.commit()

    sig = TradeSignal(
        market_id="KXBTC-TEST", question="BTC above $70k?", venue="kalshi",
        direction="YES", edge=0.05, strategy="arb",
        entry_price=0.45, amount_usd=300.0, shares=666.0, fee=9.45,
    )
    trade_id = place_trade(conn, sig, balance=10000.0)

    assert trade_id is not None
    row = conn.execute(
        "SELECT * FROM paper_trades WHERE id=?", (trade_id,)
    ).fetchone()
    assert row["market_id"] == "KXBTC-TEST"
    assert row["direction"] == "YES"
    assert row["status"] == "open"
    assert row["venue"] == "kalshi"
    assert row["entry_fee"] == pytest.approx(9.45, abs=0.01)
    assert row["strategy"] == "arb"
    assert row["expected_edge"] == pytest.approx(0.05, abs=0.001)


def test_place_trade_skips_zero_shares():
    """place_trade returns None if shares == 0 (bad entry price)."""
    from scripts.mirofish.high_freq_trader import place_trade, TradeSignal
    conn = _make_db()
    sig = TradeSignal(
        market_id="KXBTC-ZERO", question="test", venue="kalshi",
        direction="YES", edge=0.05, strategy="arb",
        entry_price=0.0, amount_usd=100.0, shares=0.0, fee=0.0,
    )
    result = place_trade(conn, sig, balance=10000.0)
    assert result is None


def test_get_open_ids_returns_set():
    """get_open_ids returns a set of market_ids currently open."""
    from scripts.mirofish.high_freq_trader import get_open_ids
    conn = _make_db()
    conn.execute(
        "INSERT INTO paper_trades (market_id, question, direction, shares, entry_price, "
        "amount_usd, status, confidence, reasoning, strategy, opened_at) "
        "VALUES ('KX-OPEN', 'q', 'YES', 10, 0.5, 100, 'open', 0.6, '', 'arb', '2026-03-27T00:00:00')"
    )
    conn.execute(
        "INSERT INTO paper_trades (market_id, question, direction, shares, entry_price, "
        "amount_usd, status, confidence, reasoning, strategy, opened_at) "
        "VALUES ('KX-CLOSED', 'q', 'YES', 10, 0.5, 100, 'closed_win', 0.6, '', 'arb', '2026-03-27T00:00:00')"
    )
    conn.commit()
    ids = get_open_ids(conn)
    assert "KX-OPEN" in ids
    assert "KX-CLOSED" not in ids
```

- [ ] **Step 5.2: Run to confirm failure**

```bash
cd /Users/nayslayer/openclaw
python3 -m pytest scripts/mirofish/tests/test_high_freq_trader.py -k "place_trade or get_open_ids" -v 2>&1 | tail -10
```
Expected: FAIL.

- [ ] **Step 5.3: Implement placement functions**

Append to `high_freq_trader.py`:

```python
# ── Trade placement ───────────────────────────────────────────────────────────

def get_open_ids(conn: sqlite3.Connection) -> set[str]:
    """Return set of market_ids with status='open'."""
    rows = conn.execute(
        "SELECT market_id FROM paper_trades WHERE status='open'"
    ).fetchall()
    return {r["market_id"] for r in rows}


def load_spot_prices(conn: sqlite3.Connection) -> dict[str, float]:
    """Load latest crypto spot prices from spot_prices table."""
    spot: dict[str, float] = {}
    try:
        rows = conn.execute("""
            SELECT ticker, amount_usd FROM spot_prices
            WHERE ticker LIKE 'SPOT:%'
            ORDER BY fetched_at DESC
        """).fetchall()
        for r in rows:
            asset = r["ticker"].replace("SPOT:", "")
            if asset not in spot:
                spot[asset] = float(r["amount_usd"])
    except Exception:
        pass
    return spot


def place_trade(
    conn: sqlite3.Connection,
    sig: "TradeSignal",
    balance: float,
) -> "int | None":
    """
    Insert a paper trade into paper_trades.
    Returns the row ID, or None if trade is invalid (zero shares).
    """
    if sig.shares <= 0:
        return None

    ts = datetime.datetime.utcnow().isoformat()
    try:
        cur = conn.execute("""
            INSERT INTO paper_trades
              (market_id, question, direction, shares, entry_price, amount_usd,
               status, confidence, reasoning, strategy, opened_at,
               venue, expected_edge, entry_fee)
            VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?, ?, ?)
        """, (
            sig.market_id,
            sig.question[:200],
            sig.direction,
            sig.shares,
            sig.entry_price,
            sig.amount_usd,
            min(sig.edge / 0.10, 1.0),   # confidence: edge scaled to 0–1
            f"{sig.strategy}: edge={sig.edge:.3f} entry={sig.entry_price:.3f}",
            sig.strategy,
            ts,
            sig.venue,
            sig.edge,
            sig.fee,
        ))
        conn.commit()
        return cur.lastrowid
    except Exception as e:
        print(f"[HFT] place_trade error: {e}")
        return None
```

- [ ] **Step 5.4: Run all tests — expect pass**

```bash
cd /Users/nayslayer/openclaw
python3 -m pytest scripts/mirofish/tests/test_high_freq_trader.py -v 2>&1 | tail -20
```
Expected: all 18 tests PASS.

- [ ] **Step 5.5: Commit**

```bash
cd /Users/nayslayer/openclaw
git add scripts/mirofish/high_freq_trader.py scripts/mirofish/tests/test_high_freq_trader.py
git commit -m "feat: add place_trade, get_open_ids, load_spot_prices"
```

---

## Task 6: Resolution Loop

**Files:**
- Modify: `scripts/mirofish/high_freq_trader.py` (add `resolve_expired`)
- Modify: `scripts/mirofish/tests/test_high_freq_trader.py`

- [ ] **Step 6.1: Write failing tests**

Append to test file:

```python
def test_resolve_expired_kalshi_win():
    """Kalshi trade resolves to closed_win when API returns result='yes' and we bet YES."""
    from scripts.mirofish.high_freq_trader import resolve_expired
    conn = _make_db()
    conn.execute(
        "INSERT INTO paper_trades (market_id, question, direction, shares, entry_price, "
        "amount_usd, status, confidence, reasoning, strategy, opened_at, venue) "
        "VALUES ('KXBTC-TEST', 'q', 'YES', 100.0, 0.45, 45.0, 'open', 0.8, '', 'arb', '2026-03-27T00:00:00', 'kalshi')"
    )
    conn.commit()

    def mock_call_kalshi(method, path, params=None):
        return {"market": {"result": "yes", "status": "finalized"}}

    with patch("scripts.mirofish.high_freq_trader._call_kalshi", side_effect=mock_call_kalshi):
        resolved = resolve_expired(conn)

    assert resolved == 1
    row = conn.execute("SELECT status, pnl, exit_price FROM paper_trades WHERE market_id='KXBTC-TEST'").fetchone()
    assert row["status"] == "closed_win"
    assert row["exit_price"] == pytest.approx(1.0)
    assert row["pnl"] > 0  # (1.0 - 0.45) * 100 = 55.0


def test_resolve_expired_kalshi_loss():
    """Kalshi trade resolves to closed_loss when result='yes' but we bet NO."""
    from scripts.mirofish.high_freq_trader import resolve_expired
    conn = _make_db()
    conn.execute(
        "INSERT INTO paper_trades (market_id, question, direction, shares, entry_price, "
        "amount_usd, status, confidence, reasoning, strategy, opened_at, venue) "
        "VALUES ('KXBTC-LOSS', 'q', 'NO', 50.0, 0.53, 26.5, 'open', 0.6, '', 'arb', '2026-03-27T00:00:00', 'kalshi')"
    )
    conn.commit()

    with patch("scripts.mirofish.high_freq_trader._call_kalshi",
               return_value={"market": {"result": "yes", "status": "finalized"}}):
        resolve_expired(conn)

    row = conn.execute("SELECT status, pnl FROM paper_trades WHERE market_id='KXBTC-LOSS'").fetchone()
    assert row["status"] == "closed_loss"
    assert row["pnl"] < 0


def test_resolve_expired_skips_no_result():
    """Trades with no result yet stay open."""
    from scripts.mirofish.high_freq_trader import resolve_expired
    conn = _make_db()
    conn.execute(
        "INSERT INTO paper_trades (market_id, question, direction, shares, entry_price, "
        "amount_usd, status, confidence, reasoning, strategy, opened_at, venue) "
        "VALUES ('KXBTC-PEND', 'q', 'YES', 10.0, 0.50, 5.0, 'open', 0.5, '', 'arb', '2026-03-27T00:00:00', 'kalshi')"
    )
    conn.commit()

    with patch("scripts.mirofish.high_freq_trader._call_kalshi",
               return_value={"market": {"result": "", "status": "open"}}):
        resolved = resolve_expired(conn)

    assert resolved == 0
    row = conn.execute("SELECT status FROM paper_trades WHERE market_id='KXBTC-PEND'").fetchone()
    assert row["status"] == "open"
```

- [ ] **Step 6.2: Run to confirm failure**

```bash
cd /Users/nayslayer/openclaw
python3 -m pytest scripts/mirofish/tests/test_high_freq_trader.py -k "resolve_expired" -v 2>&1 | tail -10
```
Expected: FAIL.

- [ ] **Step 6.3: Implement `resolve_expired`**

Append to `high_freq_trader.py`:

```python
# ── Resolution loop ───────────────────────────────────────────────────────────

def resolve_expired(conn: sqlite3.Connection) -> int:
    """
    Check all open trades against their venue API for resolution.
    Updates status, exit_price, pnl, closed_at. Returns count resolved.
    Processes max 50 at a time to bound API call latency per cycle.
    """
    open_trades = conn.execute(
        "SELECT id, market_id, direction, entry_price, shares, venue "
        "FROM paper_trades WHERE status='open' ORDER BY opened_at ASC LIMIT 50"
    ).fetchall()

    resolved = 0
    for t in open_trades:
        result = _fetch_result(t["venue"], t["market_id"])
        if result is None:
            continue  # still open

        we_bet  = t["direction"].lower()
        we_won  = (result == "yes" and we_bet == "yes") or \
                  (result == "no"  and we_bet == "no")
        exit_price = 1.0 if we_won else 0.0
        pnl        = t["shares"] * (exit_price - t["entry_price"])
        status     = "closed_win" if we_won else "closed_loss"
        now        = datetime.datetime.utcnow().isoformat()

        conn.execute("""
            UPDATE paper_trades
            SET exit_price=?, pnl=?, status=?, closed_at=?, resolved_price=?
            WHERE id=?
        """, (exit_price, pnl, status, now, exit_price, t["id"]))
        sign = "+" if pnl >= 0 else ""
        print(f"[HFT] Resolved {t['market_id'][:35]} → {status} {sign}${pnl:.2f}")
        resolved += 1

    if resolved:
        conn.commit()
    return resolved


def _fetch_result(venue: str, market_id: str) -> "str | None":
    """
    Fetch resolution result for a market.
    Returns 'yes', 'no', or None if not yet resolved.
    """
    if venue == "kalshi":
        data = _call_kalshi("GET", f"/markets/{market_id}")
        if not data:
            return None
        m = data.get("market", data)
        result = (m.get("result") or "").lower().strip()
        return result if result in ("yes", "no") else None

    # Polymarket — use gamma API
    try:
        resp = requests.get(
            GAMMA_API,
            params={"id": market_id, "closed": "true"},
            timeout=15,
        )
        resp.raise_for_status()
        raw = resp.json()
        markets = raw if isinstance(raw, list) else raw.get("markets", [raw])
        for m in markets:
            if not m.get("closed"):
                return None
            winner = (m.get("winningOutcome") or m.get("winning_side") or "").lower()
            if winner in ("yes", "no"):
                return winner
    except Exception:
        pass
    return None
```

- [ ] **Step 6.4: Run all tests — expect pass**

```bash
cd /Users/nayslayer/openclaw
python3 -m pytest scripts/mirofish/tests/test_high_freq_trader.py -v 2>&1 | tail -25
```
Expected: all 21 tests PASS.

- [ ] **Step 6.5: Commit**

```bash
cd /Users/nayslayer/openclaw
git add scripts/mirofish/high_freq_trader.py scripts/mirofish/tests/test_high_freq_trader.py
git commit -m "feat: add resolve_expired for Kalshi and Polymarket positions"
```

---

## Task 7: Strategy Weight Evolution

**Files:**
- Modify: `scripts/mirofish/high_freq_trader.py` (add `evolve_weights`)
- Modify: `scripts/mirofish/tests/test_high_freq_trader.py`

- [ ] **Step 7.1: Write failing tests**

Append to test file:

```python
def _insert_trades(conn, strategy, wins, losses):
    """Helper: insert closed win/loss trades for a given strategy."""
    for i in range(wins):
        conn.execute(
            "INSERT INTO paper_trades (market_id, question, direction, shares, entry_price, "
            "amount_usd, pnl, status, confidence, reasoning, strategy, opened_at) "
            "VALUES (?, 'q', 'YES', 10, 0.5, 50, 5.0, 'closed_win', 0.8, '', ?, '2026-03-27T00:00:00')",
            (f"KX-{strategy}-W{i}", strategy)
        )
    for i in range(losses):
        conn.execute(
            "INSERT INTO paper_trades (market_id, question, direction, shares, entry_price, "
            "amount_usd, pnl, status, confidence, reasoning, strategy, opened_at) "
            "VALUES (?, 'q', 'YES', 10, 0.5, 50, -5.0, 'closed_loss', 0.8, '', ?, '2026-03-27T00:00:00')",
            (f"KX-{strategy}-L{i}", strategy)
        )
    conn.commit()


def test_evolve_weights_increases_winning_strategy():
    """Strategy with >60% win rate gets weight bumped up."""
    from scripts.mirofish.high_freq_trader import evolve_weights
    conn = _make_db()
    _insert_trades(conn, "arb", wins=70, losses=30)  # 70% win rate
    weights = {"arb": 1.0}
    new_weights = evolve_weights(conn, weights)
    assert new_weights["arb"] > 1.0
    assert new_weights["arb"] <= 1.5


def test_evolve_weights_decreases_losing_strategy():
    """Strategy with <45% win rate gets weight cut."""
    from scripts.mirofish.high_freq_trader import evolve_weights
    conn = _make_db()
    _insert_trades(conn, "spot_lag", wins=20, losses=80)  # 20% win rate
    weights = {"spot_lag": 1.0}
    new_weights = evolve_weights(conn, weights)
    assert new_weights["spot_lag"] < 1.0
    assert new_weights["spot_lag"] >= 0.5


def test_evolve_weights_unchanged_when_insufficient_data():
    """Strategy with <10 resolved trades keeps weight at 1.0."""
    from scripts.mirofish.high_freq_trader import evolve_weights
    conn = _make_db()
    _insert_trades(conn, "momentum", wins=5, losses=3)  # only 8 trades
    weights = {"momentum": 1.0}
    new_weights = evolve_weights(conn, weights)
    assert new_weights["momentum"] == pytest.approx(1.0)
```

- [ ] **Step 7.2: Run to confirm failure**

```bash
cd /Users/nayslayer/openclaw
python3 -m pytest scripts/mirofish/tests/test_high_freq_trader.py -k "evolve_weights" -v 2>&1 | tail -10
```
Expected: FAIL.

- [ ] **Step 7.3: Implement `evolve_weights`**

Append to `high_freq_trader.py`:

```python
# ── Strategy weight evolution ─────────────────────────────────────────────────

_ALL_STRATEGIES = ("arb", "spot_lag", "momentum", "mean_reversion")


def evolve_weights(
    conn: sqlite3.Connection,
    weights: dict[str, float],
) -> dict[str, float]:
    """
    Adjust per-strategy Kelly multipliers based on last 100 resolved trades.
    Win rate > 60% → weight × 1.1 (max 1.5)
    Win rate < 45% → weight × 0.9 (min 0.5)
    < 10 resolved → weight unchanged
    """
    new_weights = dict(weights)

    for strategy in _ALL_STRATEGIES:
        rows = conn.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status='closed_win' THEN 1 ELSE 0 END) as wins
            FROM paper_trades
            WHERE strategy=?
              AND status IN ('closed_win', 'closed_loss')
            ORDER BY closed_at DESC
            LIMIT 100
        """, (strategy,)).fetchone()

        total = rows["total"] if rows else 0
        wins  = rows["wins"]  if rows else 0

        if total < 10:
            new_weights.setdefault(strategy, 1.0)
            continue

        win_rate = wins / total
        current  = new_weights.get(strategy, 1.0)

        if win_rate > 0.60:
            new_weights[strategy] = min(current * 1.1, 1.5)
        elif win_rate < 0.45:
            new_weights[strategy] = max(current * 0.9, 0.5)
        else:
            new_weights[strategy] = current  # neutral zone, hold

    return new_weights
```

- [ ] **Step 7.4: Run all tests — expect pass**

```bash
cd /Users/nayslayer/openclaw
python3 -m pytest scripts/mirofish/tests/test_high_freq_trader.py -v 2>&1 | tail -25
```
Expected: all 24 tests PASS.

- [ ] **Step 7.5: Commit**

```bash
cd /Users/nayslayer/openclaw
git add scripts/mirofish/high_freq_trader.py scripts/mirofish/tests/test_high_freq_trader.py
git commit -m "feat: add evolve_weights strategy learning"
```

---

## Task 8: Main Daemon Loop + CLI

**Files:**
- Modify: `scripts/mirofish/high_freq_trader.py` (add `run`, signal handling, `__main__`)
- Modify: `scripts/mirofish/tests/test_high_freq_trader.py` (integration smoke test)

- [ ] **Step 8.1: Write smoke test**

Append to test file:

```python
def test_single_cycle_places_and_resolves(monkeypatch):
    """
    Integration smoke test: one full cycle with mocked APIs places at least
    one trade and resolves any expired positions without crashing.
    """
    import scripts.mirofish.high_freq_trader as hft

    conn = _make_db()
    conn.execute(
        "INSERT OR REPLACE INTO context (chat_id, key, value) VALUES ('mirofish', 'starting_balance', '10000.00')"
    )
    conn.commit()

    now = datetime.datetime.utcnow()
    close_soon = (now + datetime.timedelta(hours=1)).isoformat()

    # Fake Kalshi market with arb gap
    fake_kalshi = [{
        "market_id": "KXBTC-SMOKE", "question": "BTC above $70k?", "venue": "kalshi",
        "yes_price": 0.45, "no_price": 0.58,   # gap = 0.03 > MIN_EDGE_KALSHI_ARB
        "yes_bid": 0.43, "yes_ask": 0.47,
        "event_ticker": "KXBTC-EVT", "close_time": close_soon,
        "category": "crypto", "cap_strike": 70000.0, "strike_type": "greater",
    }]

    monkeypatch.setattr(hft, "fetch_kalshi_markets", lambda: fake_kalshi)
    monkeypatch.setattr(hft, "fetch_polymarket_markets", lambda: [])
    monkeypatch.setattr(hft, "_fetch_result", lambda venue, mid: None)  # nothing to resolve

    weights = {s: 1.0 for s in hft._ALL_STRATEGIES}
    placed, resolved = hft._run_cycle(conn, weights, poly_cache=[], cycle_num=1)

    assert placed >= 1
    assert resolved == 0
    assert conn.execute("SELECT COUNT(*) FROM paper_trades WHERE status='open'").fetchone()[0] >= 1
```

- [ ] **Step 8.2: Run to confirm failure**

```bash
cd /Users/nayslayer/openclaw
python3 -m pytest scripts/mirofish/tests/test_high_freq_trader.py::test_single_cycle_places_and_resolves -v 2>&1 | tail -10
```
Expected: FAIL — `_run_cycle` not defined.

- [ ] **Step 8.3: Implement main loop**

Append to `high_freq_trader.py`:

```python
# ── Connectivity checks ───────────────────────────────────────────────────────

def _verify_connectivity() -> bool:
    """Test Kalshi prod API and Polymarket gamma API. Returns True if both reachable."""
    ok = True
    data = _call_kalshi("GET", "/exchange/status")
    if data:
        print("[HFT] Kalshi prod API: connected")
    else:
        print("[HFT] WARNING: Kalshi API unreachable — trades will skip Kalshi")
        ok = False

    try:
        resp = requests.get(GAMMA_API, params={"limit": 1}, timeout=10)
        resp.raise_for_status()
        print("[HFT] Polymarket gamma API: connected")
    except Exception as e:
        print(f"[HFT] WARNING: Polymarket API unreachable: {e}")
        ok = False

    return ok


def _notify_dashboard():
    try:
        requests.post("http://127.0.0.1:7080/api/trading/notify", timeout=2)
    except Exception:
        pass


# ── Cycle ─────────────────────────────────────────────────────────────────────

def _run_cycle(
    conn: sqlite3.Connection,
    weights: dict[str, float],
    poly_cache: list[dict],
    cycle_num: int,
) -> "tuple[int, int]":
    """
    Execute one full trading cycle.
    Returns (trades_placed, trades_resolved).
    """
    balance = get_balance(conn)
    open_ids = get_open_ids(conn)
    spot_prices = load_spot_prices(conn)
    events_traded: set[str] = set()

    # Fetch markets
    kalshi_markets = fetch_kalshi_markets()

    # Refresh Polymarket cache every POLY_REFRESH_CYCLES cycles
    if cycle_num % POLY_REFRESH_CYCLES == 1 or not poly_cache:
        fresh = fetch_polymarket_markets()
        poly_cache.clear()
        poly_cache.extend(fresh)

    all_markets = kalshi_markets + poly_cache

    # Score and place trades
    placed = 0
    kalshi_placed = 0

    for market in all_markets:
        # Enforce Kalshi per-cycle cap
        if market["venue"] == "kalshi" and kalshi_placed >= MAX_KALSHI_PER_CYCLE:
            continue

        sig = score_market(market, spot_prices, open_ids, events_traded, weights, balance)
        if sig is None:
            continue

        trade_id = place_trade(conn, sig, balance)
        if trade_id is not None:
            placed += 1
            open_ids.add(sig.market_id)
            events_traded.add(market["event_ticker"])
            if market["venue"] == "kalshi":
                kalshi_placed += 1

    # Resolve expired positions
    resolved = resolve_expired(conn)

    return placed, resolved


# ── Main daemon ───────────────────────────────────────────────────────────────

_running = True


def _handle_signal(signum, frame):
    global _running
    print(f"\n[HFT] Signal {signum} received — shutting down after this cycle...")
    _running = False


def run():
    """Main entry point. Runs the daemon loop until SIGINT/SIGTERM."""
    global _running
    _load_env()

    print("=" * 60)
    print("[HFT] High-Frequency Paper Trader starting up")
    print(f"[HFT] Cycle interval: {CYCLE_SLEEP}s | Target: 100+ bets/hour")
    print("=" * 60)

    signal.signal(signal.SIGINT,  _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    conn = get_conn()

    # Startup: clean slate + $10k wallet
    db_startup(conn)

    # Connectivity check (non-fatal — warns but continues)
    _verify_connectivity()

    # Init strategy weights
    weights: dict[str, float] = {s: 1.0 for s in _ALL_STRATEGIES}
    poly_cache: list[dict] = []

    # Session stats
    session_placed   = 0
    session_resolved = 0
    session_start    = datetime.datetime.utcnow()
    cycle_num        = 0

    print(f"\n[HFT] Clean slate. Balance: $10,000.00. Starting loop...\n")

    while _running:
        cycle_num += 1
        cycle_start = time.time()

        try:
            placed, resolved = _run_cycle(conn, weights, poly_cache, cycle_num)
            weights = evolve_weights(conn, weights)

            session_placed   += placed
            session_resolved += resolved
            balance           = get_balance(conn)
            elapsed_min       = (datetime.datetime.utcnow() - session_start).total_seconds() / 60
            rate              = session_placed / elapsed_min if elapsed_min > 0 else 0

            open_count = conn.execute(
                "SELECT COUNT(*) FROM paper_trades WHERE status='open'"
            ).fetchone()[0]

            pnl = balance - 10000.0
            pnl_sign = "+" if pnl >= 0 else ""
            print(
                f"[HFT cycle {cycle_num:4d}] "
                f"placed={placed:2d} resolved={resolved:2d} open={open_count:3d} "
                f"balance=${balance:,.2f} ({pnl_sign}${pnl:,.2f}) "
                f"rate={rate:.1f}/min"
            )

            weight_str = " | ".join(
                f"{s}:{w:.2f}" for s, w in sorted(weights.items()) if w != 1.0
            )
            if weight_str:
                print(f"[HFT]       weights: {weight_str}")

            if placed > 0 or resolved > 0:
                _notify_dashboard()

        except Exception as e:
            print(f"[HFT] Cycle {cycle_num} error: {e}")
            import traceback
            traceback.print_exc()

        # Sleep remainder of cycle
        elapsed = time.time() - cycle_start
        sleep_time = max(0, CYCLE_SLEEP - elapsed)
        if _running and sleep_time > 0:
            time.sleep(sleep_time)

    # Session summary
    elapsed_total = (datetime.datetime.utcnow() - session_start).total_seconds()
    final_balance = get_balance(conn)
    final_pnl     = final_balance - 10000.0
    print("\n" + "=" * 60)
    print("[HFT] Session complete")
    print(f"  Runtime:   {elapsed_total/60:.1f} min ({cycle_num} cycles)")
    print(f"  Placed:    {session_placed} trades ({session_placed/(elapsed_total/3600):.0f}/hr)")
    print(f"  Resolved:  {session_resolved} trades")
    print(f"  Final P&L: {'+'if final_pnl>=0 else ''}{final_pnl:,.2f} ({final_pnl/10000*100:.2f}%)")
    print(f"  Balance:   ${final_balance:,.2f}")
    print("=" * 60)
    conn.close()


if __name__ == "__main__":
    run()
```

- [ ] **Step 8.4: Run all tests — expect pass**

```bash
cd /Users/nayslayer/openclaw
python3 -m pytest scripts/mirofish/tests/test_high_freq_trader.py -v 2>&1 | tail -30
```
Expected: all 25 tests PASS.

- [ ] **Step 8.5: Smoke-test the actual startup (5-second dry run)**

```bash
cd /Users/nayslayer/openclaw
source .env 2>/dev/null || true
timeout 5 python3 -m scripts.mirofish.high_freq_trader 2>&1 || true
```
Expected output (approximately):
```
[HFT] High-Frequency Paper Trader starting up
[HFT] DB startup complete — clean slate, $10,000 balance
[HFT] Kalshi prod API: connected
[HFT] Polymarket gamma API: connected
[HFT] Clean slate. Balance: $10,000.00. Starting loop...
[HFT cycle   1] placed=N resolved=0 open=N balance=$10,000.xx ...
```
If API errors appear, check `.env` is loaded and KALSHI_API_ENV=prod.

- [ ] **Step 8.6: Final commit**

```bash
cd /Users/nayslayer/openclaw
git add scripts/mirofish/high_freq_trader.py scripts/mirofish/tests/test_high_freq_trader.py
git commit -m "feat: add main daemon loop, _run_cycle, session summary, signal handling"
```

---

## Running the Daemon

```bash
# In a tmux session:
cd /Users/nayslayer/openclaw
source .env
python3 -m scripts.mirofish.high_freq_trader

# To adjust cycle speed or edge thresholds without code changes:
HFT_CYCLE_SLEEP=20 HFT_MIN_EDGE_POLY=0.002 python3 -m scripts.mirofish.high_freq_trader
```

Stop with `Ctrl+C` — prints session summary on exit.
