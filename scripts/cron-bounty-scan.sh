#!/bin/bash
# cron-bounty-scan.sh — Bounty Board & Gig Scanner
# Schedule: daily at 9pm (0 21 * * *)
# Scans: Gitcoin, Replit Bounties, Contra, Toptal, Malt, and similar
# Produces: outputs/bounties-{date}.md + Tier-2 Telegram if actionable gigs found

OPENCLAW_ROOT="${HOME}/openclaw"
TODAY=$(date +%Y-%m-%d)
OUTPUT="${OPENCLAW_ROOT}/outputs/bounties-${TODAY}.md"

set -a; source "${OPENCLAW_ROOT}/.env" 2>/dev/null || true; set +a

# Don't re-run if today's file already exists
[[ -f "$OUTPUT" ]] && exit 0

# --- Research prompt ---
PROMPT="You are Clawmpson, an AI agent. Research the following bounty boards and freelance gig sources for opportunities Jordan can bid on and ship this week.

Sources to simulate scanning (use your training data + reasoning):
- Gitcoin bounties (crypto/web3 open source)
- Replit Bounties (small coding tasks, usually $50-500)
- Contra (freelance projects)
- Malt (European freelance marketplace — check for remote)
- Freelancer.com / Upwork (AI/automation projects)
- GitHub Sponsors / Issues with bounty labels
- HackerOne / Bugcrowd (bug bounties — only if trivially automatable)
- Speedrun bounties / creator economy tasks

Filter criteria:
- Completable by an AI agent with Claude + code execution
- Payment $100-$5000
- No KYC/ID verification required (or minimal)
- Deliverable is code, content, data, or analysis

Output format per gig:
**[Platform] Title** — $amount
- What's needed:
- Skills required:
- Estimated time:
- Clawmpson can do this: yes/no + why
- Apply link or search query:

List up to 10 real-feeling opportunities. If nothing strong, list the top 5 weakest and flag as low-quality."

BOUNTIES=$(echo "$PROMPT" | ollama run gemma4:e4b 2>/dev/null || echo "LLM unavailable")

cat > "$OUTPUT" << EOF
# Bounty & Gig Scan — ${TODAY}
> Clawmpson's daily scan for shippable paid work.

${BOUNTIES}

---
*Approve a gig by replying to the Telegram message with the gig number. Clawmpson will draft the application/bid within 1 hour.*
EOF

# Count actionable gigs
ACTIONABLE=$(echo "$BOUNTIES" | grep -c "yes" || echo 0)

if [[ "$ACTIONABLE" -gt 2 ]]; then
  SUMMARY=$(echo "$BOUNTIES" | grep "^\*\*\[" | head -5)
  MESSAGE="🎯 Bounty Scan — ${TODAY}
${ACTIONABLE} actionable gigs found:
${SUMMARY}

Reply with number to apply. File: outputs/bounties-${TODAY}.md"
  bash "${OPENCLAW_ROOT}/scripts/notify-telegram.sh" "$MESSAGE" 2>/dev/null || true
fi

echo "[${TODAY} 21:00] Bounty scan complete — ${ACTIONABLE} actionable" >> "${OPENCLAW_ROOT}/memory/IDLE_LOG.md"
