Hey — I had Claude do a deep audit of our entire OpenClaw codebase (local + the public GitHub repo) and compare it against your Arbitrage Lab strategy doc. Here's the full inventory so you can amend the strategy to layer on top of what exists.

---

## WHAT'S ALREADY BUILT AND RUNNING

We have **two parallel trading systems**, a **five-feed data layer**, a **full test suite**, a **multi-agent orchestration layer with 13 agent configs**, and a **market simulation engine** producing live research reports. 61 Python files total.

---

### System 1: trading-bot.py (Simple Polymarket Scanner)

Location: `scripts/trading-bot.py` (~400 lines)
Status: Production, cron-active

- Scans top 30 Polymarket markets by volume via gamma API
- Filters to 10%-90% odds range
- LLM analysis via local `qwen2.5:7b` — generates JSON signals with confidence (high/medium/low)
- Auto-paper-trades high/medium confidence signals
- Tracks positions in `~/openclaw/trading/positions.json`
- Mark-to-market P&L calculation
- Exports `dashboard.json` for web UI consumption
- Cron: 3x daily (9:17am, 3:17pm, 9:17pm) — scan → trade → track
- Commands: `scan`, `trade`, `portfolio`, `full`, `export`
- First trade executed: ADMK Tamil Nadu elections — BUY YES @ $0.22, edge $0.18

---

### System 2: Mirofish Trading Brain (Advanced System)

Location: `scripts/mirofish/` (10 modules + 9 test files)
Status: Phase 3 active, cron every 30 minutes

**trading_brain.py** (18,354 bytes) — Strategy engine with **four** strategies:

1. **Arbitrage Detection** — Pure math: flags when `abs(YES + NO - 1.0) > 0.03`. Buys the underpriced side. Fixed 5% sizing (Kelly doesn't apply cleanly to arb).

2. **Price-Lag Arbitrage** — Detects crypto contracts (BTC/ETH) where Polymarket odds are dislocated from spot price. Parses binary thresholds + bracket contracts from market questions. Computes implied probability vs market price. Applies expiry decay multiplier + latency penalty (5bps default). Min edge: 5bps. Kelly-sized, capped at 10% of portfolio.

3. **Momentum Detection** — Flags markets with 5%+ price moves. Separate from the LLM analysis path.

4. **LLM Analysis** — Momentum, contrarian, news catalyst detection via `qwen3:30b` through Ollama. Prompts written, integration in progress.

**Kelly sizing formula (prediction-market correct, not stock formula):**
```
b = (1 / entry_price) - 1
kelly = (confidence × b − (1 − confidence)) / b
position = min(kelly × balance, 10% × balance)
```

**paper_wallet.py** (236 lines) — SQLite-backed paper wallet state machine:
- Derives balance from trade history + mark-to-market unrealized P&L
- Stop-loss: -20% unrealized P&L (auto-close)
- Take-profit: +50% unrealized P&L (auto-close)
- Auto-closes at market expiry
- Tracks win rate, Sharpe ratio (requires 14+ days), max drawdown, daily ROI
- 10% max position cap enforced

**simulator.py** (286 lines) — CLI orchestrator:
- `--run`: fetch → analyze → trade → check stops → report
- `--migrate`: init DB schema
- `--report`: generate markdown report + graduation check
- Cron: every 30 minutes

**dashboard.py** (308 lines) — Graduation criteria engine:
- All five must pass for 14+ consecutive days before live trading unlocks:
  1. Min history: ≥ 14 days
  2. 7-day ROI: > 0%
  3. Win rate: > 55%
  4. Sharpe ratio: > 1.0 (unannualized)
  5. Max drawdown: < 25%
- Generates `READY FOR LIVE TRADING` report + one-time Telegram alert

**base_feed.py** — DataFeed protocol defining structural subtyping interface for all feeds

---

### Five Integrated Data Feeds

**1. polymarket_feed.py** (6,455 bytes) — Polymarket gamma API:
- Parses both gamma format (outcomePrices) and CLOB format (tokens array)
- SQLite cache with 6-hour TTL, graceful fallback on API failure
- Normalized output: market_id, question, category, yes_price, no_price, volume, end_date

**2. unusual_whales_feed.py** (10,286 bytes) — Four signal sources:
- Options flow (call/put sweeps + blocks)
- Dark pool blocks (institutional trades)
- Congressional trades (politician holdings disclosure)
- Institutional filings (fund position changes)
- Returns normalized signal dicts with direction (bullish/bearish/neutral)

**3. crucix_feed.py** (25,268 bytes) — OSINT + macro intelligence:
- Connects to local Crucix Express.js API (port 3117)
- Integrates **29 intelligence sources** across **6 domain normalizers**: geopolitical, military, economic, environmental, maritime, and general
- Normalizes delta signals (regime changes, critical economic data)
- Maps bearish indicators: VIX spikes, yield inversions, credit spreads, debt milestones
- Generates actionable idea signals (long/hedge/watch)

**4. spot_feed.py** (6,074 bytes) — Real-time crypto spot prices:
- Aggregates from **Binance + Coinbase**
- Used by price-lag arb strategy for BTC/ETH reference pricing

**5. base_feed.py** (424 bytes) — Protocol interface:
- Defines DataFeed structural typing for all feeds

---

### Test Suite (9 test files — NOT in original inventory)

- `test_crucix_feed.py` (23,120 bytes) — largest, comprehensive OSINT testing
- `test_dashboard.py` (7,505 bytes)
- `test_feed.py` (3,678 bytes)
- `test_positions.py` (4,723 bytes)
- `test_price_lag.py` (5,623 bytes) — price-lag arbitrage validation
- `test_spot_feed.py` (4,564 bytes)
- `test_uw_feed.py` (4,857 bytes)
- `test_wallet.py` (9,032 bytes) — paper wallet state machine tests

---

### Database (SQLite: clawmson.db) — 8 tables, not 6

1. **market_data** — Polymarket snapshots, indexed (market_id, fetched_at)
2. **paper_trades** — All trades with entry/exit/pnl/status (open, closed_win, closed_loss, expired)
3. **daily_pnl** — Aggregated daily metrics (balance, positions, realized/unrealized, win_rate, roi_pct)
4. **uw_signals** — Unusual Whales signals, indexed (ticker, fetched_at)
5. **crucix_signals** — OSINT signals
6. **spot_prices** — Crypto reference prices (Binance + Coinbase)
7. **price_lag_trades** — Arbitrage opportunity records specific to price-lag strategy
8. **context** — Key-value state store (starting_balance, config)

---

### Dashboard Server (FastAPI)

Location: `dashboard/server.py` (36,651 bytes) + `index.html` + `login.html`
- GitHub OAuth login (allowlist: nayslayer)
- JWT auth (7-day expiry), localhost bypass
- REST API: portfolio, contracts, queue, builds, logs, trading
- MARKETS tab showing Polymarket data
- Reads from: build-results, queue/pending.json, logs, trading/dashboard.json

---

### MiroFish Market Simulation Engine (Separate from Trading)

Location: `mirofish/`
Status: Producing live research reports

This is a multi-agent **market simulation** engine (distinct from the trading brain). Includes:
- `SCORING_RUBRIC.md` — 5-point evaluation rubric (accuracy, specificity, format, calibration, actionability)
- `simulation-prompt.txt` — LLM system prompt for analysis
- `mirofish-ui.html` (17,523 bytes) — Dedicated dashboard UI
- `translate-to-english.py` — UI translation utility

**Live research reports produced:**
- `report-ai-agent-market-2026-03-20.md` — Agentic AI market analysis
- `report-nfc-cards-market-2026-03-20.md` — NFC cards market analysis
- `report-saas-pricing-2026-03-20.md` — SaaS pricing research
- `report-saas-pricing-compression-2026-03-20.md` — SaaS pricing compression
- `reports/sim-should-doctor-claw-enter-the-open-webui-2026-03-23.md` — Recent competitive analysis
- Multiple validation docs

**Autoresearch engine** at `autoresearch/` with `core/`, `domains/`, `outputs/`, `meta/` subdirectories — handles market-intel, content, academic, competitive, and prediction market research domains.

**Existing arbitrage research paper:** `autoresearch/outputs/papers/market-intel-arbitrage-opportunity-landscape-2026-2026-03-22.md`

---

### OpenClaw Orchestration Layer

**5-Layer Architecture:**
- Layer 1: Operator Shell (OpenClaw + Lobster deterministic workflows)
- Layer 2: Research Agent + Goose (optional web browsing)
- Layer 3: Build Plane (Claude Code primary, Aider fallback)
- Layer 4: Inference Plane (14 local Ollama models, 264GB total on M2 Max 96GB)
- Layer 5: Data Plane (append-only logs, structured queues, SQLite, git versioning)

**13 Agent Configs** (not 2 — previous inventory missed 11):
- `orchestrator.md` — AXIS, chief coordinator, multi-model routing
- `mirofish-trader.md` — Paper trading, every 30 min
- `autoresearch-scholar.md` — Research domain agent
- `build.md` — Code generation + patching
- `clawmson-chat.md` — Conversational interface agent
- `clawmson-memory.md` — Memory management agent
- `clawteam.md` — Team coordination
- `marketing.md` — Content + outreach
- `memory-librarian.md` — Memory curation + retrieval
- `ops.md` — Operations + infrastructure
- `research.md` — General research
- `security-auditor.md` — Security scanning + auditing
- `support.md` — Support operations

**Lobster Workflows:** 14 files (8 .lobster + 2 shell scripts + CONTEXT.md) in `lobster-workflows/`

**Additional scripts (61 Python files total):** Includes `clawteam/` (7 files), `security/` (5 files), `model_router.py`, `skill_auditor.py`, and more utility scripts.

**Approval Tiers:**
- Tier 1 (auto): internal, reversible, read-only
- Tier 2 (hold): external side effects, staging, public — waits indefinitely for Telegram DM
- Tier 3 (confirm): production, financial, destructive — explicit confirmation required

**Security:** `pre-skill-install-check.sh` (PASS/WARN/FAIL) + `pre-bash-check.sh` (runtime denylist)

**Cross-session Memory:** Global `~/.claude/CLAUDE.md` + 3-layer context architecture

**MiroFish Research:** Neo4j + local Ollama for multi-agent market simulations

**Idle Protocol:** Health watchdog (every 2h), intel scan (every 4h), content pipeline (every 6h), memory consolidation (daily 11pm), idea engine (daily 11:30pm), bounty scanner (daily 9pm)

**Telegram:** DM-only interface, `!simulate` for on-demand scans, numeric user allowlist

**Budget:** Daily hard cap: $10

---

### IMPORTANT: Strategy Doc Discrepancy

Our `openclaw-v4.1-strategy.md` explicitly says:
> "MiroFish is positioned exclusively as a market intelligence service — analyzing events and trends post-facto, not predicting price movements or placing trades."

But the actual implementation does both intelligence AND active paper trading with 4 strategies + risk management. The amended strategy should acknowledge this evolution and formally incorporate the trading function into the architecture, since that's what actually exists in the codebase.

---

## WHAT YOUR STRATEGY DOC COVERS THAT WE ALREADY HAVE

No need to rebuild:

1. **Polymarket data feed** — Two systems pulling data (trading-bot.py: top 30, mirofish: top 100)
2. **LLM-based edge analysis** — Both qwen2.5:7b (fast) and qwen3:30b (deep)
3. **Arbitrage detection** — Single-venue: `abs(YES + NO - 1.0) > 0.03`
4. **Price-lag arbitrage** — Crypto spot vs Polymarket dislocation (with tests)
5. **Momentum detection** — 5%+ price moves flagged
6. **Paper execution** — Two systems (JSON-backed simple + SQLite-backed with stops)
7. **Kelly criterion sizing** — Correct prediction market formula, 10% cap
8. **Position tracking + P&L** — Mark-to-market, win rate, Sharpe, max drawdown, daily ROI
9. **Dashboard** — FastAPI server with REST API + web UI MARKETS tab
10. **Automated scheduling** — Every 30 min (mirofish) + 3x daily (simple scanner)
11. **Alerting** — Telegram notifications, portfolio digests, graduation alerts
12. **Stop-loss / take-profit** — Automated at -20% / +50%
13. **Data caching** — SQLite with TTL, graceful API fallback
14. **Test coverage** — 9 test files covering all major components

## WHAT YOUR STRATEGY DOC COVERS THAT WE DON'T HAVE YET

These are the actual gaps:

1. **Kalshi integration** — No Kalshi data feed. This blocks cross-venue arb.
2. **Cross-venue arbitrage detection** — Our arb is single-venue only. Can't detect same event priced differently across platforms.
3. **Canonical MarketEvent schema** — Feed is normalized per-venue but not venue-abstracted. Need this before adding Kalshi.
4. **Persistence filter** — Don't track spread duration. Your `spread_duration > 5s` matters for real vs fake arb.
5. **Depth-aware pricing** — Use quoted prices, not `weighted_avg_price(order_size)`.
6. **Fill probability tracking** — Not tracked. Assume fills at quoted price.
7. **Arb scoring function** — The composite `w1*spread + w2*persistence + w3*liquidity + w4*fill_probability - w5*latency_decay` doesn't exist.
8. **Realistic execution simulation** — Paper traders fill at quoted price instantly. No partial fills, randomized latency, slippage, or order book depth simulation. Biggest quality gap.
9. **Strategy tournament / alpha factory** — We have 4 strategies but no tournament engine, competitive ranking, mutation, or cross-strategy capital allocation.
10. **Edge capture rate** — Not tracked. We track P&L and win rate but not `realized_pnl / expected_pnl`.
11. **Expected vs realized PnL comparison** — Not implemented.
12. **Missed opportunity PnL** — Not tracked.
13. **Opportunity lifetime distribution** — Not tracked.
14. **Wallet / live execution architecture** — No Gnosis Safe, no bot wallet. Not needed yet.
15. **Backtesting engine** — No backtest framework for replaying historical market snapshots.

## WHAT WE HAVE THAT YOUR DOC DOESN'T ADDRESS

Your amended strategy must preserve and build on these:

1. **Two-system architecture** — Simple fast scanner + deep analysis engine. Don't collapse them.
2. **Four strategies, not one** — Arbitrage, price-lag arb, momentum, and LLM analysis. Your doc only proposes cross-venue arb.
3. **Price-lag crypto arbitrage** — Strategy not in your doc. Detects BTC/ETH Polymarket contracts dislocated from spot. Distinct edge source.
4. **Five data feeds** — Polymarket, Unusual Whales (options/dark pool/congressional/institutional), Crucix OSINT (29 sources across 6 domains), spot prices (Binance + Coinbase), and the base protocol interface. Your doc has Polymarket + Kalshi only.
5. **MiroFish simulation engine** — Produces live market research reports with a 5-point scoring rubric. Can simulate multi-agent market scenarios before committing capital. More powerful than static backtesting for prediction markets.
6. **Autoresearch engine** — Multi-domain research pipeline. Already produced an arbitrage opportunity landscape paper (2026-03-22). Your doc has no research layer.
7. **13 agent configs** — Full multi-agent system (orchestrator, trader, researcher, builder, ops, security auditor, marketing, memory, support, chat, team). Your doc has one "OpenClaw brain."
8. **Graduation gates** — Five criteria, 14 consecutive days. More disciplined than your doc.
9. **Approval tier system** — Tier 1/2/3 with Telegram hold. No auto-execution of external actions.
10. **Telegram command interface** — `!simulate` for on-demand scans, DM-only, allowlisted.
11. **Multi-model inference routing** — 14 local models, zero API cost, 264GB loaded. Different models per task type.
12. **Test suite** — 9 test files covering all major components. Production-grade engineering.
13. **Lobster deterministic workflows** — 14 workflow files for repeatable processes.
14. **Idle protocol** — System does useful work when no active task.
15. **Cross-session persistent memory** — Strategies and learnings persist automatically.
16. **Security scanning** — Pre-install + runtime denylist hooks.
17. **SQLite-first architecture** — Cached data, graceful degradation, dedicated tables for each feed + price-lag trades.
18. **Strategy doc needs updating** — v4.1 says MiroFish is intelligence-only, but implementation does active trading. Acknowledge this evolution.

---

## WHAT I NEED FROM YOU

Amend your strategy document to account for everything above:

1. **Start from what exists** — Don't rebuild anything listed in the "already have" section. Layer on top of 61 Python files, 9 test files, 13 agent configs, 5 data feeds, 8 DB tables, and 14 Lobster workflows.

2. **Prioritize by actual gap:**
   - Kalshi data feed + MarketEvent schema normalization
   - Realistic execution simulation (partial fills, slippage, latency)
   - Edge capture rate + expected vs realized PnL tracking
   - Cross-venue arb detection (requires Kalshi)
   - Arb scoring function
   - Strategy tournament engine
   - Backtesting framework

3. **Integrate quantitative + qualitative** — We use LLM judgment AND quantitative filters (Kelly, arb math, price-lag, momentum). Specify how they work together in the decision pipeline.

4. **Account for the five-feed advantage** — Unusual Whales + Crucix + spot prices feed signals that should inform prediction market conviction. Specify how congressional trades, dark pool flow, options activity, macro regime indicators, and geopolitical intelligence map to position sizing.

5. **Preserve graduation gates** — 14 days, >55% win rate, Sharpe >1.0, drawdown <25%. Don't weaken them.

6. **Preserve approval tiers** — Tier 3 for anything touching real capital.

7. **Specify OpenClaw mutation concretely** — We have 13 agents, context layers, and lobster workflows. How does strategy mutation actually work through this architecture?

8. **Revise the timeline** — We're way past Day 1. Target the actual gaps.

9. **Include all four strategies** — Arbitrage, price-lag crypto arb, momentum, and LLM analysis all belong in the tournament.

10. **Address the two-system question** — Do trading-bot.py and mirofish converge or compete?

11. **Incorporate MiroFish simulation + autoresearch** — These are research advantages your doc doesn't have. Specify how simulation informs trading decisions.

12. **Acknowledge the v4.1 strategy discrepancy** — MiroFish already trades. The amended doc should formalize this.

Give me an amended strategy that builds on our actual codebase, not a theoretical one.
