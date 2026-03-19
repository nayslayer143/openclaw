# build/CONTEXT.md — [PROJECT_NAME] Implementation Workspace

This workspace handles all code changes via Claude Code 4-mode sequence.
Receive from: `~/openclaw/repo-queue/` task packets or `../CONTEXT.md` routing.
Hand off to: `~/openclaw/build-results/` output contracts, `~/openclaw/memory/` summaries.

---

## What to Load

| Load This | Why | When | Skip These |
|-----------|-----|------|------------|
| Task packet from openclaw | Defines goal and acceptance criteria | Always | Full outputs directory |
| `../CLAUDE.md` | Repo map and forbidden ops | Before any stage | Unrelated docs |
| Relevant source files | Code to be changed | EXPLORE stage | Entire codebase |
| `plan-[slug].md` | Implementation plan | CODE stage only | Marketing docs |
| `tests/[relevant]/` | Validation target | CODE and REVIEW stages | Archive logs |

---

## The 4-Mode Sequence

1. **EXPLORE** — Map relevant files, understand impact scope. No edits. Output: file map.
2. **PLAN** — Write `plan-[slug].md`. List risks, rollback approach. No edits. Review required.
3. **CODE** — Execute plan in feature branch. Run tests. List changed files.
4. **REVIEW** — Audit diff. Challenge it. Find security issues, test gaps, edge cases. Pass or fail.

No stage runs without the previous stage's output.

---

## Skills & Tools

| Tool / Skill | Use for | When to use | Do not use for |
|--------------|---------|-------------|----------------|
| Claude Code | Implementation, plan, review | All 4 stages | Telegram notifications |
| Aider | Narrow single-file edits | When task fits in <50 lines | Architectural decisions |
| pre-bash-check.sh | Denylist enforcement | Every Bash call (hook) | — |
| lint.sh | Code quality | Every Edit call (hook) | — |

---

## What NOT to Do

- Never edit main branch directly
- Never skip PLAN stage (plan.md must exist before CODE runs)
- Never deploy without Tier-2 approval on staging, Tier-3 on production
- Never run CODE with test failures from previous stage unresolved
