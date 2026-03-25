# OpenClaw Instagram Crawler

Instagram hashtag monitor and finfluencer tracker. Extracts visual trend signals, caption sentiment, $CASHTAG mentions, content type classification, and engagement metrics from finance/crypto Instagram. Part of the OpenClaw autoresearch pipeline.

## Setup

### 1. Install Dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env — optionally add INSTAGRAM_ACCESS_TOKEN for Graph API mode
```

**Without API key:** Works out of the box using public hashtag page scraping.
**With API key:** Set `INSTAGRAM_ACCESS_TOKEN` (from Facebook Graph API Explorer) for richer data including engagement counts and business profile discovery.

### 3. Run

```bash
# Continuous monitoring (hashtags hourly, influencer profiles daily)
python crawler.py

# Single hashtag
python crawler.py --hashtag crypto

# Finfluencer activity report
python crawler.py --influencers

# One crawl cycle then exit
python crawler.py --once
```

## Watched Hashtags

Default: #crypto, #trading, #investing, #bitcoin, #stocks, #fintok, #ethereum, #defi, #forex, #stockmarket

Edit `config.py` to change the watchlist.

## Tracked Influencers

Default list in `config.py`. Add/remove usernames as needed.

## Output

- **Signal bus:** `~/openclaw/autoresearch/signals/instagram.json`
- **Local DB:** `data/signals.db` (SQLite)
- **Raw snapshots:** `data/raw/` (JSON, retained 7 days)
- **Archives:** `data/archive/` (gzipped, retained 90 days)
- **Logs:** `logs/` (daily rotation)

## Signal Format

Each signal follows the shared OpenClaw format with fields for type, ticker, direction, confidence, urgency, engagement, and tags. Instagram-specific extras include content type classification (educational, hype, news, analysis) and hashtag context.

## Rate Limiting

Requests are spaced 3-5 seconds apart with exponential backoff on rate limits (429) or blocks (403). The crawler uses a browser-like User-Agent.

## Dependencies

- `httpx` -- HTTP client
- `beautifulsoup4` -- HTML parsing
- `python-dotenv` -- Environment variable loading
