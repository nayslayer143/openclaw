# GitHub Coding Agent — OpenClaw Integration Strategy

**Date:** 2026-03-24
**Purpose:** How to use GitHub's coding agent (Copilot, Claude, Codex) in the OpenClaw workflow, and how to pair it with the repo intelligence crawler for maximum leverage.

---

## What GitHub Coding Agents Actually Do

GitHub coding agents (Copilot, Claude via @claude, Codex) work asynchronously within the pull request workflow. You assign an issue to the agent, and it autonomously creates a branch, writes commits, runs tests, and opens a draft PR. You review, comment to iterate, and merge when satisfied.

The key insight: these agents are best at well-scoped, medium-complexity tasks in codebases with good test coverage and clear structure. They struggle with vague requirements, architectural decisions, and tasks requiring deep domain context.

---

## How This Fits OpenClaw's Workflow

OpenClaw already has a task pipeline: `repo-queue/ → build-results/ → memory/`. GitHub coding agents slot in as an execution layer between queue and results.

**Current flow:**
Issue → Jordan triages → Claude Code builds → PR → review → merge

**Enhanced flow:**
Issue → Jordan triages → routes to agent (Copilot / Claude / Claude Code) based on complexity → PR → review → merge

**Routing heuristic:**
- Tier 1 (auto-assign to GitHub agent): test generation, refactors, documentation, boilerplate, dependency bumps, lint fixes
- Tier 2 (Claude Code): feature implementation, bug fixes requiring context, multi-file changes, integration work
- Tier 3 (Jordan + Claude Code): architecture decisions, new systems, strategy logic, anything touching live trading

---

## High-Leverage Use Cases for Trading Bot Stack

### 1. Backtest Scaffolding
Write an issue like: "Create a backtesting harness for the momentum strategy in `scripts/mirofish/trading_brain.py`. Use the existing paper_wallet.py patterns. Include fixtures for 30-day Polymarket data from clawmson.db. Output: win rate, Sharpe, max drawdown, edge capture rate."

The agent builds the entire harness. You review the logic.

### 2. Strategy Isolation & Refactoring
"Refactor `trading_brain.py` to extract each strategy (arb, price-lag, momentum, LLM) into separate modules under `scripts/mirofish/strategies/`. Each module should implement a `Strategy` protocol with `analyze()` and `size()` methods. Keep the brain as the orchestrator. Preserve all existing tests."

Agents excel at this — it's mechanical, testable, and well-defined.

### 3. Test Coverage Expansion
"Add unit tests for `unusual_whales_feed.py` covering: API timeout handling, malformed response parsing, rate limit backoff, and signal deduplication. Use pytest. Mock all HTTP calls."

The existing 9 test files give the agent clear patterns to follow.

### 4. Repo Integration (Crawler → Agent Pipeline)
This is where the crawler and the agent work together:
1. Crawler surfaces a high-signal repo (e.g., `nkaz001/hftbacktest` — Rust HFT backtester, 3.8k stars)
2. You study it manually, decide the integration is worth doing
3. Write an issue: "Create a Python wrapper for hftbacktest's L2 orderbook simulation. Expose a `simulate_execution(order, book_state) → fill_result` interface compatible with our `paper_wallet.py` trade execution. Add to `scripts/mirofish/execution_sim.py`."
4. Assign to GitHub agent
5. Review the PR, iterate via comments

### 5. Data Pipeline Extensions
"Add a new feed module `scripts/mirofish/kalshi_feed.py` following the `base_feed.py` DataFeed protocol. Implement: `fetch_markets()`, `fetch_orderbook(market_id)`, `get_cached(market_id)`. Use Kalshi REST v2 API (demo mode). Store in clawmson.db `kalshi_markets` table. Reference `polymarket_feed.py` for patterns."

### 6. Monitoring & Observability
"Add structured logging to `simulator.py` using Python's logging module. Log: strategy name, signal count, trade count, latency_ms, error count per run. Output as JSON lines to `logs/simulator-{date}.jsonl`. Add a health check endpoint to `dashboard/server.py` at `/api/health` that returns uptime, last run timestamp, and error count."

---

## Custom Agent Configuration

Create `.github/agents/quant-reviewer.md` in the openclaw repo:

```markdown
# Quant Strategy Reviewer

You are a quantitative strategy code reviewer for the OpenClaw trading system.

When reviewing PRs that touch files in scripts/mirofish/:
1. Check that all strategy changes include corresponding test updates
2. Verify Kelly criterion sizing uses the prediction market formula (not financial)
3. Ensure position limits are respected (10% max, -20% stop-loss, +50% take-profit)
4. Flag any hardcoded magic numbers that should be config parameters
5. Verify new feeds implement the base_feed.py DataFeed protocol
6. Check that paper wallet state changes are atomic (no partial updates)
7. Benchmark before/after if strategy logic changed

Always reference CONSTRAINTS.md for approval tier requirements.
```

This agent reviews every PR that touches trading code, catching issues before you see them.

---

## Crawler → Research → Agent Pipeline

The full loop:

```
1. Run crawler:  python github_crawler.py --trading-only --min-stars 300 --readmes
2. Review CSV:   sort by signal_score, filter by language (Python/Rust)
3. Triage:       feed top 10 JSON entries to Claude → "which are worth integrating vs studying?"
4. Study:        for top candidates, read README + source, assess integration complexity
5. Issue:        write a scoped GitHub issue for the integration
6. Assign:       @copilot or @claude on the issue
7. Review:       iterate via PR comments until satisfied
8. Merge:        CI runs, tests pass, merge to main
9. Log:          update memory/MEMORY.md with what was integrated and why
```

Schedule the crawler as a weekly cron (or Lobster workflow) to continuously surface new repos as the ecosystem evolves.

---

## WRAP Method for Writing Agent Issues

From GitHub's own guidance — treat it like assigning to a smart junior dev:

- **W**hat: specific acceptance criteria, not vague goals
- **R**eference: file paths, existing patterns, related code
- **A**rchitecture: where it fits, what it touches, what it must not break
- **P**rotection: what tests must pass, what constraints apply

Bad: "Add Kalshi support"
Good: "Create `scripts/mirofish/kalshi_feed.py` implementing the `DataFeed` protocol from `base_feed.py`. Use Kalshi REST v2 (demo mode, base URL demo.kalshi.co). Implement `fetch_markets()` returning list of active markets with YES/NO outcomes, `fetch_orderbook(market_id)` returning top 5 bid/ask levels. Cache results in clawmson.db `kalshi_markets` table (columns: market_id, ticker, title, yes_price, no_price, volume, fetched_at). Add pytest tests mocking HTTP responses. Reference `polymarket_feed.py` for patterns."

---

## What NOT to Use Agents For

- Architectural decisions (adding new systems, changing data flow)
- Strategy logic that requires market domain knowledge
- Anything touching live trading or real money
- Security-sensitive changes (auth, secrets, API key handling)
- Cross-repo orchestration changes
- Lobster workflow modifications (too context-dependent)

These stay with Jordan + Claude Code.

---

## Crawl Results Summary (2026-03-24)

102 unique repos surfaced. Top candidates for immediate study:

| Repo | Stars | Language | Why It Matters |
|------|-------|----------|----------------|
| hummingbot/hummingbot | 17.8k | Python | Market making + arbitrage, mature architecture |
| nkaz001/hftbacktest | 3.8k | Rust | L2 orderbook simulation, execution realism |
| edtechre/pybroker | 3.2k | Python | ML-integrated backtesting, clean API |
| kernc/backtesting.py | 8.1k | Python | Lightweight backtester, good patterns to study |
| barter-rs/barter-rs | 2.0k | Rust | Event-driven trading framework, modern design |
| Superalgos/Superalgos | 5.4k | JS | Visual strategy builder, community patterns |
| lorine93s/polymarket-market-maker-bot | 317 | Python | Polymarket-specific, directly relevant |

Full results: `autoresearch/outputs/datasets/trading_scan_20260324_0349.csv`
