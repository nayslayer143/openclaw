# OpenClaw Ecosystem — Master Context for ChatGPT

> Auto-generated 2026-03-29T06:00:00-07:00. Do not edit manually.
> For live code, use the GitHub MCP connector to read repos directly.

Generated: 2026-03-29T06:00:00-07:00
Machine: Jordan's MacBook Pro M2 Max (96GB)
User: nayslayer

## System Overview

OpenClaw is the operator shell for Jordan's web-based businesses. Claude Code is the build plane. Local Ollama models (14 models, ~264GB) handle inference at zero API cost. Three trading bots compete head-to-head:

| Bot | Path | Architecture | Status |
|-----|------|-------------|--------|
| Clawmpson | ~/openclaw/ | 4 strategies, 5 feeds, graduation engine, 13 agents | Active, Phase 5 |
| RivalClaw | ~/rivalclaw/ | 8 strategies + hedge engine, self-tuner, 3 feeds | Active, daily runs |
| ArbClaw | ~/arbclaw/ | Lean single-strategy arb, 5-min cycle | Not yet built |

**Gonzoclaw Dashboard:** FastAPI + HTML at localhost:7080, exposed via Cloudflare tunnel at https://www.asdfghjk.lol
**Database:** ~/.openclaw/clawmson.db (SQLite, 8 tables)
**GitHub:** https://github.com/nayslayer143/openclaw

## Directory Structure

### openclaw (/Users/nayslayer/openclaw)
```
~/openclaw
~/openclaw/.claude
~/openclaw/.git
~/openclaw/.pytest_cache
~/openclaw/.queue-locks
~/openclaw/.skills
~/openclaw/.skills/superpowers
~/openclaw/.superpowers
~/openclaw/.superpowers/brainstorm
~/openclaw/agents
~/openclaw/agents/configs
~/openclaw/agents/tools
~/openclaw/autoresearch
~/openclaw/autoresearch/core
~/openclaw/autoresearch/domains
~/openclaw/autoresearch/github-intel
~/openclaw/autoresearch/meta
~/openclaw/autoresearch/outputs
~/openclaw/autoresearch/signals
~/openclaw/benchmark
~/openclaw/build-results
~/openclaw/builds
~/openclaw/builds/ifauxto
~/openclaw/chatgpt-mcp
~/openclaw/cinema-lab
~/openclaw/cinema-lab/.pytest_cache
~/openclaw/cinema-lab/assets
~/openclaw/cinema-lab/builds
~/openclaw/cinema-lab/logs
~/openclaw/cinema-lab/remotion
~/openclaw/cinema-lab/renders
~/openclaw/cinema-lab/tests
~/openclaw/clawmpson-logs
~/openclaw/clawmpson-logs/.git
~/openclaw/clawmpson-logs/daily
~/openclaw/clawmpson-logs/memory
~/openclaw/clawmpson-logs/projects
~/openclaw/clawmpson-logs/revenue
~/openclaw/crawlers
~/openclaw/crawlers/openclaw-discord-crawler
~/openclaw/crawlers/openclaw-facebook-crawler
~/openclaw/crawlers/openclaw-instagram-crawler
~/openclaw/crawlers/openclaw-kalshi-feed
~/openclaw/crawlers/openclaw-linkedin-crawler
~/openclaw/crawlers/openclaw-moltbook-crawler
~/openclaw/crawlers/openclaw-polymarket-feed
~/openclaw/crawlers/openclaw-reddit-crawler
~/openclaw/crawlers/openclaw-seekingalpha-crawler
~/openclaw/crawlers/openclaw-stocktwits-crawler
~/openclaw/crawlers/openclaw-telegram-crawler
~/openclaw/crawlers/openclaw-tiktok-crawler
~/openclaw/crawlers/openclaw-tradingview-crawler
~/openclaw/crawlers/openclaw-unusualwhales-crawler
~/openclaw/crawlers/openclaw-x-crawler
~/openclaw/dashboard
~/openclaw/dashboard/.claude
~/openclaw/dashboard/.pytest_cache
~/openclaw/dashboard/tests
~/openclaw/docs
~/openclaw/docs/superpowers
~/openclaw/doctor-claw
~/openclaw/doctor-claw/.git
~/openclaw/doctor-claw/.next
~/openclaw/doctor-claw/app
~/openclaw/doctor-claw/components
~/openclaw/doctor-claw/data
~/openclaw/doctor-claw/lib
~/openclaw/doctor-claw/node_modules
~/openclaw/doctor-claw/supabase
~/openclaw/doctor-claw/tests
~/openclaw/doctor-claw/workers
~/openclaw/ideas
~/openclaw/ideas/media
~/openclaw/improvements
~/openclaw/liminal
~/openclaw/lobster-workflows
~/openclaw/logs
~/openclaw/memory
~/openclaw/mirofish
~/openclaw/mirofish/repo
~/openclaw/mirofish/reports
~/openclaw/openclaw-build
~/openclaw/openclaw-build/.git
~/openclaw/openclaw-build/.github
~/openclaw/openclaw-build/architecture
~/openclaw/openclaw-build/config
~/openclaw/openclaw-build/modules
~/openclaw/openclaw-build/product-vision
~/openclaw/openclaw-build/setup-guides
~/openclaw/outputs
~/openclaw/projects
~/openclaw/punch-my-baby
~/openclaw/punch-my-baby/.git
~/openclaw/punch-my-baby/.next
~/openclaw/punch-my-baby/app
~/openclaw/punch-my-baby/components
~/openclaw/punch-my-baby/lib
~/openclaw/punch-my-baby/node_modules
~/openclaw/punch-my-baby/public
~/openclaw/punch-my-baby/supabase
~/openclaw/queue
~/openclaw/repo-queue
~/openclaw/research
~/openclaw/scripts
~/openclaw/scripts/.pytest_cache
~/openclaw/scripts/autoresearch
~/openclaw/scripts/browser
~/openclaw/scripts/clawteam
~/openclaw/scripts/inspector
~/openclaw/scripts/mirofish
~/openclaw/scripts/ralph-templates
~/openclaw/scripts/security
~/openclaw/scripts/tests
~/openclaw/security
~/openclaw/security/audits
~/openclaw/security/inspector
~/openclaw/shiny-new
~/openclaw/shiny-new/.git
~/openclaw/shiny-new/.superpowers
~/openclaw/shiny-new/docs
~/openclaw/skills
~/openclaw/skills/active
~/openclaw/skills/incoming
~/openclaw/skills/rejected
~/openclaw/templates
~/openclaw/templates/repo-scaffold
~/openclaw/tests
~/openclaw/trading
```

### rivalclaw (/Users/nayslayer/rivalclaw)
```
~/rivalclaw
~/rivalclaw/.claude
~/rivalclaw/.codemonkey
~/rivalclaw/.git
~/rivalclaw/.gitignore
~/rivalclaw/.pytest_cache
~/rivalclaw/CHANGELOG.md
~/rivalclaw/CLAUDE.md
~/rivalclaw/P0-001-diagnostic.md
~/rivalclaw/README.md
~/rivalclaw/__pycache__
~/rivalclaw/auto_changelog.py
~/rivalclaw/bridge
~/rivalclaw/bridge/__pycache__
~/rivalclaw/bridge/auth.py
~/rivalclaw/bridge/control_routes.py
~/rivalclaw/bridge/db_routes.py
~/rivalclaw/bridge/kalshi_routes.py
~/rivalclaw/bridge/run.sh
~/rivalclaw/bridge/server.py
~/rivalclaw/bridge/tunnel.sh
~/rivalclaw/catalog_reader.py
~/rivalclaw/daily
~/rivalclaw/daily-update.log
~/rivalclaw/daily-update.sh
~/rivalclaw/daily/2026-03-25.md
~/rivalclaw/daily/2026-03-26.md
~/rivalclaw/daily/2026-03-27.md
~/rivalclaw/daily/2026-03-28.md
~/rivalclaw/daily/2026-03-29.md
~/rivalclaw/daily/hourly-latest.md
~/rivalclaw/daily/hourly-log.md
~/rivalclaw/daily/strategy-lab-2026-03-25.md
~/rivalclaw/daily/strategy-lab-2026-03-26.md
~/rivalclaw/daily/strategy-lab-2026-03-27.md
~/rivalclaw/daily/strategy-lab-2026-03-28.md
~/rivalclaw/daily/strategy-lab-2026-03-29.md
~/rivalclaw/data
~/rivalclaw/data/strategy-catalog.json
~/rivalclaw/docs
~/rivalclaw/docs/superpowers
~/rivalclaw/event_logger.py
~/rivalclaw/execution_router.py
~/rivalclaw/experiments
~/rivalclaw/experiments/ledger.json
~/rivalclaw/graduation.py
~/rivalclaw/hourly_report.py
~/rivalclaw/kalshi_executor.py
~/rivalclaw/kalshi_feed.py
~/rivalclaw/logs
~/rivalclaw/market_classifier.py
~/rivalclaw/notify.py
~/rivalclaw/paper_wallet.py
~/rivalclaw/polymarket_feed.py
~/rivalclaw/protocol_adapter.py
~/rivalclaw/protocol_commands.db
~/rivalclaw/protocol_commands.db-shm
~/rivalclaw/protocol_commands.db-wal
~/rivalclaw/protocol_cycles.db
~/rivalclaw/protocol_cycles.db-shm
~/rivalclaw/protocol_cycles.db-wal
~/rivalclaw/protocol_events.db
~/rivalclaw/protocol_events.db-shm
~/rivalclaw/protocol_events.db-wal
~/rivalclaw/protocol_rollout.db
~/rivalclaw/protocol_rollout.db-shm
~/rivalclaw/protocol_rollout.db-wal
~/rivalclaw/risk_engine.py
~/rivalclaw/rivalclaw.db
~/rivalclaw/rivalclaw.db-shm
~/rivalclaw/rivalclaw.db-wal
~/rivalclaw/rivalclaw.log
~/rivalclaw/run.py
~/rivalclaw/self_tuner.py
~/rivalclaw/simulator.py
~/rivalclaw/spot_feed.py
~/rivalclaw/status_ping.py
~/rivalclaw/strategies
~/rivalclaw/strategies/active
~/rivalclaw/strategies/graveyard
~/rivalclaw/strategy_lab
~/rivalclaw/strategy_lab/__init__.py
~/rivalclaw/strategy_lab/backtest.py
~/rivalclaw/strategy_lab/daily_report.py
~/rivalclaw/strategy_lab/diagnose.py
~/rivalclaw/strategy_lab/governor.py
~/rivalclaw/strategy_lab/hypothesize.py
~/rivalclaw/strategy_lab/memory.json
~/rivalclaw/strategy_lab/reports
~/rivalclaw/strategy_lab/run_cycle.py
~/rivalclaw/strategy_registry.json
~/rivalclaw/tests
~/rivalclaw/tests/__init__.py
~/rivalclaw/tests/test_execution_router.py
~/rivalclaw/tests/test_kalshi_executor.py
~/rivalclaw/tests/test_shadow_integration.py
~/rivalclaw/trading_brain.py
~/rivalclaw/venv
~/rivalclaw/weather_feed.py
```

### arbclaw (/Users/nayslayer/arbclaw)
```
~/arbclaw
~/arbclaw/.git
~/arbclaw/.gitignore
~/arbclaw/README.md
~/arbclaw/arb_strategy.py
~/arbclaw/arbclaw.db
~/arbclaw/arbclaw.db-shm
~/arbclaw/arbclaw.db-wal
~/arbclaw/daily
~/arbclaw/daily-update.log
~/arbclaw/daily-update.sh
~/arbclaw/daily/2026-03-24.md
~/arbclaw/daily/2026-03-25.md
~/arbclaw/daily/2026-03-26.md
~/arbclaw/daily/2026-03-27.md
~/arbclaw/daily/2026-03-28.md
~/arbclaw/daily/2026-03-29.md
~/arbclaw/feed.py
~/arbclaw/learned_thresholds.json
~/arbclaw/learner.py
~/arbclaw/logs
~/arbclaw/run.py
~/arbclaw/runs.log
~/arbclaw/venv
~/arbclaw/wallet.py
```

### quantumentalclaw (/Users/nayslayer/quantumentalclaw)
```
~/quantumentalclaw
~/quantumentalclaw/.codemonkey
~/quantumentalclaw/.codemonkey/wo-2026-03-27-007
~/quantumentalclaw/.codemonkey/wo-2026-03-27-008
~/quantumentalclaw/.git
~/quantumentalclaw/.gitignore
~/quantumentalclaw/.pytest_cache
~/quantumentalclaw/CHANGELOG.md
~/quantumentalclaw/CLAUDE.md
~/quantumentalclaw/README.md
~/quantumentalclaw/crontab.txt
~/quantumentalclaw/daily
~/quantumentalclaw/daily-snapshot.py
~/quantumentalclaw/daily-update.sh
~/quantumentalclaw/daily/2026-03-24.txt
~/quantumentalclaw/daily/2026-03-25.md
~/quantumentalclaw/daily/2026-03-26.md
~/quantumentalclaw/daily/2026-03-27.md
~/quantumentalclaw/daily/2026-03-28.md
~/quantumentalclaw/daily/2026-03-29.md
~/quantumentalclaw/docs
~/quantumentalclaw/engine
~/quantumentalclaw/engine/__init__.py
~/quantumentalclaw/engine/fusion.py
~/quantumentalclaw/engine/position_sizer.py
~/quantumentalclaw/engine/risk_manager.py
~/quantumentalclaw/engine/trade_filter.py
~/quantumentalclaw/execution
~/quantumentalclaw/execution/__init__.py
~/quantumentalclaw/execution/__pycache__
~/quantumentalclaw/execution/equity_wallet.py
~/quantumentalclaw/execution/live_prices.py
~/quantumentalclaw/execution/paper_wallet.py
~/quantumentalclaw/execution/protocol_adapter.py
~/quantumentalclaw/execution/router.py
~/quantumentalclaw/feeds
~/quantumentalclaw/feeds/__init__.py
~/quantumentalclaw/feeds/base_feed.py
~/quantumentalclaw/feeds/edgar_feed.py
~/quantumentalclaw/feeds/equity_feed.py
~/quantumentalclaw/feeds/event_feed.py
~/quantumentalclaw/feeds/kalshi_feed.py
~/quantumentalclaw/feeds/narrative_feed.py
~/quantumentalclaw/feeds/polymarket_feed.py
~/quantumentalclaw/feeds/spot_feed.py
~/quantumentalclaw/graduation.py
~/quantumentalclaw/hourly-report.py
~/quantumentalclaw/learning
~/quantumentalclaw/learning/__init__.py
~/quantumentalclaw/learning/analyzer.py
~/quantumentalclaw/learning/evolver.py
~/quantumentalclaw/learning/memory.py
~/quantumentalclaw/learning/trade_logger.py
~/quantumentalclaw/learning/tuner.py
~/quantumentalclaw/logs
~/quantumentalclaw/notify.py
~/quantumentalclaw/protocol_commands.db
~/quantumentalclaw/protocol_commands.db-shm
~/quantumentalclaw/protocol_commands.db-wal
~/quantumentalclaw/protocol_cycles.db
~/quantumentalclaw/protocol_cycles.db-shm
~/quantumentalclaw/protocol_cycles.db-wal
~/quantumentalclaw/protocol_events.db
~/quantumentalclaw/protocol_events.db-shm
~/quantumentalclaw/protocol_events.db-wal
~/quantumentalclaw/protocol_rollout.db
~/quantumentalclaw/protocol_rollout.db-shm
~/quantumentalclaw/protocol_rollout.db-wal
~/quantumentalclaw/quantumentalclaw.db
~/quantumentalclaw/quantumentalclaw.db-shm
~/quantumentalclaw/quantumentalclaw.db-wal
~/quantumentalclaw/quantumentalclaw.db.pre-cleanup-20260326-1813
~/quantumentalclaw/quantumentalclaw.lock
~/quantumentalclaw/requirements.txt
~/quantumentalclaw/run.py
~/quantumentalclaw/signals
~/quantumentalclaw/signals/__init__.py
~/quantumentalclaw/signals/asymmetry_module.py
~/quantumentalclaw/signals/base_signal.py
~/quantumentalclaw/signals/edgar_module.py
~/quantumentalclaw/signals/event_module.py
~/quantumentalclaw/signals/narrative_module.py
~/quantumentalclaw/signals/quant_module.py
~/quantumentalclaw/simulator.py
~/quantumentalclaw/tests
~/quantumentalclaw/tests/__init__.py
~/quantumentalclaw/tests/test_db.py
~/quantumentalclaw/tests/test_edgar_feed.py
~/quantumentalclaw/tests/test_engine.py
~/quantumentalclaw/tests/test_equity_event_feeds.py
~/quantumentalclaw/tests/test_execution.py
~/quantumentalclaw/tests/test_feeds.py
~/quantumentalclaw/tests/test_graduation.py
~/quantumentalclaw/tests/test_learning.py
~/quantumentalclaw/tests/test_narrative.py
~/quantumentalclaw/tests/test_quant_module.py
~/quantumentalclaw/tests/test_signal_modules.py
~/quantumentalclaw/tests/test_simulator.py
~/quantumentalclaw/tests/test_types.py
~/quantumentalclaw/utils
~/quantumentalclaw/utils/__init__.py
~/quantumentalclaw/utils/__pycache__
~/quantumentalclaw/utils/config.py
~/quantumentalclaw/utils/db.py
~/quantumentalclaw/utils/helpers.py
~/quantumentalclaw/utils/ticker_map.py
~/quantumentalclaw/utils/types.py
~/quantumentalclaw/venv
```

## Project Instructions (CLAUDE.md files)

### ~/openclaw/CLAUDE.md
```
# OpenClaw — Jordan's Web Business Operating System

OpenClaw is the operator shell for Jordan's web-based businesses running on an M2 Max (96GB).
Claude Code is the build plane. Local Ollama models handle all inference at zero API cost.
Lobster runs deterministic workflows. Agents route tasks. Jordan approves via Telegram DM.

**Verticals:** Trading & arbitrage · Software/app development · Agentic business ops · Marketing & growth · Content & research pipelines. Optimize across the system, not locally within one vertical.

**Strategy doc:** `~/openclaw/openclaw-v4.1-strategy.md`
**Current phase:** Phase 5 COMPLETE (2026-03-23) — full trading intelligence stack
**Last updated:** 2026-03-23

---

## Folder Structure

```
~/openclaw/
├── CLAUDE.md                    ← you are here (map only)
├── CONTEXT.md                   ← route your task here first
├── CONSTRAINTS.md               ← non-negotiable rules [Phase 1]
├── IDLE_PROTOCOL.md             ← cron schedule (lite + advanced) [Phase 1]
├── openclaw-v4.1-strategy.md    ← full strategy + phase steps
├── startup.sh                   ← cold-start script
├── .env                         ← secrets (never commit)
├── agents/configs/              ← 13 agent configs (orchestrator, trader, build, ops, research, etc.)
├── scripts/                     ← operational scripts
│   ├── trading-bot.py           ← simple Polymarket scanner + paper trader [Phase 4]
│   └── mirofish/                ← advanced trading brain (10 modules + 9 test files)
│       ├── trading_brain.py     ← 4 strategies: arb, price-lag, momentum, LLM
│       ├── paper_wallet.py      ← SQLite-backed wallet w/ stop-loss & take-profit
│       ├── polymarket_feed.py   ← gamma API + SQLite cache
│       ├── unusual_whales_feed.py ← options flow, dark pool, congressional, institutional
│       ├── crucix_feed.py   
```

### ~/rivalclaw/CLAUDE.md
```
# ArbClaw — Specialized Arbitrage Rival Instance

ArbClaw is a focused arbitrage worker designed to compete against the main OpenClaw trading stack.

It is not a general-purpose business OS.

It exists to answer one question:

Can a narrow, fast, mechanical arbitrage system outperform a broader, integrated architecture on real execution-adjusted metrics?

---

## Core Identity

ArbClaw is:
- Mechanical over narrative
- Execution-first over theory-first
- Fast over exhaustive
- Skeptical over optimistic
- Minimal over feature-heavy

ArbClaw is not allowed to be clever at the expense of truth.

---

## Mission

Maximize realized edge capture from arbitrage opportunities.

Not:
- raw PnL
- number of trades
- theoretical edge

Primary objective:

Capture as much real, executable edge as possible with minimal hidden fragility

---

## System Scope

### Included
- Polymarket market ingestion
- Canonical MarketEvent normalization
- Arbitrage detection (single-venue initially)
- Persistence + depth-aware scoring
- Resolution compatibility validation (where applicable)
- Realistic execution simulation
- Paper trading only
- Metrics tracking + export
- CLI + scheduled loop

### Excluded (by design)
- Marketing workflows
- Content generation
- Multi-domain research systems
- Broad agent orchestration
- Unused data feeds (UW, Crucix, etc.)
- Strategy diversification beyond arbitrage
- Live trading

---

## Architecture Philosophy

ArbClaw is an architecture-faithful minimal sibling of MiroFish.

Preserve:
- simulator -> brain -> wallet -> metrics flow
- SQLite-backed state
- graduation gates
- risk/accounting semantics

Remove:
- unused strategies
- unused feeds
- research/intelligence layers
- dashboard complexity

ArbClaw = MiroFish skeleton with only arb organs

---

## Control Flow

Each cycle:
1. Fetch market data
2. Normalize into MarketEvent
3. Run integrity checks (stale/anomaly)
4. Generate candidate opportunities
5. Validate resolution compatibility
6. Evaluate pers
```

### ~/quantumentalclaw/CLAUDE.md
```
# QuantumentalClaw

## What This Is

A signal fusion engine that detects asymmetric opportunities across equities and prediction markets. Runs alongside RivalClaw as a parallel trading strategy in the OpenClaw ecosystem.

**Not a generic trading bot.** Executes selectively, learns continuously, compounds edge over time.

## Core Thesis

Combine 5 independent signal types to find trades where the upside massively outweighs the downside:
1. **Quant** — price inefficiencies, cross-venue spreads, mean reversion
2. **Narrative** — keyword velocity, sentiment shifts, attention spikes
3. **Event** — earnings, FOMC, CPI — scheduled catalysts with uncertainty
4. **EDGAR** — SEC filings, insider buying clusters, material events
5. **Asymmetry** — the gatekeeper: no asymmetry = no trade

## Architecture

- **Async single-process** — `asyncio.gather()` for parallel I/O, sequential cycle execution
- **5-minute cron cycles** — fetch → signal → fuse → filter → execute → learn
- **Paper trading** — both prediction markets (Polymarket + Kalshi) and equities
- **SQLite (WAL)** — all state persisted locally
- **Learning loop** — hourly weight adjustment based on signal accuracy

## Key Files

| File | Purpose |
|------|---------|
| `simulator.py` | Async orchestrator — the main loop |
| `run.py` | CLI entry point |
| `feeds/` | Data ingestion (7 feeds) |
| `signals/` | Signal modules (5 modules) |
| `engine/` | Fusion, filtering, sizing, risk |
| `execution/` | Paper wallets + venue router |
| `learning/` | Trade logger, analyzer, evolver, memory |
| `utils/types.py` | Core dataclasses |
| `utils/db.py` | SQLite + migrations |

## Rules

1. **Asymmetry first** — no trade without asymmetry_score > 0.6
2. **Signal agreement** — at least 2 modules must agree (score > 0.5)
3. **Max 5 concurrent trades**, max 10% total exposure
4. **Daily loss circuit breaker** — stop at -3%
5. **Learning adjustments** — max +/- 5% weight change per hour, always re
```

### ~/openclaw/punch-my-baby/CLAUDE.md
```
@AGENTS.md

```

## README Files

### ~/arbclaw/README.md
```
# ArbClaw

The simplest possible Polymarket arb bot. 441 lines of Python. No AI, no agents, no dashboard. Just math.

I built this as a speed baseline for an experiment: my main system ([OpenClaw](https://gitlab.com/jordan291/openclaw)) has a lot of moving parts, and I wanted to know if all that architecture was actually slowing down arb execution. ArbClaw is the control group — what happens when you strip everything away and just run the arb logic?

## How it works

Every 5 minutes:
1. Fetch all active Polymarket markets
2. Check if YES + NO prices sum to less than 1.0 (after 2% taker fees per leg)
3. Size with Kelly criterion
4. Paper trade the underpriced side

That's it. Four files, one strategy, zero overhead.

| File | What it does | Lines |
|------|-------------|-------|
| `feed.py` | Polymarket API fetch + SQLite cache | 112 |
| `arb_strategy.py` | Cross-outcome arb detection + Kelly sizing | 77 |
| `wallet.py` | Paper wallet with latency tracking | 192 |
| `run.py` | Entry point | 60 |

## The experiment

Three systems running the same arb logic on the same machine:

| System | Complexity | Cycle |
|--------|-----------|-------|
| **ArbClaw** (this) | 4 files, 441 lines | 5 min |
| **RivalClaw** | Full architecture, arb only | 5 min |
| **Clawmpson** | Full system, 5 strategies | 30 min |

Key metric: `signal_to_trade_latency_ms` — how long from spotting an opportunity to placing the trade?

## Outcome logic

- If ArbClaw captures more edge → build a fast-path mode into Clawmpson
- If Clawmpson wins anyway → architecture validated, ArbClaw gets retired
- Either way, I learn something

## Status

Paper trading experiment running March 24 – April 7, 2026. Daily reports auto-generated in `daily/`.

Part of the [OpenClaw](https://gitlab.com/jordan291/openclaw) ecosystem.

```

### ~/openclaw/.pytest_cache/README.md
```
# pytest cache directory #

This directory contains data from the pytest's cache plugin,
which provides the `--lf` and `--ff` options, as well as the `cache` fixture.

**Do not** commit this to version control.

See [the docs](https://docs.pytest.org/en/stable/how-to/cache.html) for more information.

```

### ~/openclaw/README.md
```
# OpenClaw

My personal AI operating system. Started as a trading bot, turned into something way bigger.

OpenClaw is the central nervous system that runs my fleet of AI agents — trading, research, content, automation, all of it. Think of it like a business OS where Claude-powered agents handle the heavy lifting and I steer from the top.

## What's in here

- **Agent orchestration** — multiple specialized agents (ArbClaw, PhantomClaw, etc.) that each own a domain
- **Trading stack** — paper trading across Polymarket and equities with multiple strategies running in parallel
- **Research engine** — automated multi-domain research (market intel, content ideas, academic papers, competitive analysis)
- **Lobster workflows** — deterministic YAML-based pipelines for anything that needs to run on a schedule or with approval gates
- **Build system** — agents can pick up tasks, write code, run tests, and submit results for review
- **Memory layer** — the system learns from past runs and surfaces patterns over time

## The ecosystem

OpenClaw doesn't run alone. It's the hub for a few other projects:

| Project | What it does |
|---------|-------------|
| [Mission Control](https://gitlab.com/jordan291/openclaw-mission-control) | Next.js dashboard — monitor agents, chat with them, track costs |
| [QuantumentalClaw](https://gitlab.com/jordan291/quantumentalclaw) | Signal fusion engine for asymmetric trading |
| [RivalClaw](https://gitlab.com/jordan291/rivalclaw) | Architecture comparison experiment for arb execution |
| [ArbClaw](https://gitlab.com/jordan291/arbclaw) | Minimal arb bot — the speed baseline |

## Status

Active development. This is my daily driver — constantly evolving as I figure out what works and what doesn't. Paper trading only for now.

## Setup

This isn't really designed for others to run (yet). It's deeply tied to my local environment, API keys, and workflow. But if you're curious about any of the architecture, the `CONTEXT.md` files are
```

### ~/openclaw/chatgpt-mcp/README.md
```
# OpenClaw ChatGPT MCP Server

Bridges Claude Code → ChatGPT for deep research and terminal insights.

## Setup

### 1. Install dependencies

```bash
cd ~/openclaw/chatgpt-mcp
npm install
```

### 2. Add your OpenAI API key to `~/openclaw/.env`

```bash
echo 'OPENAI_API_KEY=sk-your-key-here' >> ~/openclaw/.env
```

### 3. Register with Claude Code

Run this once from anywhere:

```bash
claude mcp add chatgpt \
  --scope project \
  --env OPENAI_API_KEY=sk-your-key-here \
  -- node ~/openclaw/chatgpt-mcp/server.js
```

Or add it globally (available in all projects):

```bash
claude mcp add chatgpt \
  --scope user \
  --env OPENAI_API_KEY=sk-your-key-here \
  -- node ~/openclaw/chatgpt-mcp/server.js
```

### 4. Verify it works

Start Claude Code and run:
```
/mcp
```
You should see `chatgpt` listed with two tools: `deep_research` and `terminal_insights`.

## Tools

### `deep_research`
- **Model:** GPT-4o (configurable)
- **Use for:** Market research, competitive analysis, technical deep-dives
- **Formats:** brief, detailed, bullet_points
- **Cost:** ~$0.01-0.05 per call

### `terminal_insights`
- **Model:** GPT-4o-mini (configurable)
- **Use for:** Error diagnosis, build output, log analysis, test results
- **Cost:** ~$0.001-0.005 per call

## Terminal Watcher (Optional)

For passive terminal monitoring:

```bash
# Source it in your shell to watch continuously
source ~/openclaw/chatgpt-mcp/terminal-watcher.sh

# Or pipe a specific command
npm run build 2>&1 | ~/openclaw/chatgpt-mcp/terminal-watcher.sh --analyze

# Read latest insights
cat ~/openclaw/chatgpt-mcp/.terminal-insights.md
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | (required) | Your OpenAI API key |
| `CHATGPT_RESEARCH_MODEL` | `gpt-4o` | Model for deep_research |
| `CHATGPT_TERMINAL_MODEL` | `gpt-4o-mini` | Model for terminal_insights |
| `CHATGPT_RESEARCH_MAX_TOKENS` | `4096` | Max response tokens for research |
| `CHATGP
```

### ~/openclaw/cinema-lab/.pytest_cache/README.md
```
# pytest cache directory #

This directory contains data from the pytest's cache plugin,
which provides the `--lf` and `--ff` options, as well as the `cache` fixture.

**Do not** commit this to version control.

See [the docs](https://docs.pytest.org/en/stable/how-to/cache.html) for more information.

```

### ~/openclaw/cinema-lab/remotion/README.md
```
# Remotion video

<p align="center">
  <a href="https://github.com/remotion-dev/logo">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://github.com/remotion-dev/logo/raw/main/animated-logo-banner-dark.apng">
      <img alt="Animated Remotion Logo" src="https://github.com/remotion-dev/logo/raw/main/animated-logo-banner-light.gif">
    </picture>
  </a>
</p>

Welcome to your Remotion project!

## Commands

**Install Dependencies**

```console
npm install
```

**Start Preview**

```console
npm run dev
```

**Render video**

```console
npx remotion render
```

**Upgrade Remotion**

```console
npx remotion upgrade
```

## Docs

Get started with Remotion by reading the [fundamentals page](https://www.remotion.dev/docs/the-fundamentals).

## Help

We provide help on our [Discord server](https://discord.gg/6VzzNDwUwV).

## Issues

Found an issue with Remotion? [File an issue here](https://github.com/remotion-dev/remotion/issues/new).

## License

Note that for some entities a company license is needed. [Read the terms here](https://github.com/remotion-dev/remotion/blob/main/LICENSE.md).

```

### ~/openclaw/clawmpson-logs/README.md
```
