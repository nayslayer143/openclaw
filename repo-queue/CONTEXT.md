# CONTEXT.md — repo-queue/ workspace

This workspace manages task triage, prioritization, repo scouting follow-up, and task packet creation.

---

## What to Load

| Load This | Why | When | Skip These |
|-----------|-----|------|------------|
| `pending.md` | Current queue of pending work | Always | Old build diffs |
| Latest scout report from `outputs/` | Source material for triage | When triaging new items | Unrelated memory logs |
| Queue scoring rubric (if present) | Consistent scoring | When scoring items | Benchmark notes |
| `evaluated.md` | Previously evaluated repos | When checking for duplicates | Full log archive |

---

## Folder Structure

```
repo-queue/
├── CONTEXT.md      ← you are here
├── pending.md      ← items awaiting triage or execution
└── evaluated.md    ← repos already scored and decided
```

---

## The Process

1. Review `pending.md` for items awaiting triage
2. Load relevant scout reports from `outputs/`
3. Score each item against relevance, complexity, and business value
4. Decision per item: execute (→ task packet), watch (→ stay in pending), skip (→ archive)
5. For execute items: create task packet JSON → dispatch to build
6. Update `pending.md` and `evaluated.md`

---

## Task Packet Format

```json
{
  "task_id": "build-[timestamp]",
  "repo_path": "~/projects/[repo]",
  "goal": "[one specific sentence]",
  "acceptance_criteria": ["test 1", "test 2"],
  "forbidden_operations": ["never touch main branch"],
  "time_budget_minutes": 30,
  "risk_level": "low | medium | high",
  "output_location": "~/openclaw/build-results/[task-id]/"
}
```

---

## Skills & Tools

| Tool / Skill | Use for | When to use | Do not use for |
|--------------|---------|-------------|----------------|
| Research Agent | Scoring repos, analyzing scout reports | During triage | Code implementation |
| Claude Code | Creating task packet files | When dispatching work | Running builds |

---

## What NOT to Do

- Never dispatch high-risk tasks without Tier-2 approval
- Never skip scoring — every item gets a relevance score before dispatch
- Never create task packets for repos not yet evaluated
- Never load the entire outputs/ directory — only the relevant scout report

---

## Handoffs

- **Receives from:** `outputs/` (scout reports with repo recommendations)
- **Hands off to:** `build-results/` (dispatched task packets), `memory/` (rejected/deferred decisions with reasons)

---

## Greenfield Detection — Ralph vs 4-Mode Dispatch

When creating a task packet, determine build mode before dispatch:

| Signal | Build Mode | Dispatch to |
|--------|-----------|-------------|
| Repo path does not exist | Greenfield | `ralph-plan-build.lobster` |
| Repo exists but zero meaningful commits | Greenfield | `ralph-plan-build.lobster` |
| Jordan says "build from scratch" / "new project" / "create" | Greenfield | `ralph-plan-build.lobster` |
| Repo exists with code + Jordan says "fix/add/change" | Existing | `debug-and-fix.lobster` → `build-agent-bridge.sh` |
| Repo is live / has users | Existing (always) | `debug-and-fix.lobster` → `build-agent-bridge.sh` |

**When routing to Ralph — auto-scaffold before plan phase:**
```bash
# Run from target repo directory:
cp ~/openclaw/scripts/ralph-templates/PROMPT_plan.md .
cp ~/openclaw/scripts/ralph-templates/PROMPT_build.md .
mkdir -p specs
# AGENTS.md and IMPLEMENTATION_PLAN.md created by ralph-plan-build.lobster scaffold step
```

**Ralph task packet — additional fields:**
```json
{
  "task_id": "ralph-[timestamp]",
  "repo_path": "~/projects/[repo]",
  "goal": "[one specific sentence — the end state]",
  "slug": "[kebab-name]",
  "max_iterations": 0,
  "timeout_minutes": 360,
  "build_mode": "ralph"
}
```
