# Model Router — Design Spec
**Date:** 2026-03-22
**Status:** Approved
**Scope:** `scripts/model_router.py` (new) + `scripts/clawmson_chat.py` (update)

---

## Problem

OpenClaw runs 14 Ollama models locally. All Clawmson chat currently routes to a single hardcoded model (`qwen2.5:7b`). There is no awareness of task complexity, VRAM state, or model load status. Heavy tasks (code generation, synthesis) get the same cheap model as quick chat replies.

## Goal

A lightweight routing layer that picks the best available model for each request based on task type, current VRAM usage, and historical latency/success data — with graceful fallback chains when the primary model is unavailable.

---

## Architecture

```
Caller (clawmson_chat.py, cron script, agent)
    │
    ▼
model_router.route(prompt, task_type=None, intent=None)
    │
    ├─ task_type provided? ──NO──► map intent → task_type (lookup, no LLM call)
    │                               if no intent either → classify via qwen2.5:7b
    │
    ├─ poll ollama ps (cached 10s) → loaded_models, vram_used_gb
    │
    ├─ get fallback chain for task_type
    │
    ├─ walk chain: pick first model that is loaded OR fits in available VRAM
    │   (if nothing fits → pick smallest fallback unconditionally)
    │
    ├─ log routing decision to SQLite (routing_log table)
    │
    └─ return model_name (str)

Caller runs inference, then calls:
    model_router.record_result(model, task_type, latency_ms, success)
```

---

## Task Type → Model Mapping

| task_type  | Intent signals              | Fallback chain                                              |
|------------|-----------------------------|-------------------------------------------------------------|
| `chat`     | CONVERSATION, UNCLEAR       | qwen2.5:7b → qwen2.5:14b → qwen2.5:32b                     |
| `code`     | BUILD_TASK                  | qwen3-coder-next → devstral-small-2 → deepseek-coder:6.7b  |
| `research` | REFERENCE_INGEST            | qwen3:30b → qwen3:32b → qwen2.5:32b                        |
| `routing`  | STATUS_QUERY, DIRECT_COMMAND| qwen2.5:7b → llama3.2:3b                                   |
| `vision`   | (has_image=True, any intent) | qwen3-vl:32b → (no fallback — return model, caller decides)|
| `embedding`| (explicit only)             | nomic-embed-text → (no fallback)                            |

**Intent → task_type mapping (lookup table, no LLM):**
```python
INTENT_TO_TASK = {
    "CONVERSATION":     "chat",
    "UNCLEAR":          "chat",
    "BUILD_TASK":       "code",
    "REFERENCE_INGEST": "research",
    "STATUS_QUERY":     "routing",
    "DIRECT_COMMAND":   "routing",
}
```

When `task_type=None` and `intent=None`, the router calls qwen2.5:7b to classify (only for non-Telegram callers that bypass the intent pipeline).

---

## VRAM Monitoring

- Parse `ollama ps` via subprocess on each `route()` call
- Cache result for 10 seconds (avoid repeated subprocess overhead)
- VRAM ceiling: **90 GB** (6 GB headroom on M2 Max 96 GB)
- "Loaded" = model appears in `ollama ps` output
- "Fits" = current `vram_used_gb + model_size_gb ≤ 90`
- Model sizes are hardcoded from CLAUDE.md bakeoff data (no dynamic lookup needed)

**Selection logic:**
1. Prefer loaded models (no cold-load penalty)
2. Among unloaded: prefer those that fit in available VRAM
3. If nothing fits: use last model in chain unconditionally (smallest fallback)

---

## SQLite Schema

Two new tables added to `~/.openclaw/clawmson.db` (existing db, no new file):

```sql
CREATE TABLE IF NOT EXISTS routing_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type    TEXT    NOT NULL,
    model_chosen TEXT    NOT NULL,
    intent       TEXT,
    vram_used_gb REAL,
    timestamp    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS model_stats (
    model        TEXT NOT NULL,
    task_type    TEXT NOT NULL,
    call_count   INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    avg_latency_ms REAL DEFAULT 0,
    last_updated TEXT,
    PRIMARY KEY (model, task_type)
);
```

`record_result()` upserts into `model_stats` using a rolling average:
```
new_avg = (old_avg * (n-1) + new_latency) / n
```

---

## Public API

```python
# Primary — returns model name string
route(prompt: str, task_type: str = None, intent: str = None) -> str

# Call after inference completes to feed the stats loop
record_result(model: str, task_type: str, latency_ms: float, success: bool = True) -> None

# Diagnostics
get_stats() -> list[dict]          # model_stats rows
get_loaded_models() -> list[str]   # current ollama ps snapshot (uses cache)
```

---

## Changes to clawmson_chat.py

```python
# Before
model = VISION_MODEL if has_image else CHAT_MODEL

# After
import model_router as router
task_type = "vision" if has_image else "chat"
model = router.route(user_message, task_type=task_type)
```

**Env var override preserved:** If `OLLAMA_CHAT_MODEL` or `OLLAMA_VISION_MODEL` are set, the router skips its logic and returns the env var value directly. Backwards compatible.

---

## Error Handling

- `ollama ps` fails → log warning, skip VRAM check, return primary model for task_type
- All models in chain unreachable → return last model in chain, let caller surface the error
- SQLite write fails → log and continue (never block inference for stats)
- Classification LLM call fails → default to `chat` task_type

---

## Out of Scope

- Dynamic model size discovery (sizes hardcoded from bakeoff)
- Automatic fallback chain reordering based on stats (future — data collected now, logic added later)
- Multi-GPU or distributed routing
- HTTP API wrapper (callers import the module directly)
