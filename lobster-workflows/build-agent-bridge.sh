#!/bin/bash
# =============================================================================
# build-agent-bridge.sh
# OpenClaw → Claude Code CLI bridge
# Translates a task packet (JSON) into a Claude Code session and captures
# the output contract (JSON) back to build-results/.
#
# Usage:
#   ./build-agent-bridge.sh <task-packet.json>
#
# Called by: Lobster workflows (debug-and-fix.lobster, etc.)
# Output: ~/openclaw/build-results/<task-id>.json (output contract)
# Logs:   ~/openclaw/logs/build-agent-<date>.jsonl
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
OPENCLAW_ROOT="${HOME}/openclaw"
BUILD_RESULTS="${OPENCLAW_ROOT}/build-results"
LOGS_DIR="${OPENCLAW_ROOT}/logs"
STRATEGY_DOC="${OPENCLAW_ROOT}/openclaw-v4.1-strategy.md"
BUILD_CONTEXT="${OPENCLAW_ROOT}/CONTEXT.md"
BUILD_AGENT_CONFIG="${OPENCLAW_ROOT}/agents/configs/build.md"
DATE=$(date +%Y-%m-%d)
TIMESTAMP=$(date +%s)
LOG_FILE="${LOGS_DIR}/build-agent-${DATE}.jsonl"

# ---------------------------------------------------------------------------
# Validate input
# ---------------------------------------------------------------------------
if [[ $# -lt 1 ]]; then
  echo '{"error": "No task packet provided", "usage": "./build-agent-bridge.sh <task-packet.json>"}' | tee -a "$LOG_FILE"
  exit 1
fi

TASK_PACKET_FILE="$1"

if [[ ! -f "$TASK_PACKET_FILE" ]]; then
  echo "{\"error\": \"Task packet not found\", \"path\": \"${TASK_PACKET_FILE}\"}" | tee -a "$LOG_FILE"
  exit 1
fi

# Validate JSON
if ! python3 -c "import json, sys; json.load(open('${TASK_PACKET_FILE}'))" 2>/dev/null; then
  echo "{\"error\": \"Task packet is not valid JSON\", \"path\": \"${TASK_PACKET_FILE}\"}" | tee -a "$LOG_FILE"
  exit 1
fi

# Extract fields from task packet
TASK_ID=$(python3 -c "import json; d=json.load(open('${TASK_PACKET_FILE}')); print(d.get('task_id', 'build-${TIMESTAMP}'))")
REPO_PATH=$(python3 -c "import json; d=json.load(open('${TASK_PACKET_FILE}')); print(d.get('repo_path', ''))")
GOAL=$(python3 -c "import json; d=json.load(open('${TASK_PACKET_FILE}')); print(d.get('goal', ''))")
RISK_LEVEL=$(python3 -c "import json; d=json.load(open('${TASK_PACKET_FILE}')); print(d.get('risk_level', 'low'))")
TIME_BUDGET=$(python3 -c "import json; d=json.load(open('${TASK_PACKET_FILE}')); print(d.get('time_budget_minutes', 30))")
OUTPUT_LOCATION="${BUILD_RESULTS}/${TASK_ID}"

# ---------------------------------------------------------------------------
# Guard: block high-risk tasks from running unattended
# ---------------------------------------------------------------------------
if [[ "$RISK_LEVEL" == "high" ]]; then
  RESULT=$(cat <<EOF
{
  "task_id": "${TASK_ID}",
  "status": "blocked",
  "reason": "High-risk tasks require manual Claude Code session. Run interactively.",
  "task_packet": "${TASK_PACKET_FILE}",
  "suggested_next": "Open Claude Code manually in ${REPO_PATH} with this task packet"
}
EOF
)
  echo "$RESULT" > "${BUILD_RESULTS}/${TASK_ID}.json"
  echo "$RESULT" | tee -a "$LOG_FILE"
  exit 0
fi

# ---------------------------------------------------------------------------
# Prepare output directory
# ---------------------------------------------------------------------------
mkdir -p "$OUTPUT_LOCATION"
mkdir -p "$LOGS_DIR"

# Log session start
echo "{\"event\": \"session_start\", \"task_id\": \"${TASK_ID}\", \"timestamp\": ${TIMESTAMP}, \"risk\": \"${RISK_LEVEL}\", \"repo\": \"${REPO_PATH}\"}" >> "$LOG_FILE"

# ---------------------------------------------------------------------------
# Build the prompt
# ---------------------------------------------------------------------------
TASK_PACKET_CONTENTS=$(cat "$TASK_PACKET_FILE")

PROMPT=$(cat <<PROMPT
Read ${BUILD_AGENT_CONFIG} and ${BUILD_CONTEXT}.

You are the Build Agent in Jordan's OpenClaw system.
Execute the 4-mode sequence (Explore→Plan→Code→Review) for this task packet.

TASK PACKET:
${TASK_PACKET_CONTENTS}

OUTPUT LOCATION: ${OUTPUT_LOCATION}/

REQUIRED STEPS:
1. EXPLORE: Read the relevant code in ${REPO_PATH}. Map the files involved. No edits.
2. PLAN: Write your implementation plan to ${OUTPUT_LOCATION}/plan-${TASK_ID}.md. List risks and rollback approach. No edits yet.
3. CODE: Execute the plan in a feature branch. Run tests. List changed files.
4. REVIEW: Audit the diff. Challenge it. Find security issues, test gaps, edge cases.

When complete, write the output contract as valid JSON to: ${OUTPUT_LOCATION}/output-contract.json

Output contract must match this exact schema:
{
  "task_id": "${TASK_ID}",
  "status": "success | blocked | partial",
  "changed_files": [],
  "tests_run": 0,
  "tests_passed": 0,
  "tests_failed": 0,
  "unresolved_risks": [],
  "rollback_command": "",
  "summary": "",
  "suggested_next": ""
}

CONSTRAINTS:
- Never edit main branch directly
- Never run destructive commands (rm -rf, DROP TABLE, curl | sh, eval)
- Time budget: ${TIME_BUDGET} minutes — if you exceed it, write a partial output contract
- If blocked at any stage, stop and write output contract with status: "blocked" and reason
PROMPT
)

# ---------------------------------------------------------------------------
# Run Claude Code
# ---------------------------------------------------------------------------
echo "{\"event\": \"claude_start\", \"task_id\": \"${TASK_ID}\", \"timestamp\": $(date +%s)}" >> "$LOG_FILE"

# Change to repo directory if provided
if [[ -n "$REPO_PATH" && -d "$REPO_PATH" ]]; then
  cd "$REPO_PATH"
fi

# Run Claude Code non-interactively
# --allowedTools scopes what Claude Code can do in this session
# Remove --dangerously-skip-permissions only after confirming pre-bash-check.sh hook is active
CLAUDE_OUTPUT=$(claude --print \
  --allowedTools "Read,Edit,Write,Bash,Glob,Grep" \
  "$PROMPT" 2>&1) || CLAUDE_EXIT=$?

CLAUDE_EXIT="${CLAUDE_EXIT:-0}"

# ---------------------------------------------------------------------------
# Verify output contract was written
# ---------------------------------------------------------------------------
CONTRACT_FILE="${OUTPUT_LOCATION}/output-contract.json"

if [[ -f "$CONTRACT_FILE" ]]; then
  # Validate JSON
  if python3 -c "import json; json.load(open('${CONTRACT_FILE}'))" 2>/dev/null; then
    # Copy to canonical build-results location
    cp "$CONTRACT_FILE" "${BUILD_RESULTS}/${TASK_ID}.json"
    STATUS=$(python3 -c "import json; print(json.load(open('${CONTRACT_FILE}')).get('status', 'unknown'))")
    echo "{\"event\": \"session_complete\", \"task_id\": \"${TASK_ID}\", \"status\": \"${STATUS}\", \"timestamp\": $(date +%s), \"contract\": \"${BUILD_RESULTS}/${TASK_ID}.json\"}" >> "$LOG_FILE"
    echo "✓ Build agent complete. Task: ${TASK_ID} | Status: ${STATUS}"
    echo "  Contract: ${BUILD_RESULTS}/${TASK_ID}.json"
  else
    # Contract exists but is invalid JSON — wrap the raw output
    FALLBACK=$(cat <<EOF
{
  "task_id": "${TASK_ID}",
  "status": "partial",
  "summary": "Claude Code completed but output contract was malformed JSON. Review ${OUTPUT_LOCATION}/ manually.",
  "changed_files": [],
  "tests_run": 0, "tests_passed": 0, "tests_failed": 0,
  "unresolved_risks": ["Output contract JSON parse error — manual review required"],
  "rollback_command": "git checkout main -- .",
  "suggested_next": "Needs human review"
}
EOF
)
    echo "$FALLBACK" > "${BUILD_RESULTS}/${TASK_ID}.json"
    echo "{\"event\": \"contract_parse_error\", \"task_id\": \"${TASK_ID}\", \"timestamp\": $(date +%s)}" >> "$LOG_FILE"
  fi
else
  # No contract written — Claude Code may have failed or timed out
  FALLBACK=$(cat <<EOF
{
  "task_id": "${TASK_ID}",
  "status": "blocked",
  "summary": "Claude Code did not produce an output contract. Exit code: ${CLAUDE_EXIT}. Check ${LOG_FILE} for details.",
  "changed_files": [],
  "tests_run": 0, "tests_passed": 0, "tests_failed": 0,
  "unresolved_risks": ["No output contract produced — session may have failed or timed out"],
  "rollback_command": "git checkout main -- .",
  "suggested_next": "Needs human review — run task interactively in Claude Code"
}
EOF
)
  echo "$FALLBACK" > "${BUILD_RESULTS}/${TASK_ID}.json"
  echo "{\"event\": \"no_contract\", \"task_id\": \"${TASK_ID}\", \"claude_exit\": ${CLAUDE_EXIT}, \"timestamp\": $(date +%s)}" >> "$LOG_FILE"
  echo "⚠ Build agent produced no output contract. See: ${LOG_FILE}"
fi

# ---------------------------------------------------------------------------
# Output the contract path for Lobster to read
# ---------------------------------------------------------------------------
echo "${BUILD_RESULTS}/${TASK_ID}.json"
