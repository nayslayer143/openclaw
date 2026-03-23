# Price-Lag Arbitrage Strategy — Design Spec

**Date:** 2026-03-23
**Feature:** Feature B — ClawdBot price-lag arb for Mirofish paper trading simulator
**Status:** Draft

---

## Overview

Add a price-lag arbitrage strategy to Mirofish that detects dislocations between spot crypto prices (Binance/Coinbase) and Polymarket contract prices for BTC/ETH markets. Supports both binary threshold contracts ("Will BTC be above $50k?") and continuous bracket contracts ("BTC price $40k-$45k"). Uses linear edge decay, simulated execution latency, and a separate tracking table for performance analysis.

## Goals

1. Fetch real-time BTC/ETH spot prices from Binance and Coinbase (free, no auth).
2. Detect price dislocations between spot prices and Polymarket crypto contracts.
3. Model edge decay over time (linear: further from expiry = higher edge).
4. Simulate execution latency as a cost penalty.
5. Integrate as a new strategy step inside `trading_brain.analyze()`.
6. Track price-lag trades in a separate DB table for independent performance analysis.

## Non-Goals

- Live trading (paper only).
- Spot price feeds for non-crypto assets.
- Sophisticated probability models (Black-Scholes, etc.) — intentionally simplified.
- Real order execution or exchange connectivity.

---

## Module 1: spot_feed.py — Spot Price DataFeed

**File:** `/Users/nayslayer/openclaw/scripts/mirofish/spot_feed.py`

Follows the established DataFeed pattern (duck-typed Protocol compatible). Provides the same module-level interface as `unusual_whales_feed.py`, `crucix_feed.py`. Includes its own `_get_conn()` following the same pattern. All logging uses `print(f"[spot_feed] ...")`.

```python
source_name = "spot_prices"

def fetch() -> list[dict]:
    """Fetch BTC + ETH spot from Binance + Coinbase, cache, return signal dicts."""

def get_cached() -> list[dict]:
    """Return cached spot price signals from DB."""

def get_spot_dict() -> dict[str, float]:
    """Return {'BTC': price, 'ETH': price} from latest cached data.
    Used by trading_brain for structured price lookup (not signal format)."""
```

### Spot Price Sources

**Binance (primary):**
- BTC: `GET https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT`
  - Response: `{"symbol": "BTCUSDT", "price": "42350.00"}`
- ETH: `GET https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT`

**Coinbase (secondary):**
- BTC: `GET https://api.coinbase.com/v2/prices/BTC-USD/spot`
  - Response: `{"data": {"base": "BTC", "currency": "USD", "amount": "42360.00"}}`
- ETH: `GET https://api.coinbase.com/v2/prices/ETH-USD/spot`

**Averaging logic:**
- If both exchanges return successfully, average the two prices.
- If one fails, use the other.
- If both fail, return `get_cached()`.

### Signal Dict Shape

```python
{
    "source": "spot_prices",
    "ticker": "SPOT:BTC" | "SPOT:ETH",
    "signal_type": "spot_price",
    "direction": "neutral",
    "amount_usd": 42350.0,       # the spot price itself
    "description": "BTC spot: $42,350.00 (binance=$42,340.00 coinbase=$42,360.00)",
    "fetched_at": "...",
}
```

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `SPOT_CACHE_TTL_HOURS` | `0.083` | Cache TTL (5 minutes) |
| `SPOT_TIMEOUT` | `10` | HTTP timeout per request (seconds) |

### Database Table

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
```

### Caching & Degradation

- Cache TTL: 5 minutes (spot prices move faster than OSINT).
- Fresh check: `_is_cache_fresh()` — same pattern as other feeds.
- Purge: rows older than 24 hours deleted on each fetch.
- On failure: return `get_cached()` or `[]`.

---

## Module 2: Price-Lag Arb Strategy in trading_brain.py

### New Function: `_check_price_lag_arb(market, spot_prices, balance)`

**Parameters:**
- `market` — a Polymarket market dict from `polymarket_feed`
- `spot_prices` — `{"BTC": 42350.0, "ETH": 2850.0}` from `spot_feed.get_spot_dict()`
- `balance` — current paper wallet balance

**Returns:** `TradeDecision | None`

### Contract Detection

Parse the market `question` field to identify crypto price contracts:

**Binary threshold detection** — regex patterns:
- `r"(?:BTC|Bitcoin).*(?:above|over|exceed|reach|hit)\s*\$?([\d,]+[kK]?)"` → extract threshold, direction=above
- `r"(?:BTC|Bitcoin).*(?:below|under|drop)\s*\$?([\d,]+[kK]?)"` → extract threshold, direction=below
- Same patterns for ETH/Ethereum

**Continuous bracket detection** — regex:
- `r"(?:BTC|Bitcoin).*\$?([\d,]+[kK]?)\s*[-–]\s*\$?([\d,]+[kK]?)"` → extract bracket_low, bracket_high

**Price string normalization:**
- `"50,000"` → `50000.0`
- `"50k"` or `"50K"` → `50000.0`
- `"1,234.56"` → `1234.56`

If the market doesn't match any pattern, return `None` (not a crypto price contract).

### Asset Identification

From the question text:
- Contains "BTC" or "Bitcoin" → asset = "BTC"
- Contains "ETH" or "Ethereum" → asset = "ETH"
- Neither → return None

### Dislocation Computation

**Binary threshold contracts:**

```python
spot = spot_prices[asset]          # e.g., 42350.0
threshold = extracted_threshold     # e.g., 50000.0
days_to_expiry = (end_date - now).days

# Distance as fraction of spot price
distance_pct = abs(threshold - spot) / spot

# Simplified probability model:
# P(reaching threshold) decreases with distance, increases with time
# Uses a crude volatility-adjusted estimate
vol_factor = 0.5 * math.sqrt(max(days_to_expiry, 1) / 30)  # ~monthly vol scaling
if spot < threshold:  # need price to go UP to hit threshold
    implied_prob = max(0.01, min(0.99, 1.0 - distance_pct / vol_factor))
else:  # already above threshold
    implied_prob = max(0.01, min(0.99, 1.0 - distance_pct / vol_factor))
    implied_prob = 1.0 - implied_prob  # flip for "above" when already above

# Dislocation
market_yes = market["yes_price"]
raw_dislocation = abs(implied_prob - market_yes)
direction = "YES" if implied_prob > market_yes else "NO"
```

**Continuous bracket contracts:**

```python
spot = spot_prices[asset]
bracket_low, bracket_high = extracted_bounds
bracket_width = bracket_high - bracket_low
center = (bracket_low + bracket_high) / 2

if bracket_low <= spot <= bracket_high:
    # Spot inside bracket — higher probability
    dist_from_center = abs(spot - center) / (bracket_width / 2)
    implied_prob = max(0.05, 0.5 * (1.0 - dist_from_center))
else:
    # Spot outside bracket — probability drops with distance
    if spot < bracket_low:
        dist = (bracket_low - spot) / spot
    else:
        dist = (spot - bracket_high) / spot
    vol_factor = 0.5 * math.sqrt(max(days_to_expiry, 1) / 30)
    implied_prob = max(0.01, min(0.40, 0.3 * (1.0 - dist / vol_factor)))

raw_dislocation = abs(implied_prob - market_yes)
direction = "YES" if implied_prob > market_yes else "NO"
```

### Edge Decay (Linear)

```python
MAX_HORIZON_DAYS = 180
decay_multiplier = min(days_to_expiry / MAX_HORIZON_DAYS, 1.0)
```

### Latency Simulation

```python
LATENCY_PENALTY = float(os.environ.get("PRICE_LAG_LATENCY_PENALTY", "0.005"))  # 0.5%
```

Represents the cost of not being able to execute instantly — by the time a paper trade would fill, the dislocation may have partially closed.

### Final Edge Computation

```python
decayed_edge = raw_dislocation * decay_multiplier - LATENCY_PENALTY
```

### Minimum Edge Threshold

```python
PRICE_LAG_MIN_EDGE = float(os.environ.get("PRICE_LAG_MIN_EDGE", "0.05"))  # 5%
```

If `decayed_edge < PRICE_LAG_MIN_EDGE`, return None (not enough edge to trade).

### Position Sizing

Uses the existing `_kelly_size(confidence, entry_price, balance)` function.
- `confidence` = `decayed_edge` (the edge IS the confidence for this strategy)
- `entry_price` = YES or NO price depending on direction
- Capped at `MAX_POSITION_PCT` (10% of balance, same as Ollama trades)

### TradeDecision Output

```python
TradeDecision(
    market_id=market["market_id"],
    question=market["question"],
    direction=direction,      # "YES" | "NO"
    confidence=decayed_edge,
    reasoning=f"Price-lag arb: {asset} spot=${spot:,.0f} vs threshold=${threshold:,.0f}, "
              f"implied={implied_prob:.2f} vs market={market_yes:.2f}, "
              f"raw_disl={raw_dislocation:.3f}, decayed={decayed_edge:.3f}",
    strategy="price_lag_arb",
    amount_usd=amount,
    entry_price=entry_price,
    shares=amount / entry_price,
)
```

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `PRICE_LAG_MIN_EDGE` | `0.05` | Minimum decayed edge to trigger trade (5%) |
| `PRICE_LAG_LATENCY_PENALTY` | `0.005` | Simulated execution cost (0.5%) |
| `PRICE_LAG_MAX_HORIZON` | `180` | Max days for linear decay denominator |

---

## Module 3: Separate Tracking Table

### Database Schema

```sql
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

### When to Write

After `paper_wallet.execute_trade(decision)` returns successfully for a decision with `strategy == "price_lag_arb"`, write the tracking row. This is done in `simulator.py`'s trade execution loop.

The tracking table is **write-only during simulation** — it's for post-hoc analysis, not for the trading loop to read.

### Tracking Data Sources

The extra fields (spot_price, threshold, etc.) are stored in the `reasoning` string on the TradeDecision. To avoid parsing the reasoning string, add a `metadata` dict to TradeDecision as an optional field:

```python
@dataclass
class TradeDecision:
    market_id:   str
    question:    str
    direction:   str
    confidence:  float
    reasoning:   str
    strategy:    str
    amount_usd:  float
    entry_price: float
    shares:      float
    metadata:    dict | None = None  # NEW: strategy-specific data for tracking
```

For price-lag arb decisions, `metadata` contains:
```python
{
    "asset": "BTC",
    "contract_type": "binary_threshold",
    "spot_price": 42350.0,
    "threshold": 50000.0,
    "bracket_low": None,
    "bracket_high": None,
    "polymarket_price": 0.30,
    "raw_dislocation": 0.15,
    "decayed_edge": 0.072,
    "days_to_expiry": 98.0,
}
```

---

## Integration Points

### simulator.py changes

1. Add `price_lag_trades` and `spot_prices` tables to migration block.
2. Import `spot_feed` in `run_loop()`.
3. Fetch spot prices and pass to brain:
   ```python
   import scripts.mirofish.spot_feed as spot_feed
   spot_signals = spot_feed.fetch()
   spot_dict = spot_feed.get_spot_dict()
   all_signals = uw_signals + crucix_signals + spot_signals
   decisions = brain.analyze(markets, state, signals=all_signals or None, spot_prices=spot_dict)
   ```
4. After executing a price-lag trade, write the tracking row:
   ```python
   for d in decisions:
       result = wallet.execute_trade(d)
       if result and d.strategy == "price_lag_arb" and d.metadata:
           _log_price_lag_trade(d)
   ```

### trading_brain.py changes

1. Add `import math` to imports.
2. Add `PRICE_LAG_MIN_EDGE`, `PRICE_LAG_LATENCY_PENALTY`, `PRICE_LAG_MAX_HORIZON` constants.
3. Add `metadata: dict | None = None` field to TradeDecision dataclass.
4. Add helper functions:
   - `_parse_price_string(s)` — normalize "$50,000" / "50k" → float
   - `_detect_crypto_contract(market)` — returns `(asset, contract_type, threshold_or_brackets)` or None
   - `_compute_dislocation(...)` — the math from the spec
   - `_check_price_lag_arb(market, spot_prices, balance)` — orchestrates detection → dislocation → decay → decision
5. Modify `analyze()` signature: `analyze(markets, wallet, signals=None, spot_prices=None)`
6. Add Step 1.5 between existing arb and Ollama:
   ```python
   # Step 1.5: Price-lag arb (spot vs Polymarket dislocation)
   if spot_prices:
       for market in non_arb:
           pla = _check_price_lag_arb(market, spot_prices, balance)
           if pla:
               decisions.append(pla)
               arb_market_ids.add(market["market_id"])
       # Rebuild non_arb to exclude price-lag arb markets from Ollama
       non_arb = [m for m in markets if m["market_id"] not in arb_market_ids]
   ```

---

## Testing

### test_spot_feed.py

| Test | What it verifies |
|------|-----------------|
| `test_fetch_binance_and_coinbase` | Mocked responses → averaged prices → correct signal dicts |
| `test_fetch_one_exchange_down` | One exchange fails → uses other's price |
| `test_fetch_both_down` | Both fail → returns cached or [] |
| `test_get_spot_dict` | Returns `{"BTC": float, "ETH": float}` from cached data |
| `test_cache_freshness` | Fresh cache → no HTTP calls |
| `test_signal_dict_shape` | Required keys, correct types |

### test_price_lag.py

| Test | What it verifies |
|------|-----------------|
| `test_parse_price_string` | "$50,000" → 50000, "50k" → 50000, "1,234.56" → 1234.56 |
| `test_detect_binary_btc_above` | "Will BTC be above $50,000?" → (BTC, binary_threshold, 50000) |
| `test_detect_binary_eth_below` | "Will ETH drop below $2,000?" → (ETH, binary_threshold, 2000) |
| `test_detect_bracket` | "BTC price $40k-$45k" → (BTC, continuous_bracket, (40000, 45000)) |
| `test_detect_non_crypto_returns_none` | "Will Trump win?" → None |
| `test_dislocation_binary_underpriced` | spot=$42k, threshold=$50k, YES=0.10 → YES direction |
| `test_dislocation_binary_overpriced` | spot=$42k, threshold=$50k, YES=0.80 → NO direction |
| `test_dislocation_bracket_inside` | spot inside bracket → higher implied prob |
| `test_dislocation_bracket_outside` | spot outside bracket → lower implied prob |
| `test_edge_decay_linear` | 180 days → multiplier=1.0, 90 days → 0.5, 0 days → ~0 |
| `test_latency_penalty_applied` | edge is reduced by latency penalty |
| `test_min_edge_filters_small` | edge < 5% → returns None |
| `test_full_pipeline_produces_decision` | Mocked market + spot → TradeDecision with strategy="price_lag_arb" |
| `test_metadata_populated` | TradeDecision.metadata has all required tracking fields |

---

## File Change Summary

| File | Change type | Description |
|------|------------|-------------|
| `spot_feed.py` | **New** | Spot price DataFeed module (~150 lines) |
| `trading_brain.py` | Edit | Add price-lag arb strategy + metadata field (~120 lines added) |
| `simulator.py` | Edit | Add migration, spot_feed import, tracking table writes |
| `tests/test_spot_feed.py` | **New** | Spot feed tests |
| `tests/test_price_lag.py` | **New** | Price-lag arb strategy tests |
