#!/bin/bash
# =============================================================================
# cron-autoresearch.sh — Weekly AutoResearch Cycle
# Schedule: Sunday at 10pm (0 22 * * 0)
# Phase 4 — Memory Librarian · IDLE_PROTOCOL Advanced Tier
#
# Pipeline:
#   1. Read queued experiments from autoresearch/meta/discovery-log.md
#   2. Run approved experiments — market-intel first, then content, then competitive
#   3. Cap: 50 experiments, 5 min/experiment, 6-hour wall-clock
#   4. Store outputs in autoresearch/outputs/{briefs,papers,datasets}/
#   5. Send Monday morning Tier-1 brief summary to Telegram
# =============================================================================

OPENCLAW_ROOT="${HOME}/openclaw"
AUTORESEARCH_DIR="${OPENCLAW_ROOT}/autoresearch"
TODAY=$(date +%Y-%m-%d)
TIMESTAMP=$(date +%H:%M)
LOG_FILE="${OPENCLAW_ROOT}/logs/cron-autoresearch.log"
IDLE_LOG="${OPENCLAW_ROOT}/memory/IDLE_LOG.md"
DISCOVERY_LOG="${AUTORESEARCH_DIR}/meta/discovery-log.md"
OUTPUTS_BRIEFS="${AUTORESEARCH_DIR}/outputs/briefs"
OUTPUTS_PAPERS="${AUTORESEARCH_DIR}/outputs/papers"
OUTPUTS_DATASETS="${AUTORESEARCH_DIR}/outputs/datasets"

WALL_CLOCK_START=$(date +%s)
WALL_CLOCK_CAP=21600   # 6 hours in seconds
EXPERIMENT_CAP=50
EXPERIMENT_COUNT=0

# Load .env
set -a
source "${OPENCLAW_ROOT}/.env" 2>/dev/null || true
set +a

mkdir -p "${OUTPUTS_BRIEFS}" "${OUTPUTS_PAPERS}" "${OUTPUTS_DATASETS}"

echo "[$(date)] cron-autoresearch start — Sunday weekly cycle" >> "$LOG_FILE"

# =============================================================================
# Step 1: Read approved experiments from discovery-log
# =============================================================================
if [[ ! -f "$DISCOVERY_LOG" ]]; then
  echo "[$(date)] No discovery log found — skipping" >> "$LOG_FILE"
  exit 0
fi

APPROVED_EXPERIMENTS=$(grep -A5 "status: approved" "$DISCOVERY_LOG" 2>/dev/null | head -100 || echo "")

if [[ -z "$APPROVED_EXPERIMENTS" ]]; then
  echo "[$(date)] No approved experiments queued — skipping" >> "$LOG_FILE"
  cat >> "$IDLE_LOG" << LOGENTRY

### AutoResearch Weekly — ${TODAY} ${TIMESTAMP}
- Status: No approved experiments in discovery-log.md
- Action: Jordan should review discovery-log.md and approve items
LOGENTRY
  bash "${OPENCLAW_ROOT}/scripts/notify-telegram.sh" \
    "AutoResearch Sunday ${TODAY}: No approved experiments queued. Review autoresearch/meta/discovery-log.md to queue work." 2>/dev/null || true
  exit 0
fi

# =============================================================================
# Step 2: Run experiments by domain priority
# market-intel → content-research → competitive → academic → ad-hoc
# =============================================================================

run_research_experiment() {
  local DOMAIN="$1"
  local QUESTION="$2"
  local OUTPUT_TYPE="$3"   # brief | paper | dataset
  local SLUG="$4"

  # Check wall clock
  local ELAPSED=$(( $(date +%s) - WALL_CLOCK_START ))
  if [[ $ELAPSED -ge $WALL_CLOCK_CAP ]]; then
    echo "[$(date)] Wall-clock cap hit — stopping" >> "$LOG_FILE"
    return 1
  fi

  if [[ $EXPERIMENT_COUNT -ge $EXPERIMENT_CAP ]]; then
    echo "[$(date)] Experiment cap hit — stopping" >> "$LOG_FILE"
    return 1
  fi

  echo "[$(date)] Running experiment: ${DOMAIN}/${SLUG}" >> "$LOG_FILE"

  local DOMAIN_CONFIG="${AUTORESEARCH_DIR}/domains/${DOMAIN}/config.md"
  local DOMAIN_CTX=""
  [[ -f "$DOMAIN_CONFIG" ]] && DOMAIN_CTX=$(cat "$DOMAIN_CONFIG")

  local PROMPT="You are the Research Agent running an AutoResearch pipeline experiment.

Domain: ${DOMAIN}
Research question: ${QUESTION}
Output format: ${OUTPUT_TYPE}

Domain config:
${DOMAIN_CTX}

Run all 4 pipeline stages:
1. DISCOVER: frame the question, identify what you know, note what primary sources would improve this
2. GATHER: pull relevant knowledge, score each claim for relevance (1-10), flag contradictions
3. SYNTHESIZE: cross-reference findings, extract patterns, form conclusions, note confidence levels
4. STORE: write the final ${OUTPUT_TYPE} in a clean, professional format

For output format:
- brief: 1-2 pages, executive summary + 3-5 key findings + recommended actions
- paper: 5+ pages, structured sections, confidence ratings, gap analysis
- dataset: JSON structure with entities, relationships, and metadata

Be direct. No filler. Signal over length. State confidence levels explicitly."

  local OUTPUT
  # 5 min timeout per experiment
  OUTPUT=$(timeout 300 bash -c "echo \"\$PROMPT\" | ollama run llama3.3:70b" 2>/dev/null)

  if [[ -z "$OUTPUT" ]]; then
    OUTPUT=$(timeout 300 bash -c "echo \"\$PROMPT\" | ollama run qwen3:32b" 2>/dev/null || echo "Experiment failed — model unavailable")
    echo "[$(date)] Fallback to qwen3:32b for ${SLUG}" >> "$LOG_FILE"
  fi

  # Write output
  local EXT="md"
  local OUT_DIR="$OUTPUTS_BRIEFS"
  if [[ "$OUTPUT_TYPE" == "paper" ]]; then OUT_DIR="$OUTPUTS_PAPERS"; fi
  if [[ "$OUTPUT_TYPE" == "dataset" ]]; then OUT_DIR="$OUTPUTS_DATASETS"; EXT="json"; fi

  local OUT_FILE="${OUT_DIR}/${DOMAIN}-${SLUG}-${TODAY}.${EXT}"
  echo "$OUTPUT" > "$OUT_FILE"

  EXPERIMENT_COUNT=$((EXPERIMENT_COUNT + 1))
  echo "[$(date)] Experiment complete: ${OUT_FILE}" >> "$LOG_FILE"
  echo "$OUT_FILE"
}

# Parse and run approved experiments from discovery-log
# Format expected: lines with "- question: ...", "- domain: ...", "- output: ...", "- slug: ..."
COMPLETED_FILES=()

while IFS= read -r line; do
  if [[ "$line" =~ "status: approved" ]]; then
    IN_BLOCK=1
    BLOCK_DOMAIN=""
    BLOCK_QUESTION=""
    BLOCK_OUTPUT="brief"
    BLOCK_SLUG=""
  fi
  [[ "${IN_BLOCK:-0}" == "1" && "$line" =~ "domain: " ]] && BLOCK_DOMAIN=$(echo "$line" | sed 's/.*domain: //')
  [[ "${IN_BLOCK:-0}" == "1" && "$line" =~ "question: " ]] && BLOCK_QUESTION=$(echo "$line" | sed 's/.*question: //')
  [[ "${IN_BLOCK:-0}" == "1" && "$line" =~ "output: " ]] && BLOCK_OUTPUT=$(echo "$line" | sed 's/.*output: //')
  [[ "${IN_BLOCK:-0}" == "1" && "$line" =~ "slug: " ]] && BLOCK_SLUG=$(echo "$line" | sed 's/.*slug: //')

  if [[ "${IN_BLOCK:-0}" == "1" && -n "$BLOCK_DOMAIN" && -n "$BLOCK_QUESTION" && -n "$BLOCK_SLUG" ]]; then
    RESULT=$(run_research_experiment "$BLOCK_DOMAIN" "$BLOCK_QUESTION" "$BLOCK_OUTPUT" "$BLOCK_SLUG") || break
    [[ -n "$RESULT" ]] && COMPLETED_FILES+=("$RESULT")
    IN_BLOCK=0
  fi
done < "$DISCOVERY_LOG"

# =============================================================================
# Step 3: Log and notify
# =============================================================================
ELAPSED_TOTAL=$(( $(date +%s) - WALL_CLOCK_START ))
ELAPSED_MIN=$(( ELAPSED_TOTAL / 60 ))

cat >> "$IDLE_LOG" << LOGENTRY

### AutoResearch Weekly — ${TODAY} ${TIMESTAMP}
- Experiments run: ${EXPERIMENT_COUNT}
- Wall clock: ${ELAPSED_MIN} minutes
- Outputs: ${#COMPLETED_FILES[@]} files written
LOGENTRY

FILES_LIST=$(printf '%s\n' "${COMPLETED_FILES[@]}" | sed 's|.*/||' | head -10)

bash "${OPENCLAW_ROOT}/scripts/notify-telegram.sh" \
"AutoResearch Weekly — ${TODAY}

Experiments completed: ${EXPERIMENT_COUNT}
Runtime: ${ELAPSED_MIN} min

Outputs:
${FILES_LIST}

Review at: ~/openclaw/autoresearch/outputs/
Publishable items need Tier-2 approval before external delivery." 2>/dev/null || true

echo "[$(date)] cron-autoresearch complete — ${EXPERIMENT_COUNT} experiments, ${ELAPSED_MIN} min" >> "$LOG_FILE"
