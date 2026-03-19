# CONTEXT.md — OpenClaw Router

Route your task through this file before loading anything else.
Find your task in the routing table below, then go to the workspace it points to.
Do not load all workspaces at once.

---

## What this system contains

| Workspace | Purpose | Use when |
|-----------|---------|----------|
| `agents/` | Agent configs, escalation rules, role boundaries | Changing or inspecting agent behavior |
| `lobster-workflows/` | Deterministic Lobster YAML workflows and bridge scripts | Creating or modifying cron/approval workflows |
| `repo-queue/` | Pending repo work, scouting decisions, task packets | Triaging or selecting tasks to execute |
| `build-results/` | Plans, diffs, test outputs, output contracts | Implementing or reviewing code changes |
| `outputs/` | Scout reports, market intel, research deliverables | Generating or refining deliverables |
| `memory/` | Summaries, patterns, system learnings | Reviewing history or identifying improvements |
| `benchmark/` | Model bakeoffs, runtime comparisons, stack evaluations | Model or runtime decisions |
| `improvements/` | Proposals, postmortems, v-next planning | Structural change review and drafting |

---

## Task Routing

| If the task is... | Start here | You'll also need | Do NOT load initially |
|-------------------|-----------|------------------|-----------------------|
| Change agent behavior or escalation rules | `agents/CONTEXT.md` | `CONSTRAINTS.md`, related Lobster workflow | Scout outputs, benchmark docs |
| Create or modify a Lobster workflow | `lobster-workflows/CONTEXT.md` | `IDLE_PROTOCOL.md` if schedule-related, `CONSTRAINTS.md` | Build artifacts, agent configs for other roles |
| Implement a code fix or feature | Repo's `build/CONTEXT.md` | Repo `CLAUDE.md`, task packet from `repo-queue/` | Memory archive, outputs directory |
| Triage repo-queue or create a task packet | `repo-queue/CONTEXT.md` | Latest scout report from `outputs/` | Build logs, memory archive |
| Summarize completed work or extract patterns | `memory/CONTEXT.md` | Today's logs from `logs/` | Raw build artifacts, all scout outputs |
| Produce a research report or deliverable | `outputs/CONTEXT.md` | Task packet or format spec, source notes | Build logs, queue backlog |
| Run a model bakeoff or evaluate the stack | `benchmark/CONTEXT.md` | Latest bakeoff doc, benchmark prompt set | Queue items, content outputs |
| Draft or review a system improvement | `improvements/CONTEXT.md` | Proposal file, related memory summary | All active deliverables |
| Run the build agent bridge (automated) | `lobster-workflows/build-agent-bridge.sh` | Task packet JSON from `repo-queue/` | Unrelated workspace docs |
| Check system health | `logs/` + `queue/pending.json` | `IDLE_PROTOCOL.md` Cycle 1 | All workspace context |

---

## Handoff Chain

Work flows forward through this chain. Never skip steps. Never pull backward.

```
outputs/
  └─► repo-queue/        (scout finds opportunity → queued as task packet)
        └─► build-results/   (task packet dispatched → code executed → output contract)
              └─► memory/        (output contract summarized → patterns extracted)
                    └─► improvements/  (patterns → improvement proposals)
                          └─► agents/ or lobster-workflows/
                                (approved proposals → config or workflow updates)
```

If you need context from an earlier stage, load only the specific artifact referenced in
the handoff note — not the entire upstream workspace.

---

## Cross-Workspace Rules

- Finish the current workspace step before handing off. Do not load the next workspace mid-task.
- If a task spans two workspaces, note the handoff point explicitly in your work.
- `memory/` receives summaries only — never raw transcripts, never full log files.
- `improvements/` proposals are never self-applied. All changes go through a git branch + Jordan approval.

---

## Escalation

If a task doesn't fit any row in the routing table above, stop and check `CONSTRAINTS.md`
before proceeding. When in doubt, route to `improvements/CONTEXT.md` and describe the
routing ambiguity — that's a signal a new routing row is needed.

---

## Active Phases

| Phase | Status | Workspaces active |
|-------|--------|-------------------|
| Phase 0 | [x] Complete | CLAUDE.md, CONTEXT.md |
| Phase 1 | [x] Complete | + agents/, lobster-workflows/, repo-queue/, outputs/ |
| Phase 2 | [x] In progress | + build-results/, memory/, benchmark/ |
| Phase 3 | [ ] Pending | + mirofish/, revenue workflows |
| Phase 4 | [ ] Pending | + improvements/, autoresearch/, Memory Librarian |

Update the checkboxes as phases complete. The active phase row tells any session
which workspace CONTEXT.md files exist and are safe to load.

---

*This file is the router. Read it first, then go where it points.*
*For full system architecture: `openclaw-v4.1-strategy.md`*
