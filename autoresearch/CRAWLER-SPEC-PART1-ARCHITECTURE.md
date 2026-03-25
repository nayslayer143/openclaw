# OpenClaw Crawler Fleet — Master Build Spec

Read ~/openclaw/CLAUDE.md and ~/openclaw/CONSTRAINTS.md before writing any code.
Read ~/openclaw/scripts/github_crawler.py — this is the reference crawler pattern (already working).
Read ~/openclaw/scripts/repo_analyst.py — understand the Ollama analysis pipeline.
Read ~/openclaw/dashboard/server.py — understand existing endpoint patterns, auth, SSE.
Read ~/openclaw/dashboard/index.html — understand existing UI patterns and the Intel page sub-menu system.

## What This Is

A fleet of 15 platform-specific crawlers that feed trading signals, sentiment data, and trend intelligence into the OpenClaw ecosystem. Each crawler lives in its own GitHub repo, runs independently, and writes structured signals to a shared bus at `~/openclaw/autoresearch/signals/`.

The Gonzoclaw Intel page gets a tabbed sub-menu so Jordan can review signals from any platform without leaving the page.

This is NOT a batch of one-shot scripts. Each crawler is a persistent intelligence feed that runs on schedule, accumulates data, and NEVER deletes anything.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     SHARED SIGNAL BUS                           │
│        ~/openclaw/autoresearch/signals/                         │
│                                                                 │
│  [platform].json ── latest signals per platform                 │
│  [platform]_history/ ── rolling 7-day raw data                  │
│  [platform].db ── SQLite: permanent extracted signals           │
│  archive/ ── gzip compressed >7 day data                        │
└──────────────┬──────────────────────────────────────────────────┘
               │ read by
    ┌──────────┼────────────────────┐
    │          │                    │
    v          v                    v
 Clawmpson   ArbClaw            RivalClaw
 (main bot)  (arb detector)     (rival instance)
    │          │                    │
    └──────────┼────────────────────┘
               │ displayed on
               v
     Gonzoclaw /intel page
     (tabbed sub-menu per platform)
```

## Storage Architecture (SHARED — all crawlers follow this)

Each crawler repo contains:
```
openclaw-[platform]-crawler/
├── CLAUDE.md            ← Repo-specific instructions
├── README.md            ← Setup, usage, API key instructions
├── crawler.py           ← Main crawler script
├── config.py            ← Platform-specific settings
├── signals.py           ← Signal extraction + normalization
├── storage.py           ← SQLite + JSON + archive management
├── requirements.txt     ← Dependencies (minimal)
├── .env.example         ← Required env vars template
├── strategy.md          ← Future features, ideas, not-yet-built plans
├── logs/                ← Crawler logs (gitignored)
├── data/                ← Local data (gitignored)
│   ├── raw/             ← Rolling 7-day JSON
│   ├── signals.db       ← Permanent extracted signals (SQLite)
│   └── archive/         ← Gzip compressed older data
└── tests/
    └── test_crawler.py  ← Basic validation tests
```

### Storage Rules (EVERY crawler follows these)
1. **Hot signals** → `~/openclaw/autoresearch/signals/[platform].json` (shared bus, bots read here)
2. **Local SQLite** → `data/signals.db` in each crawler repo (permanent record, tiny footprint)
3. **Raw data** → `data/raw/` JSON files, auto-purge after 7 days
4. **Archives** → `data/archive/` gzip compressed, auto-purge after 90 days
5. **Google Drive sync** → optional `rclone` cron for cold archival (free 15GB)
6. **NOTHING IS EVER DELETED from SQLite** — raw data is purged, signals are permanent

### Shared Signal Format (EVERY crawler writes this)

```json
{
  "platform": "reddit",
  "crawl_id": "uuid",
  "crawled_at": "2026-03-24T16:00:00Z",
  "signals": [
    {
      "id": "signal-uuid",
      "type": "sentiment|prediction|alert|trend|strategy|news",
      "source_url": "https://...",
      "source_author": "username",
      "title": "Short signal title",
      "body": "Full text or summary (max 500 chars)",
      "ticker_or_market": "BTC|POLYMARKET:will-trump-win|AAPL",
      "direction": "bullish|bearish|neutral|unknown",
      "confidence": 0.0-1.0,
      "urgency": "realtime|hours|days|weeks",
      "engagement": {"upvotes": 0, "comments": 0, "shares": 0},
      "tags": ["crypto", "prediction-market", "momentum"],
      "raw_data": {},
      "extracted_at": "ISO8601"
    }
  ],
  "meta": {
    "total_items_scanned": 500,
    "signals_extracted": 12,
    "next_crawl_at": "ISO8601"
  }
}
```

### storage.py Template (shared across all crawlers)

```python
"""Shared storage module — copy to each crawler repo."""
import json, gzip, sqlite3, os, time
from pathlib import Path
from datetime import datetime, timedelta

OPENCLAW_SIGNALS = Path.home() / "openclaw" / "autoresearch" / "signals"
LOCAL_DATA = Path(__file__).parent / "data"
RAW_DIR = LOCAL_DATA / "raw"
ARCHIVE_DIR = LOCAL_DATA / "archive"
DB_PATH = LOCAL_DATA / "signals.db"
RAW_RETENTION_DAYS = 7
ARCHIVE_RETENTION_DAYS = 90

def init():
    """Create dirs and SQLite tables."""
    for d in [OPENCLAW_SIGNALS, RAW_DIR, ARCHIVE_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""CREATE TABLE IF NOT EXISTS signals (
        id TEXT PRIMARY KEY,
        platform TEXT,
        type TEXT,
        source_url TEXT,
        source_author TEXT,
        title TEXT,
        body TEXT,
        ticker_or_market TEXT,
        direction TEXT,
        confidence REAL,
        urgency TEXT,
        engagement_json TEXT,
        tags_json TEXT,
        raw_json TEXT,
        extracted_at TEXT,
        crawl_id TEXT
    )""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_signals_platform_time
        ON signals(platform, extracted_at)""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_signals_ticker
        ON signals(ticker_or_market)""")
    conn.commit()
    conn.close()

def write_signals(platform: str, crawl_id: str, signals: list):
    """Write signals to shared bus + local SQLite. NEVER deletes."""
    # 1. Shared bus (latest snapshot — bots read this)
    bus_file = OPENCLAW_SIGNALS / f"{platform}.json"
    payload = {
        "platform": platform,
        "crawl_id": crawl_id,
        "crawled_at": datetime.now().isoformat(),
        "signals": signals,
        "meta": {"total_signals": len(signals)},
    }
    bus_file.write_text(json.dumps(payload, indent=2))

    # 2. Raw data (rolling 7-day window)
    raw_file = RAW_DIR / f"{platform}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    raw_file.write_text(json.dumps(payload, indent=2))

    # 3. SQLite (permanent — NEVER purged)
    conn = sqlite3.connect(str(DB_PATH))
    for s in signals:
        try:
            conn.execute("""INSERT OR IGNORE INTO signals
                (id, platform, type, source_url, source_author, title, body,
                 ticker_or_market, direction, confidence, urgency,
                 engagement_json, tags_json, raw_json, extracted_at, crawl_id)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (s["id"], platform, s.get("type",""), s.get("source_url",""),
                 s.get("source_author",""), s.get("title",""), s.get("body",""),
                 s.get("ticker_or_market",""), s.get("direction","unknown"),
                 s.get("confidence",0), s.get("urgency","days"),
                 json.dumps(s.get("engagement",{})), json.dumps(s.get("tags",[])),
                 json.dumps(s.get("raw_data",{})), s.get("extracted_at",""),
                 crawl_id))
        except Exception:
            pass
    conn.commit()
    conn.close()

def cleanup():
    """Compress old raw data, purge expired archives. NEVER touches SQLite."""
    now = time.time()
    # Compress raw > 7 days to archive
    for f in RAW_DIR.glob("*.json"):
        if now - f.stat().st_mtime > RAW_RETENTION_DAYS * 86400:
            archive_path = ARCHIVE_DIR / f"{f.stem}.json.gz"
            with open(f, "rb") as src, gzip.open(archive_path, "wb") as dst:
                dst.write(src.read())
            f.unlink()
    # Purge archives > 90 days
    for f in ARCHIVE_DIR.glob("*.json.gz"):
        if now - f.stat().st_mtime > ARCHIVE_RETENTION_DAYS * 86400:
            f.unlink()
```

---

## Gonzoclaw Intel Sub-Menu Changes

### Backend: Add to ~/openclaw/dashboard/server.py

Add these endpoints (one per platform + unified):

```
GET /api/intel/signals                     → all platforms, latest signals combined
GET /api/intel/signals/{platform}          → signals for one platform
GET /api/intel/signals/{platform}/history  → historical signal data
GET /api/intel/signals/stats               → cross-platform signal stats
GET /api/intel/signals/stream              → SSE for real-time signal updates
```

Each reads from `~/openclaw/autoresearch/signals/[platform].json`.

### Frontend: Add tabbed sub-menu to Intel page in ~/openclaw/dashboard/index.html

At the top of the Intel section, add a horizontal tab bar:

```
[GitHub] [Polymarket] [Kalshi] [Reddit] [X] [Discord] [Telegram] [Stocktwits] [TradingView] [LinkedIn] [SeekingAlpha] [TikTok] [Facebook] [Instagram] [Moltbook] [ALL]
```

Requirements:
- Tabs render inline, horizontal scroll on overflow (no wrapping)
- Active tab highlighted with orange underline (matching existing accent)
- Tab shows badge count of new/unreviewed signals
- "ALL" tab shows unified feed sorted by recency
- Each tab loads its platform's signals via `/api/intel/signals/{platform}`
- Lazy-load: only fetch data when tab is clicked (fast initial load)
- Signal cards follow the same card pattern as GitHub Intel cards
- Each platform tab reuses the same filter/sort bar (direction, urgency, confidence)
- Platform-specific badges (e.g., Reddit shows subreddit, X shows follower count)
- NO full page reloads — tab switching is instant via JS

Build these 8 endpoints + the sub-menu tab system. Under 300 lines of new server.py code, under 400 lines of new HTML/JS.

---


---
CONTINUED IN: ~/openclaw/autoresearch/CRAWLER-SPEC-PART2-TIER1-TIER2A.md
