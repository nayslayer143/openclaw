# Clawmson Memory Agent Config — Hermes 5-Layer System

## Overview

Clawmson's memory system (Hermes) gives the bot persistent, layered memory across conversations.
All memory is per-`chat_id`. Memory is injected into the system prompt as `### Memory Context` before each reply.

## Layers

| Layer | Storage | Purpose |
|-------|---------|---------|
| 1. Sensory Buffer | RAM deque (10 msgs) | Immediate context passed as Ollama history |
| 2. Short-Term Memory | SQLite stm_summaries | Rolling window, auto-summarized when 50+ rows |
| 3. Episodic Memory | SQLite episodic_memories + nomic embeddings | Significant events (deploys, failures, decisions) |
| 4. Semantic Memory | SQLite semantic_facts + nomic embeddings | Facts and preferences (explicit or inferred) |
| 5. Procedural Memory | SQLite procedures | Trigger→action mappings (explicit + auto-proposed) |

## Configuration (env vars)

| Variable | Default | Description |
|----------|---------|-------------|
| CLAWMSON_SENSORY_WINDOW | 10 | Messages kept in RAM sensory buffer |
| CLAWMSON_STM_MAX_ROWS | 50 | Active rows before STM summarization fires |
| CLAWMSON_STM_BATCH | 25 | Rows archived per summarization cycle |
| CLAWMSON_EPISODIC_TOP_K | 3 | Max episodic memories returned per query |
| CLAWMSON_EPISODIC_MIN_SIM | 0.6 | Cosine similarity threshold for episodic recall |
| CLAWMSON_SEMANTIC_TOP_K | 5 | Max semantic facts returned per query |
| CLAWMSON_SEMANTIC_MIN_SIM | 0.5 | Cosine similarity threshold for semantic recall |
| CLAWMSON_SEMANTIC_MIN_CONF | 0.6 | Minimum confidence for semantic fact retrieval |
| CLAWMSON_PROC_THRESHOLD | 3 | Occurrences before auto-proposing a procedure |
| CLAWMSON_EMBED_MODEL | nomic-embed-text | Embedding model via Ollama |

## Telegram Commands

| Command | Description |
|---------|-------------|
| /memory [query] | Show current memory context (optional query filter) |
| /memory-stats | Show row counts per layer |
| /forget-memory [layer] | Clear memory (all, stm, episodic, semantic, procedural) |
| /remember key: value | Store explicit semantic fact |
| /approve-proc <id> | Approve auto-proposed procedure |
| /reject-proc <id> | Reject auto-proposed procedure (tombstone) |

## DB Tables

- `conversations` — all messages (archived=1 for old rows, never deleted)
- `stm_summaries` — STM summarization records
- `episodic_memories` — significant events with embeddings
- `semantic_facts` — key/value facts with embeddings (UNIQUE on chat_id+key)
- `procedures` — trigger→action mappings (active/pending_approval/rejected)
- `procedure_candidates` — occurrence counter before promotion to pending_approval

## Migration

Run once after deployment:
```
python3 ~/openclaw/scripts/clawmson_memory_migrate.py
```

Safe to re-run — all operations are idempotent.

## Models Used

- **Chat / summarization / significance detection**: `qwen2.5:7b` (OLLAMA_CHAT_MODEL)
- **Embeddings**: `nomic-embed-text` (CLAWMSON_EMBED_MODEL)
- **Inference**: background ThreadPoolExecutor(max_workers=1) — never blocks Telegram replies
