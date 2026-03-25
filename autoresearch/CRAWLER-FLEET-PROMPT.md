# OpenClaw Crawler Fleet — Build Prompt

Read these 4 spec files IN ORDER before writing any code:

1. ~/openclaw/autoresearch/CRAWLER-SPEC-PART1-ARCHITECTURE.md — Shared architecture, storage template, signal format, Gonzoclaw Intel sub-menu spec
2. ~/openclaw/autoresearch/CRAWLER-SPEC-PART2-TIER1-TIER2.md — Tier 1 (Polymarket, Kalshi) + Tier 2 (Reddit, X, Discord, Telegram, Stocktwits)
3. ~/openclaw/autoresearch/CRAWLER-SPEC-PART3-TIER3-TIER4.md — Tier 3 (TradingView, Seeking Alpha, Unusual Whales) + Tier 4 (LinkedIn, Facebook, Instagram, TikTok, Moltbook)
4. ~/openclaw/autoresearch/CRAWLER-SPEC-PART4-BUILD-ORDER.md — Build priority, GitHub repo creation commands, env vars, testing checklist

Also read before coding:
- ~/openclaw/CLAUDE.md — Project conventions and constraints
- ~/openclaw/CONSTRAINTS.md — Hard rules
- ~/openclaw/scripts/github_crawler.py — Reference crawler pattern (already working)
- ~/openclaw/scripts/repo_analyst.py — Ollama analysis pipeline pattern
- ~/openclaw/dashboard/server.py — Existing endpoints, auth, SSE patterns
- ~/openclaw/dashboard/index.html — Existing UI, Intel page layout

## Build Order

Start with PHASE 1 (highest alpha, all free APIs):
1. Create GitHub repos (gh repo create commands in Part 4)
2. Build openclaw-polymarket-feed (real-time WebSocket, free, no auth needed)
3. Build openclaw-kalshi-feed (real-time WebSocket, free with account)
4. Build openclaw-reddit-crawler (5-min poll, free with PRAW)
5. Add Gonzoclaw Intel tabbed sub-menu (server.py endpoints + index.html tabs)

Then PHASE 2, 3, 4 as specced.

## Key Rules
- Each crawler = separate GitHub repo
- All crawlers write to shared signal bus: ~/openclaw/autoresearch/signals/[platform].json
- Use the storage.py template from Part 1 in EVERY crawler
- NOTHING is ever deleted from SQLite — raw data purges, signals are permanent
- Every crawler under 600 lines total
- No paid APIs without explicit approval — free tiers and alternatives first
- No account creation — Jordan provides credentials via .env
- Read-only on all platforms (no posting/interacting)

Go. Build Phase 1 first, test it, then proceed through the phases.
