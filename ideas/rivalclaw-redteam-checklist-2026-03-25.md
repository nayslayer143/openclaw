# RivalClaw Red-Team Review Checklist + Autonomy Roadmap

**Date:** 2026-03-25
**Source:** Chad (ChatGPT) — hardening path from self-tuner to autonomous self-learning stack
**Status:** Reference document. Run this checklist before/during/after the 30-day RivalClaw vs Clawmpson test.
**Applies to:** RivalClaw v1 (primary), extensible to Clawmpson and ArbClaw later.

---

## When to Run This Checklist

- Before the 30-day RivalClaw vs Clawmpson test
- Weekly during the test
- Whenever a new strategy variant is promoted
- After any major drawdown, crash, or abnormal behavior

For each item: PASS / PARTIAL / FAIL / UNKNOWN
If UNKNOWN → treat as risk, not neutral.

---

## 1. North Star / Objective Alignment

### 1.1 Canonical objective
- Is there ONE clearly defined top-level objective for the whole system?
- Is it portfolio-level, net of costs, not just trade-level gross PnL?
- Is every layer optimizing toward the same north star?

**Red flag:** tuner optimizes edge capture, risk engine optimizes recent PnL, lab optimizes Sharpe, governor optimizes win rate — nobody optimizes the same actual objective.

### 1.2 Secondary objectives
- Are drawdown, robustness, calibration, and capital efficiency explicitly defined as constraints?

### 1.3 Complexity penalty
- Does the system penalize more complex variants unless they clearly outperform simpler ones?
- Can a simpler baseline beat a more complex candidate by default if performance is similar?

---

## 2. Data Integrity

### 2.1 Logging completeness
For every trade or abstention, do we have: timestamp, market ID, strategy ID/version, feature snapshot, signal/confidence, threshold state, risk decision, sizing decision, order/fill result, outcome, reason for abstention?

### 2.2 Data correctness
- Are spot prices timestamp-aligned with market snapshot at decision time?
- Are all backtests using only information available at that moment?

### 2.3 Missing data behavior
- Does the system fail safe when data is missing?
- Does it abstain rather than silently infer?

### 2.4 Version traceability
- Can every live trade be tied to an exact code/config/strategy version?
- Can every experiment be reproduced?

---

## 3. Self-Tuner Red Team

### 3.1 Volatility tuning — stable window, outlier handling, no single-asset poisoning
### 3.2 Edge capture rate — sufficient sample size, cost-inclusive, fill-realistic
### 3.3 Slippage calibration — observed spread vs realized slippage correlation, conservative sim
### 3.4 Tuner rollback — fast enough, no oscillation cycles, memory of failed changes
### 3.5 Tuner boundaries — strict clamps, no indirect stacking of small changes into large behavior shifts

---

## 4. Risk Engine Red Team

### 4.1 Regime detector validity — labels actually predictive, stable across assets
### 4.2 Tournament robustness — blended scoring (recent trades + time window + regime + confidence)
### 4.3 Risk concentration — correlation-based, not just asset labels; event clustering awareness
### 4.4 Live containment — risk engine always vetoes brain, logged, kill switch proven
### 4.5 Abstention visibility — every blocked trade has explicit reason code

---

## 5. Strategy Lab Red Team

### 5.1 Diagnosis quality — distinguish: variance, drift, data artifact, fill deterioration, structural decay, bug
### 5.2 Missed opportunity realism — filter by executable entry conditions, distinguish true miss from hindsight fantasy
### 5.3 Confidence calibration — consistent definition across all strategies
### 5.4 Mutation discipline — bounded, small batch, each tied to specific diagnosis
### 5.5 Duplicate failure prevention — memory blocks repeated bad ideas, machine-readable lessons
### 5.6 Research honesty — can return INCONCLUSIVE, no pressure to produce winners

---

## 6. Backtest / Evaluation Red Team

### 6.1 Leakage audit — no lookahead in features, prices, outcomes, regime labels
### 6.2 Fill realism — conservative fills, latency + spread widening in volatile moments
### 6.3 Cost realism — fees + slippage + execution losses everywhere, same doctrine for baseline and candidate
### 6.4 Walk-forward rigor — truly out-of-sample, multiple rolling windows, stable results
### 6.5 Robustness checks — worse slippage, worse latency, different thresholds, multiple assets/regimes, remove best trade/day
### 6.6 Sample size honesty — skeptical of low-trade candidates, confidence intervals used

---

## 7. Promotion Governor Red Team

### 7.1 All gates mandatory, no override path, no emergency promotions
### 7.2 Baseline evaluated over same window/conditions (apples-to-apples)
### 7.3 Outlier dependence — still positive after removing best trade and best day
### 7.4 Probation sizing truly smaller, demotion automatic, rollback immediate
### 7.5 Promotion memory — store exactly why promoted, compare expected vs actual if it later fails

---

## 8. Memory System Red Team

### 8.1 Lesson quality — mutation, parent, window, result, failure reason, applicable regimes, revisit conditions
### 8.2 Retrieval quality — reliably finds relevant past failures before proposing new changes
### 8.3 Contradiction handling — lessons conditional by regime, not absolute
### 8.4 Forgetting/pruning — stale memory archived without loss, distinguish obsolete from relevant

---

## 9. Autonomy Readiness

### 9.1 System knows what it CAN change (params, thresholds, filters, regime splits, abstain logic, versions)
### 9.2 System knows what it CANNOT change (global risk caps, kill switches, wallet permissions, safety logic, deployment rules)
### 9.3 Graceful degradation — if LLM fails/hallucinates, lab halts safely, production continues
### 9.4 Auditability — human can reconstruct what changed and why
### 9.5 Hard boundary between research autonomy and capital autonomy

---

## 10. Portfolio-Level Red Team

### 10.1 Strategies evaluated in combination, not just individually
### 10.2 Correlation measured, correlated failures identified
### 10.3 Capacity constraints — more signals can worsen total quality
### 10.4 Capital efficiency — learning WHERE capital is best deployed

---

## 11. Named Failure Modes to Hunt

1. **Overfit improver** — looks better in backtest, worse in live shadow
2. **Threshold death spiral** — losses → higher thresholds → fewer trades → noisier conclusions → worse tuning
3. **False missed-opportunity greed** — overlearns from unrealistically tradable big moves
4. **Zombie strategy polishing** — keeps adjusting a structurally dead strategy
5. **Lucky child promotion** — promoted on 1-2 exceptional wins
6. **Silent data poisoning** — stale/misaligned data alters conclusions
7. **Strategy starvation** — tournament suppresses viable strategies before enough evidence
8. **Memory amnesia** — forgets why a bad idea failed, retries it
9. **Complexity creep** — accumulates similar variants until registry is unmanageable
10. **Objective drift** — layers optimize different hidden objectives, system gets worse while local metrics improve

---

## 12. Required Tests Before Trusting Autonomy

1. **Replay test** — same inputs → same outputs → same decisions → same conclusions
2. **Shadow honesty test** — was shadow edge actually tradable?
3. **Counterfactual abstention test** — would relaxed filters truly improve expectancy after costs?
4. **Strategy starvation test** — risk engine unfairly suppressing strategies?
5. **Promotion audit test** — reconstruct full promotion case for last promoted candidate
6. **Rollback drill** — force rollback, verify parent restored, incident logged, production continues
7. **LLM junk-output drill** — inject malformed hypothesis, verify lab rejects safely

---

## 13. Maturity Levels

| Level | Name | Description |
|-------|------|-------------|
| 0 | Static bot | No adaptation |
| 1 | Self-tuning | Adjusts parameters within fixed logic |
| 2 | Risk-adaptive | Reallocates capital based on live conditions |
| 3 | Bounded self-improving | Creates/tests bounded variants with memory + governance |
| 4 | Autonomous research organism | Continuous diagnose→hypothesize→evaluate→shadow→promote/demote with audit trails |
| 5 | Autonomous portfolio scientist | Learns better portfolio construction, regime specialization, capital routing, retirement across families |

**RivalClaw current:** entering Level 3
**Next target:** disciplined Level 4

---

## 14. Go/No-Go Questions (before increasing autonomy)

- Can we explain why the last 3 promoted variants were promoted?
- Can we explain why the last 3 rejected variants were rejected?
- Can we reproduce the last 3 experiment results?
- Can we prove backtest/live assumptions are aligned?
- Can we distinguish temporary drift from structural alpha death?
- Can we show memory prevents repeated bad ideas?
- Can we force rollback safely right now?
- Can the lab fail without harming production?
- Do all layers optimize the same ultimate objective?
- Are we getting better learning quality, not just more activity?

If any answer is no/partial/unknown → expand autonomy carefully.

---

## 15. Next-Step Mandates (for Strategy Lab build)

1. **Canonical scoring doctrine** — one portfolio-level objective shared by tuner, risk, lab, governor
2. **Reason-for-abstention logging** — every no-trade classified
3. **Regime-conditional scorecards** — per-strategy per-regime performance memory
4. **Structural-decay detector** — distinguish parameter drift from dead-edge decay
5. **Experiment ledger** — every mutation, test, result, promotion, demotion, rollback reconstructable
6. **Autonomy boundary enforcement** — research autonomy first, capital autonomy last
7. **Weekly cemetery review** — review degraded/retired variants, identify recurring causes of death

---

## Core Standard

> RivalClaw is autonomous when it can safely observe, diagnose, mutate, test, promote, demote, and remember without requiring human judgment on normal cycles.

> Autonomy is earned by reliability, not by mutation volume.
