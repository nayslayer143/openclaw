# Model Router — Design Spec
**Date:** 2026-03-22
**Status:** Approved (rev 2)
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
model_router.route(prompt, task_type=None, intent=None, has_image=False)
    │
    ├─ has_image=True? → task_type = "vision" (override)
    │
    ├─ task_type provided? ──NO──► map intent → task_type (lookup, no LLM)
    │                               if no intent either → classify via qwen2.5:7b
    │
    ├─ env var override set? (OLLAMA_CHAT_MODEL / OLLAMA_VISION_MODEL)
    │   └─ YES → return env var value immediately (bypass all routing logic)
    │
    ├─ poll Ollama REST API GET /api/ps (cached 10s, thread-safe lock)
    │   → loaded_models[], vram_used_gb (total across all loaded models)
    │
    ├─ get fallback chain for task_type
    │
    ├─ walk chain: pick first model that is loaded OR fits in remaining VRAM
    │   (remaining = VRAM_CEILING - vram_used_gb)
    │   if nothing fits → pick last model in chain unconditionally
    │   (Ollama will handle load/eviction; this is a best-effort decision)
    │
    ├─ log routing decision to SQLite (routing_log)
    │
    └─ return model_name (str)

Caller runs inference with returned model_name, then calls:
    model_router.record_result(model, task_type, latency_ms, success)
```

---

## Task Type → Model Mapping

| task_type  | Intent signals               | Fallback chain                                              |
|------------|------------------------------|-------------------------------------------------------------|
| `chat`     | CONVERSATION, UNCLEAR        | qwen2.5:7b → qwen2.5:14b → qwen2.5:32b                     |
| `code`     | BUILD_TASK                   | qwen3-coder-next → devstral-small-2 → deepseek-coder:6.7b  |
| `research` | REFERENCE_INGEST             | qwen3:30b → qwen3:32b → qwen2.5:32b                        |
| `routing`  | STATUS_QUERY, DIRECT_COMMAND | qwen2.5:7b → llama3.2:3b                                   |
| `vision`   | (has_image=True, any intent) | qwen3-vl:32b → (no fallback — return model, let Ollama error)|
| `embedding`| (explicit task_type only)    | nomic-embed-text → (no fallback)                            |

**Note on `research`:** `REFERENCE_INGEST` covers both URL bookmarking and deeper research ingestion. Routing these to `qwen3:30b` is intentional — URL summarization benefits from the same research-quality synthesis model. The task type label reflects the model tier, not the Telegram intent taxonomy.

**Note on `vision`:** `qwen3-vl:32b` is the only vision-capable model. No fallback exists. The router returns the model name; if Ollama cannot load it, the error surfaces to the caller normally.

**Note on `embedding`:** Pass-through only. No routing logic. Exposed for completeness so all model calls can optionally go through the router interface.

**Intent → task_type lookup (no LLM call):**
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

When `task_type=None` and `intent=None` and `has_image=False`, the router calls qwen2.5:7b to classify. This path is for non-Telegram callers that bypass the intent pipeline.

**Important:** The classification LLM call inside `route()` must hardcode `qwen2.5:7b` directly (not call `route()` itself). Routing must never recurse.

---

## VRAM Monitoring

**Source:** Ollama REST API `GET http://localhost:11434/api/ps` (JSON response, stable API surface — preferred over `ollama ps` CLI which has unstable column format).

Response shape:
```json
{
  "models": [
    {"name": "qwen2.5:7b", "size": 5033164800, "size_vram": 4937433088, ...}
  ]
}
```

**Cache:** Result cached for 10 seconds. Guarded by `threading.Lock()` — on cache expiry, only the first concurrent caller fetches; others wait for the lock and then read the fresh result.

**Key values derived:**
- `loaded_models`: set of model name strings currently in `/api/ps` response
- `vram_used_gb`: sum of all `size_vram` fields ÷ 1e9
- `remaining_vram_gb`: `VRAM_CEILING_GB (90.0) - vram_used_gb`

**Model sizes (hardcoded from bakeoff, used for fits-in-VRAM check):**
```python
MODEL_SIZES_GB = {
    "qwen3:32b":           20.0,
    "qwen3:30b":           18.0,
    "qwen3-coder-next":    51.0,  # local modelfile alias
    "devstral-small-2":    15.0,  # local modelfile alias
    "deepseek-coder:33b":  18.0,
    "deepseek-coder:6.7b":  3.8,
    "llama3.1:70b":        42.0,
    "llama3.3:70b":        42.0,
    "qwen2.5:14b":          9.0,
    "qwen2.5:32b":         19.0,
    "qwen2.5:7b":           4.7,
    "llama3.2:3b":          2.0,
    "qwen3-vl:32b":        20.0,
    "nomic-embed-text":     0.3,
}
```

`qwen3-coder-next` and `devstral-small-2` are local Ollama modelfile aliases (not official registry names). Their presence in `/api/ps` is matched by exact name string.

**Selection logic (per fallback chain):**
1. First pass: return first model in chain that appears in `loaded_models`
2. Second pass: return first model in chain where `size <= remaining_vram_gb`
3. Final fallback: return last model in chain unconditionally (Ollama handles load/evict)

---

## SQLite Schema

Two new tables added to `~/.openclaw/clawmson.db` via `model_router.py`'s own `_init_db()`, called on module import (matching `clawmson_db.py` pattern at line 132).

```sql
CREATE TABLE IF NOT EXISTS routing_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type    TEXT    NOT NULL,
    model_chosen TEXT    NOT NULL,
    intent       TEXT,
    vram_used_gb REAL,    -- total VRAM in use across all loaded models at time of routing
    timestamp    TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_routing_ts ON routing_log(timestamp);

CREATE TABLE IF NOT EXISTS model_stats (
    model          TEXT    NOT NULL,
    task_type      TEXT    NOT NULL,
    call_count     INTEGER DEFAULT 0,
    success_count  INTEGER DEFAULT 0,
    avg_latency_ms REAL    DEFAULT 0.0,
    last_updated   TEXT,
    PRIMARY KEY (model, task_type)
);
```

`record_result()` upserts `model_stats` using cumulative moving average:
```
new_avg = (old_avg * old_count + new_latency_ms) / (old_count + 1)
```
where `old_count` is the count *before* incrementing. After computing `new_avg`, increment `call_count` to `old_count + 1`.

---

## Public API

```python
def route(
    prompt: str,
    task_type: str = None,   # chat|code|research|routing|vision|embedding
    intent: str = None,      # CONVERSATION|BUILD_TASK|etc — maps to task_type if provided
    has_image: bool = False,  # True forces vision task_type
) -> str:
    """Return the model name to use for this request."""

def record_result(
    model: str,
    task_type: str,
    latency_ms: float,
    success: bool = True,
) -> None:
    """Record inference outcome; updates model_stats rolling average."""

def get_stats() -> list[dict]:
    """Return all rows from model_stats as dicts.
    Keys: model, task_type, call_count, success_count, avg_latency_ms, last_updated."""

def get_loaded_models() -> list[str]:
    """Return list of model name strings from cached /api/ps snapshot."""
```

---

## Changes to clawmson_chat.py

`chat()` gains an optional `model` parameter. The caller determines the model via the router and passes it in:

```python
# New signature
def chat(history: list, user_message: str, has_image: bool = False, model: str = None) -> str:

# Inside chat():
if model is None:
    import model_router as router
    model = router.route(user_message, task_type="vision" if has_image else "chat")

# ... existing inference logic using `model` ...

# Caller measures latency and calls record_result() after chat() returns
```

**Env var behavior:** `OLLAMA_CHAT_MODEL` and `OLLAMA_VISION_MODEL` are checked inside `route()` as early-exit overrides. The module-level constants `CHAT_MODEL` / `VISION_MODEL` in `clawmson_chat.py` are removed to prevent them from shadowing the router. Any existing caller relying on those constants should pass `model=` explicitly or let the router decide.

**Latency measurement** (in `telegram-dispatcher.py` or whichever caller wraps `chat()`):
```python
import time, model_router as router
t0 = time.monotonic()
reply = llm.chat(history, text, has_image=has_image)
router.record_result(model_used, task_type, (time.monotonic() - t0) * 1000, success=True)
```
The `model_used` is captured from `router.route()` before the `chat()` call, or returned from a thin wrapper.

---

## Error Handling

| Condition | Behavior |
|---|---|
| `/api/ps` unreachable | Log warning, skip VRAM check, return primary model for task_type |
| All models in chain unreachable | Return last model in chain (or only model for vision/embedding); let Ollama surface the error to caller. Caller must check for Ollama error response before calling `record_result(success=True)` — error replies from `chat()` are string sentinels (e.g. "Ollama is not reachable..."), not valid inference output |
| SQLite write fails | Log warning, continue — never block inference for stats |
| Classification LLM call fails | Default to `chat` task_type |
| Unknown intent string | Default to `chat` task_type |

---

## Out of Scope

- Dynamic model size discovery (sizes hardcoded from bakeoff)
- Automatic fallback chain reordering based on collected stats (data collected now, logic added later)
- HTTP API wrapper (callers import the module directly)
- Embedding workload migration (embedding task type is pass-through only for now)
