#!/bin/bash
# =============================================================================
# queue-runner.sh — OpenClaw Queue Runner
# Continuously drains repo-queue/ by dispatching tasks to build-agent-bridge.sh
# Runs up to N tasks concurrently. Never idle while tasks remain.
#
# Usage:
#   ./queue-runner.sh              # default: 3 concurrent tasks
#   ./queue-runner.sh --max 5      # 5 concurrent tasks
#   ./queue-runner.sh --once       # drain queue once, then exit
#
# Logs: ~/openclaw/logs/queue-runner-<date>.log
# =============================================================================

set -u  # no -e: we handle errors explicitly in the loop

OPENCLAW_ROOT="${HOME}/openclaw"
QUEUE_DIR="${OPENCLAW_ROOT}/repo-queue"
BUILD_RESULTS="${OPENCLAW_ROOT}/build-results"
BRIDGE="${OPENCLAW_ROOT}/lobster-workflows/build-agent-bridge.sh"
LOGS_DIR="${OPENCLAW_ROOT}/logs"
LOCK_DIR="${OPENCLAW_ROOT}/.queue-locks"
PIDFILE="${OPENCLAW_ROOT}/.queue-runner.pid"

MAX_CONCURRENT=3
RUN_ONCE=false
POLL_INTERVAL=30  # seconds between queue checks

# Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --max)   MAX_CONCURRENT="$2"; shift 2 ;;
    --once)  RUN_ONCE=true; shift ;;
    *)       echo "Unknown arg: $1"; exit 1 ;;
  esac
done

mkdir -p "$LOCK_DIR" "$LOGS_DIR"

DATE=$(date +%Y-%m-%d)
LOG="${LOGS_DIR}/queue-runner-${DATE}.log"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"
}

# Check if another queue-runner is already active
if [[ -f "$PIDFILE" ]]; then
  OLD_PID=$(cat "$PIDFILE")
  if kill -0 "$OLD_PID" 2>/dev/null; then
    log "Queue runner already running (PID $OLD_PID). Exiting."
    exit 0
  else
    log "Stale PID file found (PID $OLD_PID not running). Claiming."
    rm -f "$PIDFILE"
  fi
fi

echo $$ > "$PIDFILE"
trap 'rm -f "$PIDFILE"; log "Queue runner stopped."; exit 0' EXIT INT TERM

log "Queue runner started. Max concurrent: ${MAX_CONCURRENT}. Mode: $(if $RUN_ONCE; then echo 'once'; else echo 'daemon'; fi)"

# Count running build agents
count_running() {
  local count=0
  for lockfile in "$LOCK_DIR"/*.lock; do
    [[ -f "$lockfile" ]] || continue
    local pid
    pid=$(cat "$lockfile")
    if kill -0 "$pid" 2>/dev/null; then
      count=$((count + 1))
    else
      # Stale lock — clean up
      rm -f "$lockfile"
    fi
  done
  echo "$count"
}

# Check if a task is already completed or currently running
is_task_done_or_running() {
  local task_file="$1"
  local task_id
  task_id=$(python3 -c "import json; print(json.load(open('${task_file}')).get('task_id', ''))" 2>/dev/null)
  [[ -z "$task_id" ]] && return 0  # skip if can't parse

  # Already has a build result?
  if [[ -f "${BUILD_RESULTS}/${task_id}.json" ]]; then
    return 0  # done
  fi

  # Currently locked (in progress)?
  if [[ -f "${LOCK_DIR}/${task_id}.lock" ]]; then
    local pid
    pid=$(cat "${LOCK_DIR}/${task_id}.lock")
    if kill -0 "$pid" 2>/dev/null; then
      return 0  # running
    else
      rm -f "${LOCK_DIR}/${task_id}.lock"  # stale
    fi
  fi

  return 1  # not done, not running — eligible
}

# Dispatch a single task
dispatch_task() {
  local task_file="$1"
  local task_id
  task_id=$(python3 -c "import json; print(json.load(open('${task_file}')).get('task_id', ''))" 2>/dev/null)
  [[ -z "$task_id" ]] && { log "SKIP: Could not parse task_id from ${task_file}"; return; }

  log "DISPATCH: ${task_id} (from $(basename "$task_file"))"

  # Run build agent in background, write PID to lock file
  (
    echo $BASHPID > "${LOCK_DIR}/${task_id}.lock"
    "$BRIDGE" "$task_file" >> "${LOGS_DIR}/task-${task_id}.log" 2>&1
    local exit_code=$?
    rm -f "${LOCK_DIR}/${task_id}.lock"

    if [[ $exit_code -eq 0 ]]; then
      log "COMPLETE: ${task_id} (exit 0)"
    else
      log "FAILED: ${task_id} (exit ${exit_code})"
    fi
  ) &

  # Small delay between dispatches to avoid resource spikes
  sleep 2
}

# Main loop
while true; do
  DATE=$(date +%Y-%m-%d)
  LOG="${LOGS_DIR}/queue-runner-${DATE}.log"

  running=$(count_running)
  slots=$((MAX_CONCURRENT - running))

  if [[ $slots -le 0 ]]; then
    log "All ${MAX_CONCURRENT} slots full. Waiting..."
  else
    # Find eligible tasks (oldest first)
    dispatched=0
    for task_file in $(ls -t -r "$QUEUE_DIR"/task-*.json 2>/dev/null); do
      [[ $slots -le 0 ]] && break

      if ! is_task_done_or_running "$task_file"; then
        dispatch_task "$task_file"
        slots=$((slots - 1))
        dispatched=$((dispatched + 1))
      fi
    done

    if [[ $dispatched -eq 0 && $running -eq 0 ]]; then
      log "Queue empty. No tasks running."
      if $RUN_ONCE; then
        log "Mode: once — exiting."
        exit 0
      fi
    elif [[ $dispatched -gt 0 ]]; then
      log "Dispatched ${dispatched} tasks. Running: $((running + dispatched))/${MAX_CONCURRENT}"
    fi
  fi

  if $RUN_ONCE; then
    # Wait for all background jobs to finish
    wait
    log "All tasks complete. Exiting."
    exit 0
  fi

  sleep "$POLL_INTERVAL"
done
