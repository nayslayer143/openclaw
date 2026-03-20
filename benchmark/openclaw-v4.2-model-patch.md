# OpenClaw v4.2 — Model Policy Patch
## Replace the "Model Policy" section of openclaw-v4.1-strategy.md with this document
> March 19, 2026 · Jordan · M2 Max 96GB
> Architecture unchanged. Model layer modernised.
> Two research passes (yours + ChatGPT cross-check) converged on the same corrections.

---

## What Changed and Why

**The v4.1 model policy had two problems:**

1. **The no-MoE rule was too broad.** v4.1 says "dense models only for agent work — MoE models loop endlessly on multi-step tool chains." That was accurate for early-generation MoE models (Mixtral variants, early Qwen MoE). It is not accurate for agent-optimised hybrid models released in 2025-2026. GLM-4.7-Flash (30B-A3B MoE) is explicitly designed for agent frameworks and lightweight routing. Qwen3-Coder-Next is explicitly designed for agentic coding and local development. MiniMax M2.5 is positioned for agentic tool use. All three are MoE or hybrid-MoE. Excluding them by default means excluding the strongest models in the ops and coding lanes.

**Revised rule:** Test MoE models that are explicitly optimised for agent tool-calling and local deployment. Exclude MoE models with no agent-specific post-training or no confirmed tool-call format stability (those still loop). The criterion is tool-call hygiene under test, not architecture.

2. **The model lineup was anchored to yesterday.** `glm4:7b-flash` → superseded by `glm-4.7-flash`. `llama3.1:70b` → `llama3.3:70b` delivers similar-to-3.1-405B performance at the same 70B size. `qwen2.5-coder:32b` for Aider → `qwen3-coder-next` is the current Qwen coding-agent model. The old lineup still works but leaves performance on the table.

**What did not change:** the architecture, the approval tiers, the 4-mode build loop, the task packet / output contract format, the Jake Layer routing, the security layer, the phased build plan, the revenue streams. Those are correct and current. This patch is the model layer only.

---

## Updated Model Roster

Pull these before running the role-specialist bakeoff.

| Role | Model | Pull command | Est. VRAM | Notes |
|------|-------|-------------|-----------|-------|
| Primary coder (Build Agent) | `qwen3-coder-next` | `ollama pull qwen3-coder-next` | ~52GB | 256K context, local-first, agentic coding |
| Coding challenger / cost loop | `devstral-small-2` | `ollama pull devstral-small-2` | ~16GB | Mistral's open coder for multi-file edits |
| Orchestrator / Research | `qwen3:30b` | `ollama pull qwen3:30b` | ~20GB | General-purpose, replaces 32B as orchestrator baseline |
| Business / Document Agent | `glm-5` | `ollama pull glm5` | ~45GB est. | Agentic engineering + office artifacts |
| Always-on Ops / Triage | `glm-4.7-flash` | `ollama pull glm4.7-flash` | ~19GB | 30B-A3B MoE, fast, agent-optimised |
| Deep synthesis / Memory | `llama3.3:70b` | `ollama pull llama3.3:70b` | ~42GB | ~405B quality at 70B size |
| Optional vision lane | `qwen3-vl:32b` | `ollama pull qwen3-vl:32b` | ~20GB | Screenshots, PDFs, UI review — new lane |
| Aider fallback (coding) | `qwen3-coder-next` | same as above | ~52GB | Replaces qwen2.5-coder:32b |

### Baselines being replaced (keep pulled until bakeoff confirms successors)

| Old model | New model | Reason |
|-----------|-----------|--------|
| `glm4:7b-flash` | `glm-4.7-flash` | Materially stronger, still lightweight, MoE but agent-optimised |
| `llama3.1:70b` | `llama3.3:70b` | Same VRAM, meaningfully better quality |
| `qwen2.5-coder:32b` | `qwen3-coder-next` | Current Qwen coder generation |
| `qwen3:32b` (all roles) | Role-specialist routing | Specialist models beat generalist in each lane |

---

## VRAM Rotation Strategy (critical — 96GB is tight with new lineup)

The new lineup is better but larger. You cannot load everything simultaneously.

```
Always loaded (small, fast, triage):
  glm-4.7-flash       ~19GB  ← stays resident always

Rotate by task type:
  Build task incoming → load qwen3-coder-next  (~52GB)
                      → total with ops: ~71GB  ✅ fits
                      → unload before loading synthesis

  Research/planning   → load qwen3:30b          (~20GB)
                      → total with ops: ~39GB  ✅ fits easily
                      → can load glm-5 alongside if needed: ~64GB ✅

  Document/business   → load glm-5             (~45GB)
                      → total with ops: ~64GB  ✅ fits
                      → unload before deep synthesis

  Deep synthesis      → load llama3.3:70b       (~42GB)
                      → total with ops: ~61GB  ✅ fits
                      → unload qwen3-coder-next first

  Vision task         → load qwen3-vl:32b       (~20GB)
                      → total with ops: ~39GB  ✅ fits easily

HARD CONSTRAINTS:
  ❌ qwen3-coder-next + llama3.3:70b simultaneously = ~94GB → too tight, crashes likely
  ❌ glm-5 + llama3.3:70b simultaneously = ~87GB → marginal, avoid
  ❌ qwen3-coder-next + glm-5 simultaneously = ~97GB → over limit
```

**Add to startup.sh — model rotation helpers:**
```bash
# Add these aliases to ~/.zshrc or ~/.bashrc for fast rotation:
alias oc-load-build='ollama stop llama3.3:70b; ollama stop glm5; ollama run qwen3-coder-next --keepalive 30m &'
alias oc-load-research='ollama stop qwen3-coder-next; ollama run qwen3:30b --keepalive 30m &'
alias oc-load-synthesis='ollama stop qwen3-coder-next; ollama stop glm5; ollama run llama3.3:70b --keepalive 30m &'
alias oc-load-docs='ollama stop qwen3-coder-next; ollama stop llama3.3:70b; ollama run glm5 --keepalive 30m &'
alias oc-status='ollama ps'
```

---

## Updated Static Model Assignment (post-bakeoff target)

This replaces the table in AGENT_CONFIG.md and CONSTRAINTS.md once bakeoff confirms winners.
**Do not update these files until the role-specialist bakeoff runs.**

| Role | Target model | Fallback |
|------|-------------|----------|
| Orchestrator | `qwen3:30b` | `qwen3:32b` (current) |
| Research Agent | `qwen3:30b` or `glm-5` | `qwen3:32b` |
| Build Agent | `qwen3-coder-next` | `devstral-small-2` |
| Ops Agent | `glm-4.7-flash` | `glm4:7b-flash` (current) |
| Marketing Agent [Phase 3] | `glm-5` | `qwen3:30b` |
| Support Agent [Phase 3] | `glm-4.7-flash` | `glm4:7b-flash` |
| Memory Librarian [Phase 4] | `llama3.3:70b` | `llama3.1:70b` (current) |
| Embeddings | `nomic-embed-text` | unchanged |
| Aider fallback | `qwen3-coder-next` | `devstral-small-2` |
| Vision lane [Phase 3+] | `qwen3-vl:32b` | none — skip if task has no visual component |

---

## New Vision Lane

v4.1 had no vision capability. Add this in Phase 3 when Marketing and Document agents activate.

**Use `qwen3-vl:32b` for:**
- Reviewing screenshots of competitor interfaces
- Inspecting generated landing pages before publishing
- Extracting data from PDF tables or reports
- Reviewing generated slide decks or marketing assets
- UI feedback on built interfaces

**Do not use for:**
- Code implementation (use Build Agent)
- Text-only research (wastes the multimodal capability)

Load only when a vision task is queued. 20GB footprint means it fits alongside the ops model easily.

---

## Updated Bakeoff Criteria

The v4.1 bakeoff criteria were too benchmark-centric. These replace them for the role-specialist bakeoff.

**For every task in every role, score:**

| Dimension | What to measure | Target |
|-----------|----------------|--------|
| Completion rate | Did the task finish without aborting? | 100% |
| Retries | How many times did you re-prompt or correct? | 0–1 |
| Tool-call format errors | Malformed tool calls in the session | 0 |
| Time to first useful action | From prompt to first substantive output | <3 min |
| Time to final artifact | From prompt to usable deliverable | Role-specific (see below) |
| Supervision burden | How many times did you intervene? | 0–1 |
| Output usability | Could you use this in a revenue workflow without editing? | Y/N |
| VRAM under load | Peak memory during session | Log it |
| Hallucinated actions | Invented file paths, stats, or tool calls | 0 |

**Time targets by role:**

| Role | Time to final artifact |
|------|----------------------|
| Build Agent (bug fix) | <45 min |
| Build Agent (new feature) | <90 min |
| Research Agent (repo scout) | <10 min |
| Research Agent (planning doc) | <20 min |
| Ops Agent (triage/classify) | <2 min |
| Business Agent (client report) | <15 min |
| Memory Agent (log synthesis) | <10 min |

**The output usability test is the most important.**
Ask yourself: "Could I send this diff / report / plan / draft to a client or into production without editing it?" If the answer is no, the model failed the task regardless of benchmark score.

---

## Money-Adjacent Workflow Tasks (add to bakeoff alongside role tasks)

Run these after the role-specific tasks. They test cross-role coordination, which is where the system
either works as a business or doesn't.

**MW1 — Feature to production**
Give a one-sentence feature request. Run the full debug-and-fix loop. End state: merged
branch, passing tests, staging deploy requested via Tier-2 Telegram.
Pass: complete without manual intervention in <90 minutes.

**MW2 — Scout to task packet**
Give a GitHub URL of a real tool. Run repo-scout workflow. End state: evaluated.md entry
with integrate/watch/skip verdict + if integrate, a task packet written and in repo-queue/.
Pass: defensible verdict, valid task packet JSON, no hallucinated repo details.

**MW3 — Brief to deliverable**
Give a one-paragraph market brief. End state: formatted market intel report ready to send
to a client. No MiroFish yet — just the Research + Business agents working together.
Pass: client-ready quality, no hallucinated data, under 20 minutes.

**MW4 — Support triage to draft**
Give 3 real customer messages. End state: 3 draft responses, each correctly tiered
(Tier-1 routine vs Tier-2 new customer), each under 150 words, ready to send or approve.
Pass: correct tier for all 3, accurate FAQ references, no invented promises.

Score the money-adjacent workflows on the same dimensions as role tasks.
These results matter more than the role-task scores — they reflect real operating conditions.

---

## What Stays the Same from v4.1

Everything except the model layer. To be explicit:

- Architecture (5 layers: Telegram → Operator Shell → Research/Build → Inference → Data)
- 3 Operating Modes (A/B/C)
- All 9 Core Principles
- Security layer (gateway, budget cap, approval tiers, denylist, SKILL.md audit)
- AGENT_CONFIG.md structure and templates
- IDLE_PROTOCOL.md (lite + advanced tiers)
- Claude Code integration (4-mode pattern, task packet, output contract, hooks)
- Jake Layer context routing (CLAUDE.md → CONTEXT.md → workspace CONTEXT.md)
- Aider as local fallback (now pointed at qwen3-coder-next)
- Goose as optional Research layer
- OpenHands as optional Phase 4 ticket-factory
- Phased build plan (Phase 0–4, JIT CONTEXT.md files)
- Revenue streams (MiroFish, AutoResearch, ClawHub, Automation-as-a-Service)
- Weekly metrics table (add context routing errors column per v4.1)
- Disaster recovery playbook

---

## Implementation Checklist

- [ ] Pull new baseline ops model: `ollama pull glm4.7-flash`
- [ ] Pull synthesis upgrade: `ollama pull llama3.3:70b`
- [ ] Pull coding challenger: `ollama pull qwen3-coder-next`
- [ ] Pull coding second challenger: `ollama pull devstral-small-2`
- [ ] Pull orchestrator: `ollama pull qwen3:30b`
- [ ] Pull business agent: `ollama pull glm5`
- [ ] Pull vision lane (Phase 3 prep): `ollama pull qwen3-vl:32b`
- [ ] Add rotation aliases to ~/.zshrc
- [ ] Verify each model loads cleanly: `ollama run [model] "respond with ok"` → `ollama stop [model]`
- [ ] Update CONSTRAINTS.md model assignment table (after bakeoff confirms)
- [ ] Update all 4 AGENT_CONFIG.md files (after bakeoff confirms)
- [ ] Update startup.sh with new pull commands and rotation aliases

**Do not update AGENT_CONFIG.md or CONSTRAINTS.md until the role-specialist bakeoff runs.**
Run this checklist first. Run the bakeoff second. Update configs third.

---

*Patch generated: 2026-03-19*
*Sources: your research pass + ChatGPT cross-check + Ollama library verification*
*Replaces: "Model Policy" section of openclaw-v4.1-strategy.md*
*Does not replace: any other section of v4.1*
