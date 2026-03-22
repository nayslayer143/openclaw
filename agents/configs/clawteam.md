# AGENT_CONFIG.md — ClawTeam Swarm Engine
# Human-readable source of truth for the agent registry in scripts/clawteam/registry.py

## Overview
ClawTeam is the multi-agent swarm orchestration layer for OpenClaw.
It enables multiple Ollama-powered agents to collaborate on complex tasks
using four patterns: sequential, parallel, debate, hierarchy.

## Swarm Agents

| Codename | Model | Fallback | Capabilities |
|---|---|---|---|
| AXIS | qwen3:32b | qwen2.5:7b | orchestration, synthesis, planning |
| SCOUT | qwen3:30b | qwen2.5:7b | research, intel, analysis |
| FORGE | qwen3-coder-next | devstral-small-2 | code, build, debug |
| VIGIL | qwen2.5:7b | llama3.2:3b | ops, monitoring, triage |

Internal roles (not agents, used by orchestrator):
- DECOMPOSER: qwen3:32b (fallback: qwen3:30b) — breaks task into subtasks
- SYNTHESIZER: qwen3:32b (fallback: qwen3:30b) — merges results into final output
- MANAGER: qwen3:32b — hierarchy pattern only, generates worker subtask list
- JUDGE: qwen3:32b — debate pattern only, delivers verdict on two positions

## Swarm Patterns

- **sequential** — A → B → C pipeline. Each result passed as context to next step.
- **parallel** — All subtasks run concurrently (max 3). Results merged by SYNTHESIZER.
- **debate** — SCOUT argues for, AXIS argues against, AXIS/JUDGE delivers verdict.
- **hierarchy** — MANAGER decomposes at runtime into workers, workers run in parallel.

## CLI Usage

```bash
# Run a swarm
python scripts/clawteam.py --task "research NFC card competitors" --pattern parallel

# Dry run (no execution)
python scripts/clawteam.py --task "..." --dry-run

# Resume interrupted swarm
python scripts/clawteam.py --resume swarm-1742300000-nfc

# List recent swarms
python scripts/clawteam.py --list
```

## Telegram Trigger

Send `!swarm <task>` in the Clawmson DM to start a swarm asynchronously.
The bot will confirm receipt and ping you on completion.

## SQLite State

All swarm state persists in `~/.openclaw/clawmson.db`:
- `ct_swarms` — one row per swarm run (status: pending/running/complete/partial/failed)
- `ct_subtasks` — one row per agent subtask
- `ct_messages` — agent-to-agent messages (debate/hierarchy patterns)

## Constraints

- All Ollama calls via localhost:11434 only
- Max 3 parallel workers (respects CONSTRAINTS.md sub-task limit)
- Per-subtask timeout: 300s
- Task input: max 500 chars, control chars stripped
- Swarm output never transmitted externally — local only
- --notify Telegram ping is Tier-1 (auto, no Jordan approval needed)
- No production deploys triggered by swarm output without Tier-2 approval
