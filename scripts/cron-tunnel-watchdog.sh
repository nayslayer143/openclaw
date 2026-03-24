#!/bin/bash
# cron-tunnel-watchdog.sh — keeps dashboard + tunnel alive
# Schedule: */5 * * * *

# Dashboard
if ! pgrep -f "dashboard/server.py" > /dev/null; then
  cd "$HOME/openclaw/dashboard"
  nohup python3 server.py > /dev/null 2>&1 &
  echo "[$(date)] Dashboard restarted" >> "$HOME/openclaw/logs/watchdog.log"
fi

# Tunnel
if ! pgrep -f "cloudflared tunnel.*run" > /dev/null; then
  cloudflared tunnel --config ~/.cloudflared/config.yml run gonzoclaw > /tmp/cf-tunnel.log 2>&1 &
  echo "[$(date)] Tunnel restarted" >> "$HOME/openclaw/logs/watchdog.log"
fi

# Terminal relay — clean up stale PID if process is dead
RELAY_PID="$HOME/openclaw/logs/terminal-relay.pid"
if [ -f "$RELAY_PID" ]; then
  if ! kill -0 "$(cat "$RELAY_PID")" 2>/dev/null; then
    echo "[$(date)] terminal-relay stale PID — cleaning up" >> "$HOME/openclaw/logs/watchdog.log"
    rm -f "$RELAY_PID"
  fi
fi

# Dispatcher — PID-file guarded (prevents duplicate instances)
DISP_PID="$HOME/openclaw/.dispatcher.pid"
if [[ -f "$DISP_PID" ]] && kill -0 "$(cat "$DISP_PID")" 2>/dev/null; then
  : # already running
else
  # Kill any stale instances before starting fresh
  pkill -f "telegram-dispatcher" 2>/dev/null || true
  sleep 1
  cd "$HOME/openclaw/scripts"
  OLLAMA_CHAT_MODEL=qwen3:32b OLLAMA_CLASSIFY_MODEL=qwen2.5:7b PYTHONUNBUFFERED=1 \
    nohup python3 telegram-dispatcher.py >> /tmp/openclaw-dispatcher.log 2>&1 &
  echo $! > "$DISP_PID"
  echo "[$(date)] Dispatcher restarted (PID $!)" >> "$HOME/openclaw/logs/watchdog.log"
fi
