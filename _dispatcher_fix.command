#!/bin/bash
# =============================================================================
# _dispatcher_fix.command
# Double-click from Finder to diagnose + (if needed) start the Clawmson
# Telegram dispatcher (telegram-dispatcher.py).
#
# Tees all output to:
#   ~/code/claw-core/openclaw/_dispatcher_fix.log
# =============================================================================

# Tee everything to a log file from this point on.
LOG_FILE="$HOME/code/claw-core/openclaw/_dispatcher_fix.log"
mkdir -p "$(dirname "$LOG_FILE")"
exec > >(tee "$LOG_FILE") 2>&1

OPENCLAW_ROOT="$HOME/code/claw-core/openclaw"
DISPATCHER_LOG="$OPENCLAW_ROOT/logs/dispatcher.log"

echo "============================================================"
echo "  Clawmson Telegram Dispatcher — Fix & Verify"
echo "  Timestamp:  $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "  User:       $(whoami)"
echo "  Host:       $(hostname)"
echo "  OpenClaw:   $OPENCLAW_ROOT"
echo "============================================================"
echo

# ---------- DIAGNOSTICS ------------------------------------------------------
echo "─── 1. pgrep -fl telegram-dispatcher ───"
PGREP_OUT=$(pgrep -fl telegram-dispatcher 2>/dev/null || true)
if [ -z "$PGREP_OUT" ]; then
  echo "(no matching process)"
else
  echo "$PGREP_OUT"
fi
echo

echo "─── 2. launchctl list | grep -i openclaw ───"
launchctl list 2>/dev/null | grep -i openclaw || echo "(no matching launchd jobs)"
echo

echo "─── 3. clawmpson-logs/daily/ (newest 5) ───"
ls -lat "$OPENCLAW_ROOT/clawmpson-logs/daily/" 2>/dev/null | head -5 || echo "(directory not found)"
echo

echo "─── 4. tail -30 dispatcher.log ───"
if [ -f "$DISPATCHER_LOG" ]; then
  tail -30 "$DISPATCHER_LOG"
else
  echo "no dispatcher.log at $DISPATCHER_LOG"
fi
echo

# ---------- (RE)START IF NEEDED ---------------------------------------------
echo "─── 5. Decide whether to start the dispatcher ───"
if pgrep -fl telegram-dispatcher >/dev/null 2>&1; then
  echo "Dispatcher already running — skipping start."
else
  echo "Dispatcher NOT running. Locating script…"

  # Try canonical path first.
  CAND="$OPENCLAW_ROOT/scripts/telegram-dispatcher.py"
  DISPATCHER_PATH=""
  if [ -f "$CAND" ]; then
    DISPATCHER_PATH="$CAND"
  else
    # Fall back: search anywhere under $OPENCLAW_ROOT, excluding worktrees.
    DISPATCHER_PATH=$(find "$OPENCLAW_ROOT" -name 'telegram-dispatcher.py' \
      -not -path '*/.claude/worktrees/*' -not -path '*/node_modules/*' \
      -not -path '*/.venv/*' -not -path '*/site-packages/*' \
      2>/dev/null | head -1)
  fi

  if [ -z "$DISPATCHER_PATH" ] || [ ! -f "$DISPATCHER_PATH" ]; then
    echo "ERROR: could not find telegram-dispatcher.py under $OPENCLAW_ROOT"
    echo "Aborting start."
  else
    echo "Found: $DISPATCHER_PATH"

    # Pick a python: prefer the openclaw .venv if present, else system python3.
    PYTHON_BIN="python3"
    if [ -x "$OPENCLAW_ROOT/.venv/bin/python3" ]; then
      PYTHON_BIN="$OPENCLAW_ROOT/.venv/bin/python3"
    elif [ -x "$OPENCLAW_ROOT/.venv/bin/python" ]; then
      PYTHON_BIN="$OPENCLAW_ROOT/.venv/bin/python"
    fi
    echo "Using python: $PYTHON_BIN"

    # cd into the openclaw root so any relative paths inside the dispatcher
    # resolve correctly. The dispatcher already adds its own dir to sys.path.
    mkdir -p "$OPENCLAW_ROOT/logs"
    cd "$OPENCLAW_ROOT"

    echo "Starting dispatcher (nohup, backgrounded)…"
    nohup "$PYTHON_BIN" "$DISPATCHER_PATH" >> "$DISPATCHER_LOG" 2>&1 &
    DISPATCHER_PID=$!
    disown "$DISPATCHER_PID" 2>/dev/null || true
    echo "Launched PID: $DISPATCHER_PID"
  fi
fi
echo

# ---------- VERIFY ----------------------------------------------------------
echo "─── 6. Waiting 5s then re-checking ───"
sleep 5
echo

echo "─── 7. pgrep -fl telegram-dispatcher (after wait) ───"
PGREP_AFTER=$(pgrep -fl telegram-dispatcher 2>/dev/null || true)
if [ -z "$PGREP_AFTER" ]; then
  echo "(still no matching process — start likely failed; see dispatcher.log below)"
else
  echo "$PGREP_AFTER"
fi
echo

echo "─── 8. tail -20 dispatcher.log (after wait) ───"
if [ -f "$DISPATCHER_LOG" ]; then
  tail -20 "$DISPATCHER_LOG"
else
  echo "no dispatcher.log at $DISPATCHER_LOG"
fi
echo

echo "============================================================"
echo "DONE — close this window"
echo "Full log: $LOG_FILE"
echo "============================================================"
