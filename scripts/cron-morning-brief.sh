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
# Pull today's ideas if available
IDEAS_FILE="${OPENCLAW_ROOT}/outputs/ideas-${TODAY}.md"
IDEAS_SUMMARY=""
if [[ -f "$IDEAS_FILE" ]]; then
  IDEAS_SUMMARY=$(grep "^## " "$IDEAS_FILE" | head -10 | nl -w2 -s'. ' | sed 's/## //')
fi

# Pull today's bounties if available
BOUNTIES_FILE="${OPENCLAW_ROOT}/outputs/bounties-${TODAY}.md"
BOUNTIES_SUMMARY=""
if [[ -f "$BOUNTIES_FILE" ]]; then
  BOUNTIES_SUMMARY=$(grep "^\*\*\[" "$BOUNTIES_FILE" | head -5)
fi

PROMPT="Compile a sharp morning brief. Under 12 lines total. No filler. Jordan is building to $10k/month — zero earned so far.

Overnight idle log: ${OVERNIGHT}
Completed tasks: ${COMPLETED}
Pending queue: ${PENDING}

Format:
Status: [1 line — what happened overnight]
Queue: [N pending tasks, top priority]
Ideas ready: [yes/no — how many in today's brief]
Action needed: [what Jordan should approve or decide today]"

BRIEF=$(echo "$PROMPT" | ollama run qwen2.5:7b 2>/dev/null)
if [[ -z "$BRIEF" || "$BRIEF" == *"error"* ]]; then
  # Ollama down — attempt restart and escalate
  ollama serve &>/dev/null &
  sleep 5
  BRIEF=$(echo "$PROMPT" | ollama run qwen2.5:7b 2>/dev/null)
  if [[ -z "$BRIEF" || "$BRIEF" == *"error"* ]]; then
    BRIEF="Brief unavailable — Ollama not responding (restart attempted, still down)"
    # Escalate: high-priority Telegram alert
    ESCALATION="🚨 CRITICAL: Ollama is DOWN — morning brief failed.
Restart attempted automatically but Ollama is still not responding.
This is a Tier-2 escalation — Clawmpson needs manual intervention.

Action required:
1. SSH into VPS and check: systemctl status ollama / ollama serve
2. Check disk space and GPU memory
3. Review logs: journalctl -u ollama --since '1 hour ago'"
    bash "${OPENCLAW_ROOT}/scripts/notify-telegram.sh" "$ESCALATION" 2>/dev/null || true
    # Log the failure for ops agent pickup
    echo "{\"timestamp\":$(date +%s),\"check\":\"ollama\",\"status\":\"fail\",\"detail\":\"Morning brief Ollama failure — restart failed, Tier-2 escalated\"}" >> "${OPENCLAW_ROOT}/logs/ops-${TODAY}.jsonl"
  fi
fi

# --- Build message ---
MESSAGE="☀️ Morning Brief — ${TODAY}

${BRIEF}"

if [[ -n "$IDEAS_SUMMARY" ]]; then
  MESSAGE="${MESSAGE}

💡 Today's Ideas (reply # to approve):
${IDEAS_SUMMARY}"
fi

if [[ -n "$BOUNTIES_SUMMARY" ]]; then
  MESSAGE="${MESSAGE}

🎯 Gigs ready:
${BOUNTIES_SUMMARY}"
fi

MESSAGE="${MESSAGE}

Pending approvals in queue: ${PENDING}"

bash "${OPENCLAW_ROOT}/scripts/notify-telegram.sh" "$MESSAGE" 2>/dev/null || true

# --- If NO ideas file for today, kick off idea engine now ---
if [[ ! -f "$IDEAS_FILE" ]]; then
  bash "${OPENCLAW_ROOT}/scripts/cron-idea-engine.sh" &
fi

# --- Log ---
cat >> "${OPENCLAW_ROOT}/memory/IDLE_LOG.md" << LOGENTRY

### Morning Brief — ${TODAY} 08:03
- Completed overnight: ${COMPLETED}
- Pending queue: ${PENDING}
LOGENTRY
