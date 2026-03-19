# CONTEXT.md — benchmark/ workspace

This workspace manages model bakeoffs, runtime comparisons, and stack evaluations.

---

## What to Load

| Load This | Why | When | Skip These |
|-----------|-----|------|------------|
| Latest bakeoff doc | Current benchmark results | Always | Queue or content outputs |
| Benchmark prompt set | Test inputs for evaluation | When running bakeoff | Unrelated agent configs |
| Hardware/runtime notes | M2 Max specs, memory limits | When comparing backends | Build artifacts |
| `~/openclaw/CONSTRAINTS.md` | Current model assignments | When proposing changes | Scout outputs |

---

## Folder Structure

```
benchmark/
├── CONTEXT.md              ← you are here
├── bakeoff-[date].md       ← model comparison results
├── goose-eval-[date].md    ← Goose vs Research Agent evaluation [Phase 2]
└── prompt-sets/            ← standard test prompts for bakeoffs
```

---

## The Bakeoff Process

```
1. Pull candidate model(s)
2. Run 10 consecutive chained tool-call tasks — record: format errors, retries, completion rate
3. Run 10 code-analysis tasks — record: latency, accuracy
4. Run 5 long-context summarizations (8K+ tokens) — record: quality, truncation
5. Run same prompts on Ollama backend vs MLX backend (if available)
6. Record: first-token latency, completion time, memory pressure, swap events
7. Document winner per role → bakeoff-[date].md
8. Do not change model assignments until bakeoff evidence supports it
```

---

## Current Model Inventory

| Model | Size | Role |
|-------|------|------|
| `qwen2.5:32b` | 19 GB | Orchestrator, Research, Planning |
| `deepseek-coder:33b` | 18 GB | Build/Code |
| `qwen2.5:14b` | 9 GB | Medium complexity backup |
| `qwen2.5:7b` | 4.7 GB | Ops, fast triage |
| `deepseek-coder:6.7b` | 3.8 GB | Light coding fallback |
| `llama3.2:3b` | 2 GB | Quick drafts |
| `nomic-embed-text` | 274 MB | Embeddings (always loaded) |

---

## Skills & Tools

| Tool / Skill | Use for | When to use | Do not use for |
|--------------|---------|-------------|----------------|
| Ollama CLI | Model pull, test, benchmark | All bakeoffs | Production workloads |
| Claude Code | Running structured benchmark prompts | Evaluation runs | — |
| Python | Latency measurement, stats | When precise timing needed | — |

---

## What NOT to Do

- Never change model assignments in CONSTRAINTS.md without bakeoff evidence
- Never run bakeoffs during active build tasks (resource contention)
- Never trust subjective quality assessment — use structured scoring only
- Never benchmark MoE models for agent tool-calling (they loop on multi-step chains)

---

## Handoffs

- **Receives from:** Manual request, monthly model benchmark Lobster workflow [Phase 4]
- **Hands off to:** `memory/` (winner/recommendation), `improvements/` (if config change needed)
