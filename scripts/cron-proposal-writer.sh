#!/bin/bash
# cron-proposal-writer.sh — Auto-draft proposals for approved gigs
# Triggered manually: bash cron-proposal-writer.sh PLATFORM "JOB_TITLE" BUDGET
# Or called from gig approval flow

OPENCLAW_ROOT="${HOME}/openclaw"
TODAY=$(date +%Y-%m-%d)
PLATFORM="${1:-Upwork}"
JOB_TITLE="${2:-Automation project}"
BUDGET="${3:-500}"
OUTPUT="${OPENCLAW_ROOT}/outputs/proposal-${TODAY}-$(echo "$JOB_TITLE" | tr ' ' '-' | tr '[:upper:]' '[:lower:]' | cut -c1-30).md"

set -a; source "${OPENCLAW_ROOT}/.env" 2>/dev/null || true; set +a

PROMPT="Write a winning freelance proposal for this job:
Platform: ${PLATFORM}
Job: ${JOB_TITLE}
Budget: \$${BUDGET}

Operator background: AI agent developer, full-stack (Python, Swift/iOS, JS/React), automation specialist, OpenAI/Claude API expert, Stripe integration, Telegram bots, web scraping, data pipelines.

Write the proposal in first person (as if Jordan/Omega MegaCorp is writing it).
Format:
- Opening hook (1 line that shows you read the brief)
- Why we're the right fit (2-3 sentences, specific to the job)
- Delivery approach (brief, confident, no fluff)
- Timeline + price anchor
- Call to action

Keep it under 200 words. Sound human, confident, slightly casual. No AI-sounding buzzwords."

if [[ -n "${OPENAI_API_KEY:-}" ]]; then
  PROPOSAL=$(curl -s https://api.openai.com/v1/chat/completions \
    -H "Authorization: Bearer ${OPENAI_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"gpt-4o\",\"messages\":[{\"role\":\"user\",\"content\":$(echo "$PROMPT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}],\"max_tokens\":600}" \
    2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['choices'][0]['message']['content'])" 2>/dev/null)
fi

if [[ -z "$PROPOSAL" ]]; then
  PROPOSAL=$(echo "$PROMPT" | ollama run qwen3:30b 2>/dev/null || echo "LLM unavailable")
fi

cat > "$OUTPUT" << EOF
# Proposal — ${JOB_TITLE}
**Platform:** ${PLATFORM} | **Budget:** \$${BUDGET} | **Date:** ${TODAY}

## Draft Proposal

${PROPOSAL}

---
## Checklist before sending
- [ ] Personalize opening with specific detail from the job post
- [ ] Attach 1-2 relevant portfolio items (or links to builds)
- [ ] Set bid at or slightly below budget anchor
- [ ] Follow up in 24h if no response
EOF

echo "Proposal written: ${OUTPUT}"
MESSAGE="📝 Proposal drafted: ${JOB_TITLE} (\$${BUDGET}) on ${PLATFORM}
Review + send: outputs/proposal-${TODAY}-*.md"
bash "${OPENCLAW_ROOT}/scripts/notify-telegram.sh" "$MESSAGE" 2>/dev/null || true
