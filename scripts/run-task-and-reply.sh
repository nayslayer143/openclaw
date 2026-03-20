#!/bin/bash
# run-task-and-reply.sh
# Runs a task packet through the full pipeline and sends result to Telegram.
# Usage: bash run-task-and-reply.sh <packet_path> <chat_id>

set -euo pipefail

OPENCLAW_ROOT="${HOME}/openclaw"
PACKET_PATH="$1"
CHAT_ID="$2"
TASK_NAME=$(basename "$PACKET_PATH" .json)

source "${OPENCLAW_ROOT}/.env"
BOT_TOKEN="${TELEGRAM_BOT_TOKEN}"

send_msg() {
  local text="$1"
  curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
    -H "Content-Type: application/json" \
    -d "{\"chat_id\": \"${CHAT_ID}\", \"text\": $(python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))' <<< "$text")}" \
    > /dev/null
}

send_msg "Starting build: ${TASK_NAME}"

# Run the pipeline
BRIDGE_OUTPUT=$(bash "${OPENCLAW_ROOT}/lobster-workflows/build-agent-bridge.sh" "$PACKET_PATH" 2>&1)
echo "$BRIDGE_OUTPUT"
CONTRACT_PATH=$(echo "$BRIDGE_OUTPUT" | tail -1)

# Parse result
STATUS="unknown"
SUMMARY=""
if [[ -f "$CONTRACT_PATH" ]]; then
  STATUS=$(python3 -c "import json; d=json.load(open('${CONTRACT_PATH}')); print(d.get('status','unknown'))")
  CHANGED=$(python3 -c "import json; d=json.load(open('${CONTRACT_PATH}')); print(len(d.get('changed_files',[])))")
  TESTS_RUN=$(python3 -c "import json; d=json.load(open('${CONTRACT_PATH}')); print(d.get('tests_run',0))")
  TESTS_PASS=$(python3 -c "import json; d=json.load(open('${CONTRACT_PATH}')); print(d.get('tests_passed',0))")
  SUMMARY="Files changed: ${CHANGED} | Tests: ${TESTS_PASS}/${TESTS_RUN}"
fi

case "$STATUS" in
  success)  ICON="✓" ;;
  blocked)  ICON="⚠" ;;
  failed)   ICON="✗" ;;
  *)        ICON="?" ;;
esac

send_msg "${ICON} Build ${STATUS}: ${TASK_NAME}
${SUMMARY}"
