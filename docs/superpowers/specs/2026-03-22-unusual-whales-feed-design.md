# Unusual Whales Feed Integration — Design Spec

**Date:** 2026-03-22
**Status:** Approved

---

## Goal

Add Unusual Whales as a second market data feed alongside Polymarket. UW signals (options flow, dark pool, congressional trades, institutional holdings) are fetched, cached in SQLite, and injected into the existing Ollama prompt in `trading_brain.analyze()` so the LLM can reason about cross-market relevance when making Polymarket bet decisions.

The system degrades gracefully to Polymarket-only mode when `UNUSUAL_WHALES_API_KEY` is not set.

---

## Architecture

### Signal Flow

```
simulator.run_loop()
  → polymarket_feed.fetch_markets()     # existing, unchanged
  → unusual_whales_feed.fetch()         # new — [] if key not set
  → trading_brain.analyze(markets, wallet, signals=uw_signals)
      → arb fast-path (unchanged, ignores signals)
      → Ollama prompt (enriched with UW signals when present)
  → paper_wallet.execute_trade()        # unchanged
  → paper_wallet.check_stops()         # unchanged
  → dashboard.maybe_snapshot()          # unchanged
```

### DataFeed Protocol

`scripts/mirofish/base_feed.py` — structural protocol, no shared logic:

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class DataFeed(Protocol):
    source_name: str
    def fetch(self) -> list[dict]: ...
    def get_cached(self) -> list[dict]: ...
```

No inheritance required. `unusual_whales_feed.py` satisfies it structurally. `polymarket_feed.py` is not modified — it also satisfies the protocol structurally via its existing `fetch_markets()` / `get_latest_prices()` functions exposed at module level. Future feeds just implement `fetch()` and `get_cached()`.

---

## Data Model

New table added to `MIGRATION_SQL` in `simulator.py`:

```sql
CREATE TABLE IF NOT EXISTS uw_signals (
    id          INTEGER PRIMARY KEY,
    source      TEXT NOT NULL,
    ticker      TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    direction   TEXT NOT NULL,
    amount_usd  REAL,
    description TEXT NOT NULL,
    fetched_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_uw_signals_ticker_time
    ON uw_signals(ticker, fetched_at);
```

**`source` values:** `options_flow` | `dark_pool` | `congressional` | `institutional`

**`signal_type` values:**
- options_flow: `call_sweep` | `put_sweep` | `call_block` | `put_block`
- dark_pool: `dark_pool_block`
- congressional: `buy` | `sell`
- institutional: `new_position` | `increased` | `decreased` | `closed`

**`direction` logic (deterministic, no LLM):**
- Options: calls → `bullish`, puts → `bearish`
- Dark pool: always `neutral` (intent unknown)
- Congressional: Buy → `bullish`, Sell → `bearish`
- Institutional: `units_change > 0` → `bullish`, `< 0` → `bearish`, `= 0` → `neutral`

---

## `unusual_whales_feed.py`

### Configuration

```python
UNUSUAL_WHALES_API_KEY = os.environ.get("UNUSUAL_WHALES_API_KEY", "")
UW_BASE_URL = "https://api.unusualwhales.com"
UW_CACHE_TTL_HOURS = float(os.environ.get("UW_CACHE_TTL_HOURS", "1.0"))
UW_SIGNAL_LIMIT   = int(os.environ.get("UW_SIGNAL_LIMIT", "50"))
```

Auth: `Authorization: Bearer {UNUSUAL_WHALES_API_KEY}` header on all requests.

### Public Interface

```python
source_name = "unusual_whales"

def fetch() -> list[dict]:
    """
    Fetch all 4 signal groups from UW API, cache to uw_signals table, return list.
    Returns [] immediately (with warning log) if UNUSUAL_WHALES_API_KEY not set.
    On API failure, returns cached signals (or [] if cache empty). Never raises.
    Cache TTL: UW_CACHE_TTL_HOURS (default 1h). Fresh cache skips live fetch.
    """

def get_cached() -> list[dict]:
    """
    Return signals from uw_signals table fetched within UW_CACHE_TTL_HOURS.
    No live fetch. Returns [] if cache empty or stale.
    """
```

### Normalized Signal Shape

Both `fetch()` and `get_cached()` return lists of:

```python
{
    "source":      str,   # options_flow | dark_pool | congressional | institutional
    "ticker":      str,   # e.g. "NVDA"
    "signal_type": str,   # call_sweep | put_sweep | dark_pool_block | buy | sell | ...
    "direction":   str,   # bullish | bearish | neutral
    "amount_usd":  float, # premium (options), value (dark pool/institutional), amount range midpoint (congressional)
    "description": str,   # human-readable one-liner for Ollama prompt injection
    "fetched_at":  str,   # ISO timestamp
}
```

### UW Endpoints Fetched

| Source | Endpoint | Params |
|--------|----------|--------|
| options_flow | `GET /api/option-trades/flow-alerts` | `limit=UW_SIGNAL_LIMIT` |
| dark_pool | `GET /api/darkpool/recent` | `limit=UW_SIGNAL_LIMIT` |
| congressional | `GET /api/congress/recent-trades` | `limit=UW_SIGNAL_LIMIT` |
| institutional | `GET /api/institutions/latest_filings` | `limit=UW_SIGNAL_LIMIT` |

Response envelope: `{"data": [...]}`. All responses parsed via `resp.json()["data"]`.

### Description Generation

Human-readable one-liners for Ollama context injection:

- Options flow: `"{ticker} {signal_type} exp {expiry} — ${premium:.1f}M premium, vol/OI {ratio:.1f}x"`
- Dark pool: `"{ticker} dark pool block — ${size:.1f}M at ${price:.2f}"`
- Congressional: `"{ticker} {txn_type} by {name} ({member_type}) — {amounts}"`
- Institutional: `"{ticker} {signal_type} by {institution} — {units_change:+,} units"`

### Internal Functions

```python
def _get_conn() -> sqlite3.Connection:
    # Same pattern as all other mirofish modules:
    # resolves CLAWMSON_DB_PATH from env at call time, WAL mode, row_factory=sqlite3.Row

def _call_uw(endpoint: str, params: dict) -> list[dict]:
    # GET {UW_BASE_URL}{endpoint} with Bearer auth
    # Returns resp.json()["data"] or [] on any error
    # Timeout: 30s

def _is_cache_fresh() -> bool:
    # True if any uw_signals row has fetched_at within UW_CACHE_TTL_HOURS

def _normalize_options_flow(item: dict) -> dict | None:
    # Converts UW options flow item to normalized signal dict
    # Returns None if required fields missing

def _normalize_dark_pool(item: dict) -> dict | None:
    # Converts UW dark pool item to normalized signal dict

def _normalize_congressional(item: dict) -> dict | None:
    # Converts UW congressional item to normalized signal dict

def _normalize_institutional(item: dict) -> dict | None:
    # Converts UW institutional filing item to normalized signal dict

def _store_signals(signals: list[dict]) -> None:
    # Batch INSERT OR IGNORE into uw_signals table
```

### Graceful Degradation

1. **No API key** → log warning once per process, return `[]` immediately
2. **API error** (timeout, 4xx, 5xx) → log error, fall through to cached data
3. **Cache empty** → return `[]`, no exception
4. **Malformed response item** → skip item, log debug, continue

---

## `trading_brain.py` Changes

### Signature Change

```python
def analyze(
    markets: list[dict],
    wallet: dict[str, Any],
    signals: list[dict] | None = None,
) -> list[TradeDecision]:
```

Fully backward-compatible — `signals=None` preserves existing callers.

### Ollama Prompt Injection

When `signals` is non-empty, append to the prompt after the market list and before the JSON instruction:

```
Active market signals (Unusual Whales):
- [OPTIONS_FLOW] NVDA bullish call_sweep — NVDA $1000C Apr-26 sweep, $2.5M premium, vol/OI 3.2x
- [CONGRESSIONAL] TSLA bearish sell — Sen. X sold TSLA $50K-$100K (filed 2026-03-20)
- [DARK_POOL] SPY neutral dark_pool_block — SPY dark pool block $8.2M at $520.10

When analyzing Polymarket markets, consider whether any of these signals suggest a
related outcome is more or less likely. A bullish options sweep on NVDA is a signal
that sophisticated money expects NVDA to rise — factor this into any Polymarket market
about Nvidia price, earnings, or company performance.
```

Signals are capped at 20 entries in the prompt (most recent by `fetched_at`) to avoid excessive context length.

### Arb Path

Unchanged — `_check_arbitrage()` ignores signals entirely (pure-math, no LLM).

---

## `simulator.py` Changes

### Migration

Add `uw_signals` table + index to `MIGRATION_SQL`. Idempotent (`CREATE TABLE IF NOT EXISTS`).

### `run_loop()` Addition

```python
# After feed.fetch_markets(), before brain.analyze():
import scripts.mirofish.unusual_whales_feed as uw_feed
uw_signals = uw_feed.fetch()  # [] if key not set or API down
if uw_signals:
    print(f"[mirofish] UW signals: {len(uw_signals)} ({len(set(s['ticker'] for s in uw_signals))} tickers)")

decisions = brain.analyze(markets, state, signals=uw_signals or None)
```

---

## Tests (`test_uw_feed.py`, 5 tests)

All tests use the standard `temp_db` fixture (monkeypatch `CLAWMSON_DB_PATH`, flush mirofish modules, call `migrate()`).

1. **`test_graceful_degrade_when_no_api_key`** — unset `UNUSUAL_WHALES_API_KEY`, call `fetch()`, assert returns `[]`, no exception raised
2. **`test_normalize_options_flow`** — call `_normalize_options_flow()` with a raw UW item dict, assert returned dict has all required keys with correct `direction="bullish"` for call type
3. **`test_normalize_congressional`** — call `_normalize_congressional()` with buy and sell items, assert `direction="bullish"` and `direction="bearish"` respectively
4. **`test_cache_returns_when_fresh`** — insert a signal row into `uw_signals` with `fetched_at=now`, call `fetch()` with monkeypatched `_call_uw` that raises, assert returns cached data without error
5. **`test_signals_injected_into_ollama_prompt`** — monkeypatch `_call_ollama` to capture prompt, call `analyze(markets, wallet, signals=[sample_signal])`, assert captured prompt contains `"Active market signals"` and the signal's ticker

---

## Configuration Summary (`.env`)

```bash
UNUSUAL_WHALES_API_KEY=         # empty = Polymarket-only mode
UW_CACHE_TTL_HOURS=1.0          # cache TTL in hours (default 1h)
UW_SIGNAL_LIMIT=50              # signals per endpoint (max 200)
```

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Key not set | Log warning, return `[]` |
| API timeout (30s) | Log error, return cached or `[]` |
| API 401 Unauthorized | Log error with hint to check key, return `[]` |
| API 429 Rate Limited | Log error, return cached or `[]` |
| Malformed item in response | Skip item, log debug, continue |
| DB write fails | Log error, still return fetched signals |

---

## What This Is NOT

- No WebSocket/streaming integration (REST polling only)
- No UW-native trade decisions (signals only inform Ollama, no direct `TradeDecision` from UW)
- No per-ticker targeted fetch (global recent endpoints only — targeted queries are future scope)
- No backfill of historical UW signals
- No stock/options paper trading beyond Polymarket (signals enrich Polymarket decisions only)
