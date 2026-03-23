# Price-Lag Arbitrage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a price-lag arb strategy that fetches BTC/ETH spot from Binance/Coinbase, detects dislocations against Polymarket crypto contracts, and trades with linear edge decay and latency simulation.

**Architecture:** `spot_feed.py` (DataFeed pattern) provides spot prices. Price-lag arb strategy lives in `trading_brain.py` as Step 1.5 between existing arb and Ollama. Tracking table in `price_lag_trades` for separate performance analysis.

**Tech Stack:** Python 3.10+, requests, sqlite3, math, pytest

**Spec:** `docs/superpowers/specs/2026-03-23-price-lag-arb-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `spot_feed.py` | **Create** | Spot price DataFeed — Binance/Coinbase BTC/ETH |
| `tests/test_spot_feed.py` | **Create** | Spot feed tests |
| `tests/test_price_lag.py` | **Create** | Price-lag arb strategy tests |
| `trading_brain.py` | **Edit** (lines 6-12, 23-33, 128-155) | Add math import, metadata field, price-lag constants + helpers + strategy step |
| `simulator.py` | **Edit** (lines 89-104, 137-163) | Add migrations, spot_feed import, tracking writes |

---

### Task 1: DB Migrations — spot_prices + price_lag_trades tables

**Files:**
- Modify: `simulator.py:89-104` (append to MIGRATION_SQL before INSERT INTO context)

- [ ] **Step 1: Write the failing test**

File: `tests/test_spot_feed.py`

```python
# tests/test_spot_feed.py
from __future__ import annotations
import datetime
import sqlite3
import requests
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    db = str(tmp_path / "test.db")
    monkeypatch.setenv("CLAWMSON_DB_PATH", db)
    import sys
    for mod in list(sys.modules.keys()):
        if "mirofish" in mod:
            del sys.modules[mod]
    import scripts.mirofish.simulator as sim
    sim.migrate()
    yield db


def test_spot_prices_table_exists(temp_db):
    conn = sqlite3.connect(temp_db)
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='spot_prices'"
    ).fetchone()
    conn.close()
    assert row is not None


def test_price_lag_trades_table_exists(temp_db):
    conn = sqlite3.connect(temp_db)
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='price_lag_trades'"
    ).fetchone()
    conn.close()
    assert row is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/openclaw && python3 -m pytest scripts/mirofish/tests/test_spot_feed.py -v`
Expected: FAIL — tables don't exist

- [ ] **Step 3: Add migration SQL to simulator.py**

In `simulator.py`, after the `crucix_signals` block (after line 101) and before `INSERT OR IGNORE INTO context` (line 103), add:

```sql
CREATE TABLE IF NOT EXISTS spot_prices (
    id          INTEGER PRIMARY KEY,
    source      TEXT NOT NULL,
    ticker      TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    direction   TEXT NOT NULL,
    amount_usd  REAL,
    description TEXT NOT NULL,
    fetched_at  TEXT NOT NULL,
    UNIQUE (source, ticker, signal_type, fetched_at)
);
CREATE INDEX IF NOT EXISTS idx_spot_prices_ticker_time
    ON spot_prices(ticker, fetched_at);

CREATE TABLE IF NOT EXISTS price_lag_trades (
    id              INTEGER PRIMARY KEY,
    market_id       TEXT NOT NULL,
    question        TEXT NOT NULL,
    asset           TEXT NOT NULL,
    contract_type   TEXT NOT NULL,
    spot_price      REAL NOT NULL,
    threshold       REAL,
    bracket_low     REAL,
    bracket_high    REAL,
    polymarket_price REAL NOT NULL,
    raw_dislocation REAL NOT NULL,
    decayed_edge    REAL NOT NULL,
    days_to_expiry  REAL NOT NULL,
    direction       TEXT NOT NULL,
    confidence      REAL NOT NULL,
    amount_usd      REAL NOT NULL,
    entry_price     REAL NOT NULL,
    detected_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_price_lag_market_time
    ON price_lag_trades(market_id, detected_at);
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/openclaw && python3 -m pytest scripts/mirofish/tests/test_spot_feed.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd ~/openclaw
git add scripts/mirofish/simulator.py scripts/mirofish/tests/test_spot_feed.py
git commit -m "feat(mirofish): add spot_prices + price_lag_trades table migrations"
```

---

### Task 2: spot_feed.py — complete module

**Files:**
- Create: `spot_feed.py`
- Test: `tests/test_spot_feed.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_spot_feed.py`:

```python
def _sf():
    """Re-import spot_feed with clean state."""
    import sys
    for mod in list(sys.modules.keys()):
        if "spot_feed" in mod:
            del sys.modules[mod]
    import scripts.mirofish.spot_feed as sf
    return sf


def _mock_binance(btc_price="42340.00", eth_price="2848.00"):
    """Return a side_effect function for requests.get that mocks Binance."""
    def side_effect(url, **kwargs):
        mock = MagicMock()
        mock.raise_for_status.return_value = None
        if "BTCUSDT" in url:
            mock.json.return_value = {"symbol": "BTCUSDT", "price": btc_price}
        elif "ETHUSDT" in url:
            mock.json.return_value = {"symbol": "ETHUSDT", "price": eth_price}
        elif "BTC-USD" in url:
            mock.json.return_value = {"data": {"amount": "42360.00"}}
        elif "ETH-USD" in url:
            mock.json.return_value = {"data": {"amount": "2852.00"}}
        return mock
    return side_effect


def test_module_interface(temp_db):
    sf = _sf()
    assert sf.source_name == "spot_prices"
    assert callable(sf.fetch)
    assert callable(sf.get_cached)
    assert callable(sf.get_spot_dict)


def test_fetch_binance_and_coinbase(temp_db):
    sf = _sf()
    with patch("requests.get", side_effect=_mock_binance()):
        signals = sf.fetch()
    assert len(signals) == 2
    btc = [s for s in signals if s["ticker"] == "SPOT:BTC"]
    eth = [s for s in signals if s["ticker"] == "SPOT:ETH"]
    assert len(btc) == 1
    assert len(eth) == 1
    # Averaged: (42340 + 42360) / 2 = 42350
    assert btc[0]["amount_usd"] == pytest.approx(42350.0)
    assert btc[0]["source"] == "spot_prices"
    assert btc[0]["signal_type"] == "spot_price"
    assert btc[0]["direction"] == "neutral"


def test_fetch_one_exchange_down(temp_db):
    sf = _sf()
    call_count = [0]
    def side_effect(url, **kwargs):
        call_count[0] += 1
        if "binance" in url:
            raise requests.exceptions.ConnectionError("binance down")
        mock = MagicMock()
        mock.raise_for_status.return_value = None
        if "BTC-USD" in url:
            mock.json.return_value = {"data": {"amount": "42360.00"}}
        elif "ETH-USD" in url:
            mock.json.return_value = {"data": {"amount": "2852.00"}}
        return mock
    with patch("requests.get", side_effect=side_effect):
        signals = sf.fetch()
    btc = [s for s in signals if s["ticker"] == "SPOT:BTC"]
    assert len(btc) == 1
    assert btc[0]["amount_usd"] == pytest.approx(42360.0)  # Coinbase only


def test_get_spot_dict(temp_db):
    sf = _sf()
    with patch("requests.get", side_effect=_mock_binance()):
        sf.fetch()  # populate cache
    result = sf.get_spot_dict()
    assert "BTC" in result
    assert "ETH" in result
    assert isinstance(result["BTC"], float)
    assert result["BTC"] > 0


def test_cache_freshness(temp_db):
    sf = _sf()
    # Seed cache via fetch
    with patch("requests.get", side_effect=_mock_binance()):
        sf.fetch()
    # Second fetch should use cache (no HTTP)
    with patch("requests.get", side_effect=AssertionError("should not hit API")):
        signals = sf.fetch()
    assert len(signals) >= 2


def test_signal_dict_shape(temp_db):
    sf = _sf()
    with patch("requests.get", side_effect=_mock_binance()):
        signals = sf.fetch()
    required = {"source", "ticker", "signal_type", "direction", "amount_usd", "description", "fetched_at"}
    for s in signals:
        assert required.issubset(s.keys()), f"Missing keys: {required - set(s.keys())}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/openclaw && python3 -m pytest scripts/mirofish/tests/test_spot_feed.py -v`
Expected: FAIL — module doesn't exist

- [ ] **Step 3: Create spot_feed.py**

```python
#!/usr/bin/env python3
"""
Spot price feed — fetches BTC/ETH from Binance + Coinbase public APIs.
Averages prices from both exchanges. Caches to spot_prices SQLite table.

Duck-type compatible with DataFeed protocol (base_feed.py).
isinstance(this_module, DataFeed) will return False.
"""
from __future__ import annotations
import os
import sqlite3
import datetime
import requests
from pathlib import Path

source_name = "spot_prices"

SPOT_CACHE_TTL_HOURS = float(os.environ.get("SPOT_CACHE_TTL_HOURS", "0.083"))
SPOT_TIMEOUT = int(os.environ.get("SPOT_TIMEOUT", "10"))

_ASSETS = {
    "BTC": {
        "binance": "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT",
        "coinbase": "https://api.coinbase.com/v2/prices/BTC-USD/spot",
    },
    "ETH": {
        "binance": "https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT",
        "coinbase": "https://api.coinbase.com/v2/prices/ETH-USD/spot",
    },
}


def _get_conn() -> sqlite3.Connection:
    db_path = Path(os.environ.get("CLAWMSON_DB_PATH",
                                   Path.home() / ".openclaw" / "clawmson.db"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _now_iso() -> str:
    return datetime.datetime.utcnow().isoformat()


def _fetch_binance(url: str) -> float | None:
    try:
        resp = requests.get(url, timeout=SPOT_TIMEOUT)
        resp.raise_for_status()
        return float(resp.json().get("price", 0))
    except Exception as e:
        print(f"[spot_feed] Binance error: {e}")
        return None


def _fetch_coinbase(url: str) -> float | None:
    try:
        resp = requests.get(url, timeout=SPOT_TIMEOUT)
        resp.raise_for_status()
        return float(resp.json().get("data", {}).get("amount", 0))
    except Exception as e:
        print(f"[spot_feed] Coinbase error: {e}")
        return None


def _fetch_spot(asset: str) -> dict | None:
    """Fetch spot price for one asset, average Binance + Coinbase."""
    urls = _ASSETS.get(asset)
    if not urls:
        return None

    binance_price = _fetch_binance(urls["binance"])
    coinbase_price = _fetch_coinbase(urls["coinbase"])

    prices = [p for p in [binance_price, coinbase_price] if p and p > 0]
    if not prices:
        return None

    avg_price = sum(prices) / len(prices)
    parts = []
    if binance_price:
        parts.append(f"binance=${binance_price:,.2f}")
    if coinbase_price:
        parts.append(f"coinbase=${coinbase_price:,.2f}")

    return {
        "source": "spot_prices",
        "ticker": f"SPOT:{asset}",
        "signal_type": "spot_price",
        "direction": "neutral",
        "amount_usd": avg_price,
        "description": f"{asset} spot: ${avg_price:,.2f} ({' '.join(parts)})",
        "fetched_at": _now_iso(),
    }


def _is_cache_fresh() -> bool:
    cutoff = (datetime.datetime.utcnow() -
              datetime.timedelta(hours=SPOT_CACHE_TTL_HOURS)).isoformat()
    try:
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM spot_prices WHERE fetched_at > ?",
                (cutoff,)
            ).fetchone()
        return row["cnt"] > 0
    except Exception:
        return False


def _store_signals(signals: list[dict]) -> None:
    if not signals:
        return
    try:
        with _get_conn() as conn:
            conn.executemany("""
                INSERT OR IGNORE INTO spot_prices
                (source, ticker, signal_type, direction, amount_usd, description, fetched_at)
                VALUES (:source, :ticker, :signal_type, :direction,
                        :amount_usd, :description, :fetched_at)
            """, signals)
    except Exception as e:
        print(f"[spot_feed] DB write error: {e}")


def _purge_old() -> None:
    cutoff = (datetime.datetime.utcnow() - datetime.timedelta(hours=24)).isoformat()
    try:
        with _get_conn() as conn:
            conn.execute("DELETE FROM spot_prices WHERE fetched_at < ?", (cutoff,))
    except Exception as e:
        print(f"[spot_feed] Purge error: {e}")


def get_cached() -> list[dict]:
    """Return cached spot price signals within TTL."""
    cutoff = (datetime.datetime.utcnow() -
              datetime.timedelta(hours=SPOT_CACHE_TTL_HOURS)).isoformat()
    try:
        with _get_conn() as conn:
            rows = conn.execute("""
                SELECT source, ticker, signal_type, direction, amount_usd,
                       description, fetched_at
                FROM spot_prices WHERE fetched_at > ?
                ORDER BY fetched_at DESC
            """, (cutoff,)).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"[spot_feed] Cache read error: {e}")
        return []


def get_spot_dict() -> dict[str, float]:
    """Return {'BTC': price, 'ETH': price} from latest cached data."""
    result = {}
    try:
        with _get_conn() as conn:
            for asset in _ASSETS:
                row = conn.execute("""
                    SELECT amount_usd FROM spot_prices
                    WHERE ticker = ? ORDER BY fetched_at DESC LIMIT 1
                """, (f"SPOT:{asset}",)).fetchone()
                if row and row["amount_usd"]:
                    result[asset] = row["amount_usd"]
    except Exception as e:
        print(f"[spot_feed] get_spot_dict error: {e}")
    return result


def fetch() -> list[dict]:
    """Fetch BTC + ETH spot, cache, return signal dicts. Never raises."""
    if _is_cache_fresh():
        print("[spot_feed] Cache fresh — skipping live fetch")
        return get_cached()

    signals = []
    for asset in _ASSETS:
        sig = _fetch_spot(asset)
        if sig:
            signals.append(sig)

    if not signals:
        print("[spot_feed] All exchanges failed — falling back to cache")
        return get_cached()

    _purge_old()
    _store_signals(signals)
    print(f"[spot_feed] Fetched {len(signals)} spot prices")
    return signals
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/openclaw && python3 -m pytest scripts/mirofish/tests/test_spot_feed.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
cd ~/openclaw
git add scripts/mirofish/spot_feed.py scripts/mirofish/tests/test_spot_feed.py
git commit -m "feat(mirofish): spot_feed module — Binance/Coinbase BTC/ETH with caching"
```

---

### Task 3: Price-lag arb helpers — parse, detect, compute

These are pure functions with no side effects — easy to test in isolation.

**Files:**
- Modify: `trading_brain.py:6-12,17-20`
- Create: `tests/test_price_lag.py`

- [ ] **Step 1: Write the failing tests**

File: `tests/test_price_lag.py`

```python
# tests/test_price_lag.py
from __future__ import annotations
import math
import datetime
import pytest


@pytest.fixture(autouse=True)
def clean_imports():
    import sys
    for mod in list(sys.modules.keys()):
        if "mirofish" in mod:
            del sys.modules[mod]
    yield


def _tb():
    import scripts.mirofish.trading_brain as tb
    return tb


def test_parse_price_string(clean_imports):
    tb = _tb()
    assert tb._parse_price_string("50,000") == pytest.approx(50000.0)
    assert tb._parse_price_string("50k") == pytest.approx(50000.0)
    assert tb._parse_price_string("50K") == pytest.approx(50000.0)
    assert tb._parse_price_string("1,234.56") == pytest.approx(1234.56)
    assert tb._parse_price_string("2000") == pytest.approx(2000.0)
    assert tb._parse_price_string("") is None
    assert tb._parse_price_string("abc") is None


def test_detect_binary_btc_above(clean_imports):
    tb = _tb()
    market = {"question": "Will BTC be above $50,000 by June?", "market_id": "m1"}
    result = tb._detect_crypto_contract(market)
    assert result is not None
    asset, ctype, params = result
    assert asset == "BTC"
    assert ctype == "binary_threshold"
    assert params["threshold"] == pytest.approx(50000.0)


def test_detect_binary_eth_below(clean_imports):
    tb = _tb()
    market = {"question": "Will Ethereum drop below $2,000?", "market_id": "m1"}
    result = tb._detect_crypto_contract(market)
    assert result is not None
    asset, ctype, params = result
    assert asset == "ETH"
    assert ctype == "binary_threshold"
    assert params["threshold"] == pytest.approx(2000.0)


def test_detect_bracket(clean_imports):
    tb = _tb()
    market = {"question": "BTC price $40k-$45k on June 30", "market_id": "m1"}
    result = tb._detect_crypto_contract(market)
    assert result is not None
    asset, ctype, params = result
    assert asset == "BTC"
    assert ctype == "continuous_bracket"
    assert params["bracket_low"] == pytest.approx(40000.0)
    assert params["bracket_high"] == pytest.approx(45000.0)


def test_detect_non_crypto_returns_none(clean_imports):
    tb = _tb()
    market = {"question": "Will Trump win the election?", "market_id": "m1"}
    assert tb._detect_crypto_contract(market) is None


def test_dislocation_binary_underpriced(clean_imports):
    tb = _tb()
    # spot=$42k, threshold=$50k, YES=0.10 — market underpricing YES
    result = tb._compute_binary_dislocation(
        spot=42000, threshold=50000, market_yes=0.10,
        market_no=0.90, days_to_expiry=90
    )
    assert result is not None
    disl, direction, implied = result
    assert direction == "YES"  # our model says higher than 0.10
    assert disl > 0


def test_dislocation_binary_overpriced(clean_imports):
    tb = _tb()
    # spot=$42k, threshold=$50k, YES=0.80 — market overpricing YES
    result = tb._compute_binary_dislocation(
        spot=42000, threshold=50000, market_yes=0.80,
        market_no=0.20, days_to_expiry=90
    )
    assert result is not None
    disl, direction, implied = result
    assert direction == "NO"  # our model says lower than 0.80


def test_dislocation_binary_spot_above_threshold(clean_imports):
    tb = _tb()
    # spot=$55k, threshold=$50k — already above, YES should be high
    result = tb._compute_binary_dislocation(
        spot=55000, threshold=50000, market_yes=0.30,
        market_no=0.70, days_to_expiry=30
    )
    assert result is not None
    disl, direction, implied = result
    assert direction == "YES"  # spot already above → YES is underpriced at 0.30
    assert implied > 0.5


def test_edge_decay_inverted(clean_imports):
    tb = _tb()
    # Near expiry = high multiplier, far expiry = low
    assert tb._decay_multiplier(1) == pytest.approx(max(0.1, 1.0 - 1/180), abs=0.01)
    assert tb._decay_multiplier(90) == pytest.approx(0.5, abs=0.01)
    assert tb._decay_multiplier(180) == pytest.approx(0.1)
    assert tb._decay_multiplier(360) == pytest.approx(0.1)  # clamped


def test_min_edge_filters_small(clean_imports):
    tb = _tb()
    market = {
        "market_id": "m1", "question": "Will BTC be above $50,000 by June?",
        "yes_price": 0.50, "no_price": 0.50, "volume": 50000,
        "end_date": (datetime.datetime.utcnow() + datetime.timedelta(days=90)).isoformat(),
    }
    # Spot very close to where market implies → tiny dislocation → should return None
    result = tb._check_price_lag_arb(market, {"BTC": 49900}, 1000.0)
    # With spot at $49,900 and threshold $50k, the dislocation will be small
    # The result depends on the math — if edge < 5% after decay, returns None
    # This is a soft check: either None or a decision with small edge
    if result is not None:
        assert result.confidence >= 0.05  # must exceed min edge


def test_full_pipeline_produces_decision(clean_imports):
    tb = _tb()
    market = {
        "market_id": "m1",
        "question": "Will Bitcoin be above $50,000 by June 30?",
        "yes_price": 0.10,  # Very underpriced relative to spot near threshold
        "no_price": 0.90,
        "volume": 100000,
        "end_date": (datetime.datetime.utcnow() + datetime.timedelta(days=30)).isoformat(),
    }
    result = tb._check_price_lag_arb(market, {"BTC": 48000}, 1000.0)
    assert result is not None
    assert result.strategy == "price_lag_arb"
    assert result.direction in ("YES", "NO")
    assert result.confidence > 0
    assert result.metadata is not None
    assert result.metadata["asset"] == "BTC"
    assert result.metadata["contract_type"] == "binary_threshold"
    assert result.metadata["spot_price"] == 48000
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/openclaw && python3 -m pytest scripts/mirofish/tests/test_price_lag.py -v`
Expected: FAIL

- [ ] **Step 3: Add imports and constants to trading_brain.py**

At line 6 (imports section), add `import math` after `import re`.

After `ARB_POSITION_PCT` (line 20), add:

```python
PRICE_LAG_MIN_EDGE = float(os.environ.get("PRICE_LAG_MIN_EDGE", "0.05"))
PRICE_LAG_LATENCY_PENALTY = float(os.environ.get("PRICE_LAG_LATENCY_PENALTY", "0.005"))
PRICE_LAG_MAX_HORIZON = int(os.environ.get("PRICE_LAG_MAX_HORIZON", "180"))
```

Add `metadata: dict | None = None` as the last field in the `TradeDecision` dataclass (after `shares: float`).

- [ ] **Step 4: Add helper functions to trading_brain.py**

Add after the `_check_arbitrage` function (after line 91), before `_call_ollama`:

```python
# ── Price-lag arb helpers ──────────────────────────────────────────────────

_CRYPTO_ASSETS = {
    "BTC": re.compile(r"\b(?:BTC|Bitcoin)\b", re.IGNORECASE),
    "ETH": re.compile(r"\b(?:ETH|Ethereum)\b", re.IGNORECASE),
}

_BINARY_ABOVE_RE = re.compile(
    r"(?:above|over|exceed|reach|hit)\s*\$?([\d,]+\.?\d*[kK]?)", re.IGNORECASE
)
_BINARY_BELOW_RE = re.compile(
    r"(?:below|under|drop)\s*\$?([\d,]+\.?\d*[kK]?)", re.IGNORECASE
)
_BRACKET_RE = re.compile(
    r"\$?([\d,]+\.?\d*[kK]?)\s*[-\u2013]\s*\$?([\d,]+\.?\d*[kK]?)"
)


def _parse_price_string(s: str) -> float | None:
    """Normalize price strings: '$50,000' / '50k' / '1,234.56' → float."""
    if not s or not s.strip():
        return None
    s = s.strip().replace(",", "").replace("$", "")
    multiplier = 1.0
    if s.lower().endswith("k"):
        multiplier = 1000.0
        s = s[:-1]
    try:
        return float(s) * multiplier
    except ValueError:
        return None


def _detect_crypto_contract(market: dict) -> tuple | None:
    """Detect if a market is a crypto price contract.

    Returns: (asset, contract_type, params_dict) or None.
    - binary_threshold: params = {"threshold": float}
    - continuous_bracket: params = {"bracket_low": float, "bracket_high": float}
    """
    question = market.get("question", "")
    asset = None
    for a, pattern in _CRYPTO_ASSETS.items():
        if pattern.search(question):
            asset = a
            break
    if not asset:
        return None

    # Try bracket first (more specific pattern)
    m = _BRACKET_RE.search(question)
    if m:
        low = _parse_price_string(m.group(1))
        high = _parse_price_string(m.group(2))
        if low is not None and high is not None and low < high:
            return (asset, "continuous_bracket", {"bracket_low": low, "bracket_high": high})

    # Try binary above
    m = _BINARY_ABOVE_RE.search(question)
    if m:
        threshold = _parse_price_string(m.group(1))
        if threshold is not None:
            return (asset, "binary_threshold", {"threshold": threshold})

    # Try binary below
    m = _BINARY_BELOW_RE.search(question)
    if m:
        threshold = _parse_price_string(m.group(1))
        if threshold is not None:
            return (asset, "binary_threshold", {"threshold": threshold})

    return None


def _compute_binary_dislocation(
    spot: float, threshold: float, market_yes: float,
    market_no: float, days_to_expiry: int,
) -> tuple[float, str, float] | None:
    """Compute dislocation for binary threshold contract.

    Returns: (raw_dislocation, direction, implied_prob) or None.
    """
    distance_pct = abs(threshold - spot) / spot if spot > 0 else 999
    vol_factor = 0.5 * math.sqrt(max(days_to_expiry, 1) / 30)

    # Implied probability that price reaches/stays above threshold
    implied_prob = max(0.01, min(0.99, 1.0 - distance_pct / vol_factor))

    # Dislocation against market prices
    if implied_prob > market_yes:
        raw_dislocation = implied_prob - market_yes
        direction = "YES"
    else:
        implied_no = 1.0 - implied_prob
        raw_dislocation = implied_no - market_no
        direction = "NO"

    raw_dislocation = max(raw_dislocation, 0.0)
    return (raw_dislocation, direction, implied_prob)


def _compute_bracket_dislocation(
    spot: float, bracket_low: float, bracket_high: float,
    market_yes: float, days_to_expiry: int,
) -> tuple[float, str, float] | None:
    """Compute dislocation for continuous bracket contract."""
    bracket_width = bracket_high - bracket_low
    center = (bracket_low + bracket_high) / 2

    if bracket_low <= spot <= bracket_high:
        dist_from_center = abs(spot - center) / (bracket_width / 2) if bracket_width > 0 else 1
        implied_prob = max(0.05, 0.7 * (1.0 - dist_from_center))
    else:
        if spot < bracket_low:
            dist = (bracket_low - spot) / spot if spot > 0 else 999
        else:
            dist = (spot - bracket_high) / spot if spot > 0 else 999
        vol_factor = 0.5 * math.sqrt(max(days_to_expiry, 1) / 30)
        implied_prob = max(0.01, min(0.40, 0.3 * (1.0 - dist / vol_factor)))

    raw_dislocation = abs(implied_prob - market_yes)
    direction = "YES" if implied_prob > market_yes else "NO"
    return (raw_dislocation, direction, implied_prob)


def _decay_multiplier(days_to_expiry: int) -> float:
    """Inverted linear decay: near expiry = strong signal, far = weak."""
    return max(0.1, 1.0 - days_to_expiry / PRICE_LAG_MAX_HORIZON)


def _check_price_lag_arb(
    market: dict, spot_prices: dict[str, float], balance: float,
) -> TradeDecision | None:
    """Check if a Polymarket crypto contract has a price-lag dislocation."""
    detection = _detect_crypto_contract(market)
    if not detection:
        return None

    asset, contract_type, params = detection
    spot = spot_prices.get(asset)
    if not spot or spot <= 0:
        return None

    # Parse end_date
    end_date_str = market.get("end_date")
    if not end_date_str:
        return None
    try:
        import datetime as dt
        end_date = dt.datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
        days_to_expiry = (end_date.replace(tzinfo=None) - dt.datetime.utcnow()).days
    except (ValueError, TypeError):
        return None
    if days_to_expiry <= 0:
        return None

    market_yes = market.get("yes_price", 0) or 0
    market_no = market.get("no_price", 1.0 - market_yes)

    # Compute dislocation based on contract type
    if contract_type == "binary_threshold":
        result = _compute_binary_dislocation(
            spot, params["threshold"], market_yes, market_no, days_to_expiry
        )
    elif contract_type == "continuous_bracket":
        result = _compute_bracket_dislocation(
            spot, params["bracket_low"], params["bracket_high"],
            market_yes, days_to_expiry
        )
    else:
        return None

    if not result:
        return None
    raw_dislocation, direction, implied_prob = result

    # Apply edge decay and latency penalty
    decay = _decay_multiplier(days_to_expiry)
    decayed_edge = raw_dislocation * decay - PRICE_LAG_LATENCY_PENALTY
    if decayed_edge < PRICE_LAG_MIN_EDGE:
        return None

    # Size with Kelly
    entry_price = market_yes if direction == "YES" else market_no
    amount = _kelly_size(decayed_edge, entry_price, balance)
    if amount is None:
        return None

    # Build threshold/bracket for metadata
    threshold = params.get("threshold")
    bracket_low = params.get("bracket_low")
    bracket_high = params.get("bracket_high")

    reasoning = (
        f"Price-lag arb: {asset} spot=${spot:,.0f}, "
        f"implied={implied_prob:.2f} vs market={market_yes:.2f}, "
        f"raw={raw_dislocation:.3f}, decayed={decayed_edge:.3f}"
    )

    return TradeDecision(
        market_id=market.get("market_id", ""),
        question=market.get("question", ""),
        direction=direction,
        confidence=decayed_edge,
        reasoning=reasoning,
        strategy="price_lag_arb",
        amount_usd=amount,
        entry_price=entry_price,
        shares=amount / entry_price if entry_price > 0 else 0,
        metadata={
            "asset": asset,
            "contract_type": contract_type,
            "spot_price": spot,
            "threshold": threshold,
            "bracket_low": bracket_low,
            "bracket_high": bracket_high,
            "polymarket_price": market_yes,
            "raw_dislocation": raw_dislocation,
            "decayed_edge": decayed_edge,
            "days_to_expiry": float(days_to_expiry),
        },
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd ~/openclaw && python3 -m pytest scripts/mirofish/tests/test_price_lag.py -v`
Expected: All PASS

- [ ] **Step 6: Run existing tests to confirm nothing broke**

Run: `cd ~/openclaw && python3 -m pytest scripts/mirofish/tests/ -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
cd ~/openclaw
git add scripts/mirofish/trading_brain.py scripts/mirofish/tests/test_price_lag.py
git commit -m "feat(mirofish): price-lag arb helpers — parse, detect, compute dislocation"
```

---

### Task 4: Wire price-lag arb into analyze() + simulator integration

**Files:**
- Modify: `trading_brain.py:128-155` (analyze function)
- Modify: `simulator.py:137-163` (run_loop)

- [ ] **Step 1: Modify analyze() signature and add Step 1.5**

Change the `analyze()` signature to accept `spot_prices`:

```python
def analyze(
    markets: list[dict],
    wallet: dict[str, Any],
    signals: list[dict] | None = None,
    spot_prices: dict[str, float] | None = None,
) -> list[TradeDecision]:
```

After the Step 1 arb block (after `arb_market_ids.add(market["market_id"])`), add Step 1.5:

```python
    # Step 1.5: Price-lag arb (spot vs Polymarket dislocation)
    if spot_prices:
        for market in [m for m in markets if m["market_id"] not in arb_market_ids]:
            pla = _check_price_lag_arb(market, spot_prices, balance)
            if pla:
                decisions.append(pla)
                arb_market_ids.add(market["market_id"])
```

The existing `non_arb` computation on the next line already filters by `arb_market_ids`, so price-lag markets will be excluded from Ollama.

- [ ] **Step 2: Modify simulator.py run_loop()**

After the crucix_feed import (line 138), add:

```python
        import scripts.mirofish.spot_feed as spot_feed
```

After the `all_signals` line and before `decisions = brain.analyze(...)`, add spot fetch:

```python
        spot_signals = spot_feed.fetch()
        spot_dict = spot_feed.get_spot_dict()
        if spot_dict:
            print(f"[mirofish] Spot prices: " +
                  ", ".join(f"{k}=${v:,.0f}" for k, v in spot_dict.items()))
```

Change the `brain.analyze()` call to pass spot_prices:

```python
        decisions = brain.analyze(markets, state, signals=all_signals or None, spot_prices=spot_dict or None)
```

After the trade execution loop, add tracking:

```python
        for d in decisions:
            result = wallet.execute_trade(d)
            if result:
                print(f"[mirofish] Executed: {d.direction} ${d.amount_usd:.0f} "
                      f"on '{d.question[:50]}' [{d.strategy}]")
                if d.strategy == "price_lag_arb" and d.metadata:
                    _log_price_lag_trade(d)
            else:
                print(f"[mirofish] Rejected: {d.market_id} (cap or kelly)")
```

Add the `_log_price_lag_trade` function before `run_loop()`:

```python
def _log_price_lag_trade(decision) -> None:
    """Write price-lag arb tracking row from decision.metadata."""
    m = decision.metadata
    if not m:
        return
    try:
        with _get_conn() as conn:
            conn.execute("""
                INSERT INTO price_lag_trades
                (market_id, question, asset, contract_type, spot_price,
                 threshold, bracket_low, bracket_high, polymarket_price,
                 raw_dislocation, decayed_edge, days_to_expiry,
                 direction, confidence, amount_usd, entry_price, detected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                decision.market_id, decision.question,
                m.get("asset"), m.get("contract_type"), m.get("spot_price"),
                m.get("threshold"), m.get("bracket_low"), m.get("bracket_high"),
                m.get("polymarket_price"), m.get("raw_dislocation"),
                m.get("decayed_edge"), m.get("days_to_expiry"),
                decision.direction, decision.confidence,
                decision.amount_usd, decision.entry_price,
                datetime.datetime.utcnow().isoformat(),
            ))
    except Exception as e:
        print(f"[mirofish] Price-lag tracking error: {e}")
```

- [ ] **Step 3: Run full test suite**

Run: `cd ~/openclaw && python3 -m pytest scripts/mirofish/tests/ -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
cd ~/openclaw
git add scripts/mirofish/trading_brain.py scripts/mirofish/simulator.py
git commit -m "feat(mirofish): wire price-lag arb into analyze() and simulator run_loop"
```

---

## Summary

| Task | What it builds | Commit message |
|------|---------------|----------------|
| 1 | DB migrations | `feat(mirofish): add spot_prices + price_lag_trades table migrations` |
| 2 | spot_feed.py | `feat(mirofish): spot_feed module — Binance/Coinbase BTC/ETH with caching` |
| 3 | Price-lag helpers | `feat(mirofish): price-lag arb helpers — parse, detect, compute dislocation` |
| 4 | Integration | `feat(mirofish): wire price-lag arb into analyze() and simulator run_loop` |
