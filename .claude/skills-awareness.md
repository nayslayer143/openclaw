# OpenClaw Skills Awareness

Skills available to Clawmpson and sub-agents. Reference `~/.claude/SKILLS-CATALOG.md` for full details.

---

## Clawmpson — Orchestration Skills

Clawmpson is the primary instance. These skills support its business OS role:

**Daily Operations**
- `/executive-assistant` — inbox triage, email replies, scheduling
- `/daily-task-prep` + `/daily-task-manager` — morning prep and ongoing task tracking
- `/business-development` — outreach, lead tracking, referral partners

**Research & Intelligence**
- `/last30days` — deep multi-source research (Reddit, X, YT, HN, Polymarket, etc.)
- `/osint` — systematic open-source intelligence gathering
- `/notebooklm` — turn research into podcasts, quizzes, structured content
- `/search` + `/fetch` — lightweight web lookups without full browser

**Agent Dispatch**
- `/acpx` — agent-to-agent communication protocol. Use for:
  - Dispatching prompts to sub-agents (ArbClaw, PhantomClaw)
  - Session scoping and queueing work
  - Collecting results from parallel agent runs
  - CodeMonkeyClaw work orders (alternative to `python3 ~/codemonkeyclaw/run.py submit`)

**Codebase Intelligence (Repowise MCP)**
- Already configured in this repo's CLAUDE.md
- `get_overview()` — first call on any task
- `get_context(targets=[...])` — before reading/editing files
- `get_risk(targets=[...])` — before changing hotspot files
- `search_codebase(query=...)` — prefer over grep/find
- `get_why(query=...)` — before architectural changes
- `update_decision_records(action=...)` — after every coding task

**Memory (ByteRover)**
- Persistent memory that survives session boundaries
- Use for: storing agent state, cross-session context, decision history
- Complements Repowise decision records (ByteRover = runtime state, Repowise = architectural decisions)

**Security & Shipping**
- `/review` before any merge
- `/ship` for full deploy workflow (merge, tests, version bump, changelog, PR)
- `/cso` for infrastructure audits on the OpenClaw codebase itself

---

## Sub-Agent Skill Mapping

### ArbClaw (~/arbclaw/) — Trading Arbitrage

Primary skills:
- `/alphaear-news` — real-time financial news and trends
- `/alphaear-sentiment` — score signals with FinBERT/LLM
- `/alphaear-predictor` — time-series forecasting
- `/alphaear-signal-tracker` — monitor signal evolution
- `/alphaear-stock` — ticker lookup, price history
- `/browser` + `/cookie-sync` — authenticated trading platform access

Workflow: `/alphaear-news` -> `/alphaear-sentiment` -> `/alphaear-predictor` -> execute or pass to Clawmpson

### PhantomClaw — Stealth Operations

Primary skills:
- `/osint` — intelligence gathering
- `/browser` + `/cookie-sync` — authenticated web automation
- `/opencli-rs` — platform-specific interactions (55+ sites)
- `/last30days` — recent activity monitoring

### QuantumentalClaw (~/quantumentalclaw/) — Signal Fusion

Primary skills (full AlphaEar suite):
- `/alphaear-news` + `/alphaear-sentiment` + `/alphaear-predictor` — signal generation
- `/alphaear-deepear-lite` — DeepEar dashboard signals
- `/alphaear-logic-visualizer` — transmission chain diagrams
- `/alphaear-reporter` — structured output for decision-making
- `/alphaear-signal-tracker` — track conviction over time

### RivalClaw (~/rivalclaw/) — Focused Arb Execution

Lean skill set:
- `/alphaear-news` + `/alphaear-sentiment` — signal intake
- `/alphaear-predictor` — quick forecasts
- `/browser` — execution interface
- `/search` + `/fetch` — lightweight data retrieval

### CodeMonkeyClaw (~/codemonkeyclaw/) — Engineering

Receives work orders, dispatches to open models (Qwen/DeepSeek):
- `/review` — review incoming branches before delivery
- `/sast-analysis` + SAST scanners — security check deliverables
- `/expect` — verify UI work
- `/qa` — test before handoff

---

## Architecture: How /acpx Connects

```
Clawmpson (orchestrator)
  |-- /acpx prompt --> ArbClaw (arb signals)
  |-- /acpx prompt --> PhantomClaw (stealth ops)
  |-- /acpx prompt --> CodeMonkeyClaw (engineering work orders)
  |
  |-- collects results via /acpx sessions
  |-- stores state in ByteRover
  |-- records decisions in Repowise
```

Use `/acpx` when:
- Work can be delegated to a specialized sub-agent
- You need parallel execution across agents
- A task matches a sub-agent's specialty (arb, stealth, engineering)
- You need to queue work for later execution

---

## Quick Decision Guide

| Need to... | Use |
|------------|-----|
| Research a topic | `/last30days` or `/search` |
| Get financial signals | `/alphaear-news` -> `/alphaear-sentiment` |
| Dispatch to sub-agent | `/acpx` |
| Understand this codebase | Repowise `get_overview()` + `get_context()` |
| Ship a change | `/review` -> `/ship` |
| Security check | `/cso` or `/sast-analysis` pipeline |
| Remember across sessions | ByteRover |
| Automate web tasks | `/cookie-sync` -> `/browser` |
| Generate reports | `/alphaear-reporter` or `/notebooklm` |
| Manage daily work | `/daily-task-prep` + `/daily-task-manager` |
