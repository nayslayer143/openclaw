# OpenClaw Crawler Fleet — Part 4: Build Order, Repo Creation, Config

Read Parts 1-3 first for full platform specs.
This file has: build priority order, GitHub repo creation commands, env vars, testing checklist, data flow diagram.

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
