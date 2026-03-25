# OpenClaw Crawler Fleet — Part 3: Tier 3 + Tier 4 Platform Specs

Read Part 1 first: ~/openclaw/autoresearch/CRAWLER-SPEC-PART1-ARCHITECTURE.md (architecture + storage)
Read Part 2: ~/openclaw/autoresearch/CRAWLER-SPEC-PART2-TIER1-TIER2.md (Polymarket, Kalshi, Reddit, X, Discord, Telegram, Stocktwits)

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


---
CONTINUED IN: ~/openclaw/autoresearch/CRAWLER-SPEC-PART4-BUILD-ORDER.md
