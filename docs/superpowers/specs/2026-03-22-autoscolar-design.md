# AutoScholar Design Spec
**Date:** 2026-03-22
**Status:** Reviewed (pass 3)
**Module:** `scripts/autoresearch/scholar.py`

---

## Overview

AutoScholar integrates HuggingFace's "Papers for Agents" feature into OpenClaw's research and build pipeline. It discovers, ranks, digests, and routes academic papers — surfacing actionable research to Clawmson, ClawTeam, and the overnight research loop.

---

## Architecture

Single module (`scholar.py`) with four layered responsibilities:

```
Discovery  →  Digestion  →  Action Routing  →  Telegram / Cron
```

All AI inference via local Ollama. Data in `~/.openclaw/clawmson.db`. Reports to `autoresearch/outputs/papers/`.

---

## Data Layer

### New tables added to `clawmson_db.py` `_init_db()`

```sql
CREATE TABLE IF NOT EXISTS papers (
    paper_id        TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    authors         TEXT,             -- JSON array
    abstract        TEXT,
    url             TEXT,
    relevance_score REAL,
    discovered_at   TEXT NOT NULL,    -- UTC ISO timestamp, set by save_paper()
    digested        INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS paper_digests (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id                 TEXT NOT NULL,   -- no FK enforcement (SQLite default)
    key_findings             TEXT,     -- JSON array of bullet strings
    implementable_techniques TEXT,     -- JSON array
    linked_models            TEXT,     -- JSON array of HF model/dataset IDs
    relevance_to_builds      TEXT,
    priority                 TEXT,     -- P1 / P2 / P3
    action_taken             TEXT,     -- comma-joined: improvement, bakeoff, build_note, none
    digested_at              TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_papers_digested ON papers(digested);
CREATE INDEX IF NOT EXISTS idx_papers_score ON papers(relevance_score);
CREATE INDEX IF NOT EXISTS idx_digests_paper ON paper_digests(paper_id);
```

> **Note:** SQLite does not enforce `FOREIGN KEY` constraints unless `PRAGMA foreign_keys = ON` is set per connection. This codebase does not set that pragma. The `paper_id` column in `paper_digests` is a logical reference only. `scholar.py` must ensure a `papers` row exists (via `save_paper`) before inserting into `paper_digests`.

### DB helper functions in `scholar.py`

| Function | Return | Purpose |
|----------|--------|---------|
| `save_paper(paper_id, title, authors, abstract, url, relevance_score)` | None | INSERT OR IGNORE; `discovered_at` is set to `datetime.utcnow().isoformat()` inside the function |
| `mark_digested(paper_id)` | None | Set digested=1 |
| `save_digest(paper_id, findings, techniques, models, relevance, priority, action)` | None | Insert digest row; `digested_at` set inside |
| `get_undigested(limit=20)` | `list[dict]` | Rows from `papers` where `digested=0`, ordered by `relevance_score DESC` |
| `get_recent_papers(days=7)` | `dict` | `{"total": int, "digested": int, "top_titles": list[str]}` — papers discovered in last N days. Filter: `WHERE discovered_at >= cutoff` using ISO string comparison (SQLite sorts ISO timestamps lexicographically — works correctly as long as all values are written by `datetime.utcnow().isoformat()`). |
| `get_paper_for_debate(paper_id, full=False)` | `dict` | ClawTeam shim — see spec below |

---

## Discovery Layer

### HuggingFace API endpoints

| Endpoint | Purpose |
|----------|---------|
| `https://huggingface.co/api/papers?search={query}` | Keyword/semantic search |
| `https://huggingface.co/api/papers` | Daily trending papers |
| `https://huggingface.co/papers/{paper_id}.md` | Full paper as clean markdown |

All HuggingFace HTTP requests use `timeout=HF_REQUEST_TIMEOUT` (module-level constant, default `30` seconds).

### Functions

**`search_papers(query, limit=20) -> list[dict]`**
Hits HF search API. Deduplicates against existing `papers` table (skips known `paper_id`s). Returns raw candidates.

**`embed_text(text) -> list[float]`**
Calls `nomic-embed-text` via `http://localhost:11434/api/embeddings`. Used for abstract ranking and goal vector.

**Project goal vector** — assembled at module load, embedded once, cached in memory:
```
"agent orchestration, prediction markets, memory architectures,
local LLM optimization, multi-agent systems, RAG, tool use,
web business automation, NFC cards, information products"
```

**`rank_by_relevance(candidates) -> list[dict]`**
Embeds each abstract. Computes cosine similarity against goal vector. Attaches `relevance_score`. Sorts descending. Papers below threshold are stored but not auto-digested.

> **Calibration note:** `nomic-embed-text` returns normalized vectors; cosine similarity range is [-1, 1]. The default threshold of 0.75 is a starting point — after first run, check the score distribution and adjust `SCHOLAR_RELEVANCE_THRESHOLD` if relevant papers are being filtered out.

**`discover(query=None, limit=10) -> list[dict]`**
Full pipeline: search or trending → deduplicate → embed + rank → save to DB → return ranked list.

---

## Digestion Layer

**`fetch_paper_markdown(paper_id) -> str`**
`GET https://huggingface.co/papers/{paper_id}.md` with `timeout=HF_REQUEST_TIMEOUT`. On HTTP error: look up abstract from `papers` table and return it. If paper also not in DB: return empty string. Caller must handle empty string.

**`digest_paper(paper_id) -> dict`**

**Unknown paper handling:** if `paper_id` is not in `papers` table, attempt `fetch_paper_markdown` anyway. If markdown is returned:
- Extract a real title by looking for the first `# Heading` line in the markdown; fall back to `paper_id` as the title if no heading found.
- Call `save_paper(paper_id, title=extracted_title, authors=None, abstract=None, url=f"https://huggingface.co/papers/{paper_id}", relevance_score=None)` before proceeding.
- Action routing still fires normally (title will be real, not "unknown").

If fetch returns empty string, return `{"error": "unknown_paper", "paper_id": paper_id}` immediately without any DB writes.

Steps:
1. Fetch markdown (or abstract fallback; empty string → early return)
2. Build extraction prompt for `qwen3:30b`. The `[active project context]` placeholder is replaced with the same static goal vector string used for embedding (defined in Discovery Layer). It is not dynamic:

```
Given this research paper, extract:
1. KEY_FINDINGS: 3-7 bullet points of the most important findings
2. IMPLEMENTABLE_TECHNIQUES: specific techniques we could build right now,
   in the context of: agent orchestration, prediction markets, memory
   architectures, local LLM optimization, multi-agent systems, RAG, tool use,
   web business automation
3. LINKED_MODELS: any HuggingFace model/dataset IDs mentioned
4. RELEVANCE_TO_BUILDS: how this relates to the above domains
5. PRIORITY: P1 (use now) / P2 (useful soon) / P3 (interesting later)

Return JSON only.
```

3. **Defensive JSON parsing:** strip markdown fences if present (` ```json ... ``` `), then `json.loads()`. On parse failure, log the raw response and return `{"error": "parse_failed", "raw": raw[:200]}`. Do not raise. This mirrors the try/except pattern in `clawmson_intents.py`.
4. On successful parse: save to `paper_digests`, mark paper as digested, run action routing.

**`digest_batch(paper_ids, delay=5) -> list[dict]`**
Loops `digest_paper()` with `delay` seconds between calls (named parameter, default 5). Tests pass `delay=0` to avoid real sleep. Used by auto-mode.

---

## Action Routing

Runs after each successful digest. **All matching rules fire** (not first-match-wins). `action_taken` stores a comma-joined string of all actions taken (e.g. `"improvement,bakeoff"`), or `"none"` if no rules matched.

"Implementable technique present" means `implementable_techniques` is a non-empty list (`len > 0` after JSON parse); empty list `[]`, `null`, or empty string do not trigger the rule.

| Condition | Action |
|-----------|--------|
| P1 + `len(implementable_techniques) > 0` | Write `improvements/scholar-[slug]-[date].md` |
| `len(linked_models) > 0` | Append to `benchmark/bakeoff-queue.md` (create if missing) |
| P1 + `relevance_to_builds` is non-empty string | Write `autoresearch/outputs/papers/academic-[slug]-[date].md` |
| No rules matched | Record `action_taken = "none"` |

**`bakeoff-queue.md` append format:**
```markdown
## [date] — [paper_id]
- Title: [title]
- Models: [comma-separated model IDs]
- Source: autoscholar
```

**Directory creation:** `scholar.py` calls `.mkdir(parents=True, exist_ok=True)` at module load for:
- `~/openclaw/autoresearch/outputs/papers/`
- `~/openclaw/improvements/`
- `~/openclaw/benchmark/`

---

## Telegram Integration

**Import in `telegram-dispatcher.py`:**
`scripts/` is already on `sys.path` via the existing bootstrap (line 40-42). The only requirement is that `scripts/autoresearch/__init__.py` exists. Add one import line:

```python
from autoresearch import scholar
```

No additional `sys.path` manipulation needed.

New slash commands added to `handle_message()` in `telegram-dispatcher.py`, in the `/slash commands` block:

| Command | Match rule | Behavior |
|---------|------------|----------|
| `/papers [topic]` | `text.lower().startswith("/papers")` | `discover(query=text[len("/papers"):].strip(), limit=5)` — format top 5 as summary |
| `/digest [paper_id]` | `text.lower().startswith("/digest ")` | `digest_paper(paper_id)` — send formatted digest; if result contains `"error"` key, send error to user |
| `/scholar [subcommand]` | `text.lower().startswith("/scholar")` | Parse remainder: `"status"` → `get_recent_papers(days=7)`; anything else → show brief help |

Note: Telegram delivers commands as the first token (e.g. `/scholar`), not the full string. Match on `startswith` and parse the subcommand from the remainder of `text`.

**`/digest` guard:** the dispatcher surfaces the error dict returned by `digest_paper()` (see Digestion Layer unknown-paper handling). No additional DB lookup needed — `digest_paper` already handles this path. Reply text: `"Paper [id] not found. Try /papers [topic] to discover it first."`

Natural language ("find papers on prediction market forecasting") handled by existing CONVERSATION intent — Clawmson detects scholar intent within chat handler and calls `discover()` inline. No new intent constant needed.

---

## Auto Mode

**`auto_mode(domains=None) -> dict`**
Entry point for cron:
1. For each configured domain keyword → `discover(query=keyword, limit=20)`
2. Filter: `relevance_score >= SCHOLAR_RELEVANCE_THRESHOLD` (env var, default 0.75)
3. `digest_batch()` on qualifying papers
4. Generate daily digest → `autoresearch/outputs/papers/academic-scholar-digest-[date].md`
5. Return `{"discovered": N, "digested": N, "actions_taken": ["improvement", "bakeoff", ...], "top_titles": list[str]}` — `top_titles` is the titles of the top 5 digested papers by relevance_score, used in the Telegram summary.

**Default domain keywords:**
```python
["agent orchestration", "prediction markets", "memory architectures",
 "local LLM optimization", "multi-agent systems", "RAG retrieval augmented",
 "tool use LLM", "agentic systems"]
```

**`scripts/cron-scholar.sh`**

- Schedule: nightly at 2am (`0 2 * * *`)
- Calls `auto_mode()` via a Python one-liner that prints JSON to stdout:

```bash
RESULT=$(python3 -c "
import json, sys
sys.path.insert(0, '$OPENCLAW_ROOT/scripts')
from autoresearch import scholar
print(json.dumps(scholar.auto_mode()))
")
DISCOVERED=$(echo "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['discovered'])")
DIGESTED=$(echo "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['digested'])")
ACTIONS=$(echo "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(','.join(d['actions_taken']) or 'none')")
```

- Logs to `$OPENCLAW_ROOT/logs/cron-scholar.log` (follows pattern of all peer cron scripts)
- Sends Telegram summary via `notify-telegram.sh` with this message template:

```
AutoScholar Nightly — [date]

Discovered: [N] papers
Digested: [N] papers
Actions taken: [comma-joined list or "none"]

Top papers:
• [title 1]
• [title 2]
...

Review at: ~/openclaw/autoresearch/outputs/papers/
```

- Separate from `cron-autoresearch.sh`

---

## ClawTeam Integration

```python
def get_paper_for_debate(paper_id: str, full: bool = False) -> dict:
    """
    Returns digest data for ClawTeam debate pattern.
    Joins papers + paper_digests tables.

    If paper exists but has no digest (digested=0): returns partial dict
    with title/abstract/url populated and digest fields as None.
    If paper_id unknown entirely: returns {"error": "not_found"}.

    full=True triggers a live fetch via fetch_paper_markdown(paper_id)
    (adds latency, may fail; caller should handle empty string return).

    Returns:
        {
            "title": str,
            "abstract": str,
            "key_findings": list[str] | None,
            "implementable_techniques": list[str] | None,
            "relevance_to_builds": str | None,
            "url": str,
            "full_markdown": str | None   # only if full=True, live HTTP fetch
        }
    """
```

ClawTeam calls this, builds a debate prompt, runs `clawteam.py --pattern debate`. Scholar has no dependency on ClawTeam.

---

## Configuration

| Env var | Default | Purpose |
|---------|---------|---------|
| `SCHOLAR_RELEVANCE_THRESHOLD` | `0.75` | Minimum score for auto-digest (calibrate after first run) |
| `SCHOLAR_DIGEST_MODEL` | `qwen3:30b` | Ollama model for digestion |
| `SCHOLAR_EMBED_MODEL` | `nomic-embed-text` | Ollama model for embeddings |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Existing, shared |

**Module-level constants in `scholar.py`:**
```python
HF_REQUEST_TIMEOUT = 30  # seconds, applied to all HuggingFace HTTP calls
```

---

## File Outputs

| Output | Path | Naming |
|--------|------|--------|
| Daily digest report | `autoresearch/outputs/papers/` | `academic-scholar-digest-[date].md` |
| Improvement proposal | `improvements/` | `scholar-[slug]-[date].md` |
| Bakeoff flag | `benchmark/bakeoff-queue.md` | Append (created if missing) |
| Build context note | `autoresearch/outputs/papers/` | `academic-[slug]-[date].md` |
| Agent config doc | `agents/configs/` | `autoresearch-scholar.md` |

---

## Tests (`scripts/tests/test_scholar.py`)

| Test | What it verifies |
|------|-----------------|
| `test_fetch_paper_markdown` | Mocks `requests.get`, verifies markdown returned |
| `test_fetch_paper_markdown_fallback_http_error` | HTTP error → returns abstract from DB |
| `test_fetch_paper_markdown_fallback_unknown_paper` | HTTP error + no DB row → returns empty string |
| `test_digest_paper` | Mocks Ollama call, verifies digest saved to DB and paper marked digested |
| `test_digest_paper_json_parse_error` | Malformed LLM response returns error dict, no DB write |
| `test_rank_by_relevance` | Mocks embed calls, verifies cosine sort order |
| `test_auto_mode_threshold` | Papers below threshold are stored but not digested |
| `test_get_paper_for_debate` | Returns correct fields; `full_markdown` only when `full=True` |
| `test_get_paper_for_debate_undigested` | Partial dict returned when digest row missing |
| `test_get_paper_for_debate_not_found` | Returns `{"error": "not_found"}` for unknown paper_id |

---

## New Files

| File | Purpose |
|------|---------|
| `scripts/autoresearch/scholar.py` | Main module |
| `scripts/autoresearch/__init__.py` | Package marker |
| `scripts/tests/test_scholar.py` | Tests |
| `scripts/cron-scholar.sh` | Nightly cron entry point |
| `agents/configs/autoresearch-scholar.md` | System documentation |

## Modified Files

| File | Change |
|------|--------|
| `scripts/clawmson_db.py` | Add `papers` + `paper_digests` tables + indexes to `_init_db()` |
| `scripts/telegram-dispatcher.py` | Add `from autoresearch import scholar` + `/papers`, `/digest`, `/scholar` command handlers |
