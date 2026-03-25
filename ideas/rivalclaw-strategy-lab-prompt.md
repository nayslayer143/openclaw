# RivalClaw Strategy Lab — Claude Code Build Prompt

**Status:** Ready to execute. RivalClaw v1 is the target. Clawmpson is the control group.
**Hypothesis:** A self-improving trading system with bounded mutations, backtesting, and a promotion governor will outperform a manually-tuned system over 30 days.
**Copy everything below the line into Claude Code with ~/rivalclaw/ mounted.**

---

```
# RivalClaw Strategy Lab — Phased Build

Read ~/rivalclaw/CLAUDE.md before writing any code.
Read ~/rivalclaw/trading_brain.py to understand existing 8 strategies + hedge engine.
Read ~/rivalclaw/simulator.py to understand the orchestration loop.
Read ~/rivalclaw/paper_wallet.py to understand execution sim + stops.
Read ~/rivalclaw/self_tuner.py to understand existing parameter tuning.
Read ~/rivalclaw/graduation.py to understand existing graduation gates.

## What This Is

A Strategy Lab layer on top of RivalClaw v1 that turns it from a self-tuning trader into a constrained self-improving trading system. The lab studies performance, generates bounded hypotheses, backtests them, promotes validated improvements, retires degraded strategies, and maintains memory of what was tried.

Clawmpson (~/openclaw/) is the control group — it does NOT get the Strategy Lab. After 30 days we compare RivalClaw (with lab) vs Clawmpson (without) to measure whether self-improvement actually works.

This is a 4-phase build. Phases are sequential — each phase must work before the next begins.

## PHASE 1 — Structured Logging + Data Foundation

This is the gate. The Strategy Lab is blind without data. Build the logging layer first.

### 1a. Structured Event Logger: ~/rivalclaw/event_logger.py

A module that emits machine-readable JSONL records. All other RivalClaw modules will call this instead of print() or rivalclaw.log.

Output: ~/rivalclaw/logs/events.jsonl (append-only, rotate daily)

Record types to emit:

```python
# Every record has these base fields
{
    "ts": "ISO8601",
    "type": "market_snapshot|signal|decision|trade|fill|position|outcome|error|regime|abstain",
    "strategy_version": "momentum_v1.2",
    "run_id": "uuid-per-simulator-run"
}
```

Specific record schemas:

**market_snapshot** — emitted for each market evaluated
```json
{"type": "market_snapshot", "market_id": "...", "platform": "polymarket|kalshi",
 "title": "...", "yes_price": 0.65, "no_price": 0.35, "volume": 12000,
 "spread": 0.02, "time_to_resolution_hours": 18.5}
```

**signal** — emitted when a strategy produces a signal
```json
{"type": "signal", "strategy": "momentum_v1", "market_id": "...",
 "direction": "YES|NO", "confidence": 0.72, "edge_estimate": 0.08,
 "features": {"price_velocity": 0.03, "volume_spike": true}}
```

**decision** — emitted for every entry/exit/abstain decision
```json
{"type": "decision", "action": "enter|exit|abstain|skip",
 "strategy": "...", "market_id": "...", "reason": "confidence below threshold",
 "confidence": 0.72, "threshold": 0.65, "size_proposed": 50.0}
```

**trade** — emitted when paper wallet executes
```json
{"type": "trade", "trade_id": "...", "market_id": "...", "strategy": "...",
 "direction": "YES", "size": 50.0, "price": 0.65, "fees": 0.50,
 "latency_ms": 1200, "slippage_estimate": 0.005}
```

**outcome** — emitted when a trade resolves
```json
{"type": "outcome", "trade_id": "...", "pnl_gross": 12.50, "pnl_net": 11.80,
 "fees_paid": 0.70, "hold_duration_hours": 4.2, "resolved_price": 1.0,
 "entry_price": 0.65, "was_correct": true}
```

**error** — any exception or unexpected behavior
```json
{"type": "error", "module": "polymarket_feed", "error": "timeout",
 "message": "...", "severity": "warn|error|critical"}
```

**regime** — periodic regime classification
```json
{"type": "regime", "label": "high_vol|low_vol|trending|mean_revert|unknown",
 "confidence": 0.8, "features": {"spread_avg": 0.04, "volume_trend": "rising"}}
```

### 1b. Wire logging into existing modules

Modify these files to call event_logger instead of (or in addition to) existing logging:
- simulator.py — emit run_id at start/end, market_snapshots per cycle
- trading_brain.py — emit signal + decision for every strategy evaluation
- paper_wallet.py — emit trade + outcome for every execution/resolution
- polymarket_feed.py — emit errors on API failures
- kalshi_feed.py — emit errors on API failures
- spot_feed.py — emit errors on API failures

Do NOT remove existing logging to rivalclaw.log — add structured logging alongside it.

### 1c. Strategy Version Registry: ~/rivalclaw/strategy_registry.json

Track every strategy version:
```json
{
  "strategies": [
    {
      "id": "momentum_v1.0",
      "family": "momentum",
      "version": "1.0",
      "status": "production",
      "params": {"threshold": 0.65, "max_hold_hours": 24, "size_pct": 0.05},
      "created_at": "2026-03-25",
      "promoted_at": "2026-03-25",
      "baseline_metrics": null,
      "notes": "initial production version"
    }
  ]
}
```

Register all 8 existing strategies as v1.0 production baselines.

### 1d. Experiment Ledger: ~/rivalclaw/experiments/ledger.json

Empty ledger, ready for Phase 2:
```json
{
  "experiments": []
}
```

**Phase 1 line budget:** event_logger.py (120 lines), wiring changes across existing files (80 lines total), registry + ledger (JSON files). Under 200 lines of new Python.

**Phase 1 test:** Run one full simulator cycle. Verify events.jsonl contains at least: 1 market_snapshot, 1 signal, 1 decision per strategy, trades if any triggered. Verify strategy_registry.json has all 8 strategies.

---

## PHASE 2 — Research Runner + Backtester

Build the lab's analytical engine. This runs on a separate cadence from the live trader (4x/day, not every 30 min).

### 2a. Diagnostician: ~/rivalclaw/strategy_lab/diagnose.py

Reads events.jsonl and produces a diagnostic report:
- Per-strategy: win rate, avg PnL, Sharpe, max drawdown, trade count, abstain rate
- Regime breakdown: performance per regime label
- Drift detection: is any strategy's recent 7-day performance significantly worse than its 30-day?
- Missed opportunities: markets where no strategy traded but price moved >20%
- False positives: trades that lost money — cluster by strategy + market type
- Signal decay: is confidence score correlated with actual outcome? (calibration check)

Output: ~/rivalclaw/strategy_lab/reports/diagnostic-{date}.json

### 2b. Hypothesis Generator: ~/rivalclaw/strategy_lab/hypothesize.py

Reads the diagnostic report and generates 3-5 bounded hypotheses per cycle.

Every hypothesis follows this format:
```json
{
  "id": "hyp-20260325-001",
  "observation": "momentum_v1 loses money on markets resolving in <6 hours",
  "proposed_change": "add min_resolution_hours=6 filter to momentum strategy",
  "mutation_type": "filter_addition",
  "parent_version": "momentum_v1.0",
  "candidate_version": "momentum_v1.1",
  "expected_benefit": "eliminate short-resolution losses (~$12/day)",
  "overfit_risk": "low — structural filter, not curve-fitted threshold",
  "evaluation_plan": "14-day backtest on historical events.jsonl"
}
```

Mutation types allowed in v1 (bounded genome):
- threshold_adjust: change a numeric threshold (entry confidence, size %, hold time)
- filter_addition: add a market filter (min resolution time, min liquidity, category block)
- filter_removal: remove a filter that may be too restrictive
- param_tune: adjust strategy parameters within ±20% of current value
- regime_split: split one strategy into two regime-specific variants
- abstain_rule: add a condition where the strategy should NOT trade

Mutation types NOT allowed in v1:
- full_rewrite: rewriting strategy logic from scratch
- new_strategy: creating entirely new strategy families
- risk_override: changing global risk limits (stop-loss, max position, Kelly cap)
- multi_model: adding ML model ensembles

Use Ollama (qwen3:30b) to generate hypotheses from the diagnostic data. Parse response as JSON. If LLM output is malformed, retry once, then skip.

### 2c. Backtester: ~/rivalclaw/strategy_lab/backtest.py

Takes a hypothesis + candidate parameters and replays historical events.jsonl data.

Requirements:
- Read events.jsonl for the specified data window (default: last 14 days)
- Apply candidate strategy parameters to each market_snapshot
- Simulate decisions and trades using paper_wallet rules (fees, slippage, position limits)
- Compare candidate vs baseline (parent version) on same data
- Output: backtest results JSON

```json
{
  "experiment_id": "exp-20260325-001",
  "hypothesis_id": "hyp-20260325-001",
  "candidate": "momentum_v1.1",
  "baseline": "momentum_v1.0",
  "data_window": "2026-03-11 to 2026-03-25",
  "trade_count_candidate": 42,
  "trade_count_baseline": 58,
  "pnl_candidate": 38.50,
  "pnl_baseline": 22.10,
  "win_rate_candidate": 0.62,
  "win_rate_baseline": 0.55,
  "sharpe_candidate": 1.4,
  "sharpe_baseline": 0.9,
  "max_dd_candidate": -8.2,
  "max_dd_baseline": -14.5,
  "verdict": "PROMISING|INCONCLUSIVE|REJECTED",
  "notes": "..."
}
```

Verdict rules:
- PROMISING: candidate beats baseline on net PnL, Sharpe, AND max drawdown with >20 trades
- INCONCLUSIVE: mixed results or <20 trades in window
- REJECTED: candidate worse than baseline on 2+ key metrics

### 2d. Research Runner: ~/rivalclaw/strategy_lab/run_cycle.py

Orchestrates one research cycle: diagnose → hypothesize → backtest → report.

CLI:
```
python strategy_lab/run_cycle.py                    # full cycle
python strategy_lab/run_cycle.py --diagnose-only     # just diagnostic
python strategy_lab/run_cycle.py --hypothesis hyp-id  # backtest specific hypothesis
```

Output: ~/rivalclaw/strategy_lab/reports/cycle-{date}-{time}.json

**Phase 2 line budget:** diagnose.py (150 lines), hypothesize.py (120 lines), backtest.py (180 lines), run_cycle.py (80 lines). Under 530 lines total.

**Phase 2 test:** Run a full research cycle. Verify diagnostic report identifies at least one finding. Verify at least one hypothesis is generated. Verify backtest produces results with a verdict.

---

## PHASE 3 — Shadow Mode + Promotion Governor

### 3a. Shadow Runner: modify ~/rivalclaw/simulator.py

Add shadow mode: candidate strategies run alongside production but don't affect the paper wallet.

- Shadow strategies read the same market data
- Shadow strategies generate signals and simulated decisions
- Shadow results are logged to events.jsonl with {"shadow": true}
- Shadow trades are tracked in a separate shadow_wallet (in-memory, not persisted to DB)
- After 14 days of shadow data, the candidate can be evaluated for promotion

### 3b. Promotion Governor: ~/rivalclaw/strategy_lab/governor.py

Decides whether a shadow-tested candidate can move to production.

Strategy states:
```
draft → simulated → shadow_live → probationary → production → degraded → retired
```

Promotion rules (ALL must pass):
- Shadow net PnL > baseline net PnL over 14 days
- Shadow Sharpe > baseline Sharpe
- Shadow max drawdown < baseline max drawdown (or within 5%)
- Shadow win rate > 50%
- At least 30 shadow trades
- No single trade accounts for >40% of total PnL (not one lucky outlier)
- Robustness: remove best trade, still profitable

Demotion rules (ANY triggers review):
- 7-day rolling PnL turns negative
- Drawdown exceeds 25% of allocated capital
- Win rate drops below 45% over 30+ trades
- 3+ consecutive losses exceeding stop-loss

Governor writes state changes to strategy_registry.json and logs them to events.jsonl.

### 3c. Memory Store: ~/rivalclaw/strategy_lab/memory.json

Append-only memory of what was tried:
```json
{
  "lessons": [
    {
      "date": "2026-03-25",
      "experiment_id": "exp-001",
      "strategy_family": "momentum",
      "mutation": "lower confidence threshold from 0.65 to 0.55",
      "outcome": "REJECTED — increased trade count but reduced win rate, net negative",
      "lesson": "momentum strategy requires high confidence; lowering threshold adds noise",
      "do_not_repeat_unless": "regime changes to strongly trending markets"
    }
  ]
}
```

Before generating new hypotheses, hypothesize.py must read memory.json and avoid repeating known failures.

**Phase 3 line budget:** shadow mode additions to simulator.py (60 lines), governor.py (150 lines), memory.json (structure). Under 210 lines new Python.

**Phase 3 test:** Start a shadow candidate alongside production. Run for 3+ cycles. Verify shadow trades appear in events.jsonl with shadow flag. Verify governor can evaluate and produce a verdict.

---

## PHASE 4 — Auto-Promotion with Hard Rollback

### 4a. Auto-Promote: extend governor.py

If a candidate passes ALL promotion rules AND has been in shadow for 14+ days:
- Governor auto-promotes to probationary status
- Probationary: trades with real paper wallet but at 50% normal size
- After 7 more days passing, promote to full production
- Log the promotion to memory.json

### 4b. Auto-Rollback: extend governor.py

If a probationary strategy triggers ANY demotion rule:
- Immediately revert to parent version
- Log the rollback with full context
- Mark candidate as "rolled_back" in ledger
- Add lesson to memory.json

### 4c. Daily Report: ~/rivalclaw/strategy_lab/daily_report.py

Generates the Strategy Lab Report (format from the CLAUDE.md spec):
1. System Health — active/shadow/degraded/retired counts
2. Key Findings — top positive, top negative, regime observations
3. Candidate Hypotheses — active experiments
4. Evaluation Results — backtest summaries
5. Promotions/Demotions — state changes
6. Memory Updates — new lessons
7. Next Actions — what to test next

Output: ~/rivalclaw/daily/strategy-lab-{date}.md (alongside existing daily reports)

### 4d. Cron Integration

Add Strategy Lab cadence to existing cron or daily-update.sh:
- Every 6 hours: run_cycle.py (diagnose → hypothesize → backtest)
- Daily: daily_report.py
- Shadow candidates run every simulator cycle automatically

**Phase 4 line budget:** auto-promote/rollback (60 lines added to governor.py), daily_report.py (100 lines). Under 160 lines.

**Phase 4 test:** Manually create a candidate that clearly beats baseline. Verify auto-promotion through shadow → probationary → production. Then create one that clearly fails. Verify auto-rollback fires and memory captures the lesson.

---

## Total Line Budget

| Component | Lines |
|-----------|-------|
| Phase 1: event_logger + wiring + registry | 200 |
| Phase 2: diagnose + hypothesize + backtest + runner | 530 |
| Phase 3: shadow mode + governor + memory | 210 |
| Phase 4: auto-promote/rollback + daily report | 160 |
| **Total** | **~1100 lines** |

## What NOT To Do
- Do NOT rewrite trading_brain.py — extend it with logging hooks and shadow mode
- Do NOT change paper_wallet.py's core execution logic — add event_logger calls only
- Do NOT modify graduation.py — the Strategy Lab is separate from graduation gates
- Do NOT allow the lab to change global risk parameters (stop-loss, max position, Kelly cap)
- Do NOT generate more than 10 candidates per research cycle
- Do NOT skip the shadow phase — every candidate must shadow before production
- Do NOT use external APIs for hypothesis generation — Ollama only (qwen3:30b, localhost:11434)
- Do NOT create a separate database — use JSONL files and JSON stores

## File Structure After Build

```
~/rivalclaw/
├── (existing files unchanged)
├── event_logger.py              ← Phase 1: structured JSONL logger
├── strategy_registry.json       ← Phase 1: version tracking for all 8 strategies
├── logs/
│   └── events.jsonl             ← Phase 1: append-only structured event log
├── experiments/
│   └── ledger.json              ← Phase 1: experiment tracking
├── strategy_lab/
│   ├── diagnose.py              ← Phase 2: performance diagnostics
│   ├── hypothesize.py           ← Phase 2: bounded hypothesis generation
│   ├── backtest.py              ← Phase 2: historical replay evaluator
│   ├── run_cycle.py             ← Phase 2: research cycle orchestrator
│   ├── governor.py              ← Phase 3: promotion/demotion/rollback
│   ├── memory.json              ← Phase 3: append-only lessons learned
│   ├── daily_report.py          ← Phase 4: daily strategy lab report
│   └── reports/                 ← diagnostic + cycle reports
└── daily/
    └── strategy-lab-{date}.md   ← Phase 4: daily report output
```
```
