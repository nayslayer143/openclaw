# Clawmson Hermes 5-Layer Memory System — Design Spec
**Date:** 2026-03-22
**Status:** Approved
**Scope:** `scripts/clawmson_memory.py`, `scripts/clawmson_memory_migrate.py`, `scripts/tests/test_clawmson_memory.py`, `agents/configs/clawmson-memory.md`

---

## Overview

Upgrades Clawmson from a stateless task dispatcher into a conversational AI assistant with persistent, layered memory. The system is implemented as a single new module (`clawmson_memory.py`) using Approach B — a layered module with a thin `MemoryManager` coordinator. Each of the five memory layers is a discrete class with a single clear purpose, testable in isolation.

All memory persists in the existing SQLite DB at `~/.openclaw/clawmson.db`. Embedding-based similarity uses `nomic-embed-text` via Ollama with in-memory cosine similarity (numpy). No new external dependencies beyond numpy.

---

## Architecture

### Call Flow (per Telegram message)

```
Telegram msg
  → handle_message()          [dispatcher — unchanged]
    → db.save_message()         [existing]
    → dispatch_conversation()   [existing]
      → memory.sensory()        [new — RAM deque, instant]
      → memory.retrieve()       [new — queries layers 2-5, ~50ms]
      → llm.chat(..., memory_context)  [chat.py — one new param]
      → db.save_message()       [existing]
      → memory.ingest_async()   [new — background thread, non-blocking]
      → send()                  [existing]
```

### Integration Points (only two files change)

**`telegram-dispatcher.py` — `_conversation_thread()`:**
```python
# Before
history = db.get_history(chat_id, limit=50)
reply   = llm.chat(history, effective_text, has_image=has_image)
db.save_message(chat_id, "assistant", reply)

# After
history        = memory.sensory(chat_id)
memory_context = memory.retrieve(chat_id, effective_text)
reply          = llm.chat(history, effective_text, has_image=has_image,
                          memory_context=memory_context)
db.save_message(chat_id, "assistant", reply)
memory.ingest_async(chat_id, "user", effective_text)
memory.ingest_async(chat_id, "assistant", reply)
```

**`clawmson_chat.py` — `chat()`:**
```python
def chat(history: list, user_message: str, has_image: bool = False,
         memory_context: str = "") -> str:
    system_prompt = _load_system_prompt()
    if memory_context:
        system_prompt = system_prompt + "\n\n" + memory_context
    # rest of function unchanged
```

---

## Database Schema

Four new tables are added to `clawmson.db`. The existing three tables (`conversations`, `context`, `refs`) are untouched.

```sql
-- Short-Term Memory: rolling summaries when conversation window fills
CREATE TABLE IF NOT EXISTS stm_summaries (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id   TEXT    NOT NULL,
    summary   TEXT    NOT NULL,
    msg_from  INTEGER NOT NULL,  -- conversations.id range that was summarized
    msg_to    INTEGER NOT NULL,
    timestamp TEXT    NOT NULL
);

-- Episodic Memory: significant events with emotional valence
CREATE TABLE IF NOT EXISTS episodic_memories (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id   TEXT    NOT NULL,
    content   TEXT    NOT NULL,  -- original exchange snippet
    summary   TEXT    NOT NULL,  -- LLM-distilled 1-sentence episode description
    timestamp TEXT    NOT NULL,
    valence   TEXT    NOT NULL DEFAULT 'neutral',  -- positive/negative/neutral/critical
    embedding BLOB                                  -- nomic float32, numpy.tobytes()
);

-- Semantic Memory: extracted facts and preferences
CREATE TABLE IF NOT EXISTS semantic_facts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id    TEXT    NOT NULL,
    key        TEXT    NOT NULL,  -- short label: "preferred orchestration model"
    value      TEXT    NOT NULL,  -- full fact: "Jordan prefers qwen3:32b for orchestration"
    confidence REAL    NOT NULL DEFAULT 0.8,
    source     TEXT    NOT NULL DEFAULT 'inferred',  -- 'inferred' or 'explicit'
    timestamp  TEXT    NOT NULL,
    embedding  BLOB,
    UNIQUE(chat_id, key)  -- upserted on update, no duplicates
);

-- Procedural Memory: trigger→action mappings
CREATE TABLE IF NOT EXISTS procedures (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id            TEXT    NOT NULL,
    trigger_pattern    TEXT    NOT NULL,
    action_description TEXT    NOT NULL,
    created_by         TEXT    NOT NULL DEFAULT 'explicit',  -- 'explicit' or 'proposed'
    status             TEXT    NOT NULL DEFAULT 'active',    -- 'active', 'pending_approval', 'rejected'
    occurrence_count   INTEGER NOT NULL DEFAULT 1,
    last_triggered     TEXT,
    timestamp          TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_stm_chat        ON stm_summaries(chat_id);
CREATE INDEX IF NOT EXISTS idx_episodic_chat   ON episodic_memories(chat_id);
CREATE INDEX IF NOT EXISTS idx_semantic_chat   ON semantic_facts(chat_id);
CREATE INDEX IF NOT EXISTS idx_procedures_chat ON procedures(chat_id, status);
```

**Embedding format:** `numpy.array(vector, dtype=numpy.float32).tobytes()` → BLOB.
Deserialized with `numpy.frombuffer(blob, dtype=numpy.float32)`.
Cosine similarity computed in-memory across all rows for a chat_id (negligible at personal-bot scale).

The existing `context` table remains readable but receives no new writes — `semantic_facts` supersedes it for new data.

---

## The Five Layers

### Layer 1 — SensoryBuffer

**Purpose:** Immediate conversational context for every Ollama call.

```python
class SensoryBuffer:
    _buffers: dict[str, deque]  # chat_id → deque(maxlen=10)
```

- Holds last 10 messages per chat_id in RAM (no DB reads after warm-up).
- `get(chat_id) -> list[dict]`: returns messages as `[{"role": ..., "content": ...}]`, oldest first. Passed directly as Ollama `messages` history, replacing `db.get_history(limit=50)`.
- Cold start (bot restart): seeds from `db.get_history(limit=10)` once per chat_id on first access.
- Updated synchronously on every `ingest()` call.

**Tuning knob:** `SENSORY_WINDOW = 10` (env: `CLAWMSON_SENSORY_WINDOW`)

---

### Layer 2 — ShortTermMemory

**Purpose:** Rolling context for "what were we just talking about?" queries.

- Reads/writes the existing `conversations` table.
- After each `ingest()`: if row count for `chat_id` > 50, take the oldest 25 rows, summarize via `qwen2.5:7b` ("Summarize these N exchanges in 3-5 sentences"), store in `stm_summaries`, delete the raw rows.
- `retrieve(chat_id) -> str`: returns the 2 most recent summaries as plain text. Empty string if none exist (sensory buffer covers recent context).
- Summarization runs synchronously inside the background ingest thread — does not block the Telegram reply.

**Tuning knobs:** `STM_MAX_ROWS = 50`, `STM_SUMMARIZE_BATCH = 25`, `STM_RETRIEVE_COUNT = 2`

---

### Layer 3 — EpisodicMemory

**Purpose:** Significant events and outcomes, retrievable by semantic similarity.

**Ingest pipeline (async, runs after reply is sent):**
1. **Rule pass:** scan message pair for trigger keywords: `deploy`, `broke`, `failed`, `fixed`, `shipped`, `decided`, `remember`, `never again`, `that worked`, `rollback`, `merged`, `approved`, `launched`, emotional intensifiers. If ≥1 hit → continue to LLM pass.
2. **LLM pass** (`qwen2.5:7b`, non-streaming, JSON format): prompt asks "Is this exchange episodically significant? If yes, write a 1-sentence episode summary and tag valence." Returns `{"significant": bool, "summary": str, "valence": str}`.
3. If significant: embed `summary` via `nomic-embed-text` → store in `episodic_memories`.

**Retrieve:** embed query → load all episodic embeddings for chat_id → cosine similarity → return top 3 summaries with timestamps and valence tags.

**Output format:**
```
[Episodic] [2026-03-18, critical] Deployed auth fix, broke login for 2h — rolled back.
[Episodic] [2026-03-20, positive] Shipped InformationCube landing page, Jordan approved.
```

**Tuning knobs:** `EPISODIC_TOP_K = 3`, `EPISODIC_MIN_SIMILARITY = 0.6`

---

### Layer 4 — SemanticMemory

**Purpose:** Facts, preferences, and knowledge about Jordan and the projects.

**Ingest pipeline (async):**
1. **Rule pass:** patterns `"I prefer"`, `"I always"`, `"I hate"`, `"we use"`, `"the model is"`, `"Jordan likes"`, `"never use"`, `"I never"`. Also triggers on explicit `/remember fact: <key> = <value>` command.
2. **LLM pass** (`qwen2.5:7b`, JSON): "Extract any stated facts or preferences as `[{key, value, confidence}]` pairs. Return empty list if none."
3. Upsert into `semantic_facts` (unique on `chat_id + key`). Re-embed value text on update.

**Retrieve:** embed query → cosine similarity across all semantic facts for chat_id → return top 5.

**Output format:**
```
[Semantic] Jordan prefers qwen3:32b for orchestration tasks (confidence: 0.9)
[Semantic] Never mock the database in tests — prod migration broke last quarter (confidence: 1.0)
```

**Tuning knobs:** `SEMANTIC_TOP_K = 5`, `SEMANTIC_MIN_CONFIDENCE = 0.6`, `SEMANTIC_MIN_SIMILARITY = 0.5`

---

### Layer 5 — ProceduralMemory

**Purpose:** Learned workflows and patterns triggered by Jordan's phrasing.

**Two creation paths:**

- **Explicit:** `/remember when I say "<trigger>" → <action>`. Parses trigger and action, inserts with `created_by='explicit'`, `status='active'` immediately. Active on next message.
- **Auto-proposed:** Track `(intent, action)` pair occurrences per chat. After 3 occurrences of the same pattern with no matching active procedure → create `status='pending_approval'` row → send Jordan: `"I've noticed you keep asking me to <action> when you mention '<trigger>'. Want me to remember that? /approve-proc <id> or /reject-proc <id>"`.

**Retrieve:** keyword match of `trigger_pattern` against current query text. Returns matching `action_description` for all active procedures. No embedding needed — triggers are short and exact.

**Output format:**
```
[Procedural] When Jordan says "scout X" → run research pipeline on X.
```

---

## MemoryManager — Public API

```python
class MemoryManager:
    """Coordinator. Owns all five layer instances."""

    def sensory(self, chat_id: str) -> list:
        """Return last 10 messages for Ollama history. Seeds from DB on cold start."""

    def retrieve(self, chat_id: str, query: str) -> str:
        """
        Query layers 2-5. Assemble and return memory context block.
        Returns "" if nothing relevant found.
        Output kept under 500 tokens total.
        """

    def ingest(self, chat_id: str, role: str, content: str):
        """Synchronous. Updates sensory buffer + STM. Triggers async work for layers 3-5."""

    def ingest_async(self, chat_id: str, role: str, content: str):
        """Non-blocking. Fires ingest() in a daemon thread."""

    def add_procedure(self, chat_id: str, trigger: str, action: str) -> int:
        """Explicit /remember command. Returns procedure id."""

    def approve_procedure(self, chat_id: str, proc_id: int):
        """Jordan approved a proposed procedure. Sets status='active'."""

    def reject_procedure(self, chat_id: str, proc_id: int):
        """Jordan rejected. Deletes row, resets occurrence counter."""

    def stats(self, chat_id: str) -> dict:
        """Returns counts per layer: {sensory, stm, episodic, semantic, procedural}."""

    def clear(self, chat_id: str, layer: str = "all"):
        """Clears memory for a specific layer or all layers."""
```

**`retrieve()` assembled output example:**
```
### Memory Context
[Short-term] We've been working on the GonzoClaw site redesign. Jordan approved the nav structure last week.

[Episodic] [2026-03-18, critical] Deployed auth fix, broke login for 2h — rolled back.
[Episodic] [2026-03-20, positive] Shipped InformationCube landing page, Jordan approved.

[Semantic] Jordan prefers qwen3:32b for orchestration tasks (confidence: 0.9)
[Semantic] Never mock the database in tests — prod migration broke last quarter (confidence: 1.0)

[Procedural] When Jordan says "scout X" → run research pipeline on X.
```

---

## New Telegram Commands

Added to `telegram-dispatcher.py` command routing:

| Command | Handler | Description |
|---------|---------|-------------|
| `/memory` | `handle_memory()` | Show current `retrieve()` output |
| `/memory-stats` | `handle_memory_stats()` | Counts per layer |
| `/forget-memory [layer]` | `handle_forget_memory()` | Clear all or one layer |
| `/remember <trigger> → <action>` | `handle_remember_procedure()` | Explicit procedure |
| `/approve-proc <id>` | `handle_approve_proc()` | Approve pending procedure |
| `/reject-proc <id>` | `handle_reject_proc()` | Reject pending procedure |

---

## Files Produced

| File | Purpose |
|------|---------|
| `scripts/clawmson_memory.py` | Main module — all 5 layer classes + MemoryManager |
| `scripts/clawmson_memory_migrate.py` | One-shot DB migration script |
| `scripts/tests/test_clawmson_memory.py` | 15 unit tests (offline, in-memory DB) |
| `agents/configs/clawmson-memory.md` | Agent config documenting the system |

**Modified files:**
| File | Change |
|------|--------|
| `scripts/telegram-dispatcher.py` | `_conversation_thread()` + 6 new command handlers |
| `scripts/clawmson_chat.py` | Add `memory_context: str = ""` param to `chat()` |
| `scripts/clawmson_db.py` | Add 4 new tables to `_init_db()` |

---

## Tests

All tests use `CLAWMSON_DB_PATH=:memory:` and a mocked Ollama client. No running model required.

| Test | Layer | What it verifies |
|------|-------|-----------------|
| `test_sensory_buffer_limit` | 1 | Caps at 10, oldest evicted |
| `test_sensory_cold_start` | 1 | Seeds from DB on first access |
| `test_stm_summarize_triggers` | 2 | Summarization fires when conversations > 50 |
| `test_stm_retrieve_empty` | 2 | Returns `""` when no summaries exist |
| `test_episodic_rule_pass` | 3 | Keyword triggers rule pass |
| `test_episodic_rule_no_match` | 3 | Neutral message skips LLM call |
| `test_episodic_store_retrieve` | 3 | Stores episode, cosine search returns it |
| `test_semantic_upsert` | 4 | Same key updates, no duplicate |
| `test_semantic_retrieve_topk` | 4 | Returns ≤5 most similar facts |
| `test_procedural_explicit` | 5 | `/remember` creates active procedure immediately |
| `test_procedural_proposal` | 5 | 3 occurrences triggers pending_approval |
| `test_procedural_approve_reject` | 5 | Status transitions correct |
| `test_retrieve_assembles_context` | all | Full retrieve() output under 500 tokens |
| `test_clear_layer` | all | clear(episodic) deletes only episodic rows |
| `test_ingest_async_nonblocking` | all | ingest_async() returns immediately |

---

## Tuning Reference

| Knob | Default | Env var |
|------|---------|---------|
| Sensory window | 10 msgs | `CLAWMSON_SENSORY_WINDOW` |
| STM max rows before summarize | 50 | `CLAWMSON_STM_MAX_ROWS` |
| STM summarize batch size | 25 | `CLAWMSON_STM_BATCH` |
| STM summaries returned | 2 | `CLAWMSON_STM_RETRIEVE_COUNT` |
| Episodic top-k | 3 | `CLAWMSON_EPISODIC_TOP_K` |
| Episodic min cosine similarity | 0.6 | `CLAWMSON_EPISODIC_MIN_SIM` |
| Semantic top-k | 5 | `CLAWMSON_SEMANTIC_TOP_K` |
| Semantic min confidence | 0.6 | `CLAWMSON_SEMANTIC_MIN_CONF` |
| Semantic min cosine similarity | 0.5 | `CLAWMSON_SEMANTIC_MIN_SIM` |
| Procedural proposal threshold | 3 occurrences | `CLAWMSON_PROC_THRESHOLD` |
| Memory model | `qwen2.5:7b` | `OLLAMA_CHAT_MODEL` |
| Embedding model | `nomic-embed-text` | `CLAWMSON_EMBED_MODEL` |
