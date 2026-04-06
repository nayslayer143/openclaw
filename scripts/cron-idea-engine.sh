#!/bin/bash
# cron-idea-engine.sh — Perpetual Idea Engine
# Schedule: daily at 11:30pm (30 23 * * *)
# Produces: 10+ researched money-making ideas → outputs/ideas-{date}.md
# Sends: Tier-2 Telegram for Jordan morning review

OPENCLAW_ROOT="${HOME}/openclaw"
TODAY=$(date +%Y-%m-%d)
OUTPUT="${OPENCLAW_ROOT}/outputs/ideas-${TODAY}-${HOUR}.md"

set -a; source "${OPENCLAW_ROOT}/.env" 2>/dev/null || true; set +a

# Allow 3 runs per day — use hour-stamped output files
HOUR=$(date +%H)
OUTPUT="${OPENCLAW_ROOT}/outputs/ideas-${TODAY}-${HOUR}.md"

# Throttle: slow down generation when pending backlog is large
PENDING_IDEAS=$(find "${OPENCLAW_ROOT}/ideas" -name "idea-*.json" -exec grep -l '"status": "pending"' {} \; 2>/dev/null | wc -l | tr -d ' ')
if [[ "$PENDING_IDEAS" -ge 100 ]]; then
  echo "[${TODAY}] Idea engine skipped — ${PENDING_IDEAS} pending ideas (hard cap 100)" >> "${OPENCLAW_ROOT}/memory/IDLE_LOG.md"
  exit 0
elif [[ "$PENDING_IDEAS" -ge 50 ]]; then
  # Only generate every 3rd day when backlog is 50-99
  DAY_OF_YEAR=$(date +%j)
  if [[ $((DAY_OF_YEAR % 3)) -ne 0 ]]; then
    echo "[${TODAY}] Idea engine throttled — ${PENDING_IDEAS} pending ideas (generating every 3rd day)" >> "${OPENCLAW_ROOT}/memory/IDLE_LOG.md"
    exit 0
  fi
fi

# --- Pull context ---
MEMORY=$(tail -50 "${OPENCLAW_ROOT}/memory/MEMORY.md" 2>/dev/null || echo "No memory")
PAST_IDEAS=$(ls "${OPENCLAW_ROOT}/outputs/ideas-"*.md 2>/dev/null | tail -10 | xargs grep "^##" 2>/dev/null | sed 's/.*##//' | head -50 || echo "None yet")
QUEUE=$(cat "${OPENCLAW_ROOT}/queue/pending.json" 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print('\n'.join([t.get('title','') for t in d[:10]]))" 2>/dev/null || echo "Empty")
# Pull latest market intel for grounded ideation
MARKET_INTEL=$(ls "${OPENCLAW_ROOT}/autoresearch/outputs/briefs/market-intel-"*.md 2>/dev/null | tail -1 | xargs tail -30 2>/dev/null || echo "No market intel yet")
# Pull latest prediction market signals
PREDICTION_SIGNALS=$(ls "${OPENCLAW_ROOT}/autoresearch/outputs/datasets/prediction-market-"*.json 2>/dev/null | tail -1 | xargs python3 -c "import json,sys; d=json.load(open(sys.argv[1])); ops=d.get('opportunities',[]); [print(o.get('market',''),o.get('edge',0),o.get('confidence','')) for o in ops[:5]]" 2>/dev/null || echo "No prediction signals yet")
# Pull gig/bounty context
GIGS=$(ls "${OPENCLAW_ROOT}/outputs/gigs-"*.md 2>/dev/null | tail -1 | xargs head -40 2>/dev/null || echo "No gig data yet")

# --- Generate ideas via LLM ---
PROMPT="You are Clawmpson — AI business operator, autonomous agent swarm commander, and relentless money-making engine for Jordan (Omega MegaCorp, San Francisco).

Jordan goal: \$10k/month net revenue, ASAP. Currently \$0. Every dollar counts.

Assets: Claude Opus 4.6, Ollama LLMs, Fiverr (@hiremaximus), Upwork (Adam Maximus), X (@ogdenclash), LinkedIn (Adam Maximus), Gmail API, SendGrid, Stripe, Render, Serper, Rabby (ETH), Phantom (SOL), 3000sqft SF fab lab (3D printers, sublimation, laser cutter, CNC), meOS (TestFlight), xyz.cards (live), Lenticular Fashion (holographic textiles), InformationCube (kinetic controller, shipping soon), AutoResearch pipeline, MiroFish simulation engine.

Market intelligence: ${MARKET_INTEL}
Prediction signals: ${PREDICTION_SIGNALS}
Active gigs: ${GIGS}
System memory: ${MEMORY}

Generate exactly 15 SOLID, differentiated, actionable money-making ideas. Mix quick wins (days) with medium plays (weeks). Every idea needs one specific autonomous first action Clawmpson can take TODAY.

Cover all categories:
1. Fiverr/Upwork services Clawmpson can list and deliver autonomously (AI research, content, automation)
2. Lenticular Fashion / InformationCube / xyz.cards angles
3. Prediction market / arbitrage (paper-trade first)
4. Autonomous content plays for X or LinkedIn building to monetizable audience
5. AutoResearch retainer clients (\$500-3k/month overnight research)
6. MiroFish simulation reports as market intelligence (\$200-500 one-off)
7. Greenfield SaaS builds via Ralph loop — sellable clones or agent stacks
8. Crypto/DeFi arbitrage or yield using Rabby/Phantom wallets

Format each idea EXACTLY as:
## [Title]
- **What**: 1-2 sentences
- **Revenue model**: how money flows
- **Time to first \$**: realistic
- **First action**: one specific autonomous action right now
- **Risk**: biggest blocker

Do NOT repeat ideas from: ${PAST_IDEAS}

Be ruthless. Be specific. No vague nonsense. Think like a broke genius with infinite compute and zero patience."

IDEAS=$(echo "$PROMPT" | ollama run gemma4:26b 2>/dev/null || echo "$PROMPT" | ollama run gemma4:26b 2>/dev/null)
if [[ -z "$IDEAS" || "$IDEAS" == *"error"* ]]; then
  # Ollama down — attempt restart and retry
  ollama serve &>/dev/null &
  sleep 5
  IDEAS=$(echo "$PROMPT" | ollama run gemma4:26b 2>/dev/null || echo "$PROMPT" | ollama run gemma4:26b 2>/dev/null)
  if [[ -z "$IDEAS" || "$IDEAS" == *"error"* ]]; then
    IDEAS="LLM unavailable — Ollama not responding (restart attempted, still down)"
    ESCALATION="🚨 CRITICAL: Ollama is DOWN — idea engine failed.
Restart attempted automatically but Ollama is still not responding.
Tier-2 escalation — requires manual intervention."
    bash "${OPENCLAW_ROOT}/scripts/notify-telegram.sh" "$ESCALATION" 2>/dev/null || true
    echo "{\"timestamp\":$(date +%s),\"check\":\"ollama\",\"status\":\"fail\",\"detail\":\"Idea engine Ollama failure — restart failed, Tier-2 escalated\"}" >> "${OPENCLAW_ROOT}/logs/ops-${TODAY}.jsonl"
  fi
fi

# --- Write output ---
cat > "$OUTPUT" << EOF
# Ideas Brief — ${TODAY}
> Generated by Clawmpson at $(date +"%H:%M"). 15 researched opportunities for Jordan's review.
> **Goal:** $10k/month. **Status:** $0 earned. Let's fix that.

${IDEAS}

---
*To approve an idea and push it to queue: reply to the Telegram message with the idea number.*
*Clawmpson will research further and build an action plan within 2 hours.*
EOF

# --- Telegram ping ---
SUMMARY=$(echo "$IDEAS" | grep "^## " | head -10 | nl -w2 -s'. ' | sed 's/## //')
MESSAGE="💡 Morning Ideas Brief — ${TODAY}

15 money-making ideas ready for review:
${SUMMARY}

Reply with number(s) to approve → I'll build action plans.
File: outputs/ideas-${TODAY}-${HOUR}.md"

bash "${OPENCLAW_ROOT}/scripts/notify-telegram.sh" "$MESSAGE" 2>/dev/null || true

# --- Ingest into Ideas Lab dashboard ---
python3 "${OPENCLAW_ROOT}/scripts/idea-ingest.py" "${TODAY}" 2>/dev/null || true

# --- Log ---
echo "[${TODAY} 23:30] Idea engine ran — wrote ${OUTPUT}, ingested to Ideas Lab" >> "${OPENCLAW_ROOT}/memory/IDLE_LOG.md"
