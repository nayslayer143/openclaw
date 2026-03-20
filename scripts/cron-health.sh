#!/bin/bash
# cron-health.sh — Cycle 1: Health Watchdog
# Schedule: every 30 min (*/30 * * * *)
# Implements: system-health.lobster

OPENCLAW_ROOT="${HOME}/openclaw"
DATE=$(date +%Y-%m-%d)
TS=$(date +%s)
LOG="${OPENCLAW_ROOT}/logs/ops-${DATE}.jsonl"

mkdir -p "${OPENCLAW_ROOT}/logs"

# Load .env for Telegram
set -a
source "${OPENCLAW_ROOT}/.env" 2>/dev/null || true
set +a

# --- Check Ollama ---
# Use a lightweight API ping with 30s timeout (large models can take time to load)
if curl -sf --max-time 30 http://127.0.0.1:11434/ >/dev/null 2>&1; then
  OLLAMA_STATUS="ok"
else
  OLLAMA_STATUS="fail"
  # Only restart if no Ollama process is already running
  if ! pgrep -x ollama >/dev/null 2>&1; then
    ollama serve >/tmp/ollama-restart.log 2>&1 &
  fi
fi

# --- Disk usage ---
DISK_PCT=$(df -h / | tail -1 | awk '{print $5}' | tr -d '%')

# --- Queue depth ---
QUEUE_FILE="${OPENCLAW_ROOT}/queue/pending.json"
if [[ -f "$QUEUE_FILE" ]]; then
  QUEUE_DEPTH=$(python3 -c "import json; print(len(json.load(open('${QUEUE_FILE}'))))" 2>/dev/null || echo 0)
else
  QUEUE_DEPTH=0
fi

# --- Error count in today's logs ---
ERROR_COUNT=$(grep -c 'FATAL\|ERROR' "${OPENCLAW_ROOT}/logs/"*"-${DATE}.jsonl" 2>/dev/null | awk -F: 'BEGIN{s=0} {s+=$2} END{print s+0}')

# --- Log status ---
echo "{\"event\":\"health\",\"timestamp\":${TS},\"ollama\":\"${OLLAMA_STATUS}\",\"disk_pct\":${DISK_PCT:-0},\"queue_depth\":${QUEUE_DEPTH},\"error_count\":${ERROR_COUNT}}" >> "$LOG"

# --- Alerts ---
notify() {
  bash "${OPENCLAW_ROOT}/scripts/notify-telegram.sh" "$1" 2>/dev/null || true
}

if [[ "${DISK_PCT:-0}" -gt 80 ]]; then
  notify "OpenClaw alert: Disk at ${DISK_PCT}% — needs cleanup"
fi

if [[ "${QUEUE_DEPTH:-0}" -gt 20 ]]; then
  notify "OpenClaw alert: Queue depth ${QUEUE_DEPTH} items — needs triage"
fi

if [[ "${ERROR_COUNT:-0}" -gt 5 ]]; then
  notify "OpenClaw alert: ${ERROR_COUNT} FATAL/ERROR entries today — review logs"
fi

if [[ "$OLLAMA_STATUS" == "fail" ]]; then
  notify "OpenClaw alert: Ollama was unresponsive — attempted restart"
fi
