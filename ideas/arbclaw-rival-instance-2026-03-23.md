# ArbClaw Rival Instance — Assessment & Recommendation

**Date:** 2026-03-23
**Source:** Chad (ChatGPT) proposed hub-and-spoke rival instance for arb-only trading
**Status:** Approved for scoping — run as 14-day validation experiment on same machine
**Revisit:** After Clawmpson graduation gates pass, or if paper trading reveals execution lag

---

## What Chad Proposed

A second, fully isolated OpenClaw instance ("ArbClaw") focused purely on arbitrage:
- Separate repo, DB, state — no shared code with Clawmpson
- Hub-and-spoke model with comparison contract
- One strategy (pure cross-outcome arb), no LLM/momentum/OSINT
- Own CLAUDE.md, own agent configs, own scaffold (~20 files)

---

## Initial Assessment (v1)

### Pros
- **Isolation is sound.** Can't corrupt Clawmpson's working pipeline while experimenting.
- **Empirical comparison.** Turns strategy debates into testable questions.
- **A/B testing framework.** If ArbClaw outperforms on cross-venue, that's actionable signal.
- **Narrow scope is disciplined.** Avoids second-system effect.

### Cons
- **Operational overhead.** Two sets of feeds, DBs, crons, repos = double debugging surface for one person.
- **Timing premature.** Clawmpson hasn't graduated to live trading yet.
- **Duplicates v4.2 roadmap.** Cross-venue arb already specced in Phase 5A-5C within Clawmpson.
- **Scaffold is boilerplate.** ~20 files of structure without logic — doesn't save the real work.
- **Comparison contract requires synchronized feeds.** Non-trivial engineering for fair comparison.

### Original Recommendation
Don't build ArbClaw. Instead: add pure-arb as 5th strategy in MiroFish brain, use shadow_mode for comparison, save ArbClaw design for post-graduation.

---

## Revised Assessment (v2) — Jordan's Concern: Clawmpson Is Over-Engineered for Speed

Jordan raised a legitimate concern: Clawmpson has 61 Python files, 5 feeds, 4 strategies, a graduation engine, 13 agent configs, and a 30-minute cron cycle. For prediction market arb where windows close in minutes, that's a lot of machinery between "signal detected" and "trade executed."

### The Real Question
Not "which system has better strategies" — but **does Clawmpson's complexity cost us arb alpha through execution lag?** That's testable.

### Revised Recommendation: Build It, But Lean and Time-Boxed

**Build ArbClaw as a validation experiment, not a permanent rival.**

**Scope:**
- One feed (Polymarket — Kalshi isn't wired yet anyway)
- One strategy (pure cross-outcome arb)
- One wallet (SQLite, minimal)
- One cron (5-minute cycle, not 30)
- No LLM analysis, no momentum, no OSINT, no graduation engine
- Must run on minimal resources (target: <200MB RAM)

**Run on same machine, not VPS.** Reasons:
- ArbClaw without LLM inference is a lightweight Python process — M2 Max won't notice it
- VPS adds network latency to API calls, contaminating the execution-speed measurement
- Both systems must hit the same APIs from the same network for a fair comparison
- Isolation is trivial: separate directory (`~/arbclaw/`), separate SQLite DB, separate cron, separate venv
- Save the $20/month — a VPS only makes sense post-graduation for geographic redundancy or latency-sensitive live trading

**Time-box: 14 days of paper trading.** Compare:
- Signal-to-trade latency (the core question)
- Win rate on same markets
- Edge capture rate (realized vs expected PnL)

**Resolution:**
- If ArbClaw consistently captures more edge → Clawmpson needs a fast-path execution mode, not a second system
- If Clawmpson wins anyway → architecture validated, kill ArbClaw with confidence
- Either outcome is actionable

**From Chad's proposal, keep:**
- Repo structure concept (but start with 3 files, not 20: feed, strategy, wallet)
- Comparison contract idea
- CLAUDE.md isolation principle

**From Chad's proposal, skip:**
- Full scaffold boilerplate (add complexity only when simple version proves edge)
- Separate agent configs (overkill for a 3-file system)
- Hub-and-spoke orchestration layer (just run both and compare results manually or with a simple diff script)

---

## Integration Path

1. Create `~/arbclaw/` with 3 files: `feed.py`, `arb_strategy.py`, `wallet.py`
2. 5-minute cron: fetch Polymarket outcomes → detect mispricing → Kelly size → paper trade
3. After 14 days: compare metrics against Clawmpson's arb performance on same markets
4. Decision: fast-path mode for Clawmpson, or validate current architecture, or hybrid

---

## Relationship to Other Parked Ideas

- **Moltbook Alpha Engine** (parked 2026-03-23): Distribution channel, revisit when trading is live
- **ArbClaw** (this file): Execution speed validation, build when ready to test hypothesis
- Both feed into the same question: is Clawmpson's architecture right-sized for its job?
