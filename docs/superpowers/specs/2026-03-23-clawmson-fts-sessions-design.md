# Clawmson FTS5 Search + Session Persistence Design

## Goal

Add FTS5 full-text search across all Hermes memory layers and restart-bounded session tracking with automatic resume context injection to Clawmson.

## Architecture

Two new modules, three modified files:

| File | Role |
|---|---|
| `scripts/clawmson_fts.py` (new) | FTS5 index management — index, search, remove, format |
| `scripts/clawmson_sessions.py` (new) | Session lifecycle — start, ensure, end, resume context |
| `scripts/clawmson_db.py` (modify) | Add `memory_fts` + `sessions` tables; add `fts_index()` helper; update `save_message()` and `save_reference()` to sync FTS |
| `scripts/clawmson_memory.py` (modify) | Add FTS results section to `retrieve()`; add `get_resume_context()` to MemoryManager |
| `scripts/telegram-dispatcher.py` (modify) | Session start on boot, SIGTERM handler, resume inject on first post-restart message per chat_id, new `/search` command |

FTS5 and cosine similarity are **complementary**. FTS5 handles keyword/phrase matches and works without Ollama; cosine finds semantic neighbors. Both feed into `retrieve()`.

Sessions are **restart-bounded**: one global session key per bot process run, one session record per `(session_key, chat_id)`. Resume context is injected automatically into the first Ollama call after a restart if the previous session ended within 24 hours.

---

## Database Schema

### New tables (added to `_init_db()`)

```sql
-- FTS5 virtual table — indexes content from all memory layers
CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
    content,                  -- searchable text
    source    UNINDEXED,      -- 'conversation'|'episodic'|'semantic'|'stm'|'reference'
    chat_id   UNINDEXED,
    source_id UNINDEXED,      -- rowid in the source table
    ts        UNINDEXED,
    tokenize = 'porter unicode61'
);

-- Session tracking — one record per (session_key, chat_id)
CREATE TABLE IF NOT EXISTS sessions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_key   TEXT NOT NULL,
    chat_id       TEXT NOT NULL,
    started_at    TEXT NOT NULL,
    ended_at      TEXT,
    message_count INTEGER NOT NULL DEFAULT 0,
    summary       TEXT,
    UNIQUE(session_key, chat_id)
);
CREATE INDEX IF NOT EXISTS idx_sessions_chat ON sessions(chat_id, started_at DESC);
```

### FTS sync strategy

`db.fts_index(chat_id, source, source_id, content, ts)` is the single FTS insertion point. Called from:

| Insert site | Source label | Content indexed |
|---|---|---|
| `db.save_message()` | `conversation` | message content |
| `db.save_reference()` | `reference` | title + " " + summary |
| `EpisodicMemory.ingest()` | `episodic` | summary |
| `SemanticMemory.ingest()` / `ingest_explicit()` | `semantic` | key + ": " + value |
| `ShortTermMemory.check_and_summarize()` | `stm` | summary |

---

## Module: `clawmson_fts.py`

```python
def index(chat_id: str, source: str, source_id: int, content: str, ts: str):
    """Insert one item into memory_fts."""

def remove(source: str, source_id: int):
    """Delete item from memory_fts by source + source_id."""

def search(chat_id: str, query: str, limit: int = 10) -> list[dict]:
    """
    BM25-ranked FTS5 search scoped to chat_id.
    Returns list of {source, content, snippet, ts, rank}.
    Uses: SELECT ... FROM memory_fts WHERE memory_fts MATCH ? AND chat_id = ?
          ORDER BY rank LIMIT ?
    snippet() function used for highlighted excerpts.
    """

def format_results(results: list[dict]) -> str:
    """Format search results for Telegram /search reply."""
```

### Integration into `retrieve()`

After assembling STM / episodic / semantic / procedural results, run FTS search on the same query. Append any results whose content does not prefix-match anything already in the context block, labeled `[Search]`. Cap total context at the existing 2000-char limit.

### Fallback behavior

If `_embed()` raises (Ollama unreachable), `retrieve()` catches the exception per layer and falls through to FTS results. Memory context degrades gracefully — FTS results are returned rather than an empty string.

---

## Module: `clawmson_sessions.py`

```python
SESSION_KEY_FILE = Path("/tmp/clawmson-session-key.txt")
RESUME_WINDOW_HOURS = 24  # configurable via CLAWMSON_RESUME_WINDOW_HOURS

def start_session() -> str:
    """
    Generate UUID session_key, write to SESSION_KEY_FILE.
    Returns session_key. Called once on dispatcher boot.
    Session DB records are created lazily per chat_id on first message.
    """

def ensure_session(session_key: str, chat_id: str):
    """
    INSERT OR IGNORE session record for (session_key, chat_id).
    Increments message_count. Called per-message from dispatcher.
    """

def end_all_sessions(session_key: str):
    """
    Called on SIGTERM/SIGINT.
    For each open session under session_key:
      - Fetch last 20 messages for that chat_id from conversations table
      - Generate LLM summary (3 sentences, best-effort, non-blocking with 30s timeout)
      - Set ended_at = now(), store summary
    """

def get_resume_context(chat_id: str, current_session_key: str) -> str:
    """
    Find the most recent session for chat_id where session_key != current_session_key.
    If ended_at is within RESUME_WINDOW_HOURS and summary is non-empty:
      return "### Previous Session\n<summary>"
    Else: return "".
    """
```

### Resume injection in dispatcher

```python
_SESSION_KEY: str = ""          # set on boot
_resumed: set[str] = set()      # chat_ids already resumed this process run

# In _conversation_thread():
memory_context = _memory.retrieve(chat_id, effective_text)
if chat_id not in _resumed:
    resume = sessions.get_resume_context(chat_id, _SESSION_KEY)
    if resume:
        memory_context = resume + "\n\n" + memory_context
    _resumed.add(chat_id)
```

SIGTERM handler registered in `main()`:
```python
import signal
signal.signal(signal.SIGTERM, lambda sig, frame: _shutdown())
signal.signal(signal.SIGINT,  lambda sig, frame: _shutdown())

def _shutdown():
    sessions.end_all_sessions(_SESSION_KEY)
    sys.exit(0)
```

### New Telegram command

`/search <query>` — calls `fts.search(chat_id, query)` and returns `fts.format_results()`. Registered in `/slash commands` block before `/memory`.

---

## Tests

### `scripts/tests/test_clawmson_fts.py` (7 tests)

| Test | Assertion |
|---|---|
| `test_fts_tables_exist` | `memory_fts` in `sqlite_master` after `_init_db()` |
| `test_fts_index_and_search` | Index one item, search returns it with `rank` field |
| `test_fts_cross_layer` | Items from `conversation`, `episodic`, `semantic` all returned |
| `test_fts_chat_id_scoped` | chat_id A results don't include chat_id B items |
| `test_fts_remove` | Removed item no longer in results |
| `test_fts_in_retrieve_fallback` | `retrieve()` returns FTS results when `_embed()` raises |
| `test_search_command_formats_results` | `format_results()` returns string with source labels |

### `scripts/tests/test_clawmson_sessions.py` (5 tests)

| Test | Assertion |
|---|---|
| `test_start_session_writes_key_file` | `/tmp/clawmson-session-key.txt` created with UUID |
| `test_ensure_session_creates_record` | First call creates row; second increments `message_count` |
| `test_end_all_sessions_sets_ended_at` | `ended_at` populated, summary stored after end |
| `test_get_resume_context_recent` | Session ended <24h returns `### Previous Session` block |
| `test_get_resume_context_stale` | Session ended >24h returns `""` |

**Total after this feature: 37 tests** (25 existing + 12 new).

---

## Migration

`clawmson_memory_migrate.py` is idempotent — re-running after this feature adds the two new tables without touching existing data. FTS index starts empty; it is populated going forward (no backfill of historical messages).

---

## Config (env vars)

| Variable | Default | Description |
|---|---|---|
| `CLAWMSON_RESUME_WINDOW_HOURS` | `24` | Max hours since last session to inject resume context |
| `CLAWMSON_SESSION_KEY_FILE` | `/tmp/clawmson-session-key.txt` | Where session key is written on boot |
| `CLAWMSON_FTS_LIMIT` | `5` | Max FTS results injected into `retrieve()` context |
| `CLAWMSON_SEARCH_LIMIT` | `10` | Max results for `/search` command |
