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

## Platform Crawler Specs

### TIER 1 — Real-Time Market Feeds (WebSocket/Streaming)

---

### 1. openclaw-polymarket-feed

**What:** Real-time Polymarket prediction market data — prices, volumes, new markets, resolution events.

**Why it matters:** Direct probability data on real-world events. Price movements here ARE the signal — no interpretation needed. When a market moves 5%+ in an hour, that's actionable alpha.

**API:** Gamma API (free, no auth for reads). CLOB API for order book depth (free, needs wallet).
- Gamma API: `https://gamma-api.polymarket.com/`
- CLOB API: `https://clob.polymarket.com/`
- No API key needed for read-only market data
- Rate limit: ~1000 calls/hour

**Python deps:** `py-clob-client`, `websockets`, `httpx`

**Update frequency:** REAL-TIME via WebSocket for price changes. Poll new markets every 5 minutes.

**What to crawl:**
- All active markets: current prices, volume, liquidity
- Price change alerts: flag any market moving >3% in 1 hour
- New market creation events
- Market resolution events
- Top movers (biggest price changes in last 24h)
- Category breakdown: politics, crypto, sports, science, culture

**Signal extraction:**
- Price momentum signals (rapid price movement = crowd knowledge shifting)
- Arbitrage opportunities (price discrepancies between related markets)
- Volume spikes (unusual activity = informed trading)
- New market alerts (early entry opportunities)

**Ollama analysis (hourly):** Send top 10 movers to qwen3:30b for narrative analysis:
```
"Market X moved from 0.45 to 0.72 in 2 hours. Volume 3x average.
What event likely caused this? How should our trading bots respond?
Which bot (Clawmpson/ArbClaw/RivalClaw) should act on this?"
```

**Storage:**
- WebSocket stream → SQLite immediately (every price update)
- Shared bus update every 60 seconds with latest state
- Raw WebSocket data → JSON, 7-day retention

**CLI:**
```bash
python crawler.py                    # start real-time feed
python crawler.py --backfill 24h    # fetch last 24h of data
python crawler.py --markets          # list all active markets
python crawler.py --movers           # show top movers now
```

**Repo:** `nayslayer/openclaw-polymarket-feed`

**strategy.md future items:**
- Auto-create ArbClaw tasks when cross-market arbitrage detected
- Correlation tracker: which Polymarket moves predict which other market moves
- Whale wallet tracking (large position changes)
- Market maker detection (identify informed vs noise traders)

---

### 2. openclaw-kalshi-feed

**What:** Real-time Kalshi regulated prediction market data — Fed decisions, economic indicators, weather, elections.

**Why it matters:** CFTC-regulated = more institutional flow than Polymarket. Fed rate decision markets here are leading indicators. Weather event markets can predict commodity moves.

**API:** REST + WebSocket (free, needs Kalshi account + API key).
- REST: `https://api.elections.kalshi.com/trade-api/v2/`
- WebSocket: `wss://api.elections.kalshi.com/trade-api/ws/v2`
- Demo sandbox: `https://demo-api.kalshi.co/trade-api/v2/`
- Rate limit: 10 reads/second (free tier)

**Python deps:** `kalshi-py` or `pykalshi`, `websockets`

**Update frequency:** REAL-TIME via WebSocket. REST poll for new markets every 15 minutes.

**What to crawl:**
- All active event markets: prices, volume, open interest
- Economic indicator markets (CPI, jobs report, GDP — these move everything)
- Fed rate decision markets (directly tradeable signal)
- Weather event markets (hurricane, temperature — commodity correlation)
- Election/political markets
- Settlement/resolution events

**Signal extraction:**
- Fed probability shifts (if "rate hold" goes from 80% to 60%, that's massive)
- Economic surprise signals (market pricing vs consensus)
- Event resolution alerts
- Volume anomalies (smart money positioning before announcements)

**Ollama analysis (hourly):** Focus on economic indicator markets:
```
"Kalshi 'March CPI above 3.2%' market is at 0.67, up from 0.52 yesterday.
What does this imply for equities, crypto, and prediction markets?
Generate trading signals for Clawmpson and RivalClaw."
```

**CLI:**
```bash
python crawler.py                    # start real-time feed
python crawler.py --category fed     # only Fed-related markets
python crawler.py --category econ    # economic indicators only
python crawler.py --movers           # biggest moves today
```

**Repo:** `nayslayer/openclaw-kalshi-feed`

**strategy.md future items:**
- Auto-hedge: when Kalshi Fed market moves, auto-adjust crypto positions
- Economic calendar integration (know WHEN data drops, pre-position)
- Historical accuracy tracker (how well did Kalshi predict actual outcomes?)
- Cross-platform arb: Kalshi vs Polymarket price discrepancies

---

### TIER 2 — High-Frequency Social Signal (5-15 min polls)

---

### 3. openclaw-reddit-crawler

**What:** Subreddit monitoring for trading signals, sentiment, and emerging narratives.

**Why it matters:** r/wallstreetbets moved GME. r/cryptocurrency front-runs exchange listings. Reddit is where retail crowd-sources alpha before it hits mainstream.

**API:** Free via PRAW (100 requests/min with OAuth).
- Register app at reddit.com/prefs/apps (script type)
- Env vars: `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USERNAME`, `REDDIT_PASSWORD`

**Python deps:** `praw`

**Update frequency:** Every 5 minutes for hot subreddits, every 15 minutes for others.

**Subreddits to monitor:**
```
HOT (5-min):   wallstreetbets, cryptocurrency, bitcoin, polymarket, options,
               stocks, CryptoMarkets, ethtrader, algotrading
WARM (15-min):  investing, personalfinance, SecurityAnalysis, quantfinance,
               CryptoCurrency, defi, economy, FluentInFinance
COLD (hourly): technology, MachineLearning, artificial, LocalLLaMA,
               singularity, Futurology (trend/content tracking)
```

**What to crawl:**
- New posts (title, body, score, comments count, flair)
- Top comments on rising posts (first 10 comments)
- Post velocity (posts per hour in each subreddit)
- Award/upvote velocity on individual posts (momentum indicator)
- Mentioned tickers/tokens (regex: $AAPL, $BTC, etc.)
- Sentiment keywords (bullish/bearish/moon/dump/rug/pump)

**Signal extraction:**
- Ticker mention frequency + sentiment (NLP via Ollama)
- Unusual post velocity (10x normal = something is happening)
- High-conviction posts (high upvotes + awards in short time)
- Contrarian signals (heavily downvoted bearish takes in bull subs = confirmation)
- New narrative detection (new terms/tokens appearing for first time)

**Ollama analysis (every 30 min):** Top 5 hottest posts:
```
"Analyze this Reddit post from r/wallstreetbets for trading signals:
Title: [title] | Score: [score] in [minutes] minutes
Body: [first 500 chars]
Top comment: [top comment text]
Extract: ticker, direction, confidence, urgency, and reasoning."
```

**CLI:**
```bash
python crawler.py                        # start monitoring all subreddits
python crawler.py --subreddit wallstreetbets --hot  # single subreddit, hot posts
python crawler.py --ticker AAPL          # find all mentions of a ticker
python crawler.py --sentiment            # aggregate sentiment dashboard
```

**Repo:** `nayslayer/openclaw-reddit-crawler`

**strategy.md future items:**
- User reputation scoring (track accuracy of frequent posters over time)
- Meme velocity tracker (detect emerging meme stocks before they explode)
- DD (Due Diligence) post auto-summarizer
- Cross-subreddit signal correlation
- Auto-post OpenClaw content to relevant subreddits (marketing)

---

### 4. openclaw-x-crawler

**What:** X/Twitter monitoring for breaking news, influencer calls, and market sentiment.

**Why it matters:** Breaking financial news hits X first. CT (Crypto Twitter) calls move markets in minutes. Political tweets affect prediction markets instantly.

**API:** Pay-per-use (~$0.01/tweet read). Buy $20 in credits to start.
- Developer portal: developer.x.com
- Env vars: `X_BEARER_TOKEN`, `X_API_KEY`, `X_API_SECRET`

**Python deps:** `tweepy` or `httpx` (direct REST)

**Update frequency:** Every 5 minutes for keyword searches, every 15 minutes for user timeline monitoring.

**What to monitor:**
```
KEYWORDS (5-min): "prediction market", "polymarket", "kalshi", "$BTC",
                  "$ETH", "crypto pump", "just bought", "going long",
                  "going short", "breaking:", "JUST IN", "Fed decision"
ACCOUNTS (15-min): @tier1 financial accounts, @tier1 crypto accounts,
                   @polyaborat, @Kalshi, key prediction market traders
LISTS (15-min):    Create X lists for: crypto-whales, finance-news,
                   prediction-market-traders, macro-analysts
```

**What to crawl:**
- Tweet text, engagement (likes, retweets, replies, views)
- Quote tweets (signal amplification)
- Thread detection (multi-part analysis)
- Mentioned tickers/tokens ($CASHTAG extraction)
- Engagement velocity (likes per minute — viral detection)

**Signal extraction:**
- Breaking news detection (high RT velocity + news keywords)
- Influencer calls (known-good accounts making directional bets)
- Sentiment aggregation per ticker/market
- Contrarian signals (when everyone is bullish, look for shorts)
- Meme coin alerts (new token mentions spiking)

**Budget management:**
- Track credit usage per crawl cycle
- Alert when credits drop below $5
- Auto-throttle to 1 req/min when credits low
- Prioritize keyword searches over timeline monitoring when budget tight

**CLI:**
```bash
python crawler.py                        # start monitoring
python crawler.py --keyword "polymarket" # single keyword search
python crawler.py --user elonmusk        # monitor specific user
python crawler.py --budget               # show credit usage stats
```

**Repo:** `nayslayer/openclaw-x-crawler`

**strategy.md future items:**
- Influencer accuracy scoring (who actually makes good calls?)
- Auto-reply bot for OpenClaw marketing (separate from crawler)
- Hashtag trend analysis for content marketing
- Bot detection (filter out spam signals)
- Spaces monitoring (live audio events about markets)

---

### 5. openclaw-discord-crawler

**What:** Monitor trading-focused Discord servers for signals, alpha calls, and whale alerts.

**Why it matters:** The highest-signal trading alpha on the internet happens in private Discord servers. Options flow channels, crypto alpha groups, and quant communities share actionable calls hours before they hit public feeds.

**API:** Free bot API (discord.py, no rate limit issues for reading).
- Create bot at discord.com/developers/applications
- Env vars: `DISCORD_BOT_TOKEN`
- Bot needs MESSAGE_CONTENT intent (privileged, requires verification for 100+ servers)

**Python deps:** `discord.py`

**Update frequency:** REAL-TIME (bot listens to messages as they arrive via WebSocket gateway).

**Servers to join (start with public, expand to invite-only):**
```
PUBLIC:   Crypto trading commons, DeFi Pulse, TradingView community,
          The Trading Floor, Stocktwits Discord
INVITE:   (Add as Jordan gets access — the bot just needs to be invited)
```

**What to crawl:**
- Messages in #signals, #calls, #alpha, #trading channels
- Bot alerts (whale alert bots, options flow bots already in servers)
- Pin/reaction velocity (messages getting pinned = high-signal)
- Role-gated channels (VIP/whale channels have best signal)

**Signal extraction:**
- Direct trading calls ("BUY $X at $Y, target $Z, stop $W")
- Whale alert messages (large transactions flagged by alert bots)
- Sentiment from message velocity (sudden spike in activity = event)
- Link extraction (shared TradingView charts, on-chain data)

**Important:** Bot must be READ-ONLY. Never post, react, or interact. Pure intelligence gathering.

**CLI:**
```bash
python crawler.py                        # start bot (real-time listener)
python crawler.py --servers              # list joined servers + channels
python crawler.py --export 24h           # export last 24h of signals
```

**Repo:** `nayslayer/openclaw-discord-crawler`

**strategy.md future items:**
- Server reputation scoring (which servers produce accurate signals?)
- Channel auto-discovery (find new high-signal channels)
- User accuracy tracking per server
- Cross-server signal correlation
- Image/chart OCR (extract data from shared trading charts)

---

### 6. openclaw-telegram-crawler

**What:** Monitor Telegram channels and groups for crypto signals, whale alerts, and breaking news.

**Why it matters:** Telegram is THE coordination layer for crypto. Token launches, whale movements, geo-political intel, and breaking news surface here first, especially for non-Western markets.

**API:** Free bot API (python-telegram-bot, completely free, generous limits).
- Create bot via @BotFather
- Env vars: `TELEGRAM_BOT_TOKEN`
- For channel reading: bot must be added as admin to channels

**Python deps:** `python-telegram-bot` (v22+, async)

**Update frequency:** REAL-TIME (bot receives messages via webhook or polling).

**Channels/groups to monitor:**
```
CRYPTO SIGNALS:  Whale Alert, Crypto Trading Signals, DeFi Alpha
NEWS:            Breaking Crypto News, Bloomberg Crypto, CoinDesk
PREDICTION:      Polymarket Discussion, Kalshi Traders
(Add more as Jordan discovers them — bot just needs to be added)
```

**What to crawl:**
- Channel messages (text, media captions)
- Forwarded messages (cross-channel signal amplification)
- Channel member count changes (growth = attention)
- Media attachments (chart images for future OCR)

**Signal extraction:**
- Token/ticker mentions with sentiment
- Whale movement alerts (large transaction notifications)
- Breaking news detection
- Pump/dump warnings
- Cross-channel signal repetition (same signal in 3+ channels = high confidence)

**CLI:**
```bash
python crawler.py                        # start real-time listener
python crawler.py --channels             # list monitored channels
python crawler.py --export 24h           # export recent signals
```

**Repo:** `nayslayer/openclaw-telegram-crawler`

**strategy.md future items:**
- Auto-join public channels based on keyword discovery
- Message translation (non-English channels, especially Russian/Chinese crypto communities)
- Media/chart analysis via vision model
- Forward chain analysis (trace how information propagates)

---

### 7. openclaw-stocktwits-crawler

**What:** Ticker-tagged sentiment from retail traders with structured bullish/bearish indicators.

**Why it matters:** Stocktwits is purpose-built for trading sentiment. Each message is tagged with a ticker AND a bullish/bearish indicator. This is the cleanest structured sentiment data available. Retail crowding signals have historically preceded short squeezes and meme-stock moves.

**API:** CLOSED for new registrations. Must use scraping approach.
- Primary: Playwright-based scraper for public ticker streams
- Fallback: Apify Stocktwits scraper (free tier: limited runs)
- If API reopens: `STOCKTWITS_ACCESS_TOKEN` env var ready

**Python deps:** `playwright`, `beautifulsoup4`, `httpx`

**Update frequency:** Every 10 minutes for watched tickers, every 30 minutes for discovery scan.

**Tickers to monitor:**
```
ALWAYS:    BTC.X, ETH.X, SPY, QQQ, AAPL, TSLA, NVDA, GME, AMC
DYNAMIC:   Auto-add any ticker trending on Stocktwits (>100 messages/hour)
DISCOVERY: Scan "trending" page for new tickers entering conversation
```

**What to crawl:**
- Messages per ticker: text, bullish/bearish sentiment tag, likes
- Message velocity per ticker (messages/hour)
- Trending tickers list
- User follower counts (weight signals by influence)

**Signal extraction:**
- Bullish/bearish ratio per ticker (already structured!)
- Velocity spikes (10x normal message rate = event)
- Sentiment divergence (Stocktwits bearish but price rising = potential reversal)
- New ticker discovery (tickers going from 0 to 100+ messages/hour)

**CLI:**
```bash
python crawler.py                        # start monitoring
python crawler.py --ticker AAPL          # single ticker stream
python crawler.py --trending             # show current trending
python crawler.py --sentiment BTC.X      # sentiment breakdown
```

**Repo:** `nayslayer/openclaw-stocktwits-crawler`

**strategy.md future items:**
- User accuracy scoring (backtest: did bullish callers make money?)
- Cross-reference with options flow (Stocktwits sentiment + unusual options = high conviction)
- Sector rotation detection (which sectors are getting attention?)
- Integrate with Clawmpson's strategy selector (sentiment as strategy input)

---

### TIER 3 — Hourly Analysis/Content Crawlers

---

### 8. openclaw-tradingview-crawler

**What:** Crowdsourced technical analysis ideas, consensus support/resistance levels, and chart patterns.

**Why it matters:** TradingView has the largest community of technical analysts. Their published ideas include specific price targets and chart annotations. Crowdsourced technical levels become self-fulfilling when enough traders watch the same setups.

**API:** No official API. Use `tvdatafeed` (unofficial WebSocket client).
- No auth needed for delayed data
- For real-time: TradingView username/password (free account works)
- Env vars: `TV_USERNAME`, `TV_PASSWORD` (optional, for real-time data)

**Python deps:** `tvdatafeed`, `playwright` (for ideas page scraping)

**Update frequency:** Every 60 minutes for ideas, every 15 minutes for price data.

**What to crawl:**
- Published trading ideas (ticker, direction, target price, author reputation)
- Consensus support/resistance levels per ticker
- Technical indicator signals (RSI overbought/oversold, MACD crosses)
- OHLCV data for tracked tickers (price data backup source)

**Signal extraction:**
- Consensus direction per ticker (if 80% of ideas are bullish, that's a signal)
- Key price levels (most-mentioned support/resistance)
- Pattern detection consensus (multiple analysts seeing same pattern)
- Contrarian signals (price at level where most ideas say "reversal")

**CLI:**
```bash
python crawler.py                        # start monitoring
python crawler.py --ideas BTC            # ideas for specific ticker
python crawler.py --levels AAPL          # consensus S/R levels
python crawler.py --data BTC 1h          # OHLCV data fetch
```

**Repo:** `nayslayer/openclaw-tradingview-crawler`

**strategy.md future items:**
- Idea accuracy backtesting (which TradingView authors are actually profitable?)
- Auto-generate TradingView charts for OpenClaw content marketing
- Custom indicator scripts that integrate OpenClaw signals
- Pine Script strategy export (export our strategies as TradingView scripts)

---

### 9. openclaw-seekingalpha-crawler

**What:** Long-form fundamental analysis, earnings call insights, and contrarian theses.

**Why it matters:** Seeking Alpha articles have documented, measurable price impact on tickers they cover, especially in the first hour after publication. Finance Substacks increasingly publish institutional-quality analysis before mainstream coverage.

**API:** No official API. Use RapidAPI endpoint (free tier: ~500 req/month) + RSS feeds.
- RapidAPI: sign up at rapidapi.com, subscribe to Seeking Alpha API (free tier)
- RSS: Seeking Alpha has public RSS feeds per ticker
- Env vars: `RAPIDAPI_KEY`

**Python deps:** `httpx`, `feedparser`, `beautifulsoup4`

**Update frequency:** Every 60 minutes.

**What to crawl:**
- New articles (title, author, ticker, sentiment rating)
- Earnings call transcript summaries (via free SEC EDGAR fallback)
- Author track record (historical accuracy rating if available)
- Article engagement (comments, likes)
- RSS feeds for tracked tickers

**Signal extraction:**
- New article alerts for tracked tickers (first-mover advantage)
- Earnings surprise signals (transcript analysis vs consensus)
- Contrarian theses (bearish articles on consensus-bullish stocks)
- Sector rotation narratives

**CLI:**
```bash
python crawler.py                        # start monitoring
python crawler.py --ticker AAPL          # articles about AAPL
python crawler.py --earnings             # recent earnings coverage
python crawler.py --contrarian           # find contrarian takes
```

**Repo:** `nayslayer/openclaw-seekingalpha-crawler`

**strategy.md future items:**
- Full Substack integration (monitor top finance newsletters)
- Author accuracy scoring over time
- Earnings calendar integration (pre-position before coverage hits)
- Auto-summarize long articles via Ollama

---

### 10. openclaw-unusualwhales-crawler

**What:** Options flow, dark pool data, and congressional trading alerts.

**Why it matters:** Unusual options activity is one of the strongest leading indicators for directional moves. Congressional trade tracking adds a unique political-insider signal layer.

**API:** PAID ONLY. No free tier. Entry ~$75-100/month.
- For now: build the crawler structure, use FREE ALTERNATIVES for the same data types
- Free alternatives: CBOE delayed options data, Polygon.io free tier, Tradier free tier
- Env vars: `UNUSUALWHALES_API_KEY` (future), `POLYGON_API_KEY` (free tier now)

**Python deps:** `httpx`, `polygon` (free tier)

**Update frequency:** Every 15 minutes for options flow, hourly for congressional trades.

**What to crawl (using free alternatives until UW subscription):**
- Large options trades (sweeps, unusual volume) via Polygon.io
- Options flow direction (call/put ratio, premium direction)
- Congressional trading disclosures (free via Senate/House EFDS websites)
- Dark pool prints (delayed, via free data sources)

**Signal extraction:**
- Unusual options volume per ticker (10x average = informed trading)
- Smart money direction (large block trades in one direction)
- Congressional buy/sell signals (they trade on inside info, it's documented)
- Sector flow (where is options money concentrating?)

**CLI:**
```bash
python crawler.py                        # start monitoring (free sources)
python crawler.py --flow AAPL            # options flow for ticker
python crawler.py --congress             # recent congressional trades
python crawler.py --darkpool             # dark pool activity
```

**Repo:** `nayslayer/openclaw-unusualwhales-crawler`

**strategy.md future items:**
- Subscribe to Unusual Whales API when budget allows ($75/mo)
- Auto-correlate congressional trades with prediction market movements
- Options flow → Polymarket arbitrage (if smart money is buying calls, how does prediction market move?)
- Gamma exposure tracking
- MCP server integration (Unusual Whales now offers this)

---

### TIER 4 — Content/Trend Tracking (Daily/Hourly)

---

### 11. openclaw-linkedin-crawler

**What:** Professional network signals — executive moves, company announcements, industry trend posts.

**Why it matters:** LinkedIn has unique signal: executive departures, company pivots, hiring surges, and industry thought leadership. These are slow signals (days/weeks lead time) but high-conviction.

**API:** Extremely restricted. Free Development tier only allows basic profile/sign-in.
- For content monitoring: RSS feeds from LinkedIn Pulse + public post scraping
- Legal note: LinkedIn scraping is gray area (hiQ v. LinkedIn established some precedent)
- Env vars: `LINKEDIN_EMAIL`, `LINKEDIN_PASSWORD` (for authenticated scraping, optional)

**Python deps:** `httpx`, `beautifulsoup4`, `feedparser`

**Update frequency:** Every 60 minutes for RSS, daily for deeper analysis.

**What to crawl:**
- LinkedIn Pulse articles (RSS feeds for finance/tech/crypto topics)
- Public company posts from tracked companies
- Job posting velocity (hiring surge = growth signal)
- Executive profile changes (new role = company transition signal)

**Signal extraction:**
- Executive movement alerts (CEO/CTO departures → stock impact)
- Hiring surge detection (company posting 50+ jobs in a week → expansion)
- Industry narrative tracking (what are thought leaders talking about?)
- Company sentiment from employee posts

**CLI:**
```bash
python crawler.py                        # start monitoring
python crawler.py --company "Polymarket" # track specific company
python crawler.py --executives           # executive movement alerts
python crawler.py --hiring               # hiring surge detection
```

**Repo:** `nayslayer/openclaw-linkedin-crawler`

**strategy.md future items:**
- Auto-post OpenClaw content/thought leadership (marketing)
- Company graph analysis (who's hiring FROM prediction market companies?)
- Conference/event detection (finance conferences = networking opportunities)
- B2B lead generation for any products we build

---

### 12. openclaw-facebook-crawler

**What:** Public group monitoring for retail sentiment, community trends, and mainstream narrative tracking.

**Why it matters:** Facebook groups capture mainstream retail investor sentiment that doesn't appear on Reddit/X. "Normie money" entering markets (Facebook investing groups growing) is a macro signal.

**API:** Meta Graph API (free, requires Facebook App).
- Create app at developers.facebook.com
- Public page/group data is accessible with app token
- Env vars: `FACEBOOK_APP_ID`, `FACEBOOK_APP_SECRET`

**Python deps:** `httpx`, `facebook-sdk`

**Update frequency:** Every 60 minutes for groups, daily for page analysis.

**What to crawl:**
- Public investing/trading groups (posts, comments, engagement)
- Public pages of financial companies/influencers
- Trending topics in finance/crypto categories
- Group membership growth rates (mainstream adoption signal)

**Signal extraction:**
- Mainstream adoption signals (when your aunt's Facebook group talks about crypto, top is near)
- Fear/greed from retail language patterns
- Platform trend data for content marketing
- Demographic signals (which age groups are entering markets?)

**CLI:**
```bash
python crawler.py                        # start monitoring
python crawler.py --groups               # list monitored groups
python crawler.py --trending             # finance-related trending topics
```

**Repo:** `nayslayer/openclaw-facebook-crawler`

**strategy.md future items:**
- Ad library analysis (who's spending money on trading product ads?)
- Marketplace analysis (trading-related products/services)
- Content marketing automation (auto-post to OpenClaw Facebook page)
- Facebook Shops integration for any products we sell

---

### 13. openclaw-instagram-crawler

**What:** Visual trend tracking, influencer finance content, and lifestyle-to-market signals.

**Why it matters:** Instagram captures consumer spending patterns and lifestyle trends before they show up in earnings reports. Finance influencers ("finfluencers") on Instagram reach demographics that don't use Twitter/Reddit.

**API:** Instagram Graph API (free with Facebook App, requires Instagram Business account).
- Uses same Facebook developer app
- Env vars: `INSTAGRAM_ACCESS_TOKEN` (via Facebook Graph API)

**Python deps:** `httpx`, `instaloader` (public profile scraping fallback)

**Update frequency:** Hourly for hashtag monitoring, daily for profile analysis.

**What to crawl:**
- Finance/crypto hashtags (#crypto, #trading, #investing, #bitcoin, #stocks)
- Top finfluencer posts and engagement metrics
- Reels trending in finance category
- Story mentions of market events (via highlights/saves)

**Signal extraction:**
- Hashtag velocity (sudden spike in #crypto posts = retail FOMO)
- Influencer sentiment shifts (bullish influencer turns bearish = warning)
- Consumer spending trend detection (luxury goods posts up → consumer confidence)
- Content marketing trends (what visual styles are performing for finance content?)

**CLI:**
```bash
python crawler.py                        # start monitoring
python crawler.py --hashtag crypto       # track specific hashtag
python crawler.py --influencers          # top finfluencer activity
```

**Repo:** `nayslayer/openclaw-instagram-crawler`

**strategy.md future items:**
- Auto-generate Instagram content for OpenClaw brand
- Influencer partnership discovery
- Visual trend analysis via vision model (what styles are performing?)
- Reels script generator from trading signals

---

### 14. openclaw-tiktok-crawler

**What:** Short-form video trend tracking, viral finance content, and GenZ market sentiment.

**Why it matters:** TikTok finance content reaches the youngest investor demographic. Viral "FinTok" videos have measurably moved meme stocks and crypto. This is the leading edge of retail sentiment.

**API:** Research API (academic only) or unofficial `TikTokApi` library.
- Unofficial: requires `playwright` and TikTok session cookie
- Env vars: `TIKTOK_MS_TOKEN` (from browser cookies)

**Python deps:** `TikTokApi`, `playwright`

**Update frequency:** Hourly for trending, daily for deep analysis.

**What to crawl:**
- Trending hashtags: #stocktok, #cryptotok, #investing, #trading, #fintok
- Viral finance videos (>100k views in 24h)
- Creator accounts in finance niche
- Sound/audio trends (specific sounds associated with trading content)

**Signal extraction:**
- Viral trigger detection (when a stock/token goes viral on TikTok = retail influx imminent)
- Sentiment from video engagement (comments, shares, duets)
- Mainstream adoption signals (finance content reaching non-finance audiences)
- Content marketing intelligence (what formats work for finance content on TikTok?)

**CLI:**
```bash
python crawler.py                        # start monitoring
python crawler.py --trending             # current trending finance content
python crawler.py --viral 24h            # viral finance videos last 24h
```

**Repo:** `nayslayer/openclaw-tiktok-crawler`

**strategy.md future items:**
- Auto-generate TikTok content from trading signals/results
- Sound trend analysis (what audio is associated with market moves?)
- Creator collaboration discovery
- Cross-platform viral tracking (TikTok → Twitter → Reddit pipeline)

---

### 15. openclaw-moltbook-crawler

**What:** AI agent social network monitoring — agent-generated insights, cross-agent intelligence, and emerging AI meta-signals.

**Why it matters:** Moltbook is a social network FOR AI agents. If this platform gains traction, it becomes a unique source of AI-to-AI intelligence sharing. Early presence = first-mover advantage in the agent internet ecosystem.

**API:** TBD — platform is early-stage. Build for public web scraping initially, upgrade to API when available.
- No auth required for reading public posts
- Agent identity via X/Twitter verification
- Env vars: `MOLTBOOK_API_KEY` (future), `MOLTBOOK_AGENT_TOKEN` (future)

**Python deps:** `httpx`, `beautifulsoup4`, `playwright` (if JS-rendered)

**Update frequency:** Daily (low content volume currently). Auto-increase frequency as platform grows.

**What to crawl:**
- All public posts (text, upvotes, comments)
- Submolts (topic-based communities — like subreddits)
- Agent profiles (what tools/capabilities do other agents claim?)
- Trending topics among AI agents
- Cross-references to other platforms (links shared by agents)

**Signal extraction:**
- Agent consensus signals (if multiple AI agents agree on a prediction, that's meta-signal)
- Tool/API discovery (what tools are other agents using that we aren't?)
- Trend detection in AI agent behavior patterns
- Emerging use cases for agent coordination

**CLI:**
```bash
python crawler.py                        # start monitoring
python crawler.py --posts                # latest posts
python crawler.py --submolts             # list active submolts
python crawler.py --agents               # active agent profiles
```

**Repo:** `nayslayer/openclaw-moltbook-crawler`

**strategy.md future items:**
- Register OpenClaw as an agent on Moltbook
- Auto-post OpenClaw signals/analysis to Moltbook (build reputation)
- Agent authentication integration (use Moltbook identity for cross-platform agent auth)
- Multi-agent strategy coordination (share signals between friendly agents)
- Build a Submolt for prediction market trading agents

---

## Build Priority Order

Build in this order (highest alpha first):

```
PHASE 1 — Immediate (this week):
  1. openclaw-polymarket-feed      (real-time, free, highest direct signal)
  2. openclaw-kalshi-feed          (real-time, free, regulated market data)
  3. openclaw-reddit-crawler       (5-min, free, proven retail signal source)
  4. Gonzoclaw Intel sub-menu      (required before adding more platforms)

PHASE 2 — Next week:
  5. openclaw-x-crawler            (5-min, ~$20, breaking news + CT)
  6. openclaw-discord-crawler      (real-time, free, highest signal-to-noise)
  7. openclaw-telegram-crawler     (real-time, free, crypto alpha layer)
  8. openclaw-stocktwits-crawler   (10-min, free scraping, structured sentiment)

PHASE 3 — Following week:
  9. openclaw-tradingview-crawler  (hourly, free, technical consensus)
  10. openclaw-seekingalpha-crawler (hourly, free/cheap, fundamental analysis)
  11. openclaw-unusualwhales-crawler (15-min, free alternatives first)

PHASE 4 — Content/Marketing (when ready):
  12. openclaw-linkedin-crawler    (hourly, free, professional signals)
  13. openclaw-facebook-crawler    (hourly, free, mainstream sentiment)
  14. openclaw-instagram-crawler   (hourly, free, visual trends)
  15. openclaw-tiktok-crawler      (hourly, free/fragile, viral detection)
  16. openclaw-moltbook-crawler    (daily, free, agent meta-signals)
```

## GitHub Repo Creation Commands

Run these from any directory. Each creates a repo on nayslayer's GitHub:

```bash
# Phase 1
gh repo create nayslayer/openclaw-polymarket-feed --public --description "Real-time Polymarket prediction market feed for OpenClaw trading bots" --clone
gh repo create nayslayer/openclaw-kalshi-feed --public --description "Real-time Kalshi regulated prediction market feed for OpenClaw" --clone
gh repo create nayslayer/openclaw-reddit-crawler --public --description "Reddit trading signal crawler — sentiment, tickers, narrative detection" --clone

# Phase 2
gh repo create nayslayer/openclaw-x-crawler --public --description "X/Twitter financial signal crawler — breaking news, CT alpha, sentiment" --clone
gh repo create nayslayer/openclaw-discord-crawler --public --description "Discord trading server monitor — signals, whale alerts, alpha calls" --clone
gh repo create nayslayer/openclaw-telegram-crawler --public --description "Telegram crypto signal crawler — whale alerts, breaking news, alpha" --clone
gh repo create nayslayer/openclaw-stocktwits-crawler --public --description "Stocktwits sentiment crawler — ticker-tagged bullish/bearish signals" --clone

# Phase 3
gh repo create nayslayer/openclaw-tradingview-crawler --public --description "TradingView ideas crawler — consensus technical levels and patterns" --clone
gh repo create nayslayer/openclaw-seekingalpha-crawler --public --description "Seeking Alpha article crawler — fundamental analysis and earnings signals" --clone
gh repo create nayslayer/openclaw-unusualwhales-crawler --public --description "Options flow and congressional trading signal crawler" --clone

# Phase 4
gh repo create nayslayer/openclaw-linkedin-crawler --public --description "LinkedIn professional signal crawler — executive moves, hiring surges" --clone
gh repo create nayslayer/openclaw-facebook-crawler --public --description "Facebook mainstream sentiment crawler — retail investor groups" --clone
gh repo create nayslayer/openclaw-instagram-crawler --public --description "Instagram finfluencer and visual trend crawler" --clone
gh repo create nayslayer/openclaw-tiktok-crawler --public --description "TikTok viral finance content and GenZ sentiment crawler" --clone
gh repo create nayslayer/openclaw-moltbook-crawler --public --description "Moltbook AI agent social network monitor" --clone
```

## What NOT To Build

- No auto-trading without Jordan's approval — every signal goes through Gonzoclaw review
- No paid API subscriptions without explicit approval — use free tiers and alternatives first
- No account creation on platforms — Jordan creates accounts, provides credentials
- No posting/interacting on platforms (read-only) — except where explicitly noted in strategy.md
- No new databases beyond SQLite — keep it simple
- No new frameworks — Python stdlib + minimal deps
- No authentication/password storage — use .env files only
- Don't over-engineer crawlers — each should be under 500 lines initially

## File Budget Per Crawler

- `crawler.py`: 300 lines max
- `config.py`: 50 lines max
- `signals.py`: 100 lines max
- `storage.py`: 100 lines (shared template above)
- `requirements.txt`: 5-10 deps max
- Total per crawler: under 600 lines
- Total across all 15 crawlers: under 9,000 lines

## Testing Checklist Per Crawler

- [ ] Crawler runs without API key (graceful error message)
- [ ] Crawler handles rate limits (backs off, retries)
- [ ] Crawler handles network errors (skip, log, continue)
- [ ] Signals write to shared bus (`~/openclaw/autoresearch/signals/[platform].json`)
- [ ] Signals write to local SQLite (`data/signals.db`)
- [ ] Raw data auto-purges after 7 days
- [ ] Archives compress after 7 days
- [ ] Log file updates daily at minimum
- [ ] CLI help message works (`python crawler.py --help`)
- [ ] Signal format matches shared schema (see above)

## Environment Variables Summary

```bash
# Add to ~/openclaw/.env or each crawler's .env

# Reddit
REDDIT_CLIENT_ID=xxx
REDDIT_CLIENT_SECRET=xxx
REDDIT_USERNAME=xxx
REDDIT_PASSWORD=xxx

# X/Twitter
X_BEARER_TOKEN=xxx
X_API_KEY=xxx
X_API_SECRET=xxx

# Discord
DISCORD_BOT_TOKEN=xxx

# Telegram
TELEGRAM_BOT_TOKEN=xxx

# Kalshi
KALSHI_API_KEY=xxx
KALSHI_API_SECRET=xxx

# Facebook/Instagram (shared via Meta)
FACEBOOK_APP_ID=xxx
FACEBOOK_APP_SECRET=xxx
INSTAGRAM_ACCESS_TOKEN=xxx

# TikTok
TIKTOK_MS_TOKEN=xxx

# TradingView (optional)
TV_USERNAME=xxx
TV_PASSWORD=xxx

# RapidAPI (for Seeking Alpha)
RAPIDAPI_KEY=xxx

# Polygon.io (free tier, for options flow)
POLYGON_API_KEY=xxx

# Unusual Whales (future, paid)
UNUSUALWHALES_API_KEY=xxx

# LinkedIn (optional)
LINKEDIN_EMAIL=xxx
LINKEDIN_PASSWORD=xxx

# Moltbook (future)
MOLTBOOK_API_KEY=xxx
```

## Data Flow Summary

```
TIER 1 (real-time):
  Polymarket WebSocket ─┐
  Kalshi WebSocket ─────┤
                        ├──→ ~/openclaw/autoresearch/signals/ ──→ Trading Bots
TIER 2 (5-15 min):     │                                          │
  Reddit PRAW ──────────┤                                          │
  X API ────────────────┤                                          ├──→ Gonzoclaw
  Discord bot ──────────┤                                          │    Intel Page
  Telegram bot ─────────┤                                          │    (tabbed)
  Stocktwits scraper ───┤                                          │
                        │                                          │
TIER 3 (hourly):       │    Ollama qwen3:30b                      │
  TradingView ──────────┤──→ (analysis every 30 min) ─────────────┤
  Seeking Alpha ────────┤                                          │
  Unusual Whales ───────┘                                          │
                                                                   │
TIER 4 (daily):                                                    │
  LinkedIn ─────────────┐                                          │
  Facebook ─────────────┤──→ ~/openclaw/autoresearch/signals/ ─────┘
  Instagram ────────────┤
  TikTok ───────────────┤
  Moltbook ─────────────┘
```
