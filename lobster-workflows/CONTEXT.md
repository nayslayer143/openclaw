# CONTEXT.md — lobster-workflows/ workspace

This workspace manages deterministic Lobster YAML workflows, bridge scripts, and cron scheduling.

---

## What to Load

| Load This | Why | When | Skip These |
|-----------|-----|------|------------|
| Target workflow file | The workflow being created/edited | Always | Unrelated workflows |
| `~/openclaw/IDLE_PROTOCOL.md` | Schedule reference | When editing cron-triggered workflows | Build artifacts |
| `~/openclaw/CONSTRAINTS.md` | Approval tier rules | When workflow has approval gates | Unrelated agent configs |
| Related agent config | If workflow dispatches to a specific agent | Conditional | Scout outputs |

---

## Folder Structure

```
lobster-workflows/
├── CONTEXT.md              ← you are here
├── build-agent-bridge.sh   ← OpenClaw → Claude Code bridge script
├── debug-and-fix.lobster
├── repo-scout.lobster
├── daily-intel-lite.lobster
├── system-health.lobster
├── morning-brief.lobster
├── evening-summary.lobster
├── release-candidate.lobster   [Phase 2]
├── daily-market-intel.lobster  [Phase 3]
├── model-benchmark.lobster     [Phase 4]
│
│   # AutoResearch workflows (live in autoresearch/meta/, referenced here)
└── autoresearch/meta/usecase-discovery.lobster  [cron: Mon 10pm]
```

---

## The Process

1. Identify the workflow to create or modify
2. Load the target workflow + any related schedule/constraint docs
3. Write or edit the workflow YAML
4. Test manually before enabling cron trigger
5. Commit with descriptive message
6. Enable cron only after manual test passes

---

## Skills & Tools

| Tool / Skill | Use for | When to use | Do not use for |
|--------------|---------|-------------|----------------|
| Claude Code | Writing workflow files | When workflow creation/editing needed | Running workflows |
| Lobster CLI | Testing workflows manually | Before enabling cron | — |
| Git | Branch + commit changes | Every workflow edit | — |

---

## What NOT to Do

- Never enable a cron before testing the workflow manually
- Never create workflows for phases not yet active
- Never put agent reasoning logic in workflows — workflows are deterministic
- Never skip approval gates in workflow definitions

---

## Handoffs

- **Receives from:** `improvements/` (approved workflow changes), `agents/` (if behavior change needs workflow update)
- **Hands off to:** `memory/` (workflow change summary), `repo-queue/` or `outputs/` (workflow-triggered task packets)
