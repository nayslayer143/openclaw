#!/bin/bash
# cron-morning-brief.sh — Morning Brief
# Schedule: daily at 8:03am (3 8 * * *)
# Implements: morning-brief.lobster

OPENCLAW_ROOT="${HOME}/openclaw"
TODAY=$(date +%Y-%m-%d)

# Load .env
set -a
source "${OPENCLAW_ROOT}/.env" 2>/dev/null || true
set +a

# --- Gather data ---
OVERNIGHT=$(grep -h "${TODAY}" "${OPENCLAW_ROOT}/memory/IDLE_LOG.md" 2>/dev/null | tail -20 || echo "No overnight entries")

QUEUE_FILE="${OPENCLAW_ROOT}/queue/pending.json"
COMPLETED_FILE="${OPENCLAW_ROOT}/queue/completed.json"

PENDING=$(python3 -c "import json; print(len(json.load(open('${QUEUE_FILE}'))))" 2>/dev/null || echo 0)
COMPLETED=$(python3 -c "import json; d=json.load(open('${COMPLETED_FILE}')); print(len([t for t in d if str(t.get('completed_date','')).startswith('${TODAY}')]))" 2>/dev/null || echo 0)

LOG_LINES=$(wc -l "${OPENCLAW_ROOT}/logs/"*"-${TODAY}.jsonl" 2>/dev/null | tail -1 | awk '{print $1}' || echo 0)

# --- Compile brief via Ollama ---
PROMPT="Compile a morning brief from this data. Be concise, under 10 lines, no filler.

Overnight idle log: ${OVERNIGHT}
Completed today so far: ${COMPLETED} tasks
Pending queue: ${PENDING} tasks
Log activity: ${LOG_LINES} log lines

Format:
Completed overnight: [summary or none]
Pending approvals: [any or none]
Opportunities: [from idle log if any]"

BRIEF=$(echo "$PROMPT" | ollama run qwen2.5:7b 2>/dev/null || echo "Brief unavailable — Ollama not responding")

# --- Send ---
MESSAGE="Morning Brief — ${TODAY}
${BRIEF}"

bash "${OPENCLAW_ROOT}/scripts/notify-telegram.sh" "$MESSAGE" 2>/dev/null || true

# --- Log ---
cat >> "${OPENCLAW_ROOT}/memory/IDLE_LOG.md" << LOGENTRY

### Morning Brief — ${TODAY} 08:03
- Completed overnight: ${COMPLETED}
- Pending queue: ${PENDING}
LOGENTRY
