#!/bin/bash
# =============================================================================
# cron-memory-librarian.sh — 6-hour intra-day memory synthesis
# Schedule: 0 */6 * * * (midnight, 6am, noon, 6pm)
# Phase 4 — Memory Librarian · IDLE_PROTOCOL Advanced Tier
#
# Lightweight version of nightly consolidation — scans new log entries
# since last run and appends structured summary to IDLE_LOG.md
# =============================================================================

OPENCLAW_ROOT="${HOME}/openclaw"
LOG_FILE="${OPENCLAW_ROOT}/logs/cron-memory-librarian.log"
IDLE_LOG="${OPENCLAW_ROOT}/memory/IDLE_LOG.md"
MARKER_FILE="${OPENCLAW_ROOT}/logs/.memory-librarian-lastrun"
TODAY=$(date +%Y-%m-%d)
TIMESTAMP=$(date +%H:%M)

set -a
source "${OPENCLAW_ROOT}/.env" 2>/dev/null || true
set +a

mkdir -p "${OPENCLAW_ROOT}/logs"
echo "[$(date)] cron-memory-librarian start" >> "$LOG_FILE"

# --- Get log lines since last run ---
LAST_RUN=$(cat "$MARKER_FILE" 2>/dev/null || echo "0")
NOW=$(date +%s)

# Collect recent log content (last 6 hours of jsonl logs)
LOG_CONTENT=$(find "${OPENCLAW_ROOT}/logs" -maxdepth 1 -name "*.jsonl" \
  -newer "$MARKER_FILE" 2>/dev/null \
  -exec cat {} \; 2>/dev/null | tail -200)

# Update marker
date +%s > "$MARKER_FILE"

if [[ -z "$LOG_CONTENT" ]]; then
  echo "[$(date)] No new log entries — skipping synthesis" >> "$LOG_FILE"
  exit 0
fi

TASK_COUNT=$(echo "$LOG_CONTENT" | grep -c '"event":"session_complete"' 2>/dev/null || echo 0)
ERROR_COUNT=$(echo "$LOG_CONTENT" | grep -c 'FATAL\|ERROR' 2>/dev/null || echo 0)
BLOCKED_COUNT=$(echo "$LOG_CONTENT" | grep -c '"status":"blocked"' 2>/dev/null || echo 0)

# Skip if nothing interesting
if [[ "$TASK_COUNT" -eq 0 && "$ERROR_COUNT" -eq 0 ]]; then
  echo "[$(date)] No tasks or errors in window — skipping" >> "$LOG_FILE"
  exit 0
fi

# --- Synthesize with gemma4:e4b (fast, <4K context) ---
PROMPT="Summarize the last 6 hours of OpenClaw activity. Be brief — 3-5 lines max.

Tasks completed: ${TASK_COUNT}
Errors: ${ERROR_COUNT}
Blocked: ${BLOCKED_COUNT}

Recent logs:
${LOG_CONTENT}

Output format: plain text, factual, no markdown. Cover: what ran, any errors, anything worth flagging."

SUMMARY=$(echo "$PROMPT" | timeout 120 ollama run gemma4:e4b 2>/dev/null \
  || echo "Synthesis unavailable — Ollama not responding")

# --- Append to IDLE_LOG ---
cat >> "$IDLE_LOG" << LOGENTRY

### Memory Librarian — ${TODAY} ${TIMESTAMP}
Tasks: ${TASK_COUNT} | Errors: ${ERROR_COUNT} | Blocked: ${BLOCKED_COUNT}
${SUMMARY}
LOGENTRY

echo "[$(date)] cron-memory-librarian complete — ${TASK_COUNT} tasks, ${ERROR_COUNT} errors" >> "$LOG_FILE"
