# AutoResearch — Experiment Loop

> Phase 4 only. Do not activate before Phase 3 metrics are boring for 7 days.

## Setup

Check for MLX port first:
- `github.com/trevin-creator/autoresearch-mlx`
- `github.com/miolini/autoresearch-macos`

Install whichever is more recently maintained.

## Configuration
- Model: `qwen2.5:32b` via Ollama
- Time per experiment: 5 minutes max
- Experiment cap: 50 per weekly cycle
- Wall-clock cap: 6 hours
- Schedule: Sunday nights (managed by Memory Librarian)

## Pre-activation Checklist
- [ ] MLX or Ollama backend confirmed working
- [ ] 3 test experiments completed without errors
- [ ] Memory Librarian agent config active
- [ ] Jordan approved activation via Tier-2 Telegram

## Directory Structure (after install)
```
autoresearch/
├── README.md           ← you are here
├── config.yaml         ← experiment configuration
├── experiments/        ← individual experiment results
└── reports/            ← weekly synthesis reports
```
