#!/bin/bash
# =============================================================================
# ralph-loop.sh — Autonomous greenfield build loop (Ralph Wiggum technique)
# Usage:
#   bash ralph-loop.sh plan [max_iterations]   # Phase 1: plan only
#   bash ralph-loop.sh build [max_iterations]  # Phase 2: autonomous build
#   bash ralph-loop.sh build 10                # build, stop after 10 loops
#
# Requires in the target repo:
#   PROMPT_plan.md       — planning prompt
#   PROMPT_build.md      — build prompt
#   AGENTS.md            — build/run/test commands (agent maintains this)
#   IMPLEMENTATION_PLAN.md — living TODO (agent maintains this)
#   specs/               — feature specifications
#
# Ralph is for GREENFIELD projects only. Do not run on existing production repos.
# =============================================================================

set -euo pipefail

OPENCLAW_ROOT="${HOME}/openclaw"
LOG_FILE="${OPENCLAW_ROOT}/logs/ralph-$(date +%Y-%m-%d).log"

# Load .env
set -a
source "${OPENCLAW_ROOT}/.env" 2>/dev/null || true
set +a

# --- Arg parsing ---
MODE="${1:-build}"
MAX_ITERATIONS="${2:-0}"

if [[ "$MODE" != "plan" && "$MODE" != "build" ]]; then
  echo "Usage: bash ralph-loop.sh [plan|build] [max_iterations]"
  exit 1
fi

PROMPT_FILE="PROMPT_${MODE}.md"

if [[ ! -f "$PROMPT_FILE" ]]; then
  echo "ERROR: $PROMPT_FILE not found in $(pwd)"
  echo "Ralph must be run from inside the target repo directory."
  exit 1
fi

CURRENT_BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
REPO_NAME=$(basename "$(pwd)")
ITERATION=0

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Ralph Loop — OpenClaw"
echo "  Repo:   $REPO_NAME"
echo "  Mode:   $MODE"
echo "  Branch: $CURRENT_BRANCH"
echo "  Prompt: $PROMPT_FILE"
[[ $MAX_ITERATIONS -gt 0 ]] && echo "  Max:    $MAX_ITERATIONS iterations"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Safety check — warn if on main/master
if [[ "$CURRENT_BRANCH" == "main" || "$CURRENT_BRANCH" == "master" ]]; then
  echo "WARNING: You are on branch '$CURRENT_BRANCH'."
  echo "Ralph is intended to run on a feature branch."
  read -rp "Continue anyway? (y/N) " confirm
  [[ "$confirm" != "y" && "$confirm" != "Y" ]] && exit 1
fi

# Plan mode: single pass, no loop
if [[ "$MODE" == "plan" ]]; then
  echo "[$(date)] Ralph plan pass starting" | tee -a "$LOG_FILE"
  cat "$PROMPT_FILE" | claude -p \
    --dangerously-skip-permissions \
    --output-format stream-json \
    --model claude-opus-4-6 \
    --verbose 2>>"$LOG_FILE"
  echo ""
  echo "[$(date)] Plan complete. Review IMPLEMENTATION_PLAN.md then run: bash ralph-loop.sh build" | tee -a "$LOG_FILE"
  exit 0
fi

# Build mode: loop
while true; do
  if [[ $MAX_ITERATIONS -gt 0 && $ITERATION -ge $MAX_ITERATIONS ]]; then
    echo ""
    echo "━━━ Ralph stopped: reached max iterations ($MAX_ITERATIONS) ━━━"
    break
  fi

  echo "[$(date)] ━━━ Loop $((ITERATION + 1)) starting ━━━" | tee -a "$LOG_FILE"

  cat "$PROMPT_FILE" | claude -p \
    --dangerously-skip-permissions \
    --output-format stream-json \
    --model claude-opus-4-6 \
    --verbose 2>>"$LOG_FILE" || {
      echo "[$(date)] WARNING: Claude returned non-zero exit — continuing loop" | tee -a "$LOG_FILE"
    }

  # Push after each iteration
  git push origin "$CURRENT_BRANCH" 2>>"$LOG_FILE" || {
    echo "[$(date)] Push failed — attempting to set upstream" | tee -a "$LOG_FILE"
    git push -u origin "$CURRENT_BRANCH" 2>>"$LOG_FILE" || true
  }

  ITERATION=$((ITERATION + 1))
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━ LOOP $ITERATION COMPLETE ━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
done

echo "[$(date)] Ralph loop finished — $ITERATION iterations" | tee -a "$LOG_FILE"
