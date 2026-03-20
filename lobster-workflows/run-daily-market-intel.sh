#!/bin/bash
# =============================================================================
# run-daily-market-intel.sh — Implements daily-market-intel.lobster
# Schedule: daily at 6:30am (30 6 * * *)
# Phase 3 — requires MiroFish validation pass (complete as of 2026-03-20)
#
# Pipeline:
#   1. Find today's scout reports
#   2. Skip + log if none
#   3. Extract 2-3 market-relevant items via Ollama
#   4. Run MiroFish-style synthesis per item
#   5. Write report to ~/openclaw/outputs/market-intel-{date}.md
#   6. Telegram notification with executive summary (Tier-2: Jordan approves)
#   7. Log to IDLE_LOG.md
# =============================================================================

OPENCLAW_ROOT="${HOME}/openclaw"
TODAY=$(date +%Y-%m-%d)
TIMESTAMP=$(date +%H:%M)
OUTPUTS_DIR="${OPENCLAW_ROOT}/outputs"
LOG_FILE="${OPENCLAW_ROOT}/logs/cron-market-intel.log"
IDLE_LOG="${OPENCLAW_ROOT}/memory/IDLE_LOG.md"
REPORT_OUT="${OUTPUTS_DIR}/market-intel-${TODAY}.md"

# Load .env
set -a
source "${OPENCLAW_ROOT}/.env" 2>/dev/null || true
set +a

mkdir -p "${OPENCLAW_ROOT}/logs"

echo "[$(date)] run-daily-market-intel start" >> "$LOG_FILE"

# =============================================================================
# Step 1: Find today's scout reports
# =============================================================================
SCOUTS=$(find "${OUTPUTS_DIR}" -name "*-scout-${TODAY}*.md" 2>/dev/null | head -10)

if [[ -z "$SCOUTS" ]]; then
  cat >> "$IDLE_LOG" << LOGENTRY

### Market Intel Skip — ${TODAY} ${TIMESTAMP}
- No scout reports found for today
- Skipped market intel run
LOGENTRY
  echo "[$(date)] No scout reports today — skip" >> "$LOG_FILE"
  exit 0
fi

SCOUT_COUNT=$(echo "$SCOUTS" | wc -l | tr -d ' ')
SCOUT_CONTENT=$(cat $SCOUTS 2>/dev/null | head -400)

echo "[$(date)] Found ${SCOUT_COUNT} scout report(s)" >> "$LOG_FILE"

# =============================================================================
# Step 2: Extract market-relevant items via Ollama
# =============================================================================
EXTRACT_PROMPT="You are a market intelligence analyst for a bootstrapped web business.

Review these scout reports from today and extract the 2-3 items most relevant to market intelligence.
Focus on: competitor moves, pricing changes, technology shifts, B2B SaaS signals, NFC/digital card market, automation tools.

SCOUT REPORTS:
${SCOUT_CONTENT}

For each item output EXACTLY this format:
---ITEM---
TOPIC: <one sentence>
SOURCE: <source name + credibility: high/medium/low>
SIGNAL: <why it matters for a SaaS + NFC card + automation business (1-2 sentences)>
SEED: <500 word max paragraph suitable as a MiroFish simulation seed>
---END---

If fewer than 2 items are high-signal, say so and output what you found. No filler."

echo "[$(date)] Extracting items via Ollama..." >> "$LOG_FILE"
EXTRACTED=$(echo "$EXTRACT_PROMPT" | ollama run qwen3:30b 2>/dev/null || echo "ERROR: Ollama unavailable")

if [[ "$EXTRACTED" == ERROR:* ]]; then
  echo "[$(date)] Ollama unavailable — aborting" >> "$LOG_FILE"
  bash "${OPENCLAW_ROOT}/scripts/notify-telegram.sh" \
    "Market Intel ${TODAY}: Ollama unavailable — run skipped. Check ollama serve." 2>/dev/null || true
  exit 1
fi

# =============================================================================
# Step 3: MiroFish synthesis — competitive + strategic analysis per item
# =============================================================================
SYNTHESIS_PROMPT="You are MiroFish, a competitive intelligence simulation engine.

You have extracted the following market signals from today's scout reports:

${EXTRACTED}

Run a structured competitive analysis for each item. For each:

1. MARKET DYNAMICS: What does this signal tell us about competitive movement?
2. THREAT / OPPORTUNITY: Is this a threat or opportunity for:
   - A bootstrapped SaaS operator ($500-5000/month client engagements)
   - An NFC digital business card product (B2B small team focus)
   - A workflow automation service for SMBs
3. COMPETITIVE RESPONSE: What should a solo operator do about this in the next 30 days?
4. CONFIDENCE: high / medium / low — how reliable is this signal?

Then write:
EXECUTIVE SUMMARY (3 sentences max): The single most important thing Jordan needs to know today.
TOP ACTION (1 sentence): The one concrete thing to act on if time allows.

Keep the full analysis under 800 words."

echo "[$(date)] Running MiroFish synthesis..." >> "$LOG_FILE"
SYNTHESIS=$(echo "$SYNTHESIS_PROMPT" | ollama run qwen3:30b 2>/dev/null || echo "ERROR: Ollama synthesis failed")

# =============================================================================
# Step 4: Write report
# =============================================================================
cat > "$REPORT_OUT" << REPORT
# Market Intelligence Report — ${TODAY}

**Generated:** ${TODAY} ${TIMESTAMP}
**Scout reports processed:** ${SCOUT_COUNT}
**Pipeline:** MiroFish v0.1 · Ollama qwen3:30b
**Status:** Pending Tier-2 approval (Jordan)

---

## Extracted Signals

${EXTRACTED}

---

## MiroFish Synthesis

${SYNTHESIS}

---

*Tier-2 approval required before any external delivery.*
*Reply /approve-intel-${TODAY} to mark as deliverable.*
REPORT

echo "[$(date)] Report written to ${REPORT_OUT}" >> "$LOG_FILE"

# =============================================================================
# Step 5: Extract executive summary for Telegram
# =============================================================================
EXEC_SUMMARY=$(echo "$SYNTHESIS" | python3 -c "
import sys
text = sys.stdin.read()
# Find EXECUTIVE SUMMARY section
idx = text.upper().find('EXECUTIVE SUMMARY')
if idx >= 0:
    chunk = text[idx:idx+400]
    lines = [l.strip() for l in chunk.split('\n') if l.strip()]
    # Skip the header line, take next 3 lines
    body = ' '.join(lines[1:4])
    print(body[:300])
else:
    print(text[:300])
" 2>/dev/null || echo "(see report for summary)")

TOP_ACTION=$(echo "$SYNTHESIS" | python3 -c "
import sys
text = sys.stdin.read()
idx = text.upper().find('TOP ACTION')
if idx >= 0:
    chunk = text[idx:idx+200]
    lines = [l.strip() for l in chunk.split('\n') if l.strip()]
    body = ' '.join(lines[1:3])
    print(body[:200])
else:
    print('')
" 2>/dev/null || echo "")

# =============================================================================
# Step 6: Telegram notification (Tier-2 hold)
# =============================================================================
TG_MSG="Market Intel — ${TODAY}

${EXEC_SUMMARY}

${TOP_ACTION:+Action: ${TOP_ACTION}}

Scouts processed: ${SCOUT_COUNT}
Report: ~/openclaw/outputs/market-intel-${TODAY}.md

/approve-intel-${TODAY} to mark deliverable
/deny-intel-${TODAY} to reject"

bash "${OPENCLAW_ROOT}/scripts/notify-telegram.sh" "$TG_MSG" 2>/dev/null || \
  echo "[$(date)] Telegram notification failed" >> "$LOG_FILE"

# =============================================================================
# Step 7: Log
# =============================================================================
cat >> "$IDLE_LOG" << LOGENTRY

### Market Intel — ${TODAY} ${TIMESTAMP}
- Scout reports: ${SCOUT_COUNT}
- Report: outputs/market-intel-${TODAY}.md
- Telegram: sent (Tier-2 hold)
LOGENTRY

echo "[$(date)] run-daily-market-intel complete" >> "$LOG_FILE"
