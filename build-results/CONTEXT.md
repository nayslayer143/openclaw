# CONTEXT.md — build-results/ workspace

This workspace manages implementation plans, diffs, test results, output contracts, and review decisions.

---

## What to Load

| Load This | Why | When | Skip These |
|-----------|-----|------|------------|
| Current task packet | Defines goal and acceptance criteria | Always | Broad scout reports |
| Target repo `CLAUDE.md` | Repo map, commands, forbidden ops | Always | Entire outputs directory |
| `[task-id]/plan-[slug].md` | Implementation plan | CODE and REVIEW stages | Unrelated memory summaries |
| `[task-id]/output-contract.json` | Build result | When reviewing completed work | Other task results |
| Relevant test files | Validation targets | REVIEW stage | Marketing docs |

---

## Folder Structure

```
build-results/
├── CONTEXT.md                      ← you are here
├── [task-id].json                  ← canonical output contract (copy)
├── [task-id]/
│   ├── plan-[slug].md              ← implementation plan
│   ├── output-contract.json        ← detailed output contract
│   └── [other build artifacts]
└── disaster-drill-[date].md        ← DR test results
```

---

## The Process

1. Receive dispatched task packet from `repo-queue/`
2. Build Agent runs 4-mode sequence (Explore→Plan→Code→Review)
3. Output contract written to `[task-id]/output-contract.json`
4. Canonical copy at `[task-id].json`
5. If success: summary → `memory/`, merge approval → Telegram Tier-2
6. If blocked: reason logged, task returned to `repo-queue/` with notes

---

## Output Contract Schema

```json
{
  "task_id": "build-[timestamp]",
  "status": "success | blocked | partial",
  "changed_files": ["path/to/file"],
  "tests_run": 0,
  "tests_passed": 0,
  "tests_failed": 0,
  "unresolved_risks": [],
  "rollback_command": "git checkout main -- [file]",
  "summary": "[one sentence]",
  "suggested_next": "Deploy to staging | Needs human review | Ready to merge"
}
```

---

## Skills & Tools

| Tool / Skill | Use for | When to use | Do not use for |
|--------------|---------|-------------|----------------|
| Claude Code | All 4 stages of implementation | When code changes needed | Telegram ops |
| Aider | Narrow single-file edits | Routine tasks <50 lines | Architectural decisions |
| build-agent-bridge.sh | Automated Claude Code dispatch | Lobster workflow trigger | Interactive sessions |

---

## What NOT to Do

- Never merge to main without Tier-2 approval
- Never skip the PLAN stage
- Never deploy with failing tests
- Never load the entire outputs/ or memory/ directory

---

## Handoffs

- **Receives from:** `repo-queue/` (dispatched task packets)
- **Hands off to:** `memory/` (result summaries), `repo-queue/` (blocked tasks with reason)
