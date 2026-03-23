# Mirofish Paper Trading Simulator — Design Spec
**Date:** 2026-03-22
**Status:** Approved (rev 2)
**Author:** Jordan / Claude Code

---

## Context

Clawmson (the Telegram bot) needs to prove it can make money with prediction market arbitrage **before** getting access to a real wallet. Mirofish is a paper trading simulator that runs against real-time Polymarket data using a fake wallet, tracking whether Clawmson's logic would have been profitable.

Replaces `cron-prediction-market.sh` (the existing shell-based Polymarket scanner). The cron entry changes from calling the shell script to calling `simulator.py --run`.

---

## Goals

1. Paper-trade Polymarket markets using local Ollama inference (zero API cost)
2. Track P&L, win rate, Sharpe ratio, and drawdown against a fake $1,000 wallet
3. Expose portfolio state via Telegram commands and daily digests
4. Gate live trading access behind 4 quantitative graduation criteria
5. All data in `~/.openclaw/clawmson.db` (existing SQLite, new tables)

---

## Non-Goals

- No real wallet connections
- No real money
- No external AI APIs (Ollama only)
- No multi-user support
- No backtest mode in this version (future phase — see Open Questions)

---

## Architecture

### Approach: Pipeline of independent modules (Option B)

Five focused modules communicate through shared SQLite. Each is independently testable and importable. `simulator.py` is a thin orchestrator.

```
cron (every 30 min)
  └─ simulator.py --run
        │
        ├─ polymarket_feed.fetch_markets()   → writes market_data table
        ├─ paper_wallet.get_state()          → reads paper_trades + daily_pnl
        ├─ trading_brain.analyze()           → arb check + Ollama call → list[TradeDecision]
        ├─ paper_wallet.execute_trade()      → writes paper_trades (skips if kelly ≤ 0)
        ├─ paper_wallet.check_stops(polymarket_feed.get_latest_prices()) → closes -20% / +50% positions
        └─ dashboard.maybe_snapshot()        → writes daily_pnl, generates report
```

### File layout

```
~/openclaw/scripts/mirofish/
├── __init__.py
├── paper_wallet.py
├── polymarket_feed.py
├── trading_brain.py
├── simulator.py
├── dashboard.py
└── tests/
    ├── test_wallet.py
    └── test_positions.py

~/openclaw/mirofish/reports/          # markdown report output
~/openclaw/agents/configs/mirofish-trader.md  # agent config doc
```

---

## Data Model

New tables added to `~/.openclaw/clawmson.db` via migration script (`simulator.py --migrate`).

```sql
CREATE TABLE market_data (
    id           INTEGER PRIMARY KEY,
    market_id    TEXT NOT NULL,
    question     TEXT NOT NULL,
    category     TEXT,
    yes_price    REAL,
    no_price     REAL,
    volume       REAL,
    end_date     TEXT,
    fetched_at   TEXT NOT NULL
);
-- Compound index for efficient price history and momentum queries
CREATE INDEX idx_market_data_market_time ON market_data(market_id, fetched_at);

CREATE TABLE paper_trades (
    id           INTEGER PRIMARY KEY,
    market_id    TEXT NOT NULL,
    question     TEXT NOT NULL,
    direction    TEXT NOT NULL,   -- YES | NO
    shares       REAL NOT NULL,
    entry_price  REAL NOT NULL,
    exit_price   REAL,            -- NULL = open
    amount_usd   REAL NOT NULL,
    pnl          REAL,            -- NULL = open
    status       TEXT NOT NULL,   -- open | closed_win | closed_loss | expired
    confidence   REAL NOT NULL DEFAULT 1.0,
    reasoning    TEXT NOT NULL DEFAULT '',
    strategy     TEXT NOT NULL DEFAULT 'manual',
                                  -- momentum | contrarian | arbitrage | news_catalyst | manual
    opened_at    TEXT NOT NULL,
    closed_at    TEXT
);

CREATE TABLE daily_pnl (
    id              INTEGER PRIMARY KEY,
    date            TEXT NOT NULL UNIQUE,
    balance         REAL NOT NULL,   -- closing balance for the day
    open_positions  INTEGER,
    realized_pnl    REAL,
    unrealized_pnl  REAL,
    total_trades    INTEGER,
    win_rate        REAL,
    roi_pct         REAL             -- see definition below
);
```

**`roi_pct` definition:** daily percentage return relative to the **previous day's closing balance**.
`roi_pct = (today_balance - prev_balance) / prev_balance`. For day 1, uses `starting_balance` as the denominator. This produces a time-series of chainable returns that is correct for Sharpe calculation.

**Wallet balance derivation** (never stored, always recomputed):
```python
balance = starting_balance
         + sum(pnl for closed trades)          # realized
         + sum(unrealized_pnl for open trades) # mark-to-market using latest market_data prices
```

Unrealized P&L for an open YES position: `shares * (current_yes_price - entry_price)`.
Unrealized P&L for an open NO position: `shares * (current_no_price - entry_price)`.

Wallet starting balance stored in the existing `context` table:
`(chat_id="mirofish", key="starting_balance", value="1000.00")`

---

## Module Contracts

### `paper_wallet.py`

```python
get_state() -> WalletState
# WalletState: {balance, starting_balance, open_positions: list[Trade],
#               roi_pct, win_rate, max_drawdown, sharpe_ratio, total_trades}
# balance is always derived (see formula above), never cached

execute_trade(decision: TradeDecision) -> Trade | None
# Returns None if:
#   - kelly ≤ 0 (negative edge — skip the trade)
#   - position cap would be breached (amount_usd > 10% of current balance)
# On success: writes paper_trades row with strategy/confidence/reasoning from decision
# Manual /bet trades: strategy='manual', confidence=1.0, reasoning='manual via /bet'
# Position cap is also enforced for manual /bet trades

check_stops(current_prices: dict[str, dict]) -> list[Trade]
# Closes open positions at -20% (stop-loss) or +50% (take-profit)
# Expired markets: closes using last cached price (paper trading approximation —
#   does not attempt to infer actual binary settlement outcome)

get_open_positions() -> list[Trade]

get_pnl_summary(days: int = 7) -> PnLSummary
```

### `polymarket_feed.py`

```python
fetch_markets(categories=["crypto","politics","sports","weather","tech"]) -> list[Market]
# Hits gamma-api.polymarket.com, filters: active=True, volume>$10K
# Writes to market_data table, returns list of Market dicts

get_recent_snapshots(market_id: str, limit: int = 3) -> list[dict]
# Returns the most recent `limit` price snapshots for a market
# Used by trading_brain for momentum detection (3 snapshots = last 1.5h)

get_latest_prices() -> dict[str, dict]
# Returns {market_id: {yes_price, no_price}} from most recent snapshot per market
```

### `trading_brain.py`

```python
analyze(markets: list[Market], wallet: WalletState) -> list[TradeDecision]
# Step 1: Run arbitrage check on all markets (pure math, no Ollama)
#         Flag any market where abs(yes_price + no_price - 1.0) > 0.03
# Step 2: For non-arb markets, call qwen3:30b for momentum/contrarian/news_catalyst
# Returns list of TradeDecision dicts sorted by confidence desc.
# TradeDecision: {market_id, question, direction, confidence, reasoning, strategy,
#                 amount_usd (Kelly-sized, already capped at 10%)}
# kelly ≤ 0 decisions are EXCLUDED from the returned list (caller never sees them)
```

**Kelly formula (correct for prediction markets):**
```python
b = (1 / entry_price) - 1           # payout odds (e.g. $0.30 entry → b=2.33)
kelly = (confidence * b - (1 - confidence)) / b
if kelly <= 0:
    return None  # negative edge — do not trade
position_size = min(kelly * balance, 0.10 * balance)
```

The simplified `p - (1-p)` formula assumes even money and is incorrect for Polymarket.

### `dashboard.py`

```python
generate_report(period: str = "daily") -> Path   # returns path to written .md file
check_graduation() -> GraduationStatus
# GraduationStatus: {ready: bool, roi_7d: float, win_rate: float,
#                    sharpe_all_time: float, max_drawdown: float, criteria: dict,
#                    has_minimum_history: bool}

format_portfolio_message() -> str    # Telegram-ready
format_pnl_message() -> str
format_trades_message(limit: int = 10) -> str
```

### `simulator.py`

```python
# CLI: python3 simulator.py --run | --migrate | --report
# --run:     full simulation loop (fetch → brain → trade → stops → snapshot)
# --migrate: create new DB tables (idempotent)
# --report:  generate today's report without running the trade loop
```

---

## Trading Logic

### Strategies

| Strategy | Signal | Mechanism | Where |
|---|---|---|---|
| **arbitrage** | `abs(yes + no - 1.0) > 0.03` | Pure math — no LLM needed | `trading_brain.py` fast-path |
| **momentum** | yes_price up >5% over last 3 snapshots | LLM confirms trend validity | `trading_brain.py` via Ollama |
| **contrarian** | yes_price moved >20% in one window | LLM assesses overreaction | `trading_brain.py` via Ollama |
| **news_catalyst** | LLM cross-references question against current knowledge | LLM primary | `trading_brain.py` via Ollama |

Arbitrage check runs first within `trading_brain.analyze()` (before the Ollama call) as a fast-path branch. This keeps trade decision generation in one place while avoiding unnecessary LLM calls for pure-math opportunities.

**Arbitrage trade sizing:** Arbitrage trades are single-leg — buy whichever side is underpriced (YES if `yes_price < 0.50` and the pair sums > 1.03, NO otherwise). Kelly does not apply cleanly to arb (no meaningful confidence estimate for a pure-price-gap trade), so arb positions bypass Kelly and use a fixed 5% of portfolio. `confidence` is set to the normalized gap: `min(gap / 0.10, 1.0)` where `gap = abs(yes + no - 1.0)`. `reasoning` records the raw prices and gap size.

### Stop management (checked every run)

- **Stop-loss:** close if unrealized P&L < -20% of `amount_usd`
- **Take-profit:** close if unrealized P&L > +50% of `amount_usd`
- **Expiry:** close if market `end_date` has passed, using last cached price. **Known limitation:** this is a paper trading approximation — actual Polymarket resolution is binary (1.0 or 0.0). P&L on expired positions will be approximate, not reflective of true settlement.

### Risk limits

- Max 10% of portfolio per single position (enforced in `execute_trade`, including `/bet`)
- Minimum $10K market volume (enforced in `fetch_markets`)
- Kelly ≤ 0 → skip trade entirely (enforced in `trading_brain.analyze()` before returning)
- Skip markets with fewer than 3 cached snapshots (insufficient momentum data)

---

## Graduation Criteria

Checked by `dashboard.check_graduation()` at every daily snapshot. **Minimum 14 days of `daily_pnl` history required** before `ready` can be `True` (guards against lucky single-day Sharpe spikes and std=0 division by zero). All four must pass simultaneously:

| Criterion | Threshold | Window | Data source |
|---|---|---|---|
| Min history | ≥ 14 days | — | `COUNT(daily_pnl rows)` — gates all other criteria |
| ROI | > 0% | Last 7 `daily_pnl` rows | `sum(roi_pct for last 7 rows) > 0` (approximation of net return; close enough for small daily returns near zero) |
| Win rate | > 55% | All closed trades | `closed_win / (closed_win + closed_loss)` from `paper_trades` |
| Sharpe ratio | > 1.0 | All available history | See formula below |
| Max drawdown | < 25% | All available history | See formula below |

**Sharpe calculation** (unannualized, consistent across all-time windows):
```python
daily_returns = [row.roi_pct for row in all_daily_pnl_rows]
if len(daily_returns) < 14 or std(daily_returns) == 0:
    return None  # insufficient history or zero variance — graduation blocked
sharpe = mean(daily_returns) / std(daily_returns)
# threshold > 1.0 means average daily return exceeds 1 standard deviation
```

**Max drawdown calculation:**
```python
balances = [row.balance for row in all_daily_pnl_rows]  # chronological
peak = balances[0]
max_dd = 0.0
for b in balances:
    peak = max(peak, b)
    dd = (peak - b) / peak
    max_dd = max(max_dd, dd)
# threshold: max_dd < 0.25
```

When all four pass (and history ≥ 14 days):
- Every generated report gets a `READY FOR LIVE TRADING` header
- Telegram notification fires once (flag stored in context table: `key="graduation_notified"` to prevent repeat spam)

---

## Telegram Integration

New `/slash` command handlers added to `telegram-dispatcher.py` following the existing pattern (hard routes caught before the LLM classifier):

| Command | Handler | Response |
|---|---|---|
| `/portfolio` | `dashboard.format_portfolio_message()` | Balance, open positions, unrealized P&L |
| `/pnl` | `dashboard.format_pnl_message()` | 7-day P&L, win rate, ROI, graduation status |
| `/trades` | `dashboard.format_trades_message()` | Last 10 trades (open + recently closed) |
| `/bet [market_id] [YES\|NO] [amount]` | `paper_wallet.execute_trade()` | Confirmation or rejection; enforces 10% cap |

**Daily digest** (fired from `dashboard.maybe_snapshot()` on first run of each day):
```
Mirofish Daily — 2026-03-22
P&L today: +$47.20 (+4.7%)
Open positions: 3
Win rate: 67% (12W / 6L)
Portfolio: $1,234.50
```

Outbound Telegram chat_id sourced from env var `JORDAN_TELEGRAM_CHAT_ID` (set in `~/openclaw/.env`). `simulator.py --run` loads `.env` and calls `notify-telegram.sh` for outbound messages, consistent with other cron scripts.

**Natural language** ("how are our bets doing?") — falls through to CONVERSATION intent. Clawmson's system prompt gets a one-line portfolio summary injected as a dynamic prefix in `clawmson_chat.py`.

---

## Error Handling

| Failure | Behavior |
|---|---|
| Ollama unreachable | Log error, skip trade generation, still run `check_stops()` and daily snapshot |
| Polymarket API down | Use cached `market_data` rows if < 6h old; skip entirely if stale |
| Malformed LLM response | JSON extractor with regex fallback; no trade executed if parse fails |
| `/bet` bad args | Send usage string to Telegram, no DB write |
| Kelly ≤ 0 | Skip trade silently (logged but not sent to Telegram) |
| Sharpe std=0 | Return `None` for Sharpe; graduation blocked until variance exists |
| SQLite locked | Retry once after 2s (WAL mode handles most concurrency) |

---

## Tests

### `tests/test_wallet.py`
- Starting balance $1,000 enforced from context table
- 10% position cap: trade for $101 on $1,000 balance → rejected (returns None)
- Stop-loss: position at -20% → closed on next `check_stops()` call
- Take-profit: position at +50% → closed on next `check_stops()` call
- ROI calculation: `roi_pct = (today - prev) / prev` matches manual calculation
- Sharpe ratio: known daily return sequence → expected `mean/std` value
- Sharpe std=0 guard: all identical returns → returns None, no ZeroDivisionError
- Max drawdown: known balance sequence → expected peak-to-trough value
- Balance derivation: `starting + realized_pnl + unrealized_pnl` matches expected

### `tests/test_positions.py`
- Arbitrage detection: yes=0.60 + no=0.45 → flagged (gap=0.05 > 0.03)
- Arbitrage non-detection: yes=0.60 + no=0.41 → not flagged (gap=0.01 ≤ 0.03)
- Kelly positive: confidence=0.70, entry_price=0.30, balance=$1000 → positive amount, within 10% cap
- Kelly negative: confidence=0.20, entry_price=0.80 → kelly ≤ 0 → excluded from decisions
- Kelly cap: high-confidence bet → amount_usd never exceeds 10% of balance
- Graduation: all four criteria pass + ≥14 days → `ready=True`
- Graduation: win_rate=0.50 (below 55%) → `ready=False`
- Graduation: < 14 days history → `ready=False` regardless of criteria values
- Manual `/bet` trade: strategy='manual', confidence=1.0, position cap still enforced

---

## Configuration

All defaults via environment variables (loaded from `~/openclaw/.env`):

```bash
MIROFISH_STARTING_BALANCE=1000.00
MIROFISH_INTERVAL_MINUTES=30
MIROFISH_MAX_POSITION_PCT=0.10
MIROFISH_STOP_LOSS_PCT=0.20
MIROFISH_TAKE_PROFIT_PCT=0.50
MIROFISH_MIN_MARKET_VOLUME=10000
MIROFISH_MIN_HISTORY_DAYS=14        # minimum days before graduation can fire
OLLAMA_BASE_URL=http://localhost:11434
MIROFISH_MODEL=qwen3:30b
JORDAN_TELEGRAM_CHAT_ID=            # set in .env for outbound daily digest
```

---

## Cron Change

Replace in `settings.json` (or crontab):

```
# Old
0 9,15,21 * * *  ~/openclaw/scripts/cron-prediction-market.sh

# New
*/30 * * * *  python3 ~/openclaw/scripts/mirofish/simulator.py --run >> ~/openclaw/logs/mirofish.log 2>&1
```

---

## Open Questions / Future

- **Live trading graduation:** wallet integration TBD — Polymarket uses crypto, needs separate wallet setup and Jordan Tier-3 approval
- **Backtest mode:** `simulator.py --backtest` (future) will replay cached `market_data` rows for strategy tuning without waiting 14+ days; not in scope for this build
- **Expiry settlement accuracy:** current design uses last-cached price for expired markets (paper trading approximation). A future improvement could fetch the resolved outcome from the Polymarket API and settle at 1.0/0.0
- **Vision model** (`qwen3-vl:32b`): Phase 3 possibility for chart analysis — not in scope now
