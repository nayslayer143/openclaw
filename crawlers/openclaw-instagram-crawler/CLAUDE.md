# openclaw-instagram-crawler

## What This Is
Instagram hashtag monitor and finfluencer tracker that extracts visual trend signals, sentiment from captions, ticker/token mentions, and engagement metrics. Part of the OpenClaw autoresearch pipeline.

## Architecture
- `crawler.py` -- Main entry point. Dual-mode: Instagram Graph API (when token set) or httpx + BeautifulSoup scraper fallback. CLI via argparse, monitoring loop.
- `config.py` -- All settings: watched hashtags, influencer list, intervals, rate limits. Reads from `.env`.
- `signals.py` -- Sentiment scoring (keyword-based bullish/bearish), content type classification, $CASHTAG extraction, signal construction.
- `storage.py` -- Shared storage module (SQLite + JSON bus). Identical across all crawlers.

## Key Rules
- Read `~/openclaw/CONSTRAINTS.md` before making changes.
- storage.py is a shared template -- do not modify without updating all crawlers.
- Line budgets: crawler.py (300), config.py (50), signals.py (100), storage.py (100).
- Total project under 600 lines.
- Must work WITHOUT API keys (HTML scraping fallback). Graph API used when INSTAGRAM_ACCESS_TOKEN is set.
- Respectful rate limiting: 3-5 seconds between requests, exponential backoff on 429/403.
- HTML structure may change -- all parsing uses multiple fallback strategies, never crashes.
- Network errors: log, skip, continue. Never crash on a transient failure.

## Signal Flow
```
Instagram (Graph API or HTML) -> parse posts (API JSON or BeautifulSoup) -> signals.py (score/classify) -> storage.py -> signals bus
```

## Output
- Shared bus: `~/openclaw/autoresearch/signals/instagram.json`
- Local DB: `data/signals.db`
- Raw snapshots: `data/raw/`
- Archived: `data/archive/` (gzipped after 7 days)

## CLI
```bash
python crawler.py                        # start monitoring all watched hashtags
python crawler.py --hashtag crypto       # track specific hashtag
python crawler.py --influencers          # top finfluencer activity
python crawler.py --once                 # single pass
```
