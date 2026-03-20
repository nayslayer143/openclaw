# Role-Specialist Bakeoff Matrix v2
## OpenClaw Agent Stack — Updated with v4.2 Model Layer
> March 19, 2026 · Supersedes bakeoff-role-specialist-matrix-2026-03-19.md
> Status: QUEUED — run after Phase 0 baseline bakeoff completes
> Key change from v1: new model lineup, MoE ban lifted for agent-optimised models,
> money-adjacent workflow tasks added, supervision burden added to scoring

---

## Pre-Bakeoff Checklist

Run these before touching any scoring table.

```bash
# 1. Pull all challenger models
ollama pull qwen3-coder-next      # ~52GB — primary coder
ollama pull devstral-small-2      # ~16GB — coding challenger
ollama pull qwen3:30b             # ~20GB — orchestrator/research
ollama pull glm5                  # ~45GB — business/document
ollama pull glm4.7-flash          # ~19GB — ops/triage replacement
ollama pull llama3.3:70b          # ~42GB — synthesis upgrade
ollama pull qwen3-vl:32b          # ~20GB — vision lane (Phase 3)

# 2. Confirm each loads cleanly (one at a time — do NOT load all simultaneously)
ollama run qwen3-coder-next "respond with: loaded ok" && ollama stop qwen3-coder-next
ollama run glm4.7-flash "respond with: loaded ok" && ollama stop glm4.7-flash
# repeat for each model

# 3. Log VRAM at peak load for each
# Note: watch Activity Monitor → Memory while model is warm
```

---

## Model Map (who's being tested in what role)

| Role | Baseline | Primary challenger | Secondary challenger |
|------|----------|-------------------|---------------------|
| Coding/Build | `qwen3:32b` | `qwen3-coder-next` | `devstral-small-2` |
| Research/Planning | `qwen3:32b` | `qwen3:30b` | `glm-5` |
| Ops/Triage | `glm4:7b-flash` | `glm-4.7-flash` | `qwen3:30b` |
| Business/Document | `qwen3:32b` | `glm-5` | `qwen3:30b` |
| Memory/Synthesis | `llama3.1:70b` | `llama3.3:70b` | `glm-5` |
| Vision (new lane) | none | `qwen3-vl:32b` | — |

MiniMax M2.5 and Kimi K2.5 remain on the watch list.
Confirm local quantized availability before adding to any session.

---

## Universal Scoring Dimensions

Apply these to every task in every role. Log per-task, then average per model.

| Dimension | How to measure | Target | Hard fail |
|-----------|---------------|--------|-----------|
| Completion | Did task finish without abort? | Yes | No = fail |
| Retries | Re-prompts or corrections needed | 0–1 | >3 = fail |
| Tool-call format errors | Malformed tool calls | 0 | Any = disqualify for that role |
| Time to first useful output | Prompt sent → first substantive output | <3 min | >10 min = fail |
| Time to final artifact | Prompt sent → usable deliverable | Role targets below | >2× target = fail |
| Supervision burden | Times you had to intervene mid-task | 0–1 | >3 = fail |
| Output usability | Send to client / deploy to staging without editing? | Yes | No = fail |
| Hallucinated actions | Invented paths, stats, API calls | 0 | Any = fail |
| VRAM at peak | GB used during session | Log only | — |

**Time targets:**

| Role | Bug fix | New feature | Triage task | Report | Log synthesis |
|------|---------|-------------|-------------|--------|---------------|
| Build | <45 min | <90 min | — | — | — |
| Research | — | — | — | <20 min | — |
| Ops | — | — | <2 min | — | — |
| Business | — | — | — | <15 min | — |
| Memory | — | — | — | — | <10 min |

---

## Role 1 — Coding / Build Agent

**Baseline:** `qwen3:32b` | **Challengers:** `qwen3-coder-next`, `devstral-small-2`

### Task C1 — 10-call tool-use chain (gate task)

Run 10 consecutive tool calls: Read → Edit → Bash → Edit → Read → Bash (×5).
**This is the hard gate.** Any format error = model disqualified from Build Agent role.
Do not proceed to C2–C4 if a model fails this.

Pass: 10/10 complete, 0 format errors.

### Task C2 — Multi-file bug fix

Provide a real GitHub-style bug report referencing 3 specific files. Ask for full
Explore → Plan → Code → Review sequence with output contract.

Pass: correct files identified, plan.md written before any edits, fix in feature branch (not main),
tests pass, output contract JSON valid, 0 format errors, rollback command present.

### Task C3 — Implement new API endpoint

Spec: authenticated POST endpoint, input validation, error handling (400/401/429), rate-limit stub.
Provide repo structure. Ask for branch implementation with tests.

Pass: auth and validation present, 3+ test cases written, no destructive commands, within time target.

### Task C4 — Refactor across 3 files

Provide 3 files using an old pattern. Ask for migration to new pattern without regressions.

Pass: all 3 files changed, no test regressions, rollback command in output contract.

### Scoring — Role 1

| Metric | qwen3-coder-next | devstral-small-2 | qwen3:32b (baseline) |
|--------|-----------------|-----------------|----------------------|
| C1 format errors | | | |
| C1 gate: PASS/FAIL | | | |
| C2 pass/fail | | | |
| C3 pass/fail | | | |
| C4 pass/fail | | | |
| Avg time to final artifact | | | |
| Avg retries | | | |
| Supervision interventions | | | |
| Output usability (Y/N) | | | |
| Peak VRAM (GB) | | | |

---

## Role 2 — Research / Planning Agent

**Baseline:** `qwen3:32b` | **Challengers:** `qwen3:30b`, `glm-5`

### Task R1 — Repo scout

Give a real GitHub URL. Ask for: relevance score (1–10) with evidence, install complexity,
integration risk, and verdict (integrate / watch / skip).

Pass: score justified with specific evidence, verdict defensible, 0 hallucinated repo features or star counts.

### Task R2 — Competitor gap analysis

Provide 3 real product descriptions. Ask for a structured feature gap analysis with
specific opportunities for Jordan's businesses.

Pass: each competitor accurately characterised, gaps specific and actionable, reasoning chain visible.

### Task R3 — Multi-turn research (5 tool calls)

Business question requiring: search → extract → cross-reference → synthesise → recommend.

Pass: tool calls scoped to what each step needs, no context bleed between turns, final
recommendation concrete and traceable, 5/5 calls complete with 0 format errors.

### Task R4 — Execution plan

Goal: "launch a market intelligence report product in 30 days."
Ask for phased plan with tasks, dependencies, risks, success criteria.

Pass: tasks are concrete and assignable, dependencies explicit, risks specific, timeline realistic.

### Scoring — Role 2

| Metric | qwen3:30b | glm-5 | qwen3:32b (baseline) |
|--------|----------|-------|----------------------|
| R1 pass/fail | | | |
| R2 pass/fail | | | |
| R3 pass/fail | | | |
| R4 pass/fail | | | |
| Avg time to final artifact | | | |
| Avg retries | | | |
| Supervision interventions | | | |
| Output usability (Y/N) | | | |
| Peak VRAM (GB) | | | |

---

## Role 3 — Ops / Triage Agent

**Baseline:** `glm4:7b-flash` | **Challengers:** `glm-4.7-flash`, `qwen3:30b`

Note: this role needs to be always-on and fast. Speed and accuracy over depth.
A model that takes 30 seconds to classify a Tier-2 action is useless here.

### Task O1 — Tier classification (10 items)

Give 10 mixed incoming actions. Ask for tier classification (1/2/3) with one-sentence
reasoning per item.

Pass: ≥9/10 correct. Any Tier-3 misclassified as Tier-1 = hard fail regardless of other scores.

### Task O2 — Log triage

Provide excerpts from 3 agent logs (INFO, WARNING, FATAL mix). Ask for: which FATALs
need Tier-2 Telegram, which WARNINGs can be ignored, probable root cause.

Pass: all FATALs identified, no false positives on INFO entries, root cause plausible.

### Task O3 — Task packet formatting

Convert a plain-text task description into a valid task packet JSON matching the exact schema.

Pass: valid JSON, all required fields present, no hallucinated or missing fields.

### Task O4 — Latency test

Time from prompt-send to first token and to completion on a simple classification task.

Pass: first token <5 seconds, completion <15 seconds.

### Scoring — Role 3

| Metric | glm-4.7-flash | qwen3:30b | glm4:7b-flash (baseline) |
|--------|--------------|----------|--------------------------|
| O1 correct / 10 | | | |
| O1 hard fail (T3→T1)? | | | |
| O2 pass/fail | | | |
| O3 valid JSON? | | | |
| O4 first-token latency | | | |
| O4 completion latency | | | |
| Supervision interventions | | | |
| Peak VRAM (GB) | | | |

---

## Role 4 — Business / Document Agent

**Baseline:** `qwen3:32b` | **Challengers:** `glm-5`, `qwen3:30b`

### Task B1 — Market intelligence report

Provide a topic brief (2 paragraphs). Ask for a formatted, client-ready market
intelligence report: exec summary, 3 key findings, implications, recommendations.

Pass: structured format, specific recommendations, 0 hallucinated data points,
output usability = YES (could send to paying client without edits).

### Task B2 — Product page copy

Give a product brief (1 paragraph). Ask for: headline, subheadline, 3 value props,
CTA, SEO meta description (<160 chars).

Pass: headline specific (not generic), value props concrete, meta under 160 chars.

### Task B3 — Investor update

Give a metrics snapshot (MRR, users, key wins, key challenges). Ask for a 300-word
investor update with honest narrative arc.

Pass: accurate numbers, challenges section present, clear next milestone, under 350 words.

### Task B4 — Support response draft

Give a customer complaint and relevant FAQ section. Ask for a Tier-1 draft response.

Pass: addresses specific complaint, FAQ accurately referenced, under 150 words, appropriate tone.

### Scoring — Role 4

| Metric | glm-5 | qwen3:30b | qwen3:32b (baseline) |
|--------|-------|----------|----------------------|
| B1 pass/fail | | | |
| B1 output usability | | | |
| B2 pass/fail | | | |
| B3 pass/fail | | | |
| B4 pass/fail | | | |
| Avg time to final artifact | | | |
| Avg retries | | | |
| Supervision interventions | | | |
| Peak VRAM (GB) | | | |

---

## Role 5 — Memory / Synthesis

**Baseline:** `llama3.1:70b` | **Challengers:** `llama3.3:70b`, `glm-5`

### Task M1 — Log synthesis

Provide today's agent logs (3 files, ~4K tokens). Ask for a structured MEMORY.md append:
completed tasks, patterns, errors, duration stats. No raw transcripts.

Pass: structured output, patterns extracted (not just event list), no raw log lines reproduced,
under 500 words.

### Task M2 — Long-context coherence

Provide 8K+ tokens of mixed logs. Ask for top 3 recurring failure patterns and a proposed
CONSTRAINTS.md rule for each.

Pass: patterns genuinely recurring, rules specific and implementable, no context drift.

### Task M3 — Self-improvement proposal

Provide 2 weeks of MEMORY.md entries. Ask for 3 improvement proposals for AGENT_CONFIG.md
or Lobster workflows, ranked by impact.

Pass: proposals reference specific config fields or workflow steps, ranking justified,
each implementable in <1 day, none contradict CONSTRAINTS.md.

### Scoring — Role 5

| Metric | llama3.3:70b | glm-5 | llama3.1:70b (baseline) |
|--------|-------------|-------|--------------------------|
| M1 pass/fail | | | |
| M2 pass/fail | | | |
| M3 pass/fail | | | |
| Avg time to final artifact | | | |
| Avg retries | | | |
| Supervision interventions | | | |
| Peak VRAM (GB) | | | |

---

## Role 6 — Vision Lane (new — no baseline)

**Model:** `qwen3-vl:32b` | **Baseline:** none (new capability)

Test whether vision capability is worth adding to the Phase 3 stack.
If it passes 3/4 tasks at output usability = YES, add it to the Phase 3 agent roster.

### Task V1 — Screenshot UI review

Give a screenshot of a competitor's landing page. Ask for: 3 specific UI/UX observations,
2 things to copy, 1 thing to avoid.

Pass: observations specific to screenshot (not generic), 0 invented UI elements.

### Task V2 — PDF data extraction

Give a PDF with a data table (financial or research data). Ask for the data extracted
into a structured markdown table.

Pass: all rows and columns present, no hallucinated values.

### Task V3 — Generated artifact review

Give a screenshot of a draft landing page built by the system. Ask for: what's working,
what's broken, specific fix recommendations.

Pass: identifies real issues visible in the screenshot, recommendations actionable.

### Task V4 — Slide deck review

Give 3 slide screenshots. Ask for a bullet-point review: clarity, logic, visual issues.

Pass: review addresses each slide, issues are visible in the screenshots (not invented).

### Scoring — Role 6

| Metric | qwen3-vl:32b |
|--------|-------------|
| V1 pass/fail | |
| V2 pass/fail | |
| V3 pass/fail | |
| V4 pass/fail | |
| Output usability (Y/N avg) | |
| Add to Phase 3 roster? | Y/N |
| Peak VRAM (GB) | |

---

## Money-Adjacent Workflow Tests

Run these after all role tasks are complete. They test cross-role coordination in real conditions.
Score with the same universal dimensions.

### MW1 — Feature to staging

One-sentence feature request → full debug-and-fix loop → merged branch, passing tests,
Tier-2 Telegram requesting staging deploy.

Models: Use whichever Build Agent and Ops Agent are currently leading the role scores.
Pass: complete without manual intervention in <90 minutes.

### MW2 — Scout to task packet

Real GitHub URL → repo-scout workflow → evaluated.md entry → if integrate verdict,
a valid task packet written to repo-queue/.

Models: Research Agent leader.
Pass: defensible verdict, valid task packet JSON, 0 hallucinated repo details.

### MW3 — Brief to client report

One-paragraph market brief → Research + Business agents → formatted client-ready report.

Models: Research + Business Agent leaders.
Pass: client-ready without editing, 0 hallucinated data, under 20 minutes.

### MW4 — Support triage to draft

3 real customer messages → 3 draft responses, correctly tiered, under 150 words each.

Models: Ops + Business Agent leaders.
Pass: correct tier for all 3, accurate FAQ references, 0 invented promises.

### MW Scoring

| Workflow | Models used | Pass/fail | Time | Supervision | Output usable? |
|----------|------------|-----------|------|-------------|----------------|
| MW1 | | | | | |
| MW2 | | | | | |
| MW3 | | | | | |
| MW4 | | | | | |

---

## Master Decision Sheet

Fill this after all role tasks and money-adjacent workflows complete.

| Role | Baseline | Baseline tasks passed | Winner | Winner tasks passed | Switch? |
|------|----------|-----------------------|--------|---------------------|---------|
| Coding/Build | qwen3:32b | /4 | | /4 | Y/N |
| Research | qwen3:32b | /4 | | /4 | Y/N |
| Ops/Triage | glm4:7b-flash | /4 | | /4 | Y/N |
| Business/Doc | qwen3:32b | /4 | | /4 | Y/N |
| Memory | llama3.1:70b | /3 | | /3 | Y/N |
| Vision (new) | — | — | qwen3-vl:32b | /4 | Add? Y/N |

**Switch rule:** Challenger replaces baseline only if it wins by ≥2 tasks AND matches or
beats on supervision burden AND matches or beats on VRAM usage.
One-task margin = not enough signal. Keep baseline.

**After completing the master sheet:** update AGENT_CONFIG.md files and CONSTRAINTS.md
model table with confirmed winners. Commit to git. Log to memory/MEMORY.md.

---

## Post-Bakeoff Routing Architecture (fill in with actual winners)

```
ROUTING ARCHITECTURE — fill in after bakeoff

Incoming task
     │
     ├─► Code implementation / bug fix
     │       → [winner of Role 1] _______________
     │       → fallback: [runner-up] _______________
     │
     ├─► Research / planning / multi-turn tool use
     │       → [winner of Role 2] _______________
     │
     ├─► Ops / triage / classification
     │       → [winner of Role 3] _______________   ← stays loaded always
     │
     ├─► Business documents / client deliverables
     │       → [winner of Role 4] _______________
     │
     ├─► Memory synthesis / long-context summarisation
     │       → [winner of Role 5] _______________
     │
     └─► Vision / screenshots / UI / PDF extraction   [Phase 3+]
             → qwen3-vl:32b (if added to roster)
```

---

*Generated: 2026-03-19 · Supersedes v1 bakeoff matrix*
*Run after: Phase 0 baseline bakeoff (qwen3:32b, 10/10 tool-calls)*
*Save completed results to: ~/openclaw/benchmark/bakeoff-role-specialist-[date].md*
*Update model policy with: openclaw-v4.2-model-patch.md*
