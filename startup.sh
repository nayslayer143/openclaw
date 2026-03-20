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
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "=== Stack Status ==="
echo "  Ollama:   $(pgrep -x ollama >/dev/null && echo 'running' || echo 'NOT running')"
echo "  Neo4j:    $(command -v neo4j &>/dev/null && echo 'installed' || echo 'not installed')"
echo "  OpenClaw: $(command -v openclaw &>/dev/null && echo 'installed' || echo 'not installed')"
echo ""
echo "Stack up. Morning brief at 8am."
