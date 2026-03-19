# CONTEXT.md — outputs/ workspace

This workspace manages scout reports, market intel, research deliverables, and polished outputs.

---

## What to Load

| Load This | Why | When | Skip These |
|-----------|-----|------|------------|
| Task packet or format spec | Defines deliverable requirements | Always | Build logs |
| Relevant source notes | Raw material for the output | When producing deliverables | Queue backlog |
| `~/openclaw/CONSTRAINTS.md` | Approval rules for external-facing content | When output is external-facing | Archived benchmark notes |
| Voice/style guide | Only if output is customer-facing | Conditional | Agent configs |

---

## Folder Structure

```
outputs/
├── CONTEXT.md                  ← you are here
├── [source]-scout-[date].md    ← scout reports (bookmark, reddit, etc.)
└── market-intel-[date].md      ← compiled intel reports [Phase 3]
```

---

## The Process

1. Receive task or produce scheduled output (scout report, intel brief)
2. Load relevant source material only
3. Produce the deliverable in the correct format
4. If external-facing: Tier-2 approval before marking as deliverable
5. Save to `outputs/` with correct naming convention
6. If output has implementation potential: note handoff to `repo-queue/`

---

## Skills & Tools

| Tool / Skill | Use for | When to use | Do not use for |
|--------------|---------|-------------|----------------|
| Research Agent | Producing scout reports, intel briefs | Scheduled cycles or manual request | Code changes |
| Web Search | Live research for reports | When fresh data needed | — |
| MiroFish | Simulation-backed reports | Phase 3+ only | Simple summaries |

---

## What NOT to Do

- Never publish outputs without Tier-2 approval
- Never load build logs or queue backlog when producing research
- Never run MiroFish before Phase 3 activation
- Never include raw API keys, credentials, or memory files in outputs

---

## Handoffs

- **Receives from:** Research Agent (scheduled scouts), manual requests
- **Hands off to:** `repo-queue/` (outputs with implementation potential), `memory/` (output summary)
