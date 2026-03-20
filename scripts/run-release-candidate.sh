#!/bin/bash
# =============================================================================
# run-release-candidate.sh
# Shell runner for release-candidate.lobster
# Validates a branch: tests -> lint -> diff -> Tier-2 staging approval -> deploy -> smoke
#
# Usage:
#   ./scripts/run-release-candidate.sh <repo_path> <branch_name>
#
# Example:
#   ./scripts/run-release-candidate.sh /Users/nayslayer/projects/EmergentWebActions feat/my-feature
# =============================================================================

set -euo pipefail

OPENCLAW_ROOT="${HOME}/openclaw"

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <repo_path> <branch_name>"
  exit 1
fi

REPO_PATH="$1"
BRANCH="$2"
DATE=$(date +%Y-%m-%d)
LOG="${OPENCLAW_ROOT}/logs/rc-${DATE}.jsonl"
TS=$(date +%s)

mkdir -p "${OPENCLAW_ROOT}/logs"

# Load .env for Telegram
set -a
source "${OPENCLAW_ROOT}/.env" 2>/dev/null || true
set +a

notify() {
  bash "${OPENCLAW_ROOT}/scripts/notify-telegram.sh" "$1" 2>/dev/null || true
}

log_event() {
  echo "{\"event\":\"$1\",\"branch\":\"${BRANCH}\",\"repo\":\"${REPO_PATH}\",\"timestamp\":$(date +%s)}" >> "$LOG"
}

echo "=== Release Candidate: ${BRANCH} ==="
echo "Repo: ${REPO_PATH}"
echo ""

# Verify repo and branch exist
if [[ ! -d "$REPO_PATH" ]]; then
  echo "ERROR: Repo not found: ${REPO_PATH}"
  exit 1
fi

cd "$REPO_PATH"

if ! git rev-parse --verify "origin/${BRANCH}" >/dev/null 2>&1 && \
   ! git rev-parse --verify "${BRANCH}" >/dev/null 2>&1; then
  echo "ERROR: Branch not found: ${BRANCH}"
  exit 1
fi

log_event "rc_start"

# --- Step 1: Checkout branch ---
echo "[1/6] Checking out ${BRANCH}..."
git checkout "${BRANCH}"

# --- Step 2: Run tests (fail hard) ---
echo "[2/6] Running tests..."
if ! bash ./scripts/test.sh; then
  notify "RC FAILED: ${BRANCH} — tests failed. Not deploying to staging."
  log_event "rc_tests_failed"
  echo "FAIL: tests failed on ${BRANCH}"
  exit 1
fi
echo "      Tests passed."
log_event "rc_tests_passed"

# --- Step 3: Run lint (fail hard) ---
echo "[3/6] Running lint..."
if ! bash ./scripts/lint.sh; then
  notify "RC FAILED: ${BRANCH} — lint errors. Not deploying to staging."
  log_event "rc_lint_failed"
  echo "FAIL: lint failed on ${BRANCH}"
  exit 1
fi
echo "      Lint clean."
log_event "rc_lint_passed"

# --- Step 4: Generate diff summary ---
echo "[4/6] Generating diff summary..."
DIFF_STAT=$(git diff "main...${BRANCH}" --stat 2>/dev/null || echo "No diff available")
DIFF_FILES=$(git diff "main...${BRANCH}" --name-only 2>/dev/null | head -20 | tr '\n' ', ' || echo "unknown")

# --- Step 5: Tier-2 Telegram approval for staging deploy ---
echo "[5/6] Requesting Tier-2 approval for staging deploy..."
log_event "rc_awaiting_approval"

notify "Tier-2: Release candidate ready

Branch: ${BRANCH}
Repo: ${REPO_PATH}
Tests: PASSED
Lint: CLEAN
Changed files: ${DIFF_FILES}

Diff:
${DIFF_STAT}

To deploy to staging: run manually:
  cd ${REPO_PATH} && bash scripts/deploy-staging.sh ${BRANCH}
  bash scripts/smoke-test.sh

Then reply to approve or deny promotion to production."

echo ""
echo "      Tier-2 notification sent. Staging deploy requires manual approval."
echo "      Run when ready: bash ${REPO_PATH}/scripts/deploy-staging.sh ${BRANCH}"
echo ""
echo "=== RC validation complete. Status: APPROVED-FOR-STAGING ==="
log_event "rc_approved_for_staging"
