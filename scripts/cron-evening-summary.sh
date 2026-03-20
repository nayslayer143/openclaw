#!/bin/bash
# cron-evening-summary.sh — Evening Summary
# Schedule: daily at 6:03pm (3 18 * * *)
# Implements: evening-summary.lobster

OPENCLAW_ROOT="${HOME}/openclaw"
TODAY=$(date +%Y-%m-%d)

# Load .env
set -a
source "${OPENCLAW_ROOT}/.env" 2>/dev/null || true
set +a

# --- Gather data ---
QUEUE_FILE="${OPENCLAW_ROOT}/queue/pending.json"
COMPLETED_FILE="${OPENCLAW_ROOT}/queue/completed.json"

PENDING=$(python3 -c "import json; print(len(json.load(open('${QUEUE_FILE}'))))" 2>/dev/null || echo 0)
COMPLETED=$(python3 -c "import json; d=json.load(open('${COMPLETED_FILE}')); print(len([t for t in d if str(t.get('completed_date','')).startswith('${TODAY}')]))" 2>/dev/null || echo 0)

LOG_LINES=$(wc -l "${OPENCLAW_ROOT}/logs/"*"-${TODAY}.jsonl" 2>/dev/null | awk 'END{print $1+0}' || echo 0)
ERROR_COUNT=$(grep -c 'FATAL\|ERROR' "${OPENCLAW_ROOT}/logs/"*"-${TODAY}.jsonl" 2>/dev/null | awk -F: 'BEGIN{s=0} {s+=$2} END{print s+0}' || echo 0)

# --- Compile summary via Ollama ---
PROMPT="Compile an evening summary from this data. Be concise, under 10 lines.

Tasks completed today: ${COMPLETED}
Tasks still pending: ${PENDING}
Total log lines today: ${LOG_LINES}
Errors/fatals today: ${ERROR_COUNT}

Tomorrow scheduled: system-health every 30min, intel scan 7am, morning brief 8am, this summary 6pm, nightly consolidation 11pm

Format:
Day Summary:
- Completed: [count + brief]
- Pending: [count]
- Issues: [any errors, or None]

Tomorrow: [scheduled items]"

SUMMARY=$(echo "$PROMPT" | ollama run qwen2.5:7b 2>/dev/null || echo "Summary unavailable — Ollama not responding")

# --- Send ---
MESSAGE="Evening Summary — ${TODAY}
${SUMMARY}"

bash "${OPENCLAW_ROOT}/scripts/notify-telegram.sh" "$MESSAGE" 2>/dev/null || true

# --- Log ---
cat >> "${OPENCLAW_ROOT}/memory/IDLE_LOG.md" << LOGENTRY

### Evening Summary — ${TODAY} 18:03
- Tasks completed: ${COMPLETED}
- Tasks pending: ${PENDING}
- Log activity: ${LOG_LINES} lines
- Errors: ${ERROR_COUNT}
- Nightly consolidation: scheduled for 23:03
LOGENTRY
