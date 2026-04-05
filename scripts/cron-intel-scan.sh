#!/bin/bash
# cron-intel-scan.sh — Cycle 2: Intel Scan
# Schedule: daily at 7:03am (3 7 * * *)
# Implements: daily-intel-lite.lobster

OPENCLAW_ROOT="${HOME}/openclaw"
TODAY=$(date +%Y-%m-%d)
YESTERDAY=$(date -v-1d +%Y-%m-%d 2>/dev/null || date -d yesterday +%Y-%m-%d)

# Load .env
set -a
source "${OPENCLAW_ROOT}/.env" 2>/dev/null || true
set +a

# --- Find unprocessed scout reports from last 24h ---
REPORTS=$(find "${OPENCLAW_ROOT}/outputs" -name "*-scout-*.md" -newer "${OPENCLAW_ROOT}/outputs/.last-intel-scan" 2>/dev/null | head -10)

if [[ -z "$REPORTS" ]]; then
  # Log and exit — nothing to scan
  cat >> "${OPENCLAW_ROOT}/memory/IDLE_LOG.md" << LOGENTRY

### Intel Scan — ${TODAY} 07:03
- Reports scanned: 0
- No new scout reports found
LOGENTRY
  exit 0
fi

REPORT_COUNT=$(echo "$REPORTS" | wc -l | tr -d ' ')
REPORT_CONTENT=$(cat $REPORTS 2>/dev/null | head -200)

# --- Extract signal via Ollama ---
PROMPT="Review these scout reports from the last 24 hours and extract the 1-3 highest-signal items.

${REPORT_CONTENT}

For each item:
- What it is (1 sentence)
- Why it matters to a web business building SaaS, NFC cards, and consumer tech (1 sentence)
- Recommended action: investigate | watch | ignore

No simulation. No speculation. Signal only. If nothing is high-signal, say so."

INTEL=$(echo "$PROMPT" | ollama run gemma4:e4b 2>/dev/null || echo "Intel scan unavailable — Ollama not responding")

# --- Send ---
MESSAGE="Morning Intel Brief — ${TODAY}

${INTEL}

Scout reports processed: ${REPORT_COUNT}"

bash "${OPENCLAW_ROOT}/scripts/notify-telegram.sh" "$MESSAGE" 2>/dev/null || true

# --- Mark scan timestamp ---
touch "${OPENCLAW_ROOT}/outputs/.last-intel-scan"

# --- Log ---
cat >> "${OPENCLAW_ROOT}/memory/IDLE_LOG.md" << LOGENTRY

### Intel Scan — ${TODAY} 07:03
- Reports scanned: ${REPORT_COUNT}
- Scan complete
LOGENTRY
