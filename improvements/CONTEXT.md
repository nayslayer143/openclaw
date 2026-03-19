# CONTEXT.md — improvements/ workspace

This workspace manages proposals to modify routing, configs, workflows, or structure.
Also handles postmortems and v-next planning. Nothing here is self-applied.

---

## What to Load

| Load This | Why | When | Skip These |
|-----------|-----|------|------------|
| Proposal file | The change being reviewed or drafted | Always | All active deliverables |
| Related memory summary | Pattern evidence for the proposal | When drafting from recurring failures | Broad repo queue |
| Affected config/workflow doc | What the proposal would change | When reviewing impact | Unrelated configs |
| `~/openclaw/CONSTRAINTS.md` | Approval rules | When proposal touches approval logic | Scout outputs |

---

## Folder Structure

```
improvements/
├── CONTEXT.md                      ← you are here
├── proposal-[slug]-[date].md       ← change proposals
├── postmortem-[slug]-[date].md     ← incident postmortems
├── routing-fail-[date].md          ← Jake Layer routing failures
└── mode-switch-[date].md           ← Mode A/B/C switch logs
```

---

## The Process

1. Trigger: recurring failure in `memory/MEMORY.md`, routing error, or manual review
2. Draft proposal with: what to change, why, evidence from logs/memory, rollback plan
3. Submit via Tier-2 Telegram → hold for Jordan's approval
4. If approved: create git branch → apply change → commit → notify Jordan
5. If rejected: log rejection reason to `memory/MEMORY.md`
6. Never self-apply. Ever.

---

## Proposal Format

```markdown
# Proposal: [title]
**Date:** [date]
**Author:** [agent or manual]
**Affects:** [config/workflow/routing file]

## Problem
[What's failing and how often — cite memory/log evidence]

## Proposed Change
[Exact diff or description of what changes]

## Evidence
[Links to MEMORY.md entries, log patterns, metrics]

## Rollback Plan
[How to undo if the change makes things worse]

## Risk
[Low/Medium/High + reasoning]
```

---

## Skills & Tools

| Tool / Skill | Use for | When to use | Do not use for |
|--------------|---------|-------------|----------------|
| Memory Librarian [Phase 4] | Pattern extraction, proposal drafting | Self-improvement cycle | Direct config edits |
| Git | Branch + commit approved changes | After Jordan approval only | — |

---

## What NOT to Do

- Never self-apply proposals — always git branch + Jordan approval
- Never load all active deliverables when drafting proposals
- Never propose changes without evidence from logs or memory
- Never modify proposals after submission without re-approval

---

## Handoffs

- **Receives from:** `memory/` (recurring issue patterns), manual review requests
- **Hands off to:** `agents/` or `lobster-workflows/` (approved structural changes), `memory/` (rejected proposal summaries)
