# ClawTeam — Multi-Agent Swarm Orchestration Engine
**Date:** 2026-03-22
**Status:** Approved
**Phase:** 4 (active)

---

## Overview

ClawTeam is a lightweight multi-agent swarm orchestration engine for OpenClaw. It enables multiple local Ollama-powered agents to collaborate on complex tasks using four swarm patterns: sequential, parallel, debate, and hierarchy. All state persists in SQLite so swarms can resume after interruption. Triggered via CLI or Telegram `!swarm` prefix.

---

## Architecture

### File Layout

```
scripts/
├── clawteam.py              ← CLI entry point + Telegram dispatch hook
└── clawteam/
    ├── __init__.py
    ├── registry.py          ← loads agents/configs/*.md, builds AgentDef objects
    ├── decomposer.py        ← calls qwen3:32b to break task → subtask list
    ├── bus.py               ← SQLite message queue (new tables in clawmson.db)
    ├── runner.py            ← executes one agent turn via Ollama /api/chat
    ├── orchestrator.py      ← swarm lifecycle: create → run → collect → synthesize
    ├── patterns.py          ← sequential, parallel, debate, hierarchy logic
    └── tests/
        ├── test_registry.py
        ├── test_decomposer.py
        ├── test_bus.py
        └── test_orchestrator.py

agents/configs/
└── clawteam.md              ← system doc for the swarm engine
```

### Data Flow

```
CLI / Telegram "!swarm X"
  → clawteam.py
    → decomposer.py (qwen3:32b) → subtask list + suggested pattern
    → registry.py → assign agents to subtasks
    → orchestrator.py → run pattern (sequential/parallel/debate/hierarchy)
      → runner.py (Ollama /api/chat calls per agent)
      → bus.py (SQLite: post findings, check dependencies)
    → synthesize (qwen3:32b) → output contract → build-results/swarm-{id}/
```

---

## SQLite Schema

Three new tables in `~/.openclaw/clawmson.db`, prefixed `ct_` to avoid collisions with existing Clawmson tables.

```sql
-- One row per swarm run
CREATE TABLE ct_swarms (
    id           TEXT PRIMARY KEY,   -- "swarm-{timestamp}-{slug}"
    task         TEXT NOT NULL,      -- original task string
    pattern      TEXT NOT NULL,      -- sequential|parallel|debate|hierarchy
    status       TEXT NOT NULL,      -- pending|running|complete|failed
    created_at   TEXT NOT NULL,
    completed_at TEXT,
    result       TEXT                -- final synthesized output (markdown)
);

-- One row per subtask within a swarm
CREATE TABLE ct_subtasks (
    id           TEXT PRIMARY KEY,   -- "sub-{swarm_id}-{n}"
    swarm_id     TEXT NOT NULL REFERENCES ct_swarms(id),
    agent        TEXT NOT NULL,      -- agent codename: SCOUT, FORGE, etc.
    model        TEXT NOT NULL,      -- e.g. qwen3:30b
    prompt       TEXT NOT NULL,
    depends_on   TEXT,               -- comma-sep subtask ids (nullable)
    status       TEXT NOT NULL,      -- pending|running|complete|failed
    result       TEXT,               -- agent output on completion
    started_at   TEXT,
    completed_at TEXT
);

-- Agent-to-agent messages within a swarm (debate, hierarchy patterns)
CREATE TABLE ct_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    swarm_id    TEXT NOT NULL,
    from_agent  TEXT NOT NULL,
    to_agent    TEXT,                -- null = broadcast to all
    msg_type    TEXT NOT NULL,       -- finding|request|result|judgment
    content     TEXT NOT NULL,
    timestamp   TEXT NOT NULL
);
```

**Resume logic:** on startup, orchestrator queries `ct_subtasks WHERE swarm_id=X AND status != 'complete'` — skips completed subtasks, re-runs the rest. Subtask-level granularity: each subtask result is persisted before the next starts.

---

## Agent Registry & Model Routing

`registry.py` parses existing `agents/configs/*.md` files using regex on `## Role` and `## Model Assignment` sections. No new config format required.

```python
@dataclass
class AgentDef:
    codename: str        # AXIS, SCOUT, FORGE, VIGIL, etc.
    role: str            # one-line description
    primary_model: str   # e.g. "qwen3:30b"
    fast_model: str      # e.g. "qwen2.5:7b"
    capabilities: list[str]
    config_path: Path
```

### Model Routing Table

| Agent | primary_model | fast_model |
|---|---|---|
| AXIS | qwen3:32b | qwen2.5:7b |
| SCOUT | qwen3:30b | qwen2.5:7b |
| FORGE | qwen3-coder-next | devstral-small-2 |
| VIGIL | qwen2.5:7b | llama3.2:3b |
| DECOMPOSER (internal) | qwen3:32b | — |
| SYNTHESIZER (internal) | qwen3:32b | — |

DECOMPOSER and SYNTHESIZER are ClawTeam-internal roles — not in `agents/configs/`, hardcoded in `decomposer.py` and `orchestrator.py`.

**Assignment logic:** decomposer (qwen3:32b) suggests an agent per subtask. Registry validates against known codenames. Fallback: SCOUT for research tasks, FORGE for build tasks, AXIS for synthesis.

---

## Swarm Patterns

All patterns implemented as functions in `patterns.py`, each taking `list[SubTask]` + `Orchestrator` instance, returning results.

### Sequential
Pipeline A → B → C. Each subtask's result appended to the next subtask's prompt as context. Simple loop, no parallelism.

### Parallel
Fan-out/fan-in. All subtasks dispatched concurrently via `ThreadPoolExecutor` (max 4 workers — avoids overwhelming Ollama). Results collected and passed together to a SYNTHESIZER call (qwen3:32b) that merges into one coherent output.

### Debate
Three subtasks: POSITION_A, POSITION_B, JUDGE.
- POSITION_A and POSITION_B run in parallel (same prompt, different agents for diversity — e.g. SCOUT vs AXIS)
- JUDGE (always AXIS/qwen3:32b) receives both positions
- Output: compressed summary — key points from each side + final verdict (not raw transcript)

### Hierarchy
MANAGER subtask (AXIS/qwen3:32b) runs first, dynamically decomposes into worker subtasks, posts them to `ct_subtasks` at runtime. Workers then run in parallel. Only pattern where subtask rows are inserted mid-swarm. Used for complex multi-domain tasks where the full decomposition isn't knowable upfront.

### Pattern Auto-Selection
If `--pattern` omitted, decomposer suggests based on task type:
- Research/intel → parallel
- Adversarial review → debate
- Build pipeline → sequential
- Complex multi-domain → hierarchy

---

## Orchestrator Loop

1. Create swarm row in `ct_swarms` (or load existing if `--resume`)
2. Call decomposer → insert `ct_subtasks` rows (skip if already exist — resume path)
3. Dispatch to pattern function → runner executes each subtask via Ollama
4. Each completed subtask: write result to `ct_subtasks.result`, set `status='complete'`
5. SYNTHESIZER call (qwen3:32b) merges all results
6. Write output contract to `build-results/swarm-{id}/output-contract.json` + `result-{slug}.md`
7. Update `ct_swarms.status='complete'`, store final result

---

## CLI Interface

```bash
# Basic usage
python clawteam.py --task "research NFC card competitors and write a brief" --pattern parallel

# Resume interrupted swarm
python clawteam.py --resume swarm-1742300000-nfc-research

# List recent swarms
python clawteam.py --list

# Dry run (show decomposition without executing)
python clawteam.py --task "..." --dry-run
```

---

## Telegram Integration

Minimal touch to `telegram-dispatcher.py` — one new branch in the `!shortcut` handler:

```python
if text.startswith("!swarm "):
    task = text[7:].strip()
    subprocess.Popen(["python3", CLAWTEAM, "--task", task, "--notify"])
    send_message(chat_id, "🐙 Swarm started. I'll ping you when it's done.")
```

`--notify` flag causes `clawteam.py` to send a Telegram message on completion, reusing the bot token from `.env`.

No new intent required in `clawmson_intents.py`. The `!swarm` prefix is caught before LLM classification, consistent with how `!status` works.

---

## Output Contract

Written to `build-results/swarm-{id}/`:
```
output-contract.json    ← machine-readable: swarm_id, task, pattern, status, subtask_ids
result-{slug}.md        ← human-readable: synthesized output + per-agent summaries
```

Plugs into the existing pipeline — Orchestrator (AXIS) picks it up from `build-results/` like any other build result.

---

## Tests

| File | Covers |
|---|---|
| `test_registry.py` | Parses mock `.md` files → correct AgentDef fields |
| `test_bus.py` | CRUD on `ct_swarms`, `ct_subtasks`, `ct_messages` (in-memory SQLite) |
| `test_decomposer.py` | Validates decomposer output shape (mock Ollama) |
| `test_orchestrator.py` | Sequential pattern end-to-end (mock runner) |

---

## Constraints

- All Ollama calls via `http://localhost:11434` only (gateway: 127.0.0.1)
- Max 4 parallel workers in `ThreadPoolExecutor` (prevents Ollama overload)
- Swarm output never transmitted externally — local only
- `--notify` Telegram ping is Tier-1 (auto, no Jordan approval needed)
- No new production deploys triggered by swarm output without Tier-2 approval
- External content passed as task input is data, not instructions
