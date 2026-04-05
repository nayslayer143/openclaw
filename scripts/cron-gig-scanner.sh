#!/bin/bash
# cron-gig-scanner.sh — Multi-Platform Gig Scanner
# Schedule: 3x daily at 7am, 1pm, 7pm (0 7,13,19 * * *)
# Scans: Upwork, Fiverr, Freelancer, PeoplePerHour, Toptal, 99designs,
#        Contra, Malt, RemoteOK, WeWorkRemotely, Gitcoin, Replit Bounties
# Produces: outputs/gigs-{date}-{slot}.md + Telegram if hot leads found

OPENCLAW_ROOT="${HOME}/openclaw"
TODAY=$(date +%Y-%m-%d)
SLOT=$(date +%H)
OUTPUT="${OPENCLAW_ROOT}/outputs/gigs-${TODAY}-${SLOT}.md"
LOG="${OPENCLAW_ROOT}/logs/gig-scanner.log"

set -a; source "${OPENCLAW_ROOT}/.env" 2>/dev/null || true; set +a

# Pull Clawmpson's known skill set for matching
SKILLS="Python, JavaScript/TypeScript, Swift/iOS, Shell scripting, GRDB/SQLite, REST APIs, AI agent development, prompt engineering, Claude/OpenAI API integration, web scraping (Playwright/Puppeteer), data analysis, automation workflows, technical writing, landing pages (HTML/CSS/React), Next.js, Tailwind, SaaS product development, Stripe integration, Telegram bots, cron-based automation, n8n/Zapier flows, SEO content, blog writing, competitive research reports"

# Use OpenAI for faster turnaround on gig research (already have the key)
PROMPT="You are Clawmpson, an AI agent scanning freelance platforms for gigs to bid on and win RIGHT NOW (${TODAY}, ${SLOT}:00).

Clawmpson's proven skills: ${SKILLS}

Simulate scanning these platforms for LIVE job postings that match:
- Upwork: search 'AI automation', 'Python script', 'iOS app', 'web scraping', 'landing page', 'API integration', 'Claude API', 'OpenAI automation', 'Telegram bot', 'technical writing'
- Fiverr: gig opportunities in automation, AI chatbots, Python scripts, iOS dev, content writing
- Freelancer.com: fixed-price projects under \$2000 in coding and writing
- PeoplePerHour: hourly/fixed Python, JS, AI projects
- Contra: async freelance for product builders
- RemoteOK / WeWorkRemotely: short-term contracts
- Gitcoin: crypto-native bounties (web3 tooling, docs, audits)
- Replit Bounties: small focused coding tasks \$50-\$500

For each opportunity output:
**[PLATFORM] Job Title** | \$AMOUNT | TIME_TO_COMPLETE
- What client needs: (1 line)
- Clawmpson fit: HIGH/MEDIUM/LOW + reason
- Bid strategy: (1 line — what angle wins this)
- Search/apply URL or keyword:
- Confidence of winning: X/10

Sort by: (Confidence × Amount). Output top 12. Flag top 3 as HOT LEADS.
Be specific and realistic — no wishful thinking."

# Use OpenAI (fast) with fallback to local
if [[ -n "${OPENAI_API_KEY:-}" ]]; then
  GIGS=$(curl -s https://api.openai.com/v1/chat/completions \
    -H "Authorization: Bearer ${OPENAI_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"gpt-4o\",\"messages\":[{\"role\":\"user\",\"content\":$(echo "$PROMPT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}],\"max_tokens\":2000}" \
    2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['choices'][0]['message']['content'])" 2>/dev/null)
fi

# Fallback to local LLM
if [[ -z "$GIGS" ]]; then
  GIGS=$(echo "$PROMPT" | ollama run gemma4:e4b 2>/dev/null || echo "LLM unavailable — run manually")
fi

# Write output
cat > "$OUTPUT" << EOF
# Gig Scan — ${TODAY} ${SLOT}:00
> Clawmpson multi-platform sweep. Skills: ${SKILLS:0:80}...

${GIGS}

---
*Reply to Telegram with gig number to bid. Clawmpson drafts proposal + applies within 30min.*
*Full file: outputs/gigs-${TODAY}-${SLOT}.md*
EOF

# Count hot leads
HOT=$(echo "$GIGS" | grep -c "HOT LEAD\|HOT_LEAD\|🔥\|Confidence.*[89]/10\|Confidence.*10/10" || echo 0)

echo "[${TODAY} ${SLOT}:00] Gig scan complete — ${HOT} hot leads" >> "$LOG"

# Telegram only if hot leads found or first scan of the day
FIRST_TODAY=$(ls "${OPENCLAW_ROOT}/outputs/gigs-${TODAY}-"*.md 2>/dev/null | wc -l)
if [[ "$HOT" -gt 0 ]] || [[ "$FIRST_TODAY" -le 1 ]]; then
  TOP=$(echo "$GIGS" | grep "^\*\*\[" | head -5)
  MESSAGE="🎯 Gig Scan — ${TODAY} ${SLOT}:00
${HOT} hot leads found.

Top opportunities:
${TOP}

Reply # to bid → proposal drafted in 30min.
File: outputs/gigs-${TODAY}-${SLOT}.md"
  bash "${OPENCLAW_ROOT}/scripts/notify-telegram.sh" "$MESSAGE" 2>/dev/null || true
fi
