# OpenClaw Ecosystem — Master Context for ChatGPT

> Auto-generated 2026-04-06T18:07:00-07:00. Do not edit manually.
> For live code, use the GitHub MCP connector to read repos directly.

Generated: 2026-04-06T18:07:00-07:00
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
~/openclaw/.brv
~/openclaw/.brv/context-tree
~/openclaw/.claude
~/openclaw/.git
~/openclaw/.pytest_cache
~/openclaw/.queue-locks
~/openclaw/.repowise
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
~/rivalclaw/.monitor_state.json
~/rivalclaw/.pytest_cache
~/rivalclaw/.rivalclaw_run.lock
~/rivalclaw/CHANGELOG.md
~/rivalclaw/CLAUDE.md
~/rivalclaw/P0-001-diagnostic.md
~/rivalclaw/README.md
~/rivalclaw/auto_changelog.py
~/rivalclaw/balance_watchdog.py
~/rivalclaw/bridge
~/rivalclaw/bridge/auth.py
~/rivalclaw/bridge/control_routes.py
~/rivalclaw/bridge/db_routes.py
~/rivalclaw/bridge/kalshi_routes.py
~/rivalclaw/bridge/rivalclaw.db
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
~/rivalclaw/daily/2026-03-30.md
~/rivalclaw/daily/2026-03-31.md
~/rivalclaw/daily/2026-04-01.md
~/rivalclaw/daily/2026-04-02.md
~/rivalclaw/daily/2026-04-03.md
~/rivalclaw/daily/2026-04-04.md
~/rivalclaw/daily/2026-04-05.md
~/rivalclaw/daily/2026-04-06.md
~/rivalclaw/daily/hourly-latest.md
~/rivalclaw/daily/hourly-log.md
~/rivalclaw/daily/strategy-lab-2026-03-25.md
~/rivalclaw/daily/strategy-lab-2026-03-26.md
~/rivalclaw/daily/strategy-lab-2026-03-27.md
~/rivalclaw/daily/strategy-lab-2026-03-28.md
~/rivalclaw/daily/strategy-lab-2026-03-29.md
~/rivalclaw/daily/strategy-lab-2026-03-30.md
~/rivalclaw/daily/strategy-lab-2026-03-31.md
~/rivalclaw/daily/strategy-lab-2026-04-01.md
~/rivalclaw/daily/strategy-lab-2026-04-02.md
~/rivalclaw/daily/strategy-lab-2026-04-03.md
~/rivalclaw/daily/strategy-lab-2026-04-04.md
~/rivalclaw/daily/strategy-lab-2026-04-05.md
~/rivalclaw/daily/strategy-lab-2026-04-06.md
~/rivalclaw/data
~/rivalclaw/data/strategy-catalog.json
~/rivalclaw/docs
~/rivalclaw/docs/architecture.md
~/rivalclaw/docs/configuration.md
~/rivalclaw/docs/database.md
~/rivalclaw/docs/execution.md
~/rivalclaw/docs/operations.md
~/rivalclaw/docs/risk-management.md
~/rivalclaw/docs/strategies.md
~/rivalclaw/docs/superpowers
~/rivalclaw/docs/trading-pipeline.md
~/rivalclaw/event_logger.py
~/rivalclaw/execution_router.py
~/rivalclaw/experiments
~/rivalclaw/experiments/ledger.json
~/rivalclaw/graduation.py
~/rivalclaw/hourly_report.py
~/rivalclaw/index_feed.py
~/rivalclaw/kalshi_executor.py
~/rivalclaw/kalshi_feed.py
~/rivalclaw/logs
~/rivalclaw/market_classifier.py
~/rivalclaw/notify-telegram.sh
~/rivalclaw/notify.py
~/rivalclaw/observation_feed.py
~/rivalclaw/paper_monitor.log
~/rivalclaw/paper_monitor.py
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
~/rivalclaw/risk_debug.log
~/rivalclaw/risk_engine.py
~/rivalclaw/rivalclaw.db
~/rivalclaw/rivalclaw.db-shm
~/rivalclaw/rivalclaw.db-wal
~/rivalclaw/rivalclaw.log
~/rivalclaw/rivalclaw_dispatcher.py
~/rivalclaw/run.py
~/rivalclaw/scripts
~/rivalclaw/scripts/process-quantclaw-signals.py
~/rivalclaw/self_tuner.py
~/rivalclaw/sentiment_feed.py
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
~/rivalclaw/trade_monitor.py
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
~/arbclaw/daily/2026-03-30.md
~/arbclaw/daily/2026-03-31.md
~/arbclaw/daily/2026-04-01.md
~/arbclaw/daily/2026-04-02.md
~/arbclaw/daily/2026-04-03.md
~/arbclaw/daily/2026-04-04.md
~/arbclaw/daily/2026-04-05.md
~/arbclaw/daily/2026-04-06.md
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
~/quantumentalclaw/.claude
~/quantumentalclaw/.codemonkey
~/quantumentalclaw/.codemonkey/wo-2026-03-27-007
~/quantumentalclaw/.codemonkey/wo-2026-03-27-008
~/quantumentalclaw/.git
~/quantumentalclaw/.gitignore
~/quantumentalclaw/.mcp.json
~/quantumentalclaw/.pytest_cache
~/quantumentalclaw/.repowise
~/quantumentalclaw/.repowise/mcp.json
~/quantumentalclaw/.repowise/wiki.db
~/quantumentalclaw/CHANGELOG.md
~/quantumentalclaw/CLAUDE.md
~/quantumentalclaw/README.md
~/quantumentalclaw/backups
~/quantumentalclaw/backups/protocol_commands_20260329_173024.db
~/quantumentalclaw/backups/protocol_cycles_20260329_173030.db
~/quantumentalclaw/backups/protocol_events_20260329_173024.db
~/quantumentalclaw/backups/protocol_rollout_20260329_173030.db
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
~/quantumentalclaw/daily/2026-03-30.md
~/quantumentalclaw/daily/2026-03-31.md
~/quantumentalclaw/daily/2026-04-01.md
~/quantumentalclaw/daily/2026-04-02.md
~/quantumentalclaw/daily/2026-04-03.md
~/quantumentalclaw/daily/2026-04-04.md
~/quantumentalclaw/daily/2026-04-05.md
~/quantumentalclaw/daily/2026-04-06.md
~/quantumentalclaw/docs
~/quantumentalclaw/docs/rivalclaw-bridge.md
~/quantumentalclaw/engine
~/quantumentalclaw/engine/__init__.py
~/quantumentalclaw/engine/council.py
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
~/quantumentalclaw/execution/rivalclaw_bridge.py
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
~/quantumentalclaw/learning/insights.json
~/quantumentalclaw/learning/memory.py
~/quantumentalclaw/learning/trade_logger.py
~/quantumentalclaw/learning/tuner.py
~/quantumentalclaw/logs
~/quantumentalclaw/notify-telegram.sh
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
~/quantumentalclaw/tests/test_council.py
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
~/quantumentalclaw/utils/protocol_reader.py
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
**Current phase:** Phase 5 COMPLETE (2026-03-23) → v4.5 Migration COMPLETE (2026-04-06)
**Platform:** openclaw 2026.4.5 — all 4 claws running as proper openclaw agent workspaces
**Last updated:** 2026-04-06

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
│       ├── unusual_whales_feed.p
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
---
project: arbclaw
type: trading-agent
stack: [python, sqlite]
status: active
github: https://github.com/nayslayer143/arbclaw
gitlab: https://gitlab.com/jordan291/arbclaw
instance: ArbClaw
parent: openclaw
children: []
---

# ArbClaw

Minimal arbitrage bot — the speed and execution baseline for the OpenClaw ecosystem.

## What This Is

ArbClaw is a stripped-down arb execution agent. It exists to establish a performance baseline that RivalClaw and other trading agents are compared against. The simplest possible Polymarket arb bot — no AI, no agents, no dashboard. Just math. The control group for whether OpenClaw's architecture actually helps or hurts arb execution speed.

## Architecture

- **Minimal surface area** — smallest possible codebase for arb detection and execution
- **Metrics-compatible** — exports daily JSON matching the OpenClaw comparison contract
- **Sub-agent of Clawmpson** — runs within the OpenClaw orchestration layer

## Key Files

| File/Dir | Purpose |
|----------|---------|
| `CLAUDE.md` | Agent instructions (if exists) |
| `src/` | Core arbitrage logic |

## Quick Start

```bash
git clone https://github.com/nayslayer143/arbclaw.git
cd arbclaw
cat CLAUDE.md  # Architecture and constraints
```

## Related Projects

| Project | Relationship | Repo |
|---------|-------------|------|
| OpenClaw | Parent — orchestrator | [GitHub](https://github.com/nayslayer143/openclaw) |
| RivalClaw | Sibling — arb architecture comparison | [GitHub](https://github.com/nayslayer143/rivalclaw) |
| QuantumentalClaw | Sibling — signal fusion | [GitHub](https://github.com/nayslayer143/quantumentalclaw) |

## License

Private project.

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
---
project: openclaw
type: trading-agent
stack: [python, sqlite, bash, yaml]
status: active
github: https://github.com/nayslayer143/openclaw
gitlab: https://gitlab.com/jordan291/openclaw
instance: Clawmpson
parent: none
children: [arbclaw, rivalclaw, quantumentalclaw]
---

# OpenClaw

AI operating system for web-based businesses — agent orchestration, trading, research, content, and automation on a single M2 Max.

## What This Is

OpenClaw is the central nervous system that runs a fleet of AI agents. Trading bots, research engines, content pipelines, and build systems all route through here. Claude Code is the build plane, local Ollama models handle inference at zero API cost, and deterministic Lobster workflows handle scheduling and approval gates.

## Architecture

- **Agent orchestration** — 13+ specialized agents each own a domain
- **Trading stack** — paper trading across Polymarket and equities with multiple parallel strategies
- **Research engine** — automated multi-domain research (market intel, content, academic, competitive)
- **Lobster workflows** — YAML-based deterministic pipelines with schedule and approval gates
- **Memory layer** — learns from past runs, surfaces patterns over time

## Key Files

| File/Dir | Purpose |
|----------|---------|
| `CLAUDE.md` | Agent instructions and workspace map |
| `CONTEXT.md` | Task router — start here |
| `CONSTRAINTS.md` | Non-negotiable rules |
| `openclaw-v4.1-strategy.md` | Full strategy document |
| `agents/configs/` | 13 agent configuration files |
| `scripts/mirofish/` | Advanced trading brain (10 modules) |
| `dashboard/` | Next.js monitoring dashboard |

## Quick Start

```bash
git clone https://github.com/nayslayer143/openclaw.git
cd openclaw
cat CONTEXT.md  # Route to the right workspace
```

## Related Projects

| Project | Relationship | Repo |
|---------|-------------|------|
| ArbClaw | Child — minimal arb bot | [GitHub](https://github.com/nayslayer143/arbclaw) |
| RivalClaw | Child 
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
# Clawmpson Logs

Private operational log for Clawmpson / Omega MegaCorp.
Auto-committed daily by OpenClaw at 11:55pm.

## Structure

| Folder | Contents |
|--------|----------|
| `daily/` | Daily work logs — what was built, queued, earned |
| `projects/` | Active project status snapshots |
| `memory/` | Clawmpson's accumulated knowledge and decisions |
| `revenue/` | Revenue tracking |

**Goal:** $10k/month net. Currently: $0.

## Reading the logs

Each `daily/YYYY-MM-DD.md` contains:
- What Clawmpson accomplished
- Tasks queued and completed
- Ideas generated / approved
- Revenue earned that day
- Top priority for next day

```

### ~/openclaw/doctor-claw/README.md
```
This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.

```

### ~/openclaw/liminal/README.md
```
# Liminal — Parked Tasks

Tasks that were interrupted mid-flight. Each file has enough context to resume cold.

**Convention:** `[slug].md` — one file per task, self-contained.

| File | Summary | Status |
|------|---------|--------|
| [dashboard-pwa-oauth.md](dashboard-pwa-oauth.md) | PWA dashboard with GitHub OAuth + Cloudflare tunnel | Needs OAuth credentials |

```

### ~/openclaw/openclaw-build/README.md
```
# OpenClaw — Build Documentation Layer

> **Owner:** Jordan Michael Moon Schuster / SHINY LLC
> **Status:** Active — v0.1
> **Repo type:** Private build log + documentation layer

---

## What Is OpenClaw?

OpenClaw is a self-hosted, multimodal AI co-working environment built on **Open WebUI**, running on a **Hostinger VPS**. It connects multiple frontier AI providers — Anthropic (Claude), OpenAI, and a local Ollama instance — into a unified workspace where tasks can be routed by capability, cost, and context.

This repository is the **documentation layer**: a structured build log, config reference, and architectural record for the OpenClaw stack. It exists both as an operational reference and as the foundation for eventually packaging OpenClaw as a replicable product.

---

## Current Stack

| Layer | Technology |
|-------|------------|
| **Host** | Hostinger VPS |
| **Base platform** | Open WebUI (self-hosted) |
| **HTTPS / Reverse Proxy** | Nginx + Let's Encrypt (Certbot) |
| **Auth** | [TBD — to be documented] |

---

## Active AI Integrations

### Claude (Anthropic API)
Frontier reasoning, multi-step planning, long-context analysis. Connected via Anthropic API through Open WebUI's OpenAI-compatible endpoint.

### OpenAI API
GPT-series models available for tasks requiring broad capability coverage or where OpenAI tooling is preferred.

### Ollama (Local — $0 Cost)
A local Ollama instance runs on the VPS, providing zero-API-cost inference. Currently loaded models:

| Model | Type |
|-------|------|
| `qwen3:32b` | Large reasoning / general purpose |
| `qwen3-coder-next` | Code generation and debugging |
| `devstral-small-2` | Lightweight coding assistant |
| `qwen3:30b` | General purpose (lighter than 32b) |
| `qwen3-vl:32b` | Multimodal — vision + language |
| `llama3.3:70b` | High-quality general purpose |
| `qwen2.5:7b` | Fast ops, routing, simple tasks |
| `nomic-embed-text` | Text embeddings |

---

## Documentation Structure

```
openclaw-buil
```

### ~/openclaw/punch-my-baby/README.md
```
This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.

```

### ~/openclaw/shiny-new/README.md
```
# SHINY.NEW — The Living Reinvention Engine

An Awwwards-tier cinematic web experience for the shiny.new domain. Single-file HTML, zero build step, fully self-contained.

## What It Is

A `.new`-compliant creation tool that makes people forget they're looking at a browser. Users type a fragment of an idea — a feeling, a word, a half-thought — and SHINY generates a luminous artifact of thought in return.

**Google `.new` compliance:** Users must actively CREATE something. This experience requires typed input before any content is generated. ✓

## Features

- **WebGL iridescent orb** — IcosahedronGeometry with custom GLSL vertex + fragment shaders. Multi-octave organic morphing, view-dependent soap-bubble iridescence, Fresnel rim glow, cursor reactivity
- **Particle field** — 600 AdditiveBlending particles orbiting the orb with lazy drift physics
- **CSS bloom** — `drop-shadow` filter stack simulating post-processing glow without EffectComposer
- **Glyph scramble preloader** — exotic Unicode glyphs snap into "SHINY", then cinematic slide-up reveal
- **Kinetic hero typography** — characters materialize with GSAP `back.out` easing + 3D rotateX
- **GSAP ScrollTrigger** — scroll-linked orb drift, hue shift, section reveals
- **Lenis smooth scroll** — physics-based smooth scroll wired to GSAP ticker
- **Custom cursor** — 18-particle iridescent trail with spring-follow decay, magnetic snap on interactive elements
- **Cycling placeholders** — 7 evocative suggestions that rotate every 3.8s
- **Keyword-matched responses** — 14 thematic "Shiny Things" matched by input keywords, each a vivid poetic artifact
- **Streaming text** — character-by-character reveal with natural punctuation pauses and blinking cursor
- **Glassmorphism artifact card** — `backdrop-filter: blur(40px)`, iridescent border shimmer, rotating light sweep, 3D tilt on hover
- **Mobile responsive** — reduced particle count, WebGL still runs, all interactions touch-friendly

## Te
```

### ~/quantumentalclaw/.pytest_cache/README.md
```
# pytest cache directory #

This directory contains data from the pytest's cache plugin,
which provides the `--lf` and `--ff` options, as well as the `cache` fixture.

**Do not** commit this to version control.

See [the docs](https://docs.pytest.org/en/stable/how-to/cache.html) for more information.

```

### ~/quantumentalclaw/README.md
```
---
project: quantumentalclaw
type: signal-engine
stack: [python, sqlite]
status: active
github: https://github.com/nayslayer143/quantumentalclaw
gitlab: https://gitlab.com/jordan291/quantumentalclaw
instance: QuantumentalClaw
parent: openclaw
children: []
---

# QuantumentalClaw

Signal fusion engine that detects asymmetric opportunities across equities and prediction markets.

## What This Is

Combines five independent signal types to find trades where upside massively outweighs downside. Not a generic trading bot — executes selectively, learns continuously, compounds edge over time. Runs alongside RivalClaw as a parallel strategy in the OpenClaw ecosystem.

## Architecture

Five signal types fused into a single scoring framework:

1. **Quant** — price inefficiencies, cross-venue spreads, mean reversion
2. **Narrative** — keyword velocity, sentiment shifts, attention spikes
3. **Event** — earnings, FOMC, CPI — scheduled catalysts with uncertainty
4. **EDGAR** — SEC filings, insider buying clusters, material events
5. **Cross-venue** — prediction market vs equity price divergences

## Key Files

| File/Dir | Purpose |
|----------|---------|
| `CLAUDE.md` | Agent instructions and signal architecture |
| `simulator.py` | Async orchestrator — the main loop |
| `run.py` | CLI entry point |
| `feeds/` | Data ingestion (7 feeds) |
| `signals/` | Signal modules (5 modules) |
| `engine/` | Fusion, filtering, sizing, risk |

## Quick Start

```bash
git clone https://github.com/nayslayer143/quantumentalclaw.git
cd quantumentalclaw
cat CLAUDE.md  # Architecture and signal specs
```

## Related Projects

| Project | Relationship | Repo |
|---------|-------------|------|
| OpenClaw | Parent — orchestrator | [GitHub](https://github.com/nayslayer143/openclaw) |
| RivalClaw | Sibling — arb execution | [GitHub](https://github.com/nayslayer143/rivalclaw) |
| ArbClaw | Sibling — minimal arb baseline | [GitHub](https://github.com/nayslayer143/arbclaw) |

## Licen
```

### ~/rivalclaw/.pytest_cache/README.md
```
# pytest cache directory #

This directory contains data from the pytest's cache plugin,
which provides the `--lf` and `--ff` options, as well as the `cache` fixture.

**Do not** commit this to version control.

See [the docs](https://docs.pytest.org/en/stable/how-to/cache.html) for more information.

```

### ~/rivalclaw/README.md
```
---
project: rivalclaw
type: trading-agent
stack: [python, sqlite]
status: active
github: https://github.com/nayslayer143/rivalclaw
gitlab: https://gitlab.com/jordan291/rivalclaw
instance: RivalClaw
parent: openclaw
children: []
---

# RivalClaw

Lightweight, laser-focused arbitrage trading agent. Speed and execution reliability over complexity.

## What This Is

RivalClaw is a standalone arbitrage execution engine within the OpenClaw ecosystem. It runs independently but exports daily metrics compatible with OpenClaw's comparison framework. Optimizes for reliable, repeatable, execution-realistic arbitrage — not narrative intelligence or complex reasoning.

## Architecture

- **Cycle-based execution** — runs every 10-15 minutes scanning for arb opportunities
- **Single-strategy focus** — pure arbitrage, no multi-strategy complexity
- **Metrics export** — daily JSON contract compatible with OpenClaw and ArbClaw comparison
- **Risk management** — built-in drawdown limits, slippage tracking, false positive monitoring

## Key Files

| File/Dir | Purpose |
|----------|---------|
| `CLAUDE.md` | Agent instructions and architecture rules |
| `src/` | Core trading logic |
| `daily-update.sh` | Daily report generation + git push |

## Quick Start

```bash
git clone https://github.com/nayslayer143/rivalclaw.git
cd rivalclaw
cat CLAUDE.md  # Full architecture and rules
```

## Related Projects

| Project | Relationship | Repo |
|---------|-------------|------|
| OpenClaw | Parent — orchestrator | [GitHub](https://github.com/nayslayer143/openclaw) |
| ArbClaw | Sibling — minimal arb baseline | [GitHub](https://github.com/nayslayer143/arbclaw) |
| QuantumentalClaw | Sibling — signal fusion | [GitHub](https://github.com/nayslayer143/quantumentalclaw) |

## License

Private project.

```

## Tech Stack Fingerprint

### ~/openclaw/chatgpt-mcp/package.json
```
{
  "name": "openclaw-chatgpt-mcp",
  "version": "1.0.0",
  "description": "MCP server bridging Claude Code → ChatGPT for deep research and terminal insights",
  "type": "module",
  "main": "server.js",
  "scripts": {
    "start": "node server.js",
    "dev": "node --watch server.js"
  },
  "dependencies": {
    "@modelcontextprotocol/sdk": "^1.12.1",
    "openai": "^4.80.0"
  }
}

```

### ~/openclaw/cinema-lab/remotion/package.json
```
{
  "name": "remotion",
  "version": "1.0.0",
  "description": "My Remotion video",
  "scripts": {
    "dev": "remotion studio",
    "build": "remotion bundle",
    "upgrade": "remotion upgrade",
    "lint": "eslint src && tsc"
  },
  "repository": {},
  "license": "UNLICENSED",
  "dependencies": {
    "@remotion/cli": "4.0.441",
    "react": "19.2.3",
    "react-dom": "19.2.3",
    "remotion": "4.0.441"
  },
  "devDependencies": {
    "@remotion/eslint-config-flat": "4.0.441",
    "@types/react": "19.2.7",
    "@types/web": "0.0.166",
    "eslint": "9.19.0",
    "prettier": "3.8.1",
    "typescript": "5.9.3"
  },
  "private": true
}

```

### ~/openclaw/doctor-claw/.next/package.json
```
{"type": "commonjs"}
```

### ~/openclaw/doctor-claw/package.json
```
{
  "name": "doctor-claw",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint",
    "test": "jest",
    "test:watch": "jest --watch",
    "workers": "node workers/index.js"
  },
  "dependencies": {
    "@anthropic-ai/sdk": "^0.80.0",
    "@base-ui/react": "^1.3.0",
    "@hookform/resolvers": "^5.2.2",
    "@radix-ui/react-dialog": "^1.1.15",
    "@radix-ui/react-label": "^2.1.8",
    "@radix-ui/react-separator": "^1.1.8",
    "@radix-ui/react-slot": "^1.2.4",
    "@radix-ui/react-tabs": "^1.1.13",
    "@supabase/supabase-js": "^2.99.3",
    "bullmq": "^5.71.0",
    "class-variance-authority": "^0.7.1",
    "clsx": "^2.1.1",
    "dotenv": "^17.3.1",
    "ioredis": "^5.10.1",
    "lucide-react": "^0.577.0",
    "next": "14.2.35",
    "react": "^18",
    "react-dom": "^18",
    "react-hook-form": "^7.71.2",
    "shadcn": "^4.1.0",
    "tailwind-merge": "^3.5.0",
    "tw-animate-css": "^1.4.0",
    "zod": "^4.3.6"
  },
  "devDependencies": {
    "@types/jest": "^30.0.0",
    "@types/node": "^20",
    "@types/react": "^18",
    "@types/react-dom": "^18",
    "@types/supertest": "^7.2.0",
    "jest": "^30.3.0",
    "postcss": "^8",
    "supertest": "^7.2.2",
    "tailwindcss": "^3.4.1",
    "ts-jest": "^29.4.6",
    "typescript": "^5"
  }
}

```

### ~/openclaw/punch-my-baby/.next/package.json
```
{"type": "commonjs"}
```

### ~/openclaw/punch-my-baby/package.json
```
{
  "name": "punch-my-baby",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start"
  },
  "dependencies": {
    "@anthropic-ai/sdk": "^0.80.0",
    "@base-ui/react": "^1.3.0",
    "@hookform/resolvers": "^5.2.2",
    "@supabase/supabase-js": "^2.99.3",
    "adm-zip": "^0.5.16",
    "cheerio": "^1.2.0",
    "class-variance-authority": "^0.7.1",
    "clsx": "^2.1.1",
    "lucide-react": "^0.577.0",
    "mammoth": "^1.12.0",
    "next": "16.2.1",
    "react": "19.2.4",
    "react-dom": "19.2.4",
    "react-hook-form": "^7.71.2",
    "shadcn": "^4.1.0",
    "stripe": "^20.4.1",
    "tailwind-merge": "^3.5.0",
    "tw-animate-css": "^1.4.0",
    "zod": "^4.3.6"
  },
  "devDependencies": {
    "@tailwindcss/postcss": "^4",
    "@types/adm-zip": "^0.5.8",
    "@types/node": "^20",
    "@types/react": "^19",
    "@types/react-dom": "^19",
    "tailwindcss": "^4",
    "typescript": "^5"
  }
}

```

### ~/openclaw/requirements.txt
```
# Clawmson / OpenClaw dispatcher dependencies

# Core (already in use)
requests

# HTML parsing for nitter tweet extraction
beautifulsoup4

# Link ingestion — extracts clean readable text from web pages
trafilatura

# PDF extraction
pdfplumber

# Excel/spreadsheet parsing
openpyxl

# Audio transcription (voice notes, audio files)
# Only needed if Ollama does not have a whisper model loaded.
# Install with: pip install openai-whisper
# Requires ffmpeg: brew install ffmpeg
openai-whisper

```

### ~/quantumentalclaw/requirements.txt
```
aiohttp>=3.9
httpx>=0.27
yfinance>=0.2.36
feedparser>=6.0
praw>=7.7
python-dotenv>=1.0
cryptography>=42.0
pytest>=8.0
pytest-asyncio>=0.23

```

## Git Status

### openclaw
```
Branch: main
Last commit: de90796 auto: hourly sync 2026-04-07 00:47 UTC
Uncommitted files: 9
Remote: https://github.com/nayslayer143/openclaw.git
```

### rivalclaw
```
Branch: feat/kalshi-live-bridge
Last commit: 18f410e auto: hourly sync 2026-04-07 00:47 UTC
Uncommitted files: 9
Remote: https://github.com/nayslayer143/rivalclaw.git
```

### arbclaw
```
Branch: main
Last commit: 79d8aec daily report 2026-04-06 — day 14 | bal=$ pnl=$ trades=0
Uncommitted files: 3
Remote: https://github.com/nayslayer143/arbclaw.git
```

### quantumentalclaw
```
Branch: main
Last commit: 396c899 hourly: 2026-04-07 01:00 | $4,840 | 0W/0closed | $+0 | quiet
Uncommitted files: 0
Remote: https://github.com/nayslayer143/quantumentalclaw.git
```

### doctor-claw
```
Branch: main
Last commit: 0cdc5ed chore: suppress Supabase never-type build error in next.config.mjs
Uncommitted files: 2
Remote: https://github.com/nayslayer143/doctor-claw.git
```

### punch-my-baby
```
Branch: main
Last commit: 954066f feat: file attachments, URL crawling, voice recording, mobile-first
Uncommitted files: 0
Remote: https://github.com/nayslayer143/punch-my-baby.git
```

### shiny-new
```
Branch: main
Last commit: ac64d70 feat: SHINY.NEW v3 — LaChapelle flash, phosphor trail, full-bleed §7, oracle reveal, manifesto inversion, OMEGA easter egg
Uncommitted files: 3
Remote: https://github.com/nayslayer143/shiny-new.git
```

## Environment Files (names only, NO values)
```
~/openclaw/dashboard/.env
~/openclaw/dashboard/.env.example
~/openclaw/doctor-claw/.env.local
~/openclaw/doctor-claw/.env.example
~/openclaw/.env
~/openclaw/punch-my-baby/.env.local
~/openclaw/punch-my-baby/.env.example
~/rivalclaw/.env.prev
~/rivalclaw/.env
~/quantumentalclaw/.env
~/quantumentalclaw/.env.example
~/openclaw/doctor-claw/.env.local
~/openclaw/doctor-claw/.env.example
~/openclaw/punch-my-baby/.env.local
~/openclaw/punch-my-baby/.env.example
```

## Trading State (if available)

### Clawmpson Trading Dashboard
```json
{
  "portfolio": {
    "open_positions": 1,
    "total_invested": 0,
    "total_current_value": 0,
    "total_pnl": 0,
    "total_pnl_pct": 0,
    "positions": [
      {
        "id": "pos-20260323170243-9921",
        "question": "Will the All India Anna Dravida Munnetra Kazhagam (ADMK) win the most seats in the 2026 Tamil Nadu Assembly Elections?",
        "direction": "buy_yes",
        "entry_price": 0.2155,
        "estimated_true_prob": 0.4,
        "edge": 0.1845,
        "size_usd": 10,
        "confidence": "medium",
        "reasoning": "ADMK is a strong party but faces challenges, making it more likely than priced.",
        "opened_at": "2026-03-23T17:02:43.403185",
        "status": "open",
        "pnl": 0,
        "current_price": null,
        "note": "Market not found \u2014 may have resolved"
      }
    ],
    "as_of": "2026-03-23T17:02:44.495492"
  },
  "recent_signals": [
    {
      "question": "Will the All India Anna Dravida Munnetra Kazhagam (ADMK) win the most seats in the 2026 Tamil Nadu Assembly Elections?",
      "current_yes_price": 0.2155,
      "estimated_true_prob": 0.4,
      "edge": 0.1845,
      "direction": "buy_yes",
      "confidence": "medium",
      "reasoning": "ADMK is a strong party but faces challenges, making it more likely than priced.",
      "suggested_size_usd": 10,
      "scan_time": "2026-03-23T17:02:43.387870",
      "status": "traded",
      "id": "sig-20260323170243-9921"
    }
  ],
  "history": [],
  "updated_at": "2026-03-23T17:02:44.496312"
}
```

---
End of context. Generated 2026-04-06T18:07:00-07:00.
For live code, use GitHub MCP connector -> github.com/nayslayer143/openclaw
