# Crucix OSINT Feed — Design Spec

**Date:** 2026-03-23
**Feature:** Feature A — Crucix Feed integration for Mirofish paper trading simulator
**Status:** Draft

---

## Overview

Add a new `crucix_feed.py` DataFeed module to Mirofish that fetches OSINT intelligence from the local Crucix Express.js API, normalizes all 29 sources into the standard signal dict shape, and injects them into the Ollama prompt via a two-pass format (pre-digested ideas + capped raw signals).

Crucix runs locally on port 3117 and aggregates 29 public intelligence sources (GDELT, FRED, ACLED, NASA FIRMS, NOAA, WHO, etc.) into a single `/api/data` endpoint, refreshing every 15 minutes.

## Goals

1. Bring all 29 Crucix OSINT sources into Mirofish's signal pipeline.
2. Follow the established DataFeed pattern (module-level `source_name`, `fetch()`, `get_cached()`).
3. Use synthetic category tickers for non-ticker signals (e.g., `GEO:UKRAINE`, `MACRO:VIX`).
4. Inject signals into the Ollama prompt with a two-pass format: Crucix ideas block first, then merged raw signals.
5. Cache signals in SQLite with TTL matching Crucix's 15-minute refresh cycle.
6. Degrade gracefully when Crucix is unreachable.

## Non-Goals

- Modifying Crucix itself.
- Building a separate UI or dashboard for Crucix signals.
- Implementing per-source endpoint calls (Crucix only exposes `/api/data`).
- Feature B (price-lag arbitrage strategy) — separate spec.

---

## Module Interface

**File:** `/Users/nayslayer/openclaw/scripts/mirofish/crucix_feed.py`

```python
source_name = "crucix"

def fetch() -> list[dict]:
    """Fetch from Crucix /api/data, normalize all 29 sources, cache, return signals."""

def get_cached() -> list[dict]:
    """Return cached signals from DB without hitting Crucix."""
```

Provides the same module-level interface as `unusual_whales_feed.py`. Note: module-level duck typing means `isinstance(crucix_feed, DataFeed)` will return False; callers must invoke `crucix_feed.fetch()` directly (same limitation as the UW feed). Includes its own `_get_conn()` following the same pattern as `unusual_whales_feed.py`.

All logging uses `print(f"[crucix_feed] ...")` following the established convention.

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `CRUCIX_BASE_URL` | `http://localhost:3117` | Crucix API base URL |
| `CRUCIX_CACHE_TTL_HOURS` | `0.25` | Cache TTL in hours (15 min) |
| `CRUCIX_SIGNAL_LIMIT` | `20` | Max Crucix signals per fetch after priority sort |
| `CLAWMSON_DB_PATH` | `~/.openclaw/clawmson.db` | Shared SQLite database |

---

## Database Schema

New table in `clawmson.db`, added to `simulator.py`'s idempotent migration block:

```sql
CREATE TABLE IF NOT EXISTS crucix_signals (
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
CREATE INDEX IF NOT EXISTS idx_crucix_signals_ticker_time
    ON crucix_signals(ticker, fetched_at);
```

Follows the same pattern as `uw_signals`.

---

## Standard Signal Dict Shape

Every normalizer emits dicts matching this shape (same as Unusual Whales):

```python
{
    "source": str,          # Crucix source name: "gdelt", "fred", "acled", "thermal", etc.
    "ticker": str,          # Synthetic category ticker: "GEO:UKRAINE", "MACRO:VIX", etc.
    "signal_type": str,     # Domain-specific type: "conflict_escalation", "indicator_spike", etc.
    "direction": str,       # "bullish" | "bearish" | "neutral"
    "amount_usd": float | None,  # Monetary value where applicable
    "description": str,     # Human-readable one-liner
    "fetched_at": str,      # ISO-format datetime
}
```

---

## Normalizer Architecture

Six domain normalizer functions, each receiving the full `/api/data` dict and extracting their relevant keys:

### `_normalize_geopolitical(data) -> list[dict]`

**Consumes:** `gdelt`, `acled`, `tg`

| Source | Ticker pattern | signal_type | Direction logic |
|--------|---------------|-------------|-----------------|
| `gdelt` | `GEO:{top region}` | `conflict_event`, `crisis_event`, `economy_event` | conflicts > threshold → bearish; economy events → context-dependent |
| `acled` | `GEO:{country}` | `conflict_escalation`, `armed_clash`, `airstrike` | Fatalities > 0 → bearish; by event type |
| `tg` (urgent) | `GEO:TELEGRAM` | `urgent_intel` | Urgent flags present → bearish |

**Key extraction points:**
- `gdelt.conflicts`, `gdelt.crisis`, `gdelt.topTitles` → event signals
- `acled.deadliestEvents` → individual conflict signals with lat/lon
- `tg.urgent` → high-priority Telegram posts with escalation keywords

### `_normalize_economic(data) -> list[dict]`

**Consumes:** `fred`, `energy`, `treasury`, `bls`, `gscpi`, `markets`

| Source | Ticker pattern | signal_type | Direction logic |
|--------|---------------|-------------|-----------------|
| `fred` | `MACRO:{id}` (e.g., `MACRO:VIXCLS`) | `indicator_level`, `indicator_spike` | VIX > 20 or momChangePct > 5% → bearish; unemployment spike → bearish |
| `energy` | `ENERGY:WTI`, `ENERGY:BRENT`, `ENERGY:NATGAS` | `price_level`, `inventory_signal` | Price spikes → bearish (inflation); inventory signals from `energy.signals` |
| `treasury` | `MACRO:DEBT` | `debt_milestone` | Always bearish (debt ceiling stress) |
| `bls` | `MACRO:UNRATE`, `MACRO:WAGES` | `labor_signal` | Rising unemployment → bearish; rising wages → mixed |
| `gscpi` | `MACRO:SUPPLY_CHAIN` | `supply_chain_pressure` | value > 1.0 → bearish; < -0.5 → bullish |
| `markets` | `CRYPTO:BTC`, `INDEX:SPX`, `COMMODITY:GOLD` | `price_move` | Derived from change/changePct |

**Key extraction points:**
- `fred[]` array → iterate, emit signal for each indicator with significant momChangePct
- `energy.signals[]` → pre-computed signals (INVENTORY_SPIKE, etc.)
- `treasury.signals[]` → debt milestone signals
- `markets.crypto/indexes/commodities` → price level context

### `_normalize_military(data) -> list[dict]`

**Consumes:** `thermal`, `tSignals`, `air`, `space`, `sdr`

| Source | Ticker pattern | signal_type | Direction logic |
|--------|---------------|-------------|-----------------|
| `thermal` | `MIL:{region}` | `fire_anomaly` | High confidence fires → bearish |
| `tSignals` | `MIL:STRIKE` | `military_strike` | confidence > 0.8 → bearish |
| `air` | `AIR:{region}` | `unidentified_aircraft` | noCallsign count elevated → bearish |
| `space` | `SPACE:LAUNCH`, `SPACE:MILSAT` | `satellite_deployment`, `launch_event` | Military sat deployments → bearish |
| `sdr` | `SIGINT:{region}` | `sdr_activity` | Anomalous receiver counts → neutral |

**Key extraction points:**
- `tSignals[]` → MILITARY_STRIKE with confidence scores
- `thermal[].hc` (high confidence fires), `thermal[].fires` (high intensity)
- `air[].noCallsign` → unidentified military aircraft
- `space.signals[]` → military satellite events
- `space.recentLaunches` → launch events

### `_normalize_environmental(data) -> list[dict]`

**Consumes:** `noaa`, `nuke`, `nukeSignals`, `epa`, `who`

| Source | Ticker pattern | signal_type | Direction logic |
|--------|---------------|-------------|-----------------|
| `noaa` | `ENV:{event type}` | `severe_weather` | severity == "Severe" or "Extreme" → bearish |
| `nuke` | `ENV:RADIATION` | `radiation_reading` | anom == true → bearish |
| `nukeSignals` | `ENV:RADIATION` | `radiation_anomaly` | Always bearish |
| `epa` | `ENV:EPA_RAD` | `epa_radiation` | Elevated readings → bearish |
| `who` | `ENV:OUTBREAK` | `disease_outbreak` | Always bearish |

**Key extraction points:**
- `noaa.alerts[]` → severe weather events with severity
- `nuke[]` → anomaly flags per nuclear site
- `nukeSignals[]` → elevated reading alerts
- `who[]` → disease outbreak summaries

### `_normalize_maritime(data) -> list[dict]`

**Consumes:** `chokepoints`

| Source | Ticker pattern | signal_type | Direction logic |
|--------|---------------|-------------|-----------------|
| `chokepoints` | `SEA:{label}` (e.g., `SEA:HORMUZ`) | `chokepoint_status` | Presence = context signal → neutral |

Minimal normalizer — chokepoint data is mostly positional context. Signals only emitted if chokepoint disruption indicators exist.

### `_normalize_meta(data) -> list[dict]`

**Consumes:** `delta`, `ideas`, `health`

| Source | Ticker pattern | signal_type | Direction logic |
|--------|---------------|-------------|-----------------|
| `delta.summary` | `META:REGIME` | `regime_signal` | `risk-on` → bullish, `risk-off` → bearish, `mixed` → neutral |
| `delta.signals` | `META:{type}` | `critical_change` | Per-signal: VIX_SPIKE → bearish, etc. |
| `ideas` | `IDEA:{n}` | `crucix_idea` | `long` → bullish, `hedge` → bearish, `watch` → neutral |
| `health` | (not emitted as signals) | — | Used for filtering only |

**Source naming for partition:** The `_normalize_meta` function must use these exact `source` values so `trading_brain.py` can partition signals for two-pass injection:
- Delta/regime signals: `source` = `"crucix_delta"` (not `"delta"`)
- Idea signals: `source` = `"crucix_ideas"` (not `"ideas"` or `"crucix"`)

**Health structure:** The `health` field is an array of objects: `[{n: "GDELT", err: false, stale: false}, ...]`. The `n` field maps to the Crucix source name. Before normalizing a source, look up its health entry by matching `health[].n` against the source key name (case-insensitive). Skip any source where `err == true` or `stale == true`.

---

## Priority Scoring

Before capping at `CRUCIX_SIGNAL_LIMIT`, signals are sorted by priority score (descending):

| Priority | Source category | Score |
|----------|----------------|-------|
| 1 (highest) | `delta` critical changes | 100 |
| 2 | `ideas` (pre-digested) | 90 |
| 3 | `tSignals` military strikes | 80 |
| 4 | `tg` urgent posts | 70 |
| 5 | `acled` deadliest events | 60 |
| 6 | `fred` significant moves (momChangePct > 3%) | 50 |
| 7 | `energy` signals | 45 |
| 8 | `noaa` severe/extreme alerts | 40 |
| 9 | `nukeSignals` radiation anomalies | 35 |
| 10 | Everything else | 10 |

The `_priority_score(signal)` function maps `(source, signal_type)` pairs to these scores. After sorting, the top `CRUCIX_SIGNAL_LIMIT` signals are kept; the rest are discarded before DB insertion.

---

## Two-Pass Prompt Injection

### Changes to `trading_brain.py`

The `analyze()` function's prompt construction is modified:

**Pass 1 — Crucix Ideas Block** (new, inserted before raw signals):

```
Crucix OSINT Intelligence Summary:
Overall regime: {delta.summary.direction} | {delta.summary.criticalChanges} critical changes detected

Pre-analyzed trade ideas (from cross-source OSINT correlation):
- [{type} | {confidence} confidence | {horizon}] {title} — {text}
- ...
```

This block is built from signals where `source == "crucix_ideas"`. If no ideas exist, this block is omitted.

**Pass 2 — Raw Signals** (modified existing block):

The header changes from `"Active market signals (Unusual Whales):"` to `"Active market signals:"`. Both UW and Crucix signals are merged into one list, sorted by `fetched_at` descending, and capped at `MERGED_SIGNAL_LIMIT` (default 30, new env var in `trading_brain.py`). Crucix contributes up to `CRUCIX_SIGNAL_LIMIT` (20), UW contributes up to `UW_SIGNAL_LIMIT` (20), merged list capped at 30 after interleaved sort. Each signal line includes its source for attribution:

```
- [GDELT] GEO:UKRAINE bearish conflict_escalation — 42 conflicts, Kyiv hotspot
- [OPTIONS_FLOW] NVDA bullish call_sweep — $2.5M premium
- [FRED] MACRO:VIX bearish indicator_spike — VIX at 18.5, +1.65% MoM
```

The contextual instruction is replaced with the full text specified in the `trading_brain.py` changes section above.

---

## Caching Strategy

- **Cache table:** `crucix_signals` (see schema above)
- **TTL:** `CRUCIX_CACHE_TTL_HOURS` (default 0.25 = 15 minutes)
- **Fresh check:** `_is_cache_fresh()` returns True if any row has `fetched_at` within TTL
- **On fresh cache:** `fetch()` returns `get_cached()` without hitting Crucix
- **On stale cache:** Fetch from Crucix, normalize, upsert into DB (INSERT OR IGNORE for UNIQUE dedup), return new signals
- **Upsert strategy:** DELETE rows older than 24 hours on each fetch to prevent unbounded growth, then INSERT OR IGNORE new rows

---

## Graceful Degradation

| Failure mode | Behavior |
|-------------|----------|
| Crucix unreachable (connection refused, timeout) | Log warning, return `get_cached()` |
| Crucix returns HTTP error (4xx/5xx) | Log warning, return `get_cached()` |
| Crucix returns partial data (some `health[].err == true`) | Normalize available sources, skip errored ones, log which failed |
| Crucix returns empty/malformed JSON | Log error, return `get_cached()` |
| No cached data and Crucix unreachable | Return `[]` (same as UW when no API key) |
| Individual normalizer raises exception | Catch per-normalizer, log, continue with other domains |

Request timeout: 30 seconds (Crucix response is local, should be fast).

---

## Integration Points

### `simulator.py` changes

1. Add `crucix_signals` table to migration block.
2. In `run_loop()`, add Crucix fetch alongside UW fetch:
   ```python
   uw_signals = unusual_whales_feed.fetch()
   crucix_signals = crucix_feed.fetch()
   all_signals = uw_signals + crucix_signals
   ```
3. Pass merged list to `trading_brain.analyze(markets, state, signals=all_signals or None)`.

### `trading_brain.py` changes

1. **Partition signals** at the top of the prompt-building section:
   ```python
   crucix_ideas = [s for s in signals if s.get("source") == "crucix_ideas"]
   regime_signals = [s for s in signals if s.get("source") == "crucix_delta"]
   raw_signals = [s for s in signals if s.get("source") not in ("crucix_ideas", "crucix_delta")]
   ```
2. **Build Pass 1 ideas block** from `crucix_ideas` + `regime_signals`. Omit entirely if both are empty.
3. **Build Pass 2 raw signals block** from `raw_signals` (both UW and Crucix). Replace the existing `[:20]` slice with a merged cap of `MERGED_SIGNAL_LIMIT` (default 30, env var). Signals are sorted by `fetched_at` descending, then capped.
4. **Replace the prompt header** from `"Active market signals (Unusual Whales):"` to `"Active market signals:"`.
5. **Replace the contextual instruction** (currently UW-specific with NVDA example) with:
   ```
   When analyzing Polymarket markets, consider whether any of these signals
   suggest a related outcome is more or less likely. OSINT signals (geopolitical
   conflicts, economic indicators, military activity, environmental disasters)
   indicate macro regime shifts. Market flow signals (options sweeps, dark pool
   blocks, congressional trades) indicate where sophisticated money is positioning.
   Both can create edge in prediction markets tied to related outcomes.
   ```

---

## Testing

**File:** `tests/test_crucix_feed.py`

### Test fixtures

A realistic but trimmed `/api/data` JSON blob covering all 6 domains (~50-80 lines). Includes at least one signal per normalizer domain plus the `health` and `delta` objects.

### Test cases

| Test | What it verifies |
|------|-----------------|
| `test_normalize_geopolitical` | GDELT/ACLED/TG → correct tickers (`GEO:*`), directions, signal_types |
| `test_normalize_economic` | FRED/energy/treasury/BLS → correct tickers (`MACRO:*`, `ENERGY:*`), direction logic for VIX spike, unemployment rise |
| `test_normalize_military` | thermal/tSignals/air/space → `MIL:*` tickers, strike confidence thresholds |
| `test_normalize_environmental` | NOAA/nuke/WHO → `ENV:*` tickers, severity filtering |
| `test_normalize_maritime` | Chokepoints → `SEA:*` tickers |
| `test_normalize_meta` | Delta/ideas → `META:*` and `IDEA:*` tickers, regime direction mapping |
| `test_priority_scoring` | Signals sorted correctly, cap applied |
| `test_fetch_integration` | Mocked `requests.get` → full pipeline → valid signal dicts |
| `test_fetch_caching` | Fresh cache → no HTTP call; stale cache → HTTP call |
| `test_fetch_crucix_down` | ConnectionError → returns cached or `[]` |
| `test_health_filtering` | Sources with `err: true` skipped |
| `test_signal_dict_shape` | Every emitted signal has all required keys with correct types |
| `test_old_signals_purged` | Rows older than 24h are deleted on fetch |

### Test for `trading_brain.py` changes

| Test | What it verifies |
|------|-----------------|
| `test_prompt_two_pass_injection` | Ideas block appears before raw signals block |
| `test_prompt_mixed_sources` | Both UW and Crucix signals appear in raw block with correct source labels |
| `test_prompt_no_ideas` | When no crucix_ideas signals, ideas block is omitted |
| `test_merged_signal_cap` | Merged UW + Crucix signals capped at MERGED_SIGNAL_LIMIT |

---

## File Change Summary

| File | Change type | Description |
|------|------------|-------------|
| `crucix_feed.py` | **New** | Crucix DataFeed module (~300-400 lines) |
| `simulator.py` | Edit | Add migration, fetch Crucix in run_loop, merge signals |
| `trading_brain.py` | Edit | Two-pass prompt injection, generic signal header |
| `tests/test_crucix_feed.py` | **New** | Unit + integration tests for the feed |
| `tests/test_uw_feed.py` | Edit | Update `"Unusual Whales"` assertion to match new generic header |
| `tests/test_feed.py` or `tests/test_brain.py` | Edit | Add tests for modified prompt construction |
