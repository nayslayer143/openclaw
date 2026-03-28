# High-Frequency Paper Trader — Design Spec
**Date:** 2026-03-27
**Status:** Approved
**Target:** 100+ paper bets/hour across Kalshi (prod) and Polymarket
**Wallet:** $10,000 fresh start

---

## 1. Architecture

New file: `scripts/mirofish/high_freq_trader.py` — a standalone daemon that owns the full trading loop. No modifications to existing modules.

```
high_freq_trader.py (daemon)
  │
  ├── STARTUP (one-time)
  │     ├── verify_kalshi()      → test prod API connectivity
  │     ├── verify_polymarket()  → test gamma API connectivity
  │     ├── db_clean()           → wipe all stale open paper_trades
  │     ├── clear_context_noise()→ remove wallet-reset spam from context table
  │     ├── set_balance($10k)    → write starting_balance to context
  │     └── init_weights()       → all strategy weights = 1.0
  │
  ├── MAIN LOOP (every 30 seconds)
  │     ├── fetch_kalshi_markets()     → short-expiry series, prod API
  │     ├── fetch_polymarket_markets() → gamma API (every 5th cycle)
  │     ├── score_all_markets()        → pure math, no LLM
  │     ├── place_all_valid_trades()   → no per-cycle trade cap
  │     ├── resolve_expired()          → check API results, close positions
  │     ├── evolve_strategy_weights()  → learn from last 100 resolved
  │     └── print_cycle_summary()      → stdout + dashboard notify
  │
  └── STATE (in-memory, reset each cycle)
        ├── open_positions: set[market_id]   (loaded from DB each cycle)
        ├── strategy_weights: dict[str, float]  (persisted across cycles)
        └── poly_cache: list[dict]           (refreshed every 5 cycles)
```

**Reused from existing codebase:**
- `kalshi_feed._call_kalshi()` — authenticated Kalshi API calls
- `paper_wallet._get_conn()` — SQLite connection to clawmson.db
- `spot_prices` table — crypto spot data written by existing spot_feed cron

---

## 2. Strategies, Fees & Venue Routing

### Fee Model

| Venue | Formula | Effective rate |
|-------|---------|----------------|
| Kalshi | `0.07 × shares × price × (1−price)` | ~1–1.2% avg, peaks at 50¢ contracts |
| Polymarket (US) | `0.001 × trade_value` | 10 bps flat |

### Strategy-to-Venue Mapping

| Strategy | Primary venue | Min net edge | Logic |
|----------|--------------|--------------|-------|
| `arb` | Both (Poly preferred) | Poly: 0.3% · Kalshi: 2.0% | yes+no gap > 1.0 |
| `spot_lag` | Kalshi | 2.5% | spot price vs bracket strike |
| `momentum` | Polymarket | 0.3% | 15-min spot trend continuation |
| `mean_reversion` | Polymarket | 0.3% | fade overpriced YES/NO (>0.85 or <0.15) |

### Position Sizing

- **Polymarket:** 1.5% of balance per trade, no per-cycle cap (fees are cheap)
- **Kalshi:** 3% of balance per trade, max 15 trades per cycle (fee drag real)
- **Hard ceiling (both):** 5% of balance per single position
- **Kelly multiplier:** base size × strategy_weight (range: 0.5×–1.5×)

### Execution Realism

- Kalshi fee deducted: `0.07 × shares × entry_price × (1−entry_price)`
- Polymarket fee deducted: `0.001 × amount_usd`
- Slippage: 0.3% applied to entry price (both venues)
- Partial fill: uniform random 85–100%, position size scaled accordingly

### Filtering

- Min edge (after fees): per strategy table above
- Min entry price: $0.05 (no penny contracts)
- Max bid/ask spread: 25%
- No duplicate `market_id` in open positions
- Max 1 bet per event per cycle

---

## 3. Market Discovery & Resolution

### Kalshi Markets (fetched every cycle via prod API)

```
15-min series:  KXDOGE15M, KXADA15M, KXBNB15M, KXBCH15M, KXBTC15M, KXETH15M
Hourly series:  INXI, NASDAQ100I, KXUSDJPYH, KXBTCUSD, KXETHUSD
6-12hr series:  KXBTC, KXETH, KXSOL (daily brackets)
Broad sweep:    All open markets with close_time < now+24hr
```

Only markets with `close_time < now + 24hr` are eligible.

### Polymarket Markets (gamma API, cached)

```
Filter:     endDate > now AND endDate < now+24hr AND volume > $1,000
Categories: crypto, sports, politics, weather
Fetch freq: Every 5 cycles (~2.5 min); use cache otherwise
```

### Resolution Logic

Runs every cycle on ALL open positions:

- **Kalshi:** `GET /markets/{ticker}` → check `result` field → win/loss close
- **Polymarket:** `GET /markets?id=...` → check `closed` + `winning_side` → close
- Closed trade logs: `strategy`, `edge_at_entry`, `pnl`, `fee_paid`, `outcome`

### DB

Reuses existing `paper_trades` table schema — no column changes.
`venue` inferred from `market_id` prefix: `KX*` → Kalshi, else → Polymarket.
One new index added on startup:
```sql
CREATE INDEX IF NOT EXISTS idx_pt_status_opened ON paper_trades(status, opened_at);
```

---

## 4. Daemon Loop & Monitoring

### Startup Sequence

1. Test Kalshi prod API (one GET call)
2. Test gamma API (one GET call)
3. DELETE all rows in `paper_trades` where `status='open'`
4. DELETE noise rows from `context` where `key LIKE 'wallet_reset_%'`
5. UPSERT `context` row: `chat_id='mirofish', key='starting_balance', value='10000.00'`
6. Print confirmation and begin loop

### Cycle Timing

```
fetch_kalshi        ~1-2s
fetch_polymarket    ~1s (every 5th cycle)
score_markets       <0.1s
place_trades        ~0.5s
resolve_expired     ~2-5s (API calls)
evolve_weights      <0.1s
sleep(30)
─────────────────
Total cycle: ~35-40s → ~90 cycles/hour → 100+ bets/hour achievable at 1.1+ trades/cycle avg
```

### Cycle Summary (stdout each loop)

```
[HFT cycle 42] placed=3 resolved=7 open=19 balance=$10,284 (+2.8%)
  arb: 2 placed, win_rate=71% | spot_lag: 1 placed, win_rate=58%
```

### Strategy Weight Evolution (each cycle)

- Pull last 100 resolved trades per strategy from `paper_trades`
- Win rate > 60%: `weight = min(weight × 1.1, 1.5)`
- Win rate < 45%: `weight = max(weight × 0.9, 0.5)`
- < 10 resolved trades: weight stays at 1.0 (insufficient data)

### Lifecycle

- Run via: `python3 -m scripts.mirofish.high_freq_trader`
- Graceful shutdown on SIGINT/SIGTERM: prints session summary, exits cleanly
- No cron needed — run in tmux session

### Interaction with Existing System

- `fast_scanner.py` cron can stay running — writes to same `paper_trades` table, no conflict
- `simulator.py` 30-min runs unaffected
- Does NOT import from or modify any existing mirofish module (only reads `_call_kalshi`, `_get_conn`)

---

## 5. Out of Scope

- Live trading (paper only — no real order submission)
- LLM-scored trades (Ollama path stays in simulator.py)
- Markets resolving > 24hr from now
- Kalshi demo API (prod only per user confirmation)
