#!/bin/bash
# cron-skill-upgrade.sh — Weekly Skill & Tool Upgrade Research
# Schedule: Mondays at 6am (0 6 * * 1)
# Researches: new tools for web search, scraping, gig delivery, AI capabilities
# Produces: improvements/skill-upgrade-{date}.md + Tier-2 Telegram for approval

OPENCLAW_ROOT="${HOME}/openclaw"
TODAY=$(date +%Y-%m-%d)
OUTPUT="${OPENCLAW_ROOT}/improvements/skill-upgrade-${TODAY}.md"

set -a; source "${OPENCLAW_ROOT}/.env" 2>/dev/null || true; set +a

CURRENT_SKILLS="ollama (local LLMs), Claude API, OpenAI API, GRDB, Swift/iOS, Python, bash scripting, cron scheduling, Telegram bot, SERP research (manual), xcodegen, GRDB migrations, Stripe API (planned)"

PROMPT="You are Clawmpson's upgrade advisor. Research and recommend the most valuable tools and skills to install/learn this week to maximize gig-winning and revenue generation.

Current capabilities: ${CURRENT_SKILLS}

Research these upgrade categories:

1. WEB SEARCH & SCRAPING TOOLS
   - Serper.dev (Google SERP API) — fast, cheap, \$50/mo for 50k queries
   - SerpAPI — richer data, \$75/mo
   - Brave Search API — free tier available
   - Firecrawl — intelligent web scraping with LLM extraction
   - Jina AI Reader — clean content extraction from any URL (free tier)
   - Playwright (already installable via npm/pip)
   - Crawl4AI — open source async crawler
   - Perplexity API — search-augmented LLM

2. GIG PLATFORM APIs
   - Upwork API (read job feeds, submit proposals programmatically)
   - Fiverr API / RSS feeds for buyer requests
   - Freelancer.com API
   - Contra API

3. CONTENT & DESIGN DELIVERY
   - Stable Diffusion / FLUX for design gigs
   - Ideogram API for logo/graphic work
   - Canva API for templated design delivery
   - ElevenLabs for voice/audio gigs

4. CODING DELIVERY UPGRADES
   - E2B (sandboxed code execution for clients)
   - Modal.com (serverless Python functions for client delivery)
   - Vercel API (instant deploy client landing pages)

5. SEARCH SKILL IMPROVEMENTS
   - Advanced Google dork patterns for lead gen
   - LinkedIn Sales Navigator scraping patterns
   - Reddit niche audience research patterns
   - GitHub trending repo analysis for emerging gig demand

For each tool/skill:
**Tool Name** — \$cost/mo (or free)
- What it unlocks for Clawmpson:
- Install method: (pip install X / npm install X / API key only)
- Priority: INSTALL NOW / THIS WEEK / RESEARCH ONLY
- ROI estimate: what gigs does this enable?

Group by priority. Top 5 get INSTALL NOW status."

if [[ -n "${OPENAI_API_KEY:-}" ]]; then
  UPGRADES=$(curl -s https://api.openai.com/v1/chat/completions \
    -H "Authorization: Bearer ${OPENAI_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"gpt-4o\",\"messages\":[{\"role\":\"user\",\"content\":$(echo "$PROMPT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}],\"max_tokens\":2500}" \
    2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['choices'][0]['message']['content'])" 2>/dev/null)
fi

if [[ -z "$UPGRADES" ]]; then
  UPGRADES=$(echo "$PROMPT" | ollama run qwen3:32b 2>/dev/null || echo "LLM unavailable")
fi

cat > "$OUTPUT" << EOF
# Skill Upgrade Brief — ${TODAY}
> Weekly capability research. INSTALL NOW items need Jordan approval before execution.

${UPGRADES}

---
## How to action this
- **INSTALL NOW items**: Reply to Telegram with item number → Clawmpson installs + tests within 2h
- **THIS WEEK items**: Added to queue automatically
- **RESEARCH ONLY**: Filed for future reference
EOF

# Extract install-now items for Telegram
INSTALLS=$(echo "$UPGRADES" | grep -A1 "INSTALL NOW" | grep "^\*\*" | head -5 | sed 's/\*\*//g')

MESSAGE="🔧 Weekly Skill Upgrade Brief — ${TODAY}

Top tools to install this week:
${INSTALLS}

Reply with item number(s) to approve installation.
Full brief: improvements/skill-upgrade-${TODAY}.md"

bash "${OPENCLAW_ROOT}/scripts/notify-telegram.sh" "$MESSAGE" 2>/dev/null || true

echo "[${TODAY}] Skill upgrade brief generated → ${OUTPUT}" >> "${OPENCLAW_ROOT}/memory/IDLE_LOG.md"
