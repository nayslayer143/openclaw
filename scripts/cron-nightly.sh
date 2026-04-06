#!/bin/bash
# cron-nightly.sh — Daily Memory Consolidation
# Schedule: daily at 11:03pm (3 23 * * *)
# Implements: IDLE_PROTOCOL Cycle 4

OPENCLAW_ROOT="${HOME}/openclaw"
TODAY=$(date +%Y-%m-%d)
YESTERDAY=$(date -v-1d +%Y-%m-%d 2>/dev/null || date -d yesterday +%Y-%m-%d)
ARCHIVE_DIR="${OPENCLAW_ROOT}/logs/archive"
TS=$(date +%s)

# Load .env
set -a
source "${OPENCLAW_ROOT}/.env" 2>/dev/null || true
set +a

mkdir -p "$ARCHIVE_DIR"

# --- Gather today's logs ---
LOG_CONTENT=$(cat "${OPENCLAW_ROOT}/logs/"*"-${TODAY}.jsonl" 2>/dev/null || echo "")
BUILD_RESULTS=$(ls "${OPENCLAW_ROOT}/build-results/"*".json" 2>/dev/null | xargs -I{} python3 -c "import json,sys; d=json.load(open('{}',errors='ignore')); print(d.get('task_id','?'), d.get('status','?'), d.get('summary','')[:80])" 2>/dev/null | head -20 || echo "No build results today")

TASK_COUNT=$(echo "$LOG_CONTENT" | grep -c '"event":"session_complete"' 2>/dev/null || echo 0)
ERROR_COUNT=$(echo "$LOG_CONTENT" | grep -c 'FATAL\|ERROR' 2>/dev/null || echo 0)
BLOCKED_COUNT=$(echo "$LOG_CONTENT" | grep -c '"status":"blocked"' 2>/dev/null || echo 0)

# --- Summarize via Ollama ---
PROMPT="Summarize today's OpenClaw activity for the memory log. Be structured and brief.

Today: ${TODAY}
Tasks completed: ${TASK_COUNT}
Build results: ${BUILD_RESULTS}
Errors in logs: ${ERROR_COUNT}
Blocked tasks: ${BLOCKED_COUNT}

Write a 5-10 line structured summary covering:
1. What was accomplished
2. Any recurring errors or blockers
3. Patterns worth noting for future sessions
4. One suggested improvement if obvious

Format as plain text. No markdown headers. Be factual."

# Short nightly summary (<4K tokens) — gemma4:e4b is fast for summary tasks
# gemma4:26b-A4B (MoE) is reserved for long-context work (self-improvement, autoresearch papers)
SUMMARY=$(echo "$PROMPT" | ollama run gemma4:e4b 2>/dev/null || echo "Consolidation unavailable — Ollama not responding")

# --- Append to MEMORY.md ---
cat >> "${OPENCLAW_ROOT}/memory/IDLE_LOG.md" << LOGENTRY

### Nightly Consolidation — ${TODAY} 23:03
Tasks: ${TASK_COUNT} complete, ${BLOCKED_COUNT} blocked, ${ERROR_COUNT} errors
${SUMMARY}
LOGENTRY

# --- Archive logs older than 7 days ---
find "${OPENCLAW_ROOT}/logs" -maxdepth 1 -name "*.jsonl" -mtime +7 -exec mv {} "${ARCHIVE_DIR}/" \; 2>/dev/null || true

# --- Tier-1 Telegram notification ---
bash "${OPENCLAW_ROOT}/scripts/notify-telegram.sh" "Nightly check — ${TODAY} | Tasks: ${TASK_COUNT} complete, ${BLOCKED_COUNT} blocked, ${ERROR_COUNT} errors" 2>/dev/null || true
