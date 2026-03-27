#!/bin/bash
# =============================================================================
# claw-bootstrap.sh — Bootstrap tmux sessions for all OpenClaw instances
# Creates tmux sessions, launches Claude Code inside each, updates state file.
# Called by startup.sh on cold start.
# =============================================================================

set -euo pipefail

OPENCLAW_ROOT="${OPENCLAW_ROOT:-$HOME/openclaw}"
STATE_DIR="$HOME/.openclaw"
STATE_FILE="$STATE_DIR/claw-sessions.json"
LOG_FILE="$OPENCLAW_ROOT/logs/bootstrap.log"
PID_FILE="$STATE_DIR/claw-session-manager.pid"

mkdir -p "$STATE_DIR" "$OPENCLAW_ROOT/logs"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# ---------------------------------------------------------------------------
# Claw definitions: name|tmux_session|workdir
# ---------------------------------------------------------------------------
CLAWS=(
  "clawmpson|claw-clawmpson|$HOME/openclaw"
  "rival|claw-rival|$HOME/rivalclaw"
  "quant|claw-quant|$HOME/quantumentalclaw"
  "monkey|claw-monkey|$HOME/codemonkeyclaw"
)

log "=== Claw Bootstrap Start ==="

for entry in "${CLAWS[@]}"; do
  IFS='|' read -r name session workdir <<< "$entry"

  # Skip if workdir doesn't exist
  if [[ ! -d "$workdir" ]]; then
    log "[$name] workdir $workdir does not exist — skipping"
    continue
  fi

  # Check if tmux session exists
  if tmux has-session -t "$session" 2>/dev/null; then
    log "[$name] tmux session '$session' already exists"
  else
    log "[$name] creating tmux session '$session' in $workdir"
    tmux new-session -d -s "$session" -c "$workdir" -x 200 -y 50
  fi

  # Check if claude is running inside the session
  # Get the PID of the shell in pane 0, then check children for claude
  pane_pid=$(tmux list-panes -t "$session" -F '#{pane_pid}' 2>/dev/null | head -1)
  claude_running=false
  claude_pid=""

  if [[ -n "$pane_pid" ]]; then
    claude_pid=$(pgrep -P "$pane_pid" -f "claude" 2>/dev/null | head -1 || true)
    if [[ -n "$claude_pid" ]]; then
      claude_running=true
    fi
  fi

  if [[ "$claude_running" == "true" ]]; then
    log "[$name] claude already running (PID $claude_pid)"
  else
    log "[$name] launching claude in session '$session'"
    tmux send-keys -t "$session" "claude" Enter
    sleep 1
    # Re-check PID after launch
    pane_pid=$(tmux list-panes -t "$session" -F '#{pane_pid}' 2>/dev/null | head -1)
    claude_pid=$(pgrep -P "$pane_pid" -f "claude" 2>/dev/null | head -1 || true)
  fi

  # Update state file using python3
  python3 -c "
import json, os, time

state_file = '$STATE_FILE'
name = '$name'
session = '$session'
workdir = '$workdir'
claude_pid = '$claude_pid'
claude_running = $( [[ "$claude_running" == "true" ]] && echo "True" || echo "False" )

# Load existing state or start fresh
if os.path.exists(state_file):
    with open(state_file) as f:
        try:
            state = json.load(f)
        except json.JSONDecodeError:
            state = {}
else:
    state = {}

now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

if name not in state:
    state[name] = {
        'session': session,
        'workdir': workdir,
        'status': 'unknown',
        'pid': None,
        'started': None,
        'tokenUsage': None,
        'lastOutput': None,
        'reboots': 0,
        'lastRebootReason': None,
    }

entry = state[name]
entry['session'] = session
entry['workdir'] = workdir

if claude_running:
    entry['status'] = 'running'
    entry['pid'] = int(claude_pid) if claude_pid else None
    if entry.get('started') is None:
        entry['started'] = now
else:
    entry['status'] = 'starting'
    entry['pid'] = int(claude_pid) if claude_pid else None
    entry['started'] = now

with open(state_file, 'w') as f:
    json.dump(state, f, indent=2)
"

  log "[$name] state updated → $STATE_FILE"
done

# ---------------------------------------------------------------------------
# Start session manager daemon if not running
# ---------------------------------------------------------------------------
SESSION_MANAGER="$OPENCLAW_ROOT/scripts/claw-session-manager.py"

if [[ -f "$SESSION_MANAGER" ]]; then
  if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    log "session manager already running (PID $(cat "$PID_FILE"))"
  else
    rm -f "$PID_FILE"
    log "starting session manager daemon"
    nohup python3 "$SESSION_MANAGER" \
      >> "$OPENCLAW_ROOT/logs/session-manager.log" 2>&1 &
    echo $! > "$PID_FILE"
    log "session manager started (PID $!)"
  fi
else
  log "session manager script not found at $SESSION_MANAGER — skipping"
fi

log "=== Claw Bootstrap Complete ==="
