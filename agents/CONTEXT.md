# CONTEXT.md — agents/ workspace

This workspace manages agent configurations, escalation rules, and role boundaries.

---

## What to Load

| Load This | Why | When | Skip These |
|-----------|-----|------|------------|
| `configs/[role].md` | The agent config being edited | Always | Configs for unrelated roles |
| `~/openclaw/CONSTRAINTS.md` | Approval tiers and hard rules | Always | Benchmark docs |
| Related Lobster workflow | If behavior is workflow-driven | When editing workflow-linked behavior | Scout outputs |
| `~/openclaw/memory/MEMORY.md` | Only if debugging recurring failure | Conditional | Full log archive |

---

## Folder Structure

```
agents/
├── CONTEXT.md          ← you are here
└── configs/
    ├── orchestrator.md
    ├── research.md
    ├── build.md
    ├── ops.md
    ├── marketing.md    [Phase 3]
    ├── support.md      [Phase 3]
    └── memory-librarian.md [Phase 4]
```

---

## The Process

1. Identify which agent config needs changes
2. Load that config + CONSTRAINTS.md
3. Make the change in a git branch
4. If behavior change affects a Lobster workflow, load that workflow too
5. Test the change with one representative task
6. Commit with descriptive message

---

## Skills & Tools

| Tool / Skill | Use for | When to use | Do not use for |
|--------------|---------|-------------|----------------|
| Claude Code | Editing config files | When config changes are needed | Running agent workflows |
| Git | Branch + commit changes | Every config edit | — |

---

## What NOT to Do

- Never edit configs for agents not yet activated (respect phase gates)
- Never add personality content — configs are functional only
- Never remove security rules from any config
- Never self-apply improvement proposals — always git branch + Jordan approval

---

## Handoffs

- **Receives from:** `improvements/` (approved behavior change proposals)
- **Hands off to:** `memory/` (config change summary), `lobster-workflows/` (if workflow update needed)
