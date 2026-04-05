#!/bin/bash
# =============================================================================
# cron-self-improvement.sh — Cycle 5: Self-Improvement Loop
# Schedule: every 48 hours at 10pm (0 22 */2 * *)
# Phase 4 — Memory Librarian · IDLE_PROTOCOL Advanced Tier
#
# Pipeline:
#   1. Read last 14 days of IDLE_LOG.md
#   2. Extract recurring failure patterns (3+ occurrences)
#   3. Draft up to 3 improvement proposals
#   4. Send Tier-2 Telegram per proposal — hold for Jordan approval
#   5. Log cycle run to IDLE_LOG.md
# =============================================================================

OPENCLAW_ROOT="${HOME}/openclaw"
TODAY=$(date +%Y-%m-%d)
TIMESTAMP=$(date +%H:%M)
LOG_FILE="${OPENCLAW_ROOT}/logs/cron-self-improvement.log"
IDLE_LOG="${OPENCLAW_ROOT}/memory/IDLE_LOG.md"
MEMORY_FILE="${OPENCLAW_ROOT}/memory/MEMORY.md"
IMPROVEMENTS_DIR="${OPENCLAW_ROOT}/improvements"

# Load .env
set -a
source "${OPENCLAW_ROOT}/.env" 2>/dev/null || true
set +a

mkdir -p "${OPENCLAW_ROOT}/logs" "${IMPROVEMENTS_DIR}"

echo "[$(date)] cron-self-improvement start" >> "$LOG_FILE"

# =============================================================================
# Step 1: Read last 14 days of logs and memory
# =============================================================================
# Get last 14 days of IDLE_LOG
IDLE_CONTENT=$(tail -300 "${IDLE_LOG}" 2>/dev/null || echo "")
MEMORY_CONTENT=$(tail -150 "${MEMORY_FILE}" 2>/dev/null || echo "")

if [[ -z "$IDLE_CONTENT" && -z "$MEMORY_CONTENT" ]]; then
  echo "[$(date)] No log content found — skipping cycle" >> "$LOG_FILE"
  cat >> "$IDLE_LOG" << LOGENTRY

### Self-Improvement Cycle — ${TODAY} ${TIMESTAMP}
- No log content available — skipped
LOGENTRY
  exit 0
fi

# =============================================================================
# Step 2: Pattern extraction via gemma4:31b (with fallback)
# =============================================================================
ANALYSIS_PROMPT="You are the Memory Librarian for an AI operating system called OpenClaw.

Review the last 14 days of operation logs below and identify recurring failure patterns.

IDLE LOG (last 300 lines):
${IDLE_CONTENT}

MEMORY SUMMARY (last 150 lines):
${MEMORY_CONTENT}

Rules for pattern identification:
- A pattern requires 3+ occurrences to qualify
- Focus on: model failures, routing errors, blocked tasks, timeout patterns, skipped crons
- Do NOT flag one-off events as patterns
- Do NOT propose changes without concrete log evidence

For each pattern found (max 3), output EXACTLY this format:
---PATTERN---
SLUG: <kebab-case-name>
OCCURRENCES: <count>
DESCRIPTION: <one sentence — what keeps failing>
EVIDENCE: <2-3 specific log entries that prove the pattern>
PROPOSED_FIX: <one concrete change to a config file, cron schedule, or workflow>
AFFECTED_FILE: <exact file path to change>
RISK: low | medium | high
---END---

If fewer than 3 qualifying patterns exist, output only what you found.
If no qualifying patterns exist, output: NO_PATTERNS_FOUND"

echo "[$(date)] Running pattern analysis via gemma4:31b..." >> "$LOG_FILE"

ANALYSIS=$(echo "$ANALYSIS_PROMPT" | ollama run gemma4:31b 2>/dev/null)
if [[ -z "$ANALYSIS" || "$ANALYSIS" == *"Error"* ]]; then
  echo "[$(date)] gemma4:31b unavailable, falling back to gemma4:31b" >> "$LOG_FILE"
  ANALYSIS=$(echo "$ANALYSIS_PROMPT" | ollama run gemma4:31b 2>/dev/null || echo "NO_PATTERNS_FOUND")
fi

if [[ "$ANALYSIS" == *"NO_PATTERNS_FOUND"* ]] || [[ -z "$ANALYSIS" ]]; then
  echo "[$(date)] No qualifying patterns found — clean cycle" >> "$LOG_FILE"
  cat >> "$IDLE_LOG" << LOGENTRY

### Self-Improvement Cycle — ${TODAY} ${TIMESTAMP}
- Patterns analyzed: 14 days of logs
- Result: No recurring failures found — system healthy
LOGENTRY
  bash "${OPENCLAW_ROOT}/scripts/notify-telegram.sh" \
    "Self-Improvement Cycle ${TODAY}: No recurring failures found. System clean." 2>/dev/null || true
  exit 0
fi

echo "[$(date)] Patterns found — drafting proposals" >> "$LOG_FILE"

# =============================================================================
# Step 3: Write proposal files and send Tier-2 Telegram per proposal
# =============================================================================
PROPOSAL_COUNT=0

# Parse each pattern block
while IFS= read -r -d '' block; do
  [[ -z "$block" ]] && continue
  [[ $PROPOSAL_COUNT -ge 3 ]] && break

  SLUG=$(echo "$block" | grep "^SLUG:" | sed 's/^SLUG: *//')
  DESCRIPTION=$(echo "$block" | grep "^DESCRIPTION:" | sed 's/^DESCRIPTION: *//')
  EVIDENCE=$(echo "$block" | awk '/^EVIDENCE:/{flag=1; next} /^PROPOSED_FIX:/{flag=0} flag{print}')
  PROPOSED_FIX=$(echo "$block" | grep "^PROPOSED_FIX:" | sed 's/^PROPOSED_FIX: *//')
  AFFECTED_FILE=$(echo "$block" | grep "^AFFECTED_FILE:" | sed 's/^AFFECTED_FILE: *//')
  RISK=$(echo "$block" | grep "^RISK:" | sed 's/^RISK: *//')
  OCCURRENCES=$(echo "$block" | grep "^OCCURRENCES:" | sed 's/^OCCURRENCES: *//')

  [[ -z "$SLUG" || -z "$PROPOSED_FIX" ]] && continue

  PROPOSAL_FILE="${IMPROVEMENTS_DIR}/proposal-${SLUG}-${TODAY}.md"

  cat > "$PROPOSAL_FILE" << PROPOSAL
# Proposal: ${DESCRIPTION}
**Date:** ${TODAY}
**Author:** Memory Librarian (auto-generated)
**Affects:** ${AFFECTED_FILE}
**Risk:** ${RISK}
**Status:** Pending Jordan approval

## Problem
${DESCRIPTION}

Occurrences in last 14 days: ${OCCURRENCES}

## Evidence
${EVIDENCE}

## Proposed Change
${PROPOSED_FIX}

## Rollback Plan
Revert via: git checkout main -- ${AFFECTED_FILE}

## Approval
Reply /approve-proposal-${SLUG}-${TODAY} to implement
Reply /deny-proposal-${SLUG}-${TODAY} to reject
Do NOT self-apply. Wait for explicit Jordan approval.
PROPOSAL

  PROPOSAL_COUNT=$((PROPOSAL_COUNT + 1))
  echo "[$(date)] Proposal written: ${PROPOSAL_FILE}" >> "$LOG_FILE"

  # Tier-2 Telegram hold
  bash "${OPENCLAW_ROOT}/scripts/notify-telegram.sh" \
"Self-Improvement Proposal ${PROPOSAL_COUNT}/3 — ${TODAY}

Pattern: ${DESCRIPTION}
Occurrences: ${OCCURRENCES}
Risk: ${RISK}
Fix: ${PROPOSED_FIX}

File: ${PROPOSAL_FILE}

/approve-proposal-${SLUG}-${TODAY} to implement
/deny-proposal-${SLUG}-${TODAY} to reject" 2>/dev/null || true

done < <(echo "$ANALYSIS" | awk '/^---PATTERN---/{block=""} /^---END---/{print block"\0"} !/^---PATTERN---|^---END---/{block=block"\n"$0}')

# =============================================================================
# Step 4: Log cycle completion
# =============================================================================
cat >> "$IDLE_LOG" << LOGENTRY

### Self-Improvement Cycle — ${TODAY} ${TIMESTAMP}
- Patterns analyzed: 14 days of logs
- Proposals drafted: ${PROPOSAL_COUNT}
- Status: Tier-2 hold — awaiting Jordan approval
LOGENTRY

echo "[$(date)] cron-self-improvement complete — ${PROPOSAL_COUNT} proposals drafted" >> "$LOG_FILE"
