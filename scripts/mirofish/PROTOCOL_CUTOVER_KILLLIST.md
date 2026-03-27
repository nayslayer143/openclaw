# Clawmpson paper_trades Write Census

## Summary
- **11 files INSERT** (production writers)
- **18 files SELECT** (readers — across production, dashboard, inspector, audit)
- **13 files UPDATE** (close/resolve logic)
- **0 files DELETE**

Test files (INSERT only, into isolated in-memory DBs): `test_verifier.py`, `test_dashboard.py`, `test_strategy_tracker.py`, `test_wallet.py`, `test_security_auditor.py` — excluded from classification below.

---

## Schema Reference (canonical — defined in simulator.py)

Core columns (DDL):
```
id, market_id, question, direction, shares, entry_price, exit_price,
amount_usd, pnl, status, confidence, reasoning, strategy, opened_at, closed_at
```

Migrated-in columns (via `simulate.migrate()`):
```
binary_outcome TEXT, resolved_price REAL, resolution_source TEXT,
entry_fee REAL DEFAULT 0, exit_fee REAL DEFAULT 0
```

Future schema variant (QuantumentalClaw — **different DB**):
```
decision_id, pnl_usd, fill_price, fill_shares, fill_amount_usd, executed_at, exit_at,
signal_to_trade_latency_ms
```

---

## Files

---

### paper_wallet.py — MUST_MIRROR

**Path:** `/Users/nayslayer/openclaw/scripts/mirofish/paper_wallet.py`

**Operations:** INSERT, SELECT, UPDATE

**Columns used:**
- INSERT: `market_id, question, direction, shares, entry_price, amount_usd, status ('open'), confidence, reasoning, strategy, opened_at, entry_fee`
- SELECT (balance): `pnl` (SUM), `status` filter; `market_id, direction, shares, entry_price` (open positions); `strategy, entry_price, pnl, market_id, question` (circuit breaker analysis)
- SELECT (stops): full `*` + JOIN to `market_data.end_date`; reads `shares, entry_price, direction, amount_usd, entry_fee, market_id, id`
- SELECT (open positions): full `*` WHERE status='open'
- UPDATE (check_stops): `exit_price, pnl, status, closed_at, exit_fee` WHERE id=?

**Dependencies:**
- `lastrowid` — returned in `execute_trade()` result dict as `"id"`, then used by `simulator.py` to call `tracker.record_trade_open(trade_id=result["id"])`
- `status` field — drives wallet balance computation and circuit breaker logic
- `entry_fee` column — must exist (migrated in); used in PnL net calculation
- `exit_fee` column — must exist; written by `check_stops()`
- `_SUBAGENT_STRATEGIES` exclusion list — balance computation filters out sub-agent trades
- Reads `context` table for starting_balance and trading_status (halted flag)

**Notes:** Central wallet authority. `execute_trade()` is the canonical INSERT path for Clawmpson's brain trades. `check_stops()` is the canonical UPDATE path for stop-loss/take-profit/expiry closes. Any live-trades table introduced in Phase 3 must mirror these two paths or shim them.

---

### arbclaw.py — MUST_MIRROR

**Path:** `/Users/nayslayer/openclaw/scripts/mirofish/arbclaw.py`

**Operations:** INSERT, SELECT, UPDATE

**Columns used:**
- INSERT: `market_id, question, direction, shares, entry_price, amount_usd, status ('open'), confidence, reasoning, strategy ('arbclaw_single_venue'), opened_at, entry_fee`
- SELECT: `SUM(pnl)` WHERE status!='open' (balance); `market_id` WHERE status='open' (duplicate guard); `id, market_id, direction, entry_price, shares` WHERE strategy LIKE 'arbclaw%' AND status='open' (resolve loop, two separate queries)
- UPDATE: `exit_price, pnl, status, closed_at` WHERE id=?

**Dependencies:**
- `lastrowid` — stored in `new_ids` set to skip freshly-placed trades during same-run resolution
- `strategy` field — filtered with `LIKE 'arbclaw%'` for resolution queries
- `entry_fee` must exist (migrated)

**Notes:** Writes directly, bypasses `paper_wallet.execute_trade()`. Runs on 5-minute cron. Has two resolution loops: `_resolve_expired()` (inner function) and an inline loop in `run()`. Both write the same UPDATE.

---

### phantomclaw.py — MUST_MIRROR

**Path:** `/Users/nayslayer/openclaw/scripts/mirofish/phantomclaw.py`

**Operations:** INSERT, SELECT, UPDATE

**Columns used:**
- INSERT: `market_id, question, direction, shares, entry_price, amount_usd, status ('open'), confidence, reasoning, strategy ('phantomclaw_fv'), opened_at, entry_fee`
- SELECT: `id, market_id, direction, entry_price, shares` WHERE strategy LIKE 'phantomclaw%' AND status='open' (early-exit + resolve); `SUM(pnl)` WHERE strategy LIKE 'phantomclaw%' (balance); `market_id` WHERE status='open' (dedup); strategy LIKE 'phantomclaw%' AND status='open' (open positions for display)
- UPDATE (early exit): `status, exit_price, pnl, closed_at` WHERE id=?
- UPDATE (resolve): `exit_price, pnl, status, closed_at` WHERE id=?

**Dependencies:**
- `lastrowid` — stored in `new_ids` set to skip same-run trades
- `strategy` field — filtered with `LIKE 'phantomclaw%'`
- Uses its own $1000 virtual wallet (isolated balance from Clawmpson via strategy filter)
- Reads `bot_config.should_early_exit()` and cross-references `kalshi_markets` for current price

**Notes:** Sub-agent of Clawmpson. Has an early-exit path (additional UPDATE before resolution) that sets status to closed_win/closed_loss based on live price before Kalshi API confirms result.

---

### calendarclaw.py — MUST_MIRROR

**Path:** `/Users/nayslayer/openclaw/scripts/mirofish/calendarclaw.py`

**Operations:** INSERT, SELECT, UPDATE

**Columns used:**
- INSERT: `market_id, question, direction, shares, entry_price, amount_usd, status ('open'), confidence, reasoning, strategy ('calendarclaw'), opened_at, entry_fee`
- SELECT: `SUM(pnl)` WHERE strategy='calendarclaw' (balance); `market_id` WHERE status='open' (dedup, global)
- UPDATE: `exit_price, pnl, status, closed_at` WHERE id=?

**Dependencies:**
- `strategy='calendarclaw'` filter for isolation
- Global `status='open'` dedup check (reads all open positions, not just own)
- Own $1000 wallet via strategy-filtered PnL sum

---

### sentimentclaw.py — MUST_MIRROR

**Path:** `/Users/nayslayer/openclaw/scripts/mirofish/sentimentclaw.py`

**Operations:** INSERT, SELECT, UPDATE

**Columns used:**
- INSERT: `market_id, question, direction, shares, entry_price, amount_usd, status ('open'), confidence, reasoning, strategy ('sentimentclaw'), opened_at, entry_fee`
- SELECT: `SUM(pnl)` WHERE strategy='sentimentclaw' (balance); `id, market_id, direction, entry_price, shares` WHERE strategy='sentimentclaw' AND status='open' (resolve); `market_id` WHERE status='open' (global dedup)
- UPDATE: `exit_price, pnl, status, closed_at` WHERE id=?

**Dependencies:**
- `strategy='sentimentclaw'` filter for isolation
- Global `market_id` dedup check

---

### newsclaw.py — MUST_MIRROR

**Path:** `/Users/nayslayer/openclaw/scripts/mirofish/newsclaw.py`

**Operations:** INSERT, SELECT, UPDATE

**Columns used:**
- INSERT: `market_id, question, direction, shares, entry_price, amount_usd, status ('open'), confidence, reasoning, strategy ('newsclaw'), opened_at, entry_fee`
- SELECT: `SUM(pnl)` WHERE strategy='newsclaw' (balance); `id, market_id, direction, entry_price, shares` WHERE strategy='newsclaw' AND status='open' (resolve); `market_id` WHERE status='open' (global dedup)
- UPDATE: `exit_price, pnl, status, closed_at` WHERE id=?

**Dependencies:**
- `strategy='newsclaw'` filter for isolation
- Global `market_id` dedup check

---

### dataharvester.py — MUST_MIRROR

**Path:** `/Users/nayslayer/openclaw/scripts/mirofish/dataharvester.py`

**Operations:** INSERT, SELECT

**Columns used:**
- INSERT: `market_id, question, direction, shares, entry_price, amount_usd, status ('open'), confidence, reasoning, strategy ('dataharvester'), opened_at, entry_fee`
- SELECT: `SUM(pnl)` WHERE strategy='dataharvester' AND status IN closed (balance); `market_id` WHERE status='open' (dedup)

**Dependencies:**
- Own $1000 wallet via strategy-filtered PnL sum
- Does NOT have its own resolve/UPDATE path — relies on `simulator.py` / `paper_wallet.check_stops()` to close its trades
- No `lastrowid` consumed

**Notes:** No resolution loop. Trades are closed only by the main simulator stop-check. Safe to migrate if simulator cutover includes `dataharvester` strategy in stop checks.

---

### hedged_strategies.py — MUST_MIRROR

**Path:** `/Users/nayslayer/openclaw/scripts/mirofish/hedged_strategies.py`

**Operations:** INSERT, SELECT, UPDATE

**Columns used:**
- INSERT: `market_id, question, direction, shares, entry_price, amount_usd, status ('open'), confidence, reasoning, strategy, opened_at, entry_fee` (strategy values: `hedged_bracket_main`, `hedged_bracket_hedge`, `fade_public`, `vol_straddle_yes`, `vol_straddle_no`)
- SELECT: `SUM(pnl)` WHERE status!='open' (balance); `market_id` WHERE status='open' (dedup)
- UPDATE: `exit_price, pnl, status, closed_at` WHERE id=?

**Dependencies:**
- `lastrowid` returned from `_place()` — accumulated in `new_ids` set to guard against self-resolution in same run
- Resolves against `strategy IN (list of hedged strategies)`

---

### math_strategies.py — MUST_MIRROR

**Path:** `/Users/nayslayer/openclaw/scripts/mirofish/math_strategies.py`

**Operations:** INSERT, SELECT, UPDATE

**Columns used:**
- INSERT: `market_id, question, direction, shares, entry_price, amount_usd, status ('open'), confidence, reasoning, strategy, opened_at, entry_fee` (strategy values: `expiry_convergence`, `cross_bracket_arb`, `correlation_arb`, `mean_reversion`)
- SELECT: `SUM(pnl)` WHERE status!='open' (balance); `market_id` WHERE status='open' (dedup)
- UPDATE: `exit_price, pnl, status, closed_at` WHERE id=?

**Dependencies:**
- `lastrowid` accumulated in `new_ids` (passed by reference into `_place()`)
- Resolves against `strategy IN (list of math strategies)`

---

### fast_scanner.py — MUST_MIRROR

**Path:** `/Users/nayslayer/openclaw/scripts/mirofish/fast_scanner.py`

**Operations:** INSERT, SELECT, UPDATE

**Columns used:**
- INSERT (`_place_trade()`): `market_id, question, direction, shares, entry_price, amount_usd, status ('open'), confidence, reasoning, strategy, opened_at` — **NOTE: does NOT include `entry_fee`**
- SELECT: `SUM(pnl)` WHERE status!='open' (balance); `market_id, question` WHERE status='open' (dedup); `id, market_id, direction, entry_price, shares` WHERE status='open' AND market_id LIKE 'KX%' (Kalshi resolve)
- UPDATE: `exit_price, pnl, status, closed_at` WHERE id=?

**Dependencies:**
- `lastrowid` stored in `new_trade_ids` set
- `_place_trade()` bypasses `paper_wallet` entirely — no execution sim, no cap check, no entry_fee column written
- Strategy values: `fast_arb`, `price_momentum_15m`, `price_momentum_5m` (and others depending on market scanning logic)

**Notes:** Fast path — deliberately skips `paper_wallet.execute_trade()` for speed. No `entry_fee` written. Any cutover shim must handle missing `entry_fee` gracefully.

---

### crypto_spot_trader.py — MUST_MIRROR

**Path:** `/Users/nayslayer/openclaw/scripts/mirofish/crypto_spot_trader.py`

**Operations:** INSERT, SELECT, UPDATE

**Columns used:**
- INSERT: `market_id ('SPOT:<asset>'), question, direction (YES/NO mapped from BUY/SELL), shares, entry_price, amount_usd, status ('open'), confidence, reasoning, strategy ('crypto_spot_mean_rev' or 'crypto_spot_momentum'), opened_at, entry_fee`
- SELECT: full `*` WHERE market_id='SPOT:<asset>' AND status='open' AND strategy LIKE 'crypto_spot_%' (position check); `SUM(pnl)` WHERE status!='open' (balance)
- UPDATE: `exit_price, pnl, status, closed_at` WHERE id=? — **NOTE: no `exit_fee` written**

**Dependencies:**
- Uses synthetic `market_id` pattern `SPOT:<ASSET>` — not a real Kalshi/Polymarket ID
- Direction mapping: BUY→YES, SELL→NO (non-standard; must be noted for any aggregation)
- `entry_price` here is actual USD spot price (e.g. $83,000), not a probability — differs from all other strategies

**Notes:** Schema-compatible but semantically different. Spot price as `entry_price` makes standard PnL calcs incompatible with prediction market trades. Phase 3 integration must handle this case separately or filter `strategy LIKE 'crypto_spot_%'`.

---

### simulator.py — MUST_SHIM

**Path:** `/Users/nayslayer/openclaw/scripts/mirofish/simulator.py`

**Operations:** SELECT, UPDATE (DDL CREATE TABLE, plus migration ALTER TABLE ADD COLUMN)

**Columns used:**
- DDL: defines full canonical schema (see Schema Reference above)
- SELECT (Kalshi resolve): `id, market_id, direction, entry_price, shares, amount_usd` WHERE status='open' AND market_id LIKE 'KX%'
- SELECT (Polymarket resolve): `id, market_id, direction, entry_price, shares, amount_usd, entry_fee` WHERE status='open' AND market_id NOT LIKE 'KX%'
- UPDATE (Kalshi): `exit_price, pnl, status, closed_at` WHERE id=?
- UPDATE (Polymarket): `exit_price, pnl, status, closed_at, binary_outcome, resolved_price, resolution_source` WHERE id=? — **writes `binary_outcome`, `resolved_price`, `resolution_source`**
- Calls `tracker.sync_from_paper_trades()` after each run

**Dependencies:**
- `entry_fee` column must exist before Polymarket resolution path runs (reads it for PnL calc)
- `binary_outcome`, `resolved_price`, `resolution_source` — written only by Polymarket resolver; must be present post-migration
- Migration (`migrate()`) adds the 5 extra columns idempotently; must run before any Phase 3 table cutover

**Notes:** This is the schema owner. `migrate()` must be run (or its equivalent) before any cutover. The `_resolve_polymarket_trades()` function writes the most columns of any UPDATE path; it is the only place `binary_outcome`, `resolved_price`, and `resolution_source` are written.

---

### dashboard.py (mirofish) — SAFE_TO_REMOVE (READ-ONLY)

**Path:** `/Users/nayslayer/openclaw/scripts/mirofish/dashboard.py`

**Operations:** SELECT

**Columns used:**
- `status` (graduation check, snapshot counts)
- `pnl` (SUM realized)
- `market_id, question, direction, amount_usd, pnl, status, strategy, opened_at, closed_at` (report generation, recent 10 trades)
- `COUNT(*)` WHERE status='open' and WHERE status!='open'

**Dependencies:**
- Reads from `paper_trades` only for reporting and daily snapshot values written to `daily_pnl`
- Does NOT write back to `paper_trades`
- Indirectly depends on `status` values being correct (graduation criteria use win_rate from status counts)

---

### security_auditor.py — SAFE_TO_REMOVE (READ-ONLY)

**Path:** `/Users/nayslayer/openclaw/scripts/mirofish/security_auditor.py`

**Operations:** SELECT

**Columns used:**
- `SUM(amount_usd)` WHERE status='open' OR (closed today) (daily exposure check)
- `COUNT(*)` WHERE status='open' (open position count)
- `COUNT(*)` WHERE market_id=? AND direction=? AND opened_at>? AND status='open' (duplicate check)

**Dependencies:**
- Read-only audit gate — called BEFORE each trade INSERT in `simulator.run_loop()`
- Depends on `amount_usd`, `status`, `market_id`, `direction`, `opened_at` columns

---

### calibrator.py — SAFE_TO_REMOVE (READ-ONLY)

**Path:** `/Users/nayslayer/openclaw/scripts/mirofish/calibrator.py`

**Operations:** SELECT

**Columns used:**
- `entry_price, direction, pnl, amount_usd, status, confidence, closed_at` WHERE strategy=? AND status IN closed AND closed_at > cutoff

**Dependencies:**
- Pure analytics — reads closed trades per strategy, computes win-rate, avg win/loss, entry-price bucket distribution
- No writes to `paper_trades`

---

### strategy_tracker.py — MUST_SHIM

**Path:** `/Users/nayslayer/openclaw/scripts/mirofish/strategy_tracker.py`

**Operations:** SELECT

**Columns used:**
- `sync_from_paper_trades()`: full `id, strategy, market_id, direction, entry_price, exit_price, amount_usd, confidence, pnl, status, opened_at, closed_at` via LEFT JOIN to `strategy_performance` to find unsynced trades

**Dependencies:**
- `sync_from_paper_trades()` is called by `simulator.run_loop()` on every cycle (twice: once before trades, once after snapshot)
- Reads `paper_trades.id` as foreign key for `strategy_performance.trade_id`
- If `paper_trades` is replaced or renamed, `strategy_performance` JOIN will break and sync will silently stop recording
- Must be shimmed to read from the new live-trades table if cutover moves data out of `paper_trades`

---

### edge_persistence.py — SAFE_TO_REMOVE (READ-ONLY via strategy_performance)

**Path:** `/Users/nayslayer/openclaw/scripts/mirofish/edge_persistence.py`

**Operations:** SELECT (indirect — reads `strategy_performance`, not `paper_trades` directly)

**Columns used:**
- Does NOT query `paper_trades` directly in `compute_from_trades()`
- Reads `strategy_performance.market_id, strategy, expected_edge, realized_pnl, amount_usd, opened_at, closed_at`

**Dependencies:**
- Comment in docstring mentions "from closed paper_trades" but actual SQL reads `strategy_performance`
- No direct `paper_trades` dependency at runtime

**Notes:** The grep hit was a docstring comment, not a live query. Classified conservatively as SAFE_TO_REMOVE for Phase 3 purposes.

---

### dashboard/server.py — MUST_SHIM

**Path:** `/Users/nayslayer/openclaw/dashboard/server.py`

**Operations:** SELECT (multiple contexts across 4 different DB connections)

**Columns used (Clawmpson context, `clawmson.db`):**
- `SUM(pnl)`, `status`, full `*` for open trades; `strategy, entry_price, pnl, confidence, opened_at, shares, amount_usd, market_id, question, direction` (positions and closed display)
- `signal_to_trade_latency_ms` — **NOTE: this column is NOT in the core schema DDL; it is a forward-looking column expected from the Phase 3 integration schema**
- `COUNT(*) WHERE status='open'`, `SUM(pnl) WHERE status IN closed`
- Per-agent stats: `COUNT(*), SUM(pnl)` WHERE strategy=? AND status IN closed; `id, market_id, question, direction, entry_price, shares, amount_usd, opened_at` WHERE strategy=? AND status='open'
- PhantomClaw positions: `id, market_id, question, direction, entry_price, amount_usd, confidence, opened_at, strategy` WHERE strategy LIKE 'phantomclaw%'
- RivalClaw (`rivalclaw.db`): `market_id, question, direction, strategy, entry_price, amount_usd, confidence, opened_at, pnl` WHERE status='open' — Mirofish-compatible schema
- QuantumentalClaw (`quantumentalclaw.db`): **different schema** — reads `pnl_usd`, `decision_id`, `fill_price`, `fill_shares`, `fill_amount_usd`, `executed_at`, `exit_at` via JOIN to `trade_decisions`

**Dependencies:**
- `signal_to_trade_latency_ms` — referenced in `_rivalclaw_state()` and an unnamed state function around line 1395; will throw `KeyError` on `sqlite3.Row` access if column is absent. This column is NOT in the Mirofish `paper_trades` DDL — it is a future/Phase 3 column.
- QuantumentalClaw block uses a completely different schema — already isolated to `_quantumentalclaw_state()` function with try/except wrapping
- All reads are wrapped in try/except at the function level; failures degrade gracefully but silently

**Notes:** The `signal_to_trade_latency_ms` reference in `_rivalclaw_state()` (line 1395) and around line 1408 suggests the dashboard was written anticipating a future schema that adds this column to the Mirofish `paper_trades` table. This is a BLOCK_CUTOVER risk if Phase 3 renames the table without adding this column first.

---

### scripts/inspector/hallucination_detector.py — SAFE_TO_REMOVE (READ-ONLY)

**Path:** `/Users/nayslayer/openclaw/scripts/inspector/hallucination_detector.py`

**Operations:** SELECT

**Columns used:**
- Full `*` WHERE (strategy LIKE '%llm%' OR reasoning IS NOT NULL AND reasoning != '')
- Reads `id, market_id, entry_price, opened_at` from result rows

**Dependencies:**
- Audit tool — reads `paper_trades`, writes to its own `hallucination_checks` table in a separate DB
- No writes back to `paper_trades`

---

### scripts/inspector/stats_auditor.py — SAFE_TO_REMOVE (READ-ONLY)

**Path:** `/Users/nayslayer/openclaw/scripts/inspector/stats_auditor.py`

**Operations:** SELECT

**Columns used:**
- Full `*` (all columns) via `SELECT * FROM paper_trades`

**Dependencies:**
- Reads entire table for win-rate, position-sizing, and PnL checks
- No writes to `paper_trades`

---

### scripts/inspector/resolution_auditor.py — SAFE_TO_REMOVE (READ-ONLY)

**Path:** `/Users/nayslayer/openclaw/scripts/inspector/resolution_auditor.py`

**Operations:** SELECT

**Columns used:**
- Full `*` WHERE status IN ('closed_win','closed_loss','expired')

**Dependencies:**
- Reads closed trades, writes to `resolution_audits` table in inspector DB
- No writes to `paper_trades`

---

### scripts/inspector/verifier.py — SAFE_TO_REMOVE (READ-ONLY)

**Path:** `/Users/nayslayer/openclaw/scripts/inspector/verifier.py`

**Operations:** SELECT

**Columns used:**
- Full `*` (all trades)

**Dependencies:**
- Reads all trades, writes to `verified_trades` table in inspector DB
- No writes to `paper_trades`

---

## Phase 3 Cutover Risk Register

| Risk | Affected Files | Severity |
|------|---------------|----------|
| `signal_to_trade_latency_ms` column missing | `dashboard/server.py` lines 1395, 1408, 1417 | HIGH — will throw on any Row access if column absent |
| `entry_fee` / `exit_fee` columns missing (pre-migration) | `paper_wallet.py`, `simulator.py`, all sub-agents | HIGH — PnL calculation wrong or exception on missing col |
| `binary_outcome`, `resolved_price`, `resolution_source` columns missing | `simulator.py` Polymarket resolver | MEDIUM — UPDATE will fail if cols absent |
| `lastrowid` consumption chain | `paper_wallet.py` → `simulator.py` → `strategy_tracker.py` | HIGH — if INSERT changes to a different table, `record_trade_open(trade_id=result["id"])` will reference a wrong or nonexistent ID |
| `strategy_performance` JOIN on `paper_trades.id` | `strategy_tracker.sync_from_paper_trades()` | HIGH — silent data loss if IDs change |
| `fast_scanner._place_trade()` bypasses wallet | `fast_scanner.py` | MEDIUM — no execution sim, no circuit breaker, no `entry_fee` written |
| `crypto_spot_trader` synthetic market_id + USD entry_price | `crypto_spot_trader.py` | MEDIUM — non-standard semantics; must be filtered in any aggregation |
| QuantumentalClaw schema divergence | `dashboard/server.py` `_quantumentalclaw_state()` | LOW — already isolated to separate function + DB |

---

## Migration Order for Phase 3

1. Run `simulator.migrate()` on target DB to ensure all 5 optional columns exist
2. Add `signal_to_trade_latency_ms` column to `paper_trades` (or add to migration script) before dashboard cutover
3. Shim `strategy_tracker.sync_from_paper_trades()` to read from new live-trades table if `paper_trades` is replaced
4. Update `paper_wallet.execute_trade()` to write to new table (or keep writing to `paper_trades` as write-through mirror)
5. Update all 8 sub-agent INSERT paths (arbclaw, phantomclaw, calendarclaw, sentimentclaw, newsclaw, dataharvester, hedged_strategies, math_strategies, fast_scanner, crypto_spot_trader) to write to new table
6. Inspector tools (`hallucination_detector`, `stats_auditor`, `resolution_auditor`, `verifier`) can stay reading `paper_trades` until data is fully migrated, then point at new table

---

*Census completed 2026-03-26. Read-only task — no files were modified.*
