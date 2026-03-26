# OpenClaw Ecosystem — Master Context for ChatGPT

> Auto-generated 2026-03-26T03:07:00-07:00. Do not edit manually.
> For live code, use the GitHub MCP connector to read repos directly.

Generated: 2026-03-26T03:07:00-07:00
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
~/openclaw/chatgpt-mcp
~/openclaw/cinema-lab
~/openclaw/cinema-lab/builds
~/openclaw/cinema-lab/logs
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
~/openclaw/dashboard/.pytest_cache
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
~/openclaw/scripts/mirofish
~/openclaw/scripts/ralph-templates
~/openclaw/scripts/security
~/openclaw/scripts/tests
~/openclaw/security
~/openclaw/security/audits
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
~/rivalclaw/.git
~/rivalclaw/.gitignore
~/rivalclaw/CHANGELOG.md
~/rivalclaw/CLAUDE.md
~/rivalclaw/README.md
~/rivalclaw/auto_changelog.py
~/rivalclaw/daily
~/rivalclaw/daily-update.log
~/rivalclaw/daily-update.sh
~/rivalclaw/daily/2026-03-25.md
~/rivalclaw/daily/hourly-latest.md
~/rivalclaw/daily/hourly-log.md
~/rivalclaw/daily/strategy-lab-2026-03-25.md
~/rivalclaw/docs
~/rivalclaw/docs/superpowers
~/rivalclaw/event_logger.py
~/rivalclaw/experiments
~/rivalclaw/experiments/ledger.json
~/rivalclaw/graduation.py
~/rivalclaw/hourly_report.py
~/rivalclaw/kalshi_feed.py
~/rivalclaw/logs
~/rivalclaw/market_classifier.py
~/rivalclaw/notify.py
~/rivalclaw/paper_wallet.py
~/rivalclaw/polymarket_feed.py
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
~/quantumentalclaw/docs
~/quantumentalclaw/engine
~/quantumentalclaw/engine/__init__.py
~/quantumentalclaw/engine/fusion.py
~/quantumentalclaw/engine/position_sizer.py
~/quantumentalclaw/engine/risk_manager.py
~/quantumentalclaw/engine/trade_filter.py
~/quantumentalclaw/execution
~/quantumentalclaw/execution/__init__.py
~/quantumentalclaw/execution/equity_wallet.py
~/quantumentalclaw/execution/live_prices.py
~/quantumentalclaw/execution/paper_wallet.py
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
~/quantumentalclaw/quantumentalclaw.db
~/quantumentalclaw/quantumentalclaw.db-shm
~/quantumentalclaw/quantumentalclaw.db-wal
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

Lean arbitrage validation experiment — 14-day paper trading test to determine whether Clawmpson's full trading stack introduces execution lag on prediction market arb opportunities.

## Hypothesis

Clawmpson runs 5 strategies, 5 feeds, LLM analysis, and a graduation engine on a 30-minute cron cycle. For cross-outcome arb where mispricing windows close in minutes, that machinery may cost alpha through execution lag. ArbClaw tests this by running a single strategy on a 5-minute cycle with zero overhead.

## Architecture

| File | Purpose | Lines |
|------|---------|-------|
| `feed.py` | Polymarket gamma API fetch + SQLite cache | 112 |
| `arb_strategy.py` | Cross-outcome arb detection + Kelly sizing | 77 |
| `wallet.py` | Paper wallet with signal-to-trade latency tracking | 192 |
| `run.py` | Entry point chaining feed -> strategy -> wallet | 60 |

**Total: 441 lines.** No LLM. No OSINT. No momentum. No agents. No dashboard.

## Strategy

Pure cross-outcome arb only: detect when YES + NO prices for the same Polymarket market sum to less than 1.0 after accounting for 2% taker fees per leg. Kelly criterion sizes positions. Buy the underpriced side.

## Paper Wallet Rules

- Starting capital: $1,000
- Max position: 10% of balance
- Stop-loss: -20%
- Take-profit: +50%
- Key metric: `signal_to_trade_latency_ms`

## Cron

Runs every 5 minutes (vs Clawmpson's 30-minute cycle).

## Comparison (after 14 days)

| Metric | ArbClaw Target | Clawmpson Baseline |
|--------|---------------|-------------------|
| Signal-to-trade latency | <30s | ~30min cycle |
| Win rate | Track | Track |
| Edge capture rate | Track | Track |
| Total PnL | Track | Track |

## Outcome

- If ArbClaw captures more edge -> build fast-path mode into Clawmpson
- If Clawmpson wins anyway -> architecture validated, delete ArbClaw
- Either way, we learn something

## Daily Reports

Auto-generated daily performance reports are posted to `daily/` by cron at 11:50 PM.

## Status

**Experiment start:
```

### ~/openclaw/.pytest_cache/README.md
```
# pytest cache directory #

This directory contains data from the pytest's cache plugin,
which provides the `--lf` and `--ff` options, as well as the `cache` fixture.

**Do not** commit this to version control.

See [the docs](https://docs.pytest.org/en/stable/how-to/cache.html) for more information.

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
# QuantumentalClaw

Signal fusion engine for asymmetric trading across equities and prediction markets.

Part of the [OpenClaw](https://github.com/nayslayer) ecosystem.

## Quick Start

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Fill in API keys
python run.py --migrate
python run.py --run
```

## Architecture

Async single-process. 5 signal modules fused into trade decisions with continuous learning.

```
Feeds (7) → Signals (5) → Fusion → Filter → Size → Risk → Execute → Learn
```

## Status

V1 build in progress. Paper trading only.

```

### ~/rivalclaw/README.md
```
# RivalClaw

Architecture-faithful arb-only sibling of Mirofish. Part of a three-way comparison experiment testing whether Clawmpson's trading architecture introduces execution lag on arbitrage opportunities.

## The Experiment

Three systems run the same cross-outcome arb logic against the same Polymarket API on the same machine:

| System | Architecture | Cron | Purpose |
|--------|-------------|------|---------|
| **ArbClaw** | 4 files, no overhead | */5 | Speed baseline — what does zero architecture cost? |
| **RivalClaw** | Mirofish skeleton, arb-only | */5 | Architecture test — does the framework itself add lag? |
| **Clawmpson** | Full Mirofish, 5 strategies | */30 | Production baseline — does strategy contention matter? |

## Architecture

RivalClaw preserves Mirofish's control flow shape while stripping non-arb organs:

```
simulator.run_loop()
  -> polymarket_feed.fetch_markets()     # configurable cache/categories
  -> trading_brain.analyze()             # arb-only + integrity guards
  -> paper_wallet.execute_trade()        # frozen Mirofish execution sim
  -> paper_wallet.check_stops()          # same SL/TP + expiry logic
  -> graduation.maybe_snapshot()         # same 4 graduation gates
```

| File | Lines | Preserves from Mirofish |
|------|-------|------------------------|
| simulator.py | ~160 | run_loop orchestration, migration, cycle metrics |
| trading_brain.py | ~130 | TradeDecision, arb detection, Kelly, integrity guards |
| paper_wallet.py | ~280 | Execution sim, stops, mark-to-market, balance derivation |
| polymarket_feed.py | ~160 | Gamma API, SQLite cache, price parsing |
| graduation.py | ~120 | 4 graduation gates, daily snapshot |
| run.py | ~30 | CLI entry point |

## Arb Logic Parity

Arb math is identical to ArbClaw — same fee computation, same Kelly formula, same thresholds:
- Fee: 2% of min(price, 1-price) per leg
- Min edge: 0.5% after fees
- Kelly cap: 10% of balance

## What RivalClaw Adds Over ArbClaw

These are the "arch
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
Last commit: 481eaf5 auto: 2026-03-26 03:00 state snapshot
Uncommitted files: 9
Remote: https://github.com/nayslayer143/openclaw.git
```

### rivalclaw
```
Branch: main
Last commit: e601da2 feat: 5 new quant strategies — 21 total, 80 signals/cycle
Uncommitted files: 19
Remote: https://github.com/nayslayer143/rivalclaw.git
```

### arbclaw
```
Branch: main
Last commit: a2613e9 daily report 2026-03-26 — day 3 | bal=$ pnl=$ trades=0
Uncommitted files: 3
Remote: https://github.com/nayslayer143/arbclaw.git
```

### quantumentalclaw
```
Branch: main
Last commit: 7c0b1f5 hourly: 2026-03-26 10:00 | $68,981 | 8W/27closed | $+1,726 | calm
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
End of context. Generated 2026-03-26T03:07:00-07:00.
For live code, use GitHub MCP connector -> github.com/nayslayer143/openclaw
