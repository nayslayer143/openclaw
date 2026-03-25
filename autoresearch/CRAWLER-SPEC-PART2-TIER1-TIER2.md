# OpenClaw Crawler Fleet — Part 2: Tier 1 + Tier 2 Platform Specs

Read Part 1 first: ~/openclaw/autoresearch/CRAWLER-SPEC-PART1-ARCHITECTURE.md
That file has: shared architecture, storage template (storage.py), signal format, and Gonzoclaw Intel sub-menu spec.

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


---
CONTINUED IN: ~/openclaw/autoresearch/CRAWLER-SPEC-PART3-TIER3-TIER4.md
