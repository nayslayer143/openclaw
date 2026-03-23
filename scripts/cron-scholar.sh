#!/bin/bash
# =============================================================================
# cron-scholar.sh — AutoScholar Nightly Discovery + Digestion
# Schedule: nightly at 2am (0 2 * * *)
# Phase 4 — AutoScholar · IDLE_PROTOCOL Advanced Tier
#
# Pipeline:
#   1. Run auto_mode() — discover + rank + digest new papers
#   2. Log results to logs/cron-scholar.log
#   3. Send Telegram summary via notify-telegram.sh
# =============================================================================

OPENCLAW_ROOT="${HOME}/openclaw"
TODAY=$(date +%Y-%m-%d)
LOG_FILE="${OPENCLAW_ROOT}/logs/cron-scholar.log"

mkdir -p "${OPENCLAW_ROOT}/logs"

echo "[$(date)] cron-scholar start" >> "$LOG_FILE"

# Load .env
set -a
source "${OPENCLAW_ROOT}/.env" 2>/dev/null || true
set +a

# Run auto_mode and capture JSON result
RESULT=$(python3 -c "
import json, sys
sys.path.insert(0, '${OPENCLAW_ROOT}/scripts')
from autoresearch import scholar
print(json.dumps(scholar.auto_mode()))
" 2>> "$LOG_FILE")

if [[ -z "$RESULT" ]]; then
  echo "[$(date)] auto_mode returned no output — check errors above" >> "$LOG_FILE"
  bash "${OPENCLAW_ROOT}/scripts/notify-telegram.sh" \
    "AutoScholar Nightly ${TODAY}: Failed to run. Check ~/openclaw/logs/cron-scholar.log" 2>/dev/null || true
  exit 1
fi

DISCOVERED=$(echo "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('discovered', 0))" 2>/dev/null || echo "?")
DIGESTED=$(echo "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('digested', 0))" 2>/dev/null || echo "?")
ACTIONS=$(echo "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); acts=d.get('actions_taken',[]); print(','.join(acts) if acts else 'none')" 2>/dev/null || echo "?")
TOP_TITLES=$(echo "$RESULT" | python3 -c "
import json,sys
d=json.load(sys.stdin)
titles=d.get('top_titles',[])
print('\n'.join('• ' + t for t in titles[:5]) if titles else '(none)')
" 2>/dev/null || echo "(none)")

echo "[$(date)] discovered=${DISCOVERED} digested=${DIGESTED} actions=${ACTIONS}" >> "$LOG_FILE"

bash "${OPENCLAW_ROOT}/scripts/notify-telegram.sh" \
"AutoScholar Nightly — ${TODAY}

Discovered: ${DISCOVERED} papers
Digested: ${DIGESTED} papers
Actions taken: ${ACTIONS}

Top papers:
${TOP_TITLES}

Review at: ~/openclaw/autoresearch/outputs/papers/" 2>/dev/null || true

echo "[$(date)] cron-scholar complete" >> "$LOG_FILE"
