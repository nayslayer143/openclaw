# CONTEXT.md — memory/ workspace

This workspace manages structured summaries, pattern extraction, and system learnings.
Memory stores patterns and decisions — never raw transcripts or full log files.

---

## What to Load

| Load This | Why | When | Skip These |
|-----------|-----|------|------------|
| Recent logs from `logs/` | Source for today's summarization | Daily consolidation cycle | Raw build artifacts |
| Relevant result summaries | Completed work to summarize | After build completion | All scout outputs |
| Current improvement proposals | When reviewing trends | Trend analysis | Full repo queue |
| `MEMORY.md` | Current memory state | Always | Archived logs older than 7 days |

---

## Folder Structure

```
memory/
├── CONTEXT.md      ← you are here
├── MEMORY.md       ← append-only structured summaries (newest first)
└── IDLE_LOG.md     ← idle protocol cycle logs
```

---

## The Process

1. Triggered by: Daily Memory Consolidation (Cycle 4), build completion, or manual request
2. Read relevant source (today's logs, result summaries)
3. Extract: completed tasks, errors, patterns, durations, decisions
4. Append structured summary to `MEMORY.md` — NOT raw transcripts
5. If recurring failure pattern found: draft proposal → `improvements/`
6. Compress logs older than 7 days → `logs/archive/`

---

## MEMORY.md Format

```markdown
### [Date] — [Summary Type]
- **Completed:** [task list with outcomes]
- **Errors:** [any failures and root causes]
- **Patterns:** [recurring observations]
- **Decisions:** [choices made and rationale]
- **Duration:** [time spent]
```

---

## Skills & Tools

| Tool / Skill | Use for | When to use | Do not use for |
|--------------|---------|-------------|----------------|
| Orchestrator / Memory Librarian [Phase 4] | Summarization, pattern extraction | Daily consolidation | Code implementation |
| `qwen3:32b` | Deep synthesis of patterns | When 8K+ context needed | Simple log archival |

---

## What NOT to Do

- Never store raw transcripts in MEMORY.md
- Never store full log files — summaries only
- Never self-apply improvement proposals found during pattern analysis
- Never load all build artifacts or scout outputs for summarization

---

## Handoffs

- **Receives from:** `build-results/` (result summaries), `logs/` (daily consolidation)
- **Hands off to:** `improvements/` (recurring issue proposals)
