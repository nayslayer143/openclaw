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
    summary       TEXT,            -- NULL when session ended ungracefully (kill -9, power loss)
    UNIQUE(session_key, chat_id)
);
CREATE INDEX IF NOT EXISTS idx_sessions_chat ON sessions(chat_id, started_at DESC);
```

**FTS5 availability**: The implementation must verify FTS5 support at startup with
`conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_check USING fts5(x)")` and
log a warning + disable FTS if unavailable (macOS system Python may ship without FTS5).
Test files must include a `@unittest.skipUnless(FTS5_AVAILABLE, "FTS5 not supported")` guard.

### FTS sync strategy

`db.fts_index(chat_id, source, source_id, content, ts)` is the single FTS insertion point.
Each call site **must capture `cursor.lastrowid` in the same connection context** as the INSERT
and pass it as `source_id`. The five call sites are:

| Insert site | Source label | Content indexed | `source_id` from |
|---|---|---|---|
| `db.save_message()` | `conversation` | message content | `cursor.lastrowid` after INSERT into conversations |
| `db.save_reference()` | `reference` | title + " " + summary | `cursor.lastrowid` after INSERT into refs |
| `EpisodicMemory.ingest()` | `episodic` | summary | `cursor.lastrowid` after INSERT into episodic_memories |
| `SemanticMemory.ingest()` / `ingest_explicit()` | `semantic` | key + ": " + value | `cursor.lastrowid` after INSERT/UPSERT into semantic_facts |
| `ShortTermMemory.check_and_summarize()` | `stm` | summary | `cursor.lastrowid` after INSERT into stm_summaries |

`db.fts_index()` accepts an optional `conn` argument. When provided, the FTS INSERT runs
inside the caller's existing transaction (required for `save_message` and `save_reference`
which use `with db._get_conn() as conn:`). When `conn=None`, a new connection is opened.

**FTS and `MemoryManager.clear()`**: When `clear(chat_id, layer)` deletes rows from a source
table, FTS entries for those rows are **not** automatically removed in this version. This is a
known limitation: `/search` may return stale results after `/forget-memory`. Acceptable for
v1; FTS-on-clear deferred to a future iteration.

---

## Module: `clawmson_fts.py`

```python
FTS5_AVAILABLE: bool  # set at module init by probing sqlite3

def index(chat_id: str, source: str, source_id: int, content: str, ts: str,
          conn=None):
    """Insert one item into memory_fts. No-op if FTS5 unavailable."""

def remove(source: str, source_id: int):
    """Delete item from memory_fts by source + source_id. No-op if FTS5 unavailable."""

def search(chat_id: str, query: str, limit: int = 10) -> list[dict]:
    """
    BM25-ranked FTS5 search scoped to chat_id.
    Returns list of {source, content, snippet, ts, rank}.
    Returns [] if FTS5 unavailable or query is empty.

    Query is wrapped in double-quotes for phrase search before passing to MATCH,
    e.g. query="hello world" → MATCH '"hello world"'.
    OperationalError from malformed FTS5 queries is caught and returns [].

    SQL pattern:
      SELECT source, content, snippet(memory_fts,0,'>>','<<','...',8) AS snippet,
             ts, rank
      FROM memory_fts
      WHERE memory_fts MATCH ? AND chat_id = ?
      ORDER BY rank LIMIT ?
    """

def format_results(results: list[dict]) -> str:
    """Format search results for Telegram /search reply.
    Each result: '[source] snippet (ts)'
    Returns 'No results found.' if list is empty.
    """
```

### Integration into `retrieve()`

After assembling STM / episodic / semantic / procedural results, run `fts.search(chat_id, query, limit=CLAWMSON_FTS_LIMIT)`. Append results labeled `[Search]`, deduplicating by `source_id` against any episodic/semantic results already included. Apply the existing 2000-char cap to the combined output.

Deduplication rule: skip FTS result if `(source, source_id)` already appears in the context (tracked as a set during assembly, not string prefix matching).

### Fallback behavior

If `_embed()` raises (Ollama unreachable), `retrieve()` catches the exception per layer and falls through to FTS results. Memory context degrades gracefully — FTS results are returned rather than an empty string.

---

## Module: `clawmson_sessions.py`

```python
SESSION_KEY_FILE = Path(os.environ.get(
    "CLAWMSON_SESSION_KEY_FILE", "/tmp/clawmson-session-key.txt"
))
RESUME_WINDOW_HOURS = int(os.environ.get("CLAWMSON_RESUME_WINDOW_HOURS", "24"))

def start_session() -> str:
    """
    Generate UUID session_key, write to SESSION_KEY_FILE.
    Returns session_key. Called once on dispatcher boot.
    Session DB records are created lazily per chat_id on first message.
    """

def ensure_session(session_key: str, chat_id: str):
    """
    INSERT OR IGNORE session record for (session_key, chat_id).
    Increments message_count on every call (including the INSERT).
    Called per-message from dispatcher.
    """

def end_all_sessions(session_key: str):
    """
    Called on SIGTERM/SIGINT. Sets ended_at = utcnow() for all open sessions
    under session_key. Does NOT generate LLM summaries (avoids blocking shutdown
    and race with executor). summary remains NULL for ungracefully-ended sessions.

    get_resume_context() handles NULL summary gracefully (returns "" in that case).
    """

def get_resume_context(chat_id: str, current_session_key: str) -> str:
    """
    Find the most recent session for chat_id where session_key != current_session_key.

    Returns "### Previous Session\n<summary>" if ALL of:
      - ended_at IS NOT NULL (session ended gracefully — end_all_sessions was called)
      - ended_at is within RESUME_WINDOW_HOURS of utcnow()
      - summary IS NOT NULL and non-empty

    Returns "" in all other cases, including:
      - No previous session exists (first ever run)
      - ended_at IS NULL (killed without SIGTERM — power loss, kill -9)
      - summary IS NULL (end_all_sessions ran but no summary was generated)
      - Gap exceeds RESUME_WINDOW_HOURS
    """
```

**Session summary generation** (deferred from SIGTERM): Instead of LLM summarization at
shutdown, the summary is generated lazily. When `end_all_sessions()` sets `ended_at`,
it also queues a background task via the existing `MemoryManager._executor` to fetch
the last 20 messages and generate a 3-sentence LLM summary for each open session.
The executor's `max_workers=1` serializes these writes. If the process is killed before
the task completes, `summary` remains NULL and `get_resume_context()` returns `""` —
acceptable degraded behavior.

**`end_all_sessions()` contract**: Sets `ended_at` synchronously (blocking but instant —
just a DB write). Submits LLM summary tasks to `MemoryManager._executor` as fire-and-forget.
Calls `MemoryManager._executor.shutdown(wait=False)` to allow in-flight tasks to complete
without blocking `sys.exit(0)`.

### Resume injection in dispatcher

```python
_SESSION_KEY: str = ""                    # set on boot
_resumed: set[str] = set()               # chat_ids already resumed this process run
_resumed_lock = threading.Lock()          # guards check-then-add

# In _conversation_thread():
memory_context = _memory.retrieve(chat_id, effective_text)
with _resumed_lock:
    already_resumed = chat_id in _resumed
    if not already_resumed:
        _resumed.add(chat_id)
if not already_resumed:
    resume = sessions.get_resume_context(chat_id, _SESSION_KEY)
    if resume:
        memory_context = resume + "\n\n" + memory_context
```

The lock ensures that two concurrent `_conversation_thread` calls for the same `chat_id`
cannot both inject resume context (TOCTOU race prevention).

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

`/search <query>` registered in `/slash commands` block **before** `/memory-stats` (most
specific first). Empty-arg behavior: if the text after `/search` is blank, reply with
`"Usage: /search <query>"` and return.

Full routing entry:
```python
if lower.startswith("/search"):
    query = text[len("/search"):].strip()
    if not query:
        send(chat_id, "Usage: /search <query>")
    else:
        results = fts.search(chat_id, query, limit=CLAWMSON_SEARCH_LIMIT)
        send(chat_id, fts.format_results(results))
    return
```

---

## Tests

### `scripts/tests/test_clawmson_fts.py` (8 tests)

All tests guarded with `@unittest.skipUnless(FTS5_AVAILABLE, "FTS5 not supported")`.
`FTS5_AVAILABLE` is imported from `clawmson_fts`.

| Test | Assertion |
|---|---|
| `test_fts_tables_exist` | `memory_fts` in `sqlite_master` after `_init_db()` |
| `test_fts_index_and_search` | Index one item, search returns it with `rank` field |
| `test_fts_cross_layer` | Items from `conversation`, `episodic`, `semantic` all returned |
| `test_fts_chat_id_scoped` | chat_id A results don't include chat_id B items |
| `test_fts_remove` | Removed item no longer in results |
| `test_fts_in_retrieve_fallback` | `retrieve()` returns FTS results when `_embed()` raises |
| `test_search_command_formats_results` | `format_results()` returns string with source labels |
| `test_fts_malformed_query_returns_empty` | `search(chat_id, '"')` returns `[]`, no exception |

### `scripts/tests/test_clawmson_sessions.py` (6 tests)

| Test | Assertion |
|---|---|
| `test_start_session_writes_key_file` | Key file created with valid UUID |
| `test_ensure_session_creates_record` | First call creates row; second increments `message_count` |
| `test_end_all_sessions_sets_ended_at` | `ended_at` populated for all open sessions |
| `test_get_resume_context_recent` | Session ended <24h with summary returns `### Previous Session` block |
| `test_get_resume_context_stale` | Session ended >24h returns `""` |
| `test_get_resume_context_null_ended_at` | Session with `ended_at=NULL` (kill -9 case) returns `""` |

**Total after this feature: 39 tests** (25 existing + 14 new).

---

## Migration

`clawmson_memory_migrate.py` is idempotent — re-running after this feature adds the two new
tables without touching existing data. FTS index starts empty and is populated going forward
(no backfill of historical messages).

---

## Config (env vars)

| Variable | Default | Description |
|---|---|---|
| `CLAWMSON_RESUME_WINDOW_HOURS` | `24` | Max hours since last session to inject resume context |
| `CLAWMSON_SESSION_KEY_FILE` | `/tmp/clawmson-session-key.txt` | Where session key is written on boot |
| `CLAWMSON_FTS_LIMIT` | `5` | Max FTS results injected into `retrieve()` context |
| `CLAWMSON_SEARCH_LIMIT` | `10` | Max results for `/search` command |
