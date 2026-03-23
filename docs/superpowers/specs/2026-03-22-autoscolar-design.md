# AutoScholar Design Spec
**Date:** 2026-03-22
**Status:** Approved
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
    discovered_at   TEXT NOT NULL,
    digested        INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS paper_digests (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id                 TEXT NOT NULL REFERENCES papers(paper_id),
    key_findings             TEXT,     -- JSON array of bullet strings
    implementable_techniques TEXT,     -- JSON array
    linked_models            TEXT,     -- JSON array of HF model/dataset IDs
    relevance_to_builds      TEXT,
    priority                 TEXT,     -- P1 / P2 / P3
    action_taken             TEXT,     -- improvement / bakeoff / build_note / none
    digested_at              TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_papers_digested ON papers(digested);
CREATE INDEX IF NOT EXISTS idx_papers_score ON papers(relevance_score);
CREATE INDEX IF NOT EXISTS idx_digests_paper ON paper_digests(paper_id);
```

### DB helper functions in `scholar.py`

| Function | Purpose |
|----------|---------|
| `save_paper(paper_id, title, authors, abstract, url, relevance_score)` | Insert or ignore |
| `mark_digested(paper_id)` | Set digested=1 |
| `save_digest(paper_id, findings, techniques, models, relevance, priority, action)` | Insert digest row |
| `get_undigested(limit=20)` | For auto-mode sweep |
| `get_recent_papers(days=7)` | For `/scholar status` |
| `get_paper_for_debate(paper_id, full=False)` | ClawTeam shim — returns digest dict, optionally includes full_markdown |

---

## Discovery Layer

### HuggingFace API endpoints

| Endpoint | Purpose |
|----------|---------|
| `https://huggingface.co/api/papers?search={query}` | Keyword/semantic search |
| `https://huggingface.co/api/papers` | Daily trending papers |
| `https://huggingface.co/papers/{paper_id}.md` | Full paper as clean markdown |

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

**`discover(query=None, limit=10) -> list[dict]`**
Full pipeline: search or trending → deduplicate → embed + rank → save to DB → return ranked list.

---

## Digestion Layer

**`fetch_paper_markdown(paper_id) -> str`**
`GET https://huggingface.co/papers/{paper_id}.md`. Falls back to abstract if fetch fails.

**`digest_paper(paper_id) -> dict`**
1. Fetch markdown (or abstract fallback)
2. Build extraction prompt for `qwen3:30b`:

```
Given this research paper, extract:
1. KEY_FINDINGS: 3-7 bullet points of the most important findings
2. IMPLEMENTABLE_TECHNIQUES: specific techniques we could build right now
3. LINKED_MODELS: any HuggingFace model/dataset IDs mentioned
4. RELEVANCE_TO_BUILDS: how this relates to [active project context]
5. PRIORITY: P1 (use now) / P2 (useful soon) / P3 (interesting later)

Return JSON only.
```

3. Parse JSON → save to `paper_digests` → mark paper as digested
4. Run action routing (see below)

**`digest_batch(paper_ids) -> list[dict]`**
Loops `digest_paper()` with 5s delay between calls. Used by auto-mode.

---

## Action Routing

Runs after each digest. Rules evaluated in order:

| Condition | Action |
|-----------|--------|
| P1 + implementable technique present | Write `improvements/scholar-[slug]-[date].md` |
| Linked HF models found | Append flag to `benchmark/bakeoff-queue.md` |
| P1 + relevance to active build | Write `autoresearch/outputs/papers/academic-[slug]-[date].md` |
| P2/P3 or no action matched | Record `action_taken = "none"` |

---

## Telegram Integration

New slash commands added to `telegram-dispatcher.py`:

| Command | Behavior |
|---------|----------|
| `/papers [topic]` | `discover(query=topic, limit=5)` — format top 5 as summary |
| `/digest [paper_id]` | `digest_paper(paper_id)` — send formatted digest |
| `/scholar status` | `get_recent_papers(days=7)` — counts + top titles |

Natural language ("find papers on prediction market forecasting") handled by existing CONVERSATION intent — Clawmson detects scholar intent within chat handler and calls `discover()` inline. No new intent constant needed.

---

## Auto Mode

**`auto_mode(domains=None) -> dict`**
Entry point for cron:
1. For each configured domain keyword → `discover(query=keyword, limit=20)`
2. Filter: `relevance_score >= SCHOLAR_RELEVANCE_THRESHOLD` (env var, default 0.75)
3. `digest_batch()` on qualifying papers
4. Generate daily digest → `autoresearch/outputs/papers/academic-scholar-digest-[date].md`
5. Return `{discovered: N, digested: N, actions_taken: [...]}`

**Default domain keywords:**
```python
["agent orchestration", "prediction markets", "memory architectures",
 "local LLM optimization", "multi-agent systems", "RAG retrieval augmented",
 "tool use LLM", "agentic systems"]
```

**`scripts/cron-scholar.sh`**
- Schedule: nightly at 2am (`0 2 * * *`)
- Calls `auto_mode()` via Python
- Sends Telegram summary via `notify-telegram.sh`
- Separate from `cron-autoresearch.sh`

---

## ClawTeam Integration

```python
def get_paper_for_debate(paper_id: str, full: bool = False) -> dict:
    """
    Returns digest data for ClawTeam debate pattern.
    Caller builds the swarm prompt; this function provides the subject.

    Returns:
        {
            "title": str,
            "abstract": str,
            "key_findings": list[str],
            "implementable_techniques": list[str],
            "relevance_to_builds": str,
            "url": str,
            "full_markdown": str | None   # only if full=True
        }
    """
```

ClawTeam calls this, builds a debate prompt, runs `clawteam.py --pattern debate`. Scholar has no dependency on ClawTeam.

---

## Configuration

| Env var | Default | Purpose |
|---------|---------|---------|
| `SCHOLAR_RELEVANCE_THRESHOLD` | `0.75` | Minimum score for auto-digest |
| `SCHOLAR_DIGEST_MODEL` | `qwen3:30b` | Ollama model for digestion |
| `SCHOLAR_EMBED_MODEL` | `nomic-embed-text` | Ollama model for embeddings |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Existing, shared |

---

## File Outputs

| Output | Path | Naming |
|--------|------|--------|
| Daily digest report | `autoresearch/outputs/papers/` | `academic-scholar-digest-[date].md` |
| Improvement proposal | `improvements/` | `scholar-[slug]-[date].md` |
| Bakeoff flag | `benchmark/` | `bakeoff-queue.md` (append) |
| Build context note | `autoresearch/outputs/papers/` | `academic-[slug]-[date].md` |
| Agent config doc | `agents/configs/` | `autoresearch-scholar.md` |

---

## Tests (`scripts/tests/test_scholar.py`)

| Test | What it verifies |
|------|-----------------|
| `test_fetch_paper_markdown` | Mocks `requests.get`, verifies markdown returned |
| `test_fetch_paper_markdown_fallback` | Verifies fallback to abstract on HTTP error |
| `test_digest_paper` | Mocks Ollama call, verifies digest saved to DB and paper marked digested |
| `test_rank_by_relevance` | Mocks embed calls, verifies cosine sort order |
| `test_auto_mode_threshold` | Papers below threshold are stored but not digested |
| `test_get_paper_for_debate` | Returns correct fields, full_markdown only when full=True |

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
| `scripts/clawmson_db.py` | Add `papers` + `paper_digests` tables to `_init_db()` |
| `scripts/telegram-dispatcher.py` | Add `/papers`, `/digest`, `/scholar` command handlers |
