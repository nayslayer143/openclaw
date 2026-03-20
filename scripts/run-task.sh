#!/bin/bash
# run-task.sh — full execution loop: task packet → bridge → Telegram

set -euo pipefail

OPENCLAW_ROOT="${HOME}/openclaw"
SCRIPTS_DIR="${OPENCLAW_ROOT}/scripts"

if [[ $# -lt 1 ]]; then
  echo "Usage: ./scripts/run-task.sh <task-packet.json>"
  exit 1
fi

TASK_PACKET="$1"

echo "=== OpenClaw Task Runner ==="
echo "Task packet: ${TASK_PACKET}"
echo ""

echo "[1/3] Running build agent bridge..."
BRIDGE_OUTPUT=$(bash "${OPENCLAW_ROOT}/lobster-workflows/build-agent-bridge.sh" "$TASK_PACKET")
echo "$BRIDGE_OUTPUT"
CONTRACT_PATH=$(echo "$BRIDGE_OUTPUT" | tail -1)

echo ""
echo "[2/3] Output contract: ${CONTRACT_PATH}"
echo ""

SEP="—————————————"

if [[ -f "$CONTRACT_PATH" ]]; then
  STATUS=$(python3 -c "import json; d=json.load(open('${CONTRACT_PATH}')); print(d.get('status','unknown'))")
  TASK_ID=$(python3 -c "import json; d=json.load(open('${CONTRACT_PATH}')); print(d.get('task_id','unknown'))")
  SUMMARY=$(python3 -c "import json; d=json.load(open('${CONTRACT_PATH}')); print(d.get('summary','No summary'))")
  CHANGED=$(python3 -c "import json; d=json.load(open('${CONTRACT_PATH}')); print(', '.join(d.get('changed_files',[])))")
  TESTS_PASSED=$(python3 -c "import json; d=json.load(open('${CONTRACT_PATH}')); print(d.get('tests_passed',0))")
  TESTS_RUN=$(python3 -c "import json; d=json.load(open('${CONTRACT_PATH}')); print(d.get('tests_run',0))")
  RISKS=$(python3 -c "import json; d=json.load(open('${CONTRACT_PATH}')); print('\n'.join('- ' + r for r in d.get('unresolved_risks',[])))")
  SUGGESTED=$(python3 -c "import json; d=json.load(open('${CONTRACT_PATH}')); print(d.get('suggested_next',''))")

  if [[ "$STATUS" == "success" ]]; then
    MESSAGE="✓ Build complete

${TASK_ID}

${SEP}

${SUMMARY}

${SEP}

- Changed: ${CHANGED:-none}
- Tests: ${TESTS_PASSED}/${TESTS_RUN} passed

${SEP}

/approve-${TASK_ID}"

  elif [[ "$STATUS" == "blocked" ]]; then
    MESSAGE="⚠ Build blocked

${TASK_ID}

${SEP}

${SUMMARY}

${SEP}

${RISKS:-no risks logged}

${SEP}

Next: ${SUGGESTED}"

  else
    MESSAGE="✗ Build incomplete

${TASK_ID}

${SEP}

${SUMMARY}

${SEP}

Review: ${CONTRACT_PATH}"
  fi

else
  STATUS="error"
  MESSAGE="✗ No output contract

$(basename ${TASK_PACKET})

${SEP}

Build agent produced no contract. Check logs."
fi

echo "[3/3] Sending Telegram notification..."
bash "${SCRIPTS_DIR}/notify-telegram.sh" "$MESSAGE"

echo ""
echo "=== Done. Status: ${STATUS} ==="
