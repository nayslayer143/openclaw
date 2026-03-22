# Twitter Scout Pipeline — Design Spec
**Date:** 2026-03-22
**Project:** Clawmson (OpenClaw Telegram Bot)
**Status:** Approved

---

## Overview

A Twitter/X link scouting pipeline for Clawmson. Jordan pastes Twitter/X links into Telegram; Clawmson extracts tweet content using a multi-strategy fallback chain, categorizes each tweet via local Ollama inference, stores results in SQLite, and returns an immediate digest. A daily-repeatable workflow with `/scout` command for on-demand digests.

---

## Architecture

### File Map

```
scripts/
├── clawmson_twitter.py      NEW  — extraction + categorization engine
├── clawmson_scout.py        NEW  — Telegram UX layer (handle, digest, format)
├── clawmson_db.py           MOD  — scout_links table + 3 new functions (additive only)
└── telegram-dispatcher.py  MOD  — pre-route Twitter detection + /scout command
```

No separate config file. Nitter instances and settings live as module-level constants in `clawmson_twitter.py`, matching the existing codebase pattern.

### Data Flow

```
Telegram message
  → dispatcher pre-route check (Twitter URL regex — runs BEFORE intent classification)
    → _scout_thread (background thread)
      → clawmson_scout.handle_scout_links()
        → clawmson_twitter.process_batch()
          → extract_tweet() [nitter → fxtwitter → oembed fallback chain]
          → categorize_tweet() [qwen2.5:7b via Ollama, format: json]
          → extract_github_repos()
        → clawmson_db.save_scout_link() × N
      → format_scout_report() → send to Telegram

/scout command
  → clawmson_scout.generate_digest() → send to Telegram
```

---

## Data Model

New table in `clawmson_db.py`, added via the existing `_init_db()` call:

```sql
CREATE TABLE IF NOT EXISTS scout_links (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id         TEXT NOT NULL,
    url             TEXT NOT NULL,
    author          TEXT,
    tweet_text      TEXT,
    category        TEXT,
    relevance_score INTEGER,
    summary         TEXT,
    action_items    TEXT,       -- JSON array
    github_repos    TEXT,       -- JSON array
    linked_urls     TEXT,       -- JSON array
    processed_at    TEXT NOT NULL,
    raw_data        TEXT        -- JSON blob of full extraction result
);
CREATE INDEX IF NOT EXISTS idx_scout_chat ON scout_links(chat_id);
CREATE INDEX IF NOT EXISTS idx_scout_cat  ON scout_links(category);
```

**Category values:** `tool | technique | business_intel | code_pattern | market_intel | irrelevant | extraction_failed`

**New DB functions (additive, no existing functions changed):**
- `save_scout_link(chat_id, url, extraction, categorization)` — inserts one row
- `get_scout_links(chat_id, since_hours=24, category=None)` — filtered fetch
- `get_scout_digest(chat_id, since_hours=24)` — counts by category + top items by relevance

---

## Module: `clawmson_twitter.py`

### Constants

```python
NITTER_INSTANCES = [
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
    "https://nitter.net",
]
RATE_LIMIT_DELAY = 0.5   # seconds between requests to nitter
REQUEST_TIMEOUT  = 15    # seconds
SCOUT_MODEL      = os.environ.get("OLLAMA_SCOUT_MODEL", "qwen2.5:7b")
```

### Extraction Fallback Chain

`extract_tweet(url: str) -> dict` tries strategies in order, stopping on first success:

1. **Nitter (primary)** — replaces `x.com`/`twitter.com` with each nitter instance domain, fetches HTML, calls `parse_nitter(html)` (BeautifulSoup). Tries all instances before giving up.
2. **FxTwitter (fallback 1)** — replaces domain with `fxtwitter.com`, parses Open Graph meta tags via `parse_fxtwitter(url)`.
3. **OEmbed (fallback 2)** — hits `https://publish.twitter.com/oembed?url={url}`, strips HTML from returned `html` field via `parse_oembed(url)`.
4. **All fail** — returns `{"extraction_failed": True, "methods_tried": [...], "url": url}`.

All three parsers return the same dict shape:
```python
{
    "author": str,
    "text": str,
    "media_urls": list,
    "linked_urls": list,
    "timestamp": str,
    "raw_html": str,
    "method": str   # "nitter"|"fxtwitter"|"oembed"
}
```

### Categorization

`categorize_tweet(tweet_text: str, linked_urls: list) -> dict`

Calls Ollama with `format: "json"`. System prompt:

> "You are an AI research scout for OpenClaw, a multimodal AI workspace. Categorize this tweet and extract actionable intelligence.
>
> Categories:
> - tool: A new tool, library, framework, or software that could improve our AI/dev workflow
> - technique: A prompting technique, coding pattern, or methodology worth trying
> - business_intel: Business insights, market data, funding news, or competitive intelligence
> - code_pattern: Specific code snippets, architectures, or implementations to study
> - market_intel: Market trends, pricing strategies, user behavior data, or opportunity signals
> - irrelevant: Not actionable for an AI agent automation setup
>
> Return JSON: {category, relevance_score (1-10), summary (1 sentence), action_items (array of specific next steps)}"

Falls back to `{category: "extraction_failed", relevance_score: 0, summary: "", action_items: []}` if Ollama is unreachable.

### Other Functions

- `extract_github_repos(text: str) -> list` — regex scan for `github.com/owner/repo` patterns, returns deduplicated list
- `process_batch(urls: list) -> dict` — iterates with `time.sleep(RATE_LIMIT_DELAY)` between requests. Returns `{results: [...], stats: {total, succeeded, failed, by_category: {}}}`

---

## Module: `clawmson_scout.py`

### Functions

**`handle_scout_links(chat_id, message_text) -> str`**
Entry point called from dispatcher thread. Extracts Twitter URLs from message, sends "🔍 Scouting N links..." immediately, calls `process_batch()`, saves each result, returns formatted summary.

**`generate_digest(chat_id, since_hours=24) -> str`**
Pulls from `get_scout_digest()`, formats grouped breakdown by category, sorted by relevance score descending. Used by `/scout` command.

**`format_scout_report(results: list) -> str`**
Compact immediate-feedback message:
```
📊 Scout Report (5 links)
🔧 3 tools · 💡 1 technique · 🗑 1 irrelevant

Top find (9/10): [summary of highest relevance item]

Send /scout for full digest.
```

**Category emoji map:**
| Category | Emoji |
|----------|-------|
| tool | 🔧 |
| technique | 💡 |
| business_intel | 📈 |
| code_pattern | 🧩 |
| market_intel | 📊 |
| irrelevant | 🗑 |
| extraction_failed | ❌ |

---

## Changes to `telegram-dispatcher.py`

**Two additions only. No existing logic modified.**

### 1. Pre-route Twitter detection

Inserted at the top of `handle_message()`, before the `!` shortcut block:

```python
_TWITTER_RE = re.compile(r'https?://(x\.com|twitter\.com)/\w+/status/\d+')

# in handle_message(), before shortcut block:
if text and _TWITTER_RE.search(text):
    t = threading.Thread(target=_scout_thread, args=(chat_id, text), daemon=True)
    t.start()
    send(chat_id, f"🔍 Scouting {len(_TWITTER_RE.findall(text))} link(s)...")
    db.save_message(chat_id, "user", text, message_id=msg_id)
    return
```

### 2. `/scout` command

Added to the slash commands block:

```python
if lower == "/scout":
    send(chat_id, scout.generate_digest(chat_id))
    return
if lower == "/scout clear":
    send(chat_id, "Scout queue clear is not yet implemented.")
    return
```

### 3. Import

```python
import clawmson_scout as scout
```

---

## Dependencies

- `beautifulsoup4` — add to `requirements.txt` (for nitter HTML parsing)
- `requests` — already present
- `re`, `json`, `time`, `datetime` — stdlib

---

## Error Handling

- If a nitter instance times out or returns non-200, try the next instance silently.
- If ALL extraction methods fail for a URL, store with `category="extraction_failed"` and `raw_data` containing `methods_tried` list. Never drop a URL silently.
- If Ollama is unreachable during categorization, store the extraction result with `category="extraction_failed"` and `relevance_score=0`. Bot continues processing remaining URLs.
- Rate limit: `RATE_LIMIT_DELAY = 0.5s` between nitter requests. No rate limiting on fxtwitter/oembed calls.
- Extraction + categorization runs in a daemon thread — dispatcher is never blocked.

---

## End-to-End Flow Example

1. Jordan sends: `"check these out https://x.com/foo/status/123 https://x.com/bar/status/456"`
2. Dispatcher detects 2 Twitter status URLs, sends "🔍 Scouting 2 links...", returns immediately.
3. Background thread: `process_batch([url1, url2])` → extract each → categorize each → save each.
4. Clawmson sends: "📊 Scout Report (2 links)\n🔧 1 tool · 📈 1 business_intel\n\nTop find (8/10): ..."
5. Jordan sends `/scout` → gets full digest of last 24h grouped by category.
6. All results queryable forever via `get_scout_links()`.
