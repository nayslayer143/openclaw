# Agent Config: Mirofish Trader

**Role:** Paper trading simulator for Polymarket prediction markets
**Status:** Active (Phase 4)
**Mode:** Paper trading only — no real capital until graduation criteria met

---

## What It Does

Runs every 30 minutes via cron. Fetches live Polymarket markets, analyzes them
for trading opportunities using qwen3:30b, executes paper trades against a fake
$1,000 wallet, and manages positions (stop-loss / take-profit). Generates daily
P&L reports and fires Telegram digests.

Replaces: `cron-prediction-market.sh`

---

## Pipeline

```
polymarket_feed.fetch_markets()
  → paper_wallet.get_state()
  → trading_brain.analyze()     # arb fast-path + qwen3:30b
  → paper_wallet.execute_trade()
  → paper_wallet.check_stops()
  → dashboard.maybe_snapshot()
```

---

## Key Files

| File | Purpose |
|------|---------|
| `scripts/mirofish/simulator.py` | CLI orchestrator (`--run`, `--migrate`, `--report`) |
| `scripts/mirofish/paper_wallet.py` | Wallet state, P&L math, stop management |
| `scripts/mirofish/polymarket_feed.py` | Polymarket API + SQLite cache |
| `scripts/mirofish/trading_brain.py` | Arbitrage detection, Kelly sizing, Ollama |
| `scripts/mirofish/dashboard.py` | Graduation check, reports, Telegram formatting |
| `~/.openclaw/clawmson.db` | DB: `market_data`, `paper_trades`, `daily_pnl` tables |
| `~/openclaw/mirofish/reports/` | Generated markdown reports |

---

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/portfolio` | Current balance, open positions, unrealized P&L |
| `/pnl` | 7-day P&L, win rate, ROI, graduation status |
| `/trades` | Last 10 trades |
| `/bet [market_id] [YES\|NO] [amount]` | Manual paper trade |

---

## Trading Strategies

| Strategy | Signal | Method |
|----------|--------|--------|
| arbitrage | `abs(YES + NO - 1.0) > 0.03` | Pure math, 5% fixed sizing |
| momentum | YES price up >5% over 3 snapshots | qwen3:30b |
| contrarian | YES price moved >20% in one window | qwen3:30b |
| news_catalyst | LLM has relevant knowledge | qwen3:30b |

**Kelly sizing** (prediction market formula):
```
b = (1 / entry_price) - 1
kelly = (confidence × b − (1 − confidence)) / b
position = min(kelly × balance, 10% × balance)
```

---

## Graduation Criteria (all must pass for 14+ days)

| Criterion | Threshold |
|-----------|-----------|
| Min history | ≥ 14 days |
| 7-day ROI | > 0% |
| Win rate | > 55% |
| Sharpe ratio | > 1.0 (unannualized mean/std) |
| Max drawdown | < 25% |

When all pass: report gets `READY FOR LIVE TRADING` header + one-time Telegram alert.
Live wallet access requires separate Tier-3 Jordan approval.

---

## Risk Limits

- Max 10% of portfolio per position (hard cap, including manual `/bet`)
- Minimum $10K market volume
- Kelly ≤ 0 → trade skipped (negative edge)
- Stop-loss: -20% unrealized P&L
- Take-profit: +50% unrealized P&L

---

## Model

- **Trading analysis:** `qwen3:30b` (research/business model — 3x daily research tasks, 18 GB)
- **Inference:** Local Ollama at `http://localhost:11434` — zero API cost

---

## Configuration (`.env`)

```bash
MIROFISH_STARTING_BALANCE=1000.00
MIROFISH_MAX_POSITION_PCT=0.10
MIROFISH_STOP_LOSS_PCT=0.20
MIROFISH_TAKE_PROFIT_PCT=0.50
MIROFISH_MIN_MARKET_VOLUME=10000
MIROFISH_MIN_HISTORY_DAYS=14
MIROFISH_MODEL=qwen3:30b
JORDAN_TELEGRAM_CHAT_ID=<your_chat_id>
```

---

## Cron Entry

```
*/30 * * * *  python3 ~/openclaw/scripts/mirofish/simulator.py --run >> ~/openclaw/logs/mirofish.log 2>&1
```

---

## Known Limitations

- Expired market P&L uses last cached price, not actual binary settlement (approximation)
- Sharpe ratio requires 14+ days of data (std=0 guard before that)
- No backtest mode in current version (future phase)
