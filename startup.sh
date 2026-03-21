#!/bin/bash
# =============================================================================
# startup.sh — OpenClaw Cold Start
# Run after Mac restart or add to macOS Login Items
# =============================================================================

set -euo pipefail

echo "=== OpenClaw v4.1 Cold Start ==="
echo "Date: $(date)"
echo ""

# ---------------------------------------------------------------------------
# GPU cap (resets on restart — must run each boot)
# ---------------------------------------------------------------------------
echo "→ Setting GPU memory cap..."
sudo sysctl iogpu.wired_limit_mb=73728 2>/dev/null && echo "  ✓ GPU cap: 72GB" || echo "  ⚠ GPU cap: failed (may need sudo)"

# ---------------------------------------------------------------------------
# Ollama parallelism (conservative — Phase 0-1)
# Phase 2: change to OLLAMA_NUM_PARALLEL=4, OLLAMA_MAX_QUEUE=128
# Phase 4+: change to OLLAMA_NUM_PARALLEL=6, OLLAMA_MAX_QUEUE=512
# ---------------------------------------------------------------------------
export OLLAMA_NUM_PARALLEL=2
export OLLAMA_MAX_QUEUE=32
echo "→ Ollama parallelism: ${OLLAMA_NUM_PARALLEL} parallel, ${OLLAMA_MAX_QUEUE} queue"

# ---------------------------------------------------------------------------
# Neo4j (guarded — install with: brew install neo4j)
# ---------------------------------------------------------------------------
if command -v neo4j &>/dev/null; then
  neo4j start 2>/dev/null && echo "→ Neo4j: started" || echo "→ Neo4j: already running or failed"
else
  echo "→ Neo4j: not installed (needed for MiroFish in Phase 2+)"
fi

# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------
if pgrep -x "ollama" >/dev/null 2>&1; then
  echo "→ Ollama: already running"
else
  echo "→ Starting Ollama..."
  ollama serve > /tmp/ollama.log 2>&1 &
  sleep 5
fi

# Health check
if ollama list > /dev/null 2>&1; then
  echo "→ Ollama: ready"
  echo "  Models loaded:"
  ollama list 2>/dev/null | tail -n +2 | awk '{print "    - "$1" ("$3" "$4")"}'
else
  echo "✗ Ollama: failed — check /tmp/ollama.log"
  exit 1
fi

# ---------------------------------------------------------------------------
# Verify critical models
# ---------------------------------------------------------------------------
echo ""
echo "→ Checking critical models..."
MISSING=0
for MODEL in "qwen3:32b" "glm4:7b-flash" "nomic-embed-text"; do
  if ollama list 2>/dev/null | grep -q "$MODEL"; then
    echo "  ✓ $MODEL"
  else
    echo "  ✗ $MODEL — MISSING (run: ollama pull $MODEL)"
    MISSING=$((MISSING + 1))
  fi
done

if [[ $MISSING -gt 0 ]]; then
  echo "  ⚠ $MISSING critical model(s) missing"
fi

# ---------------------------------------------------------------------------
# OpenClaw (guarded — may not be installed yet)
# ---------------------------------------------------------------------------
if command -v openclaw &>/dev/null; then
  openclaw start
  echo "→ OpenClaw: started"
else
  echo "→ OpenClaw CLI: not installed yet"
fi

# ---------------------------------------------------------------------------
# Queue Runner — Clawmpson never sleeps
# ---------------------------------------------------------------------------
QUEUE_RUNNER="${OPENCLAW_ROOT:-$HOME/openclaw}/scripts/queue-runner.sh"
if [[ -f "$QUEUE_RUNNER" ]]; then
  if [[ -f "$HOME/openclaw/.queue-runner.pid" ]] && kill -0 "$(cat "$HOME/openclaw/.queue-runner.pid")" 2>/dev/null; then
    echo "→ Queue runner: already running (PID $(cat "$HOME/openclaw/.queue-runner.pid"))"
  else
    nohup "$QUEUE_RUNNER" --max 3 > /dev/null 2>&1 &
    echo "→ Queue runner: started (PID $!, max 3 concurrent)"
  fi
else
  echo "→ Queue runner: not found at $QUEUE_RUNNER"
fi

# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
if pgrep -f "openclaw/dashboard/server.py" >/dev/null 2>&1; then
  echo "→ Dashboard: already running"
else
  cd "$HOME/openclaw/dashboard" && nohup python3 server.py > /dev/null 2>&1 &
  echo "→ Dashboard: started on :7080 (PID $!)"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "=== Stack Status ==="
echo "  Ollama:       $(pgrep -x ollama >/dev/null && echo 'running' || echo 'NOT running')"
echo "  Neo4j:        $(command -v neo4j &>/dev/null && echo 'installed' || echo 'not installed')"
echo "  OpenClaw:     $(command -v openclaw &>/dev/null && echo 'installed' || echo 'not installed')"
echo "  Queue Runner: $(pgrep -f queue-runner.sh >/dev/null && echo 'running' || echo 'NOT running')"
echo "  Dashboard:    $(pgrep -f 'dashboard/server.py' >/dev/null && echo 'running on :7080' || echo 'NOT running')"
echo ""
echo "Stack up. Clawmpson never sleeps."

# ---------------------------------------------------------------------------
# Cloudflare Tunnel — GonzoClaw mobile access
# ---------------------------------------------------------------------------
if pgrep -f "cloudflared tunnel" >/dev/null 2>&1; then
  echo "→ Cloudflare tunnel: already running"
else
  cloudflared tunnel --config ~/.cloudflared/config.yml run gonzoclaw > /tmp/cf-tunnel.log 2>&1 &
  sleep 4
  echo "→ Cloudflare tunnel: https://www.asdfghjk.lol"
  bash "$HOME/openclaw/scripts/notify-telegram.sh" "GonzoClaw online: https://www.asdfghjk.lol" 2>/dev/null || true
fi
