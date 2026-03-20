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

## Confirmed Model Assignments (bakeoff 2026-03-19)

| Model | Role |
|-------|------|
| `qwen3:32b` | Orchestrator / Memory / Synthesis |
| `qwen3:30b` | Research / Planning / Business |
| `qwen3-coder-next` | Build / Code (primary) |
| `devstral-small-2` | Build / Code (fallback) |
| `qwen2.5:7b` | Ops / Fast triage / Routing |
| `nomic-embed-text` | Embeddings (always loaded) |

See `bakeoff-role-specialist-2026-03-19.md` for full results.
v4.2 policy patch: `openclaw-v4.2-model-patch.md` (MoE ban lifted for agent-optimized models).

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
- MoE models allowed for agent tool-calling if agent-optimized (see v4.2 patch)

---

## Handoffs

- **Receives from:** Manual request, monthly model benchmark Lobster workflow [Phase 4]
- **Hands off to:** `memory/` (winner/recommendation), `improvements/` (if config change needed)
