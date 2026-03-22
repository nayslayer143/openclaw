# Mirofish Paper Trading Simulator — Design Spec
**Date:** 2026-03-22
**Status:** Approved
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
        ├─ trading_brain.analyze()           → calls qwen3:30b via Ollama
        ├─ paper_wallet.execute_trade()      → writes paper_trades
        ├─ paper_wallet.check_stops()        → closes -20% / +50% positions
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
CREATE INDEX idx_market_data_id ON market_data(market_id);
CREATE INDEX idx_market_data_fetched ON market_data(fetched_at);

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
    confidence   REAL,
    reasoning    TEXT,
    strategy     TEXT,            -- momentum | contrarian | arbitrage | news_catalyst
    opened_at    TEXT NOT NULL,
    closed_at    TEXT
);

CREATE TABLE daily_pnl (
    id              INTEGER PRIMARY KEY,
    date            TEXT NOT NULL UNIQUE,
    balance         REAL NOT NULL,
    open_positions  INTEGER,
    realized_pnl    REAL,
    unrealized_pnl  REAL,
    total_trades    INTEGER,
    win_rate        REAL,
    roi_pct         REAL
);
```

Wallet starting balance stored in the existing `context` table:
`(chat_id="mirofish", key="starting_balance", value="1000.00")`

Wallet current balance is always derived from `paper_trades` (never stored directly).

---

## Module Contracts

### `paper_wallet.py`

```python
get_state() -> WalletState
# WalletState: {balance, starting_balance, open_positions, roi_pct,
#               win_rate, max_drawdown, sharpe_ratio, total_trades}

execute_trade(decision: TradeDecision) -> Trade | None
# Returns None if position cap would be breached (10% of portfolio max)

check_stops(current_prices: dict[str, dict]) -> list[Trade]
# Closes open positions at -20% (stop-loss) or +50% (take-profit)
# Also closes expired markets using last cached price

get_open_positions() -> list[Trade]

get_pnl_summary(days: int = 7) -> PnLSummary
```

### `polymarket_feed.py`

```python
fetch_markets(categories=["crypto","politics","sports","weather","tech"]) -> list[Market]
# Hits gamma-api.polymarket.com, filters: active=True, volume>$10K
# Writes to market_data table, returns list of Market dicts

get_price_history(market_id: str, days: int) -> list[dict]
# Reads from market_data table (cached snapshots)

get_latest_prices() -> dict[str, dict]
# Returns {market_id: {yes_price, no_price}} for all known markets
```

### `trading_brain.py`

```python
analyze(markets: list[Market], wallet: WalletState) -> list[TradeDecision]
# Calls qwen3:30b. Returns list of TradeDecision dicts sorted by confidence desc.
# TradeDecision: {market_id, question, direction, confidence, reasoning, strategy,
#                 amount_usd (Kelly-sized)}
```

### `dashboard.py`

```python
generate_report(period: str = "daily") -> Path   # returns path to written .md file
check_graduation() -> GraduationStatus
# GraduationStatus: {ready: bool, roi_7d: float, win_rate: float,
#                    sharpe_all_time: float, max_drawdown: float, criteria: dict}

format_portfolio_message() -> str    # Telegram-ready
format_pnl_message() -> str
format_trades_message(limit: int = 10) -> str
```

### `simulator.py`

```python
# CLI: python3 simulator.py --run | --backtest | --migrate | --report
```

---

## Trading Logic

### Strategies

| Strategy | Signal | Mechanism |
|---|---|---|
| **momentum** | yes_price up >5% over last 3 snapshots | LLM confirms trend validity |
| **contrarian** | yes_price moved >20% in one window | LLM assesses overreaction |
| **arbitrage** | `abs(yes + no - 1.0) > 0.03` | Pure math — no LLM call needed |
| **news_catalyst** | LLM cross-references question against current knowledge | LLM primary |

Arbitrage check runs first in `polymarket_feed.py` (pre-LLM, pure math). The brain call handles momentum/contrarian/news in a single prompt.

### Position sizing — correct Kelly for prediction markets

```python
b = (1 / entry_price) - 1           # payout odds (e.g. $0.30 entry → b=2.33)
kelly = (confidence * b - (1 - confidence)) / b
position_size = min(kelly * balance, 0.10 * balance)  # hard cap: 10% per position
```

The simplified `p - (1-p)` formula assumes even money and is wrong for Polymarket.

### Stop management (checked every run)

- **Stop-loss:** close if unrealized P&L < -20% of `amount_usd`
- **Take-profit:** close if unrealized P&L > +50% of `amount_usd`
- **Expiry:** close if market `end_date` has passed, using last cached price

### Risk limits

- Max 10% of portfolio per single position (enforced in `execute_trade`)
- Minimum $10K market volume (enforced in `fetch_markets`)
- Skip markets with < 6h of price history (insufficient momentum data)

---

## Graduation Criteria

Checked by `dashboard.check_graduation()` at every daily snapshot. All four must pass simultaneously:

| Criterion | Threshold | Window |
|---|---|---|
| ROI | > 0% | Last 7 days (`daily_pnl` rows) |
| Win rate | > 55% | All closed trades |
| Sharpe ratio | > 1.0 | All available history (not capped at 7 days — 7 points is statistically unreliable) |
| Max drawdown | < 25% | Peak-to-trough in balance over all history |

**Sharpe calculation:**
```python
daily_returns = [row.roi_pct for row in daily_pnl_rows]
sharpe = mean(daily_returns) / std(daily_returns) * sqrt(len(daily_returns))
```

When all four pass:
- Every generated report gets a `READY FOR LIVE TRADING` header
- Telegram notification fires once (flag stored in context table to prevent repeat spam)

---

## Telegram Integration

New `/slash` command handlers added to `telegram-dispatcher.py` following the existing pattern (hard routes caught before the LLM classifier):

| Command | Handler | Response |
|---|---|---|
| `/portfolio` | `dashboard.format_portfolio_message()` | Balance, open positions, unrealized P&L |
| `/pnl` | `dashboard.format_pnl_message()` | 7-day P&L, win rate, ROI, graduation status |
| `/trades` | `dashboard.format_trades_message()` | Last 10 trades (open + recently closed) |
| `/bet [market_id] [YES\|NO] [amount]` | `paper_wallet.execute_trade()` | Confirmation or rejection message |

**Daily digest** (fired from `dashboard.maybe_snapshot()` on first daily run):
```
Mirofish Daily — 2026-03-22
P&L today: +$47.20 (+4.7%)
Open positions: 3
Win rate: 67% (12W / 6L)
Portfolio: $1,234.50
```

**Natural language** ("how are our bets doing?") — falls through to CONVERSATION intent. Clawmson's system prompt gets portfolio summary injected as context (one-line summary appended to `clawmson-chat.md` context block or passed as a dynamic prefix).

---

## Error Handling

| Failure | Behavior |
|---|---|
| Ollama unreachable | Log error, skip trade generation, still run `check_stops()` and daily snapshot |
| Polymarket API down | Use cached `market_data` rows if < 6h old; skip entirely if stale |
| Malformed LLM response | JSON extractor with regex fallback; no trade executed if parse fails |
| `/bet` bad args | Send usage string to Telegram, no DB write |
| SQLite locked | Retry once after 2s (WAL mode handles most concurrency) |

---

## Tests

### `tests/test_wallet.py`
- Starting balance $1,000 enforced from context table
- 10% position cap: trade for $101 on $1,000 balance → rejected
- Stop-loss: position at -20% → closed on next `check_stops()` call
- Take-profit: position at +50% → closed on next `check_stops()` call
- ROI calculation over N days matches manual calculation
- Sharpe ratio: known daily return sequence → expected value

### `tests/test_positions.py`
- Arbitrage detection: yes=0.60 + no=0.45 → flagged (sum=1.05, gap>0.03)
- Arbitrage non-detection: yes=0.60 + no=0.41 → not flagged (sum=1.01, gap≤0.03)
- Kelly sizing: confidence=0.70, entry_price=0.30, balance=$1000 → within cap
- Kelly sizing: high-confidence bet → never exceeds 10% cap
- Graduation: all four criteria pass → `ready=True`
- Graduation: win_rate=0.50 (below 55%) with other criteria passing → `ready=False`

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
OLLAMA_BASE_URL=http://localhost:11434
MIROFISH_MODEL=qwen3:30b
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

- Live trading graduation: wallet integration TBD (Polymarket uses crypto — needs separate wallet setup and Jordan Tier-3 approval)
- Backtest mode: `simulator.py --backtest` will replay cached `market_data` rows — useful for strategy tuning without waiting 7 days
- Vision model (`qwen3-vl:32b`) could analyze chart screenshots in Phase 3 — not in scope now
