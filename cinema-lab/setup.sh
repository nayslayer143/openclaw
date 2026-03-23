#!/bin/bash
# ══════════════════════════════════════════════════════════════════
# CINEMA LAB — One-shot setup for cinematic web testing pipeline
# Run this once to set up everything
# ══════════════════════════════════════════════════════════════════

set -e

OPENCLAW_ROOT="$HOME/openclaw"
CINEMA_DIR="$OPENCLAW_ROOT/cinema-lab"
BUILDS_DIR="$CINEMA_DIR/builds"
SKILL_DIR="$HOME/.claude/skills/cinematic-web"

echo "◆ CINEMA LAB SETUP"
echo "══════════════════════════════════════════════════════════════"

# 1. Create cinema-lab directories
echo "► Creating cinema-lab directories..."
mkdir -p "$CINEMA_DIR"
mkdir -p "$BUILDS_DIR"
mkdir -p "$CINEMA_DIR/logs"
mkdir -p "$SKILL_DIR/references"

# 2. Create the index.json if it doesn't exist
if [ ! -f "$CINEMA_DIR/index.json" ]; then
  echo '{"builds": [], "current_tier": 1, "last_batch": null}' > "$CINEMA_DIR/index.json"
  echo "  ✓ Created index.json"
fi

# 3. Copy prompt bank
echo "► Installing prompt bank..."
# The prompt bank should be at the same level as this script
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/cinema-lab-prompt-bank.json" ]; then
  cp "$SCRIPT_DIR/cinema-lab-prompt-bank.json" "$CINEMA_DIR/prompt-bank.json"
  echo "  ✓ Prompt bank installed (25 prompts across 5 tiers)"
else
  echo "  ⚠ prompt-bank.json not found next to this script — copy it manually to $CINEMA_DIR/prompt-bank.json"
fi

echo ""
echo "◆ SETUP COMPLETE"
echo "══════════════════════════════════════════════════════════════"
echo ""
echo "Next steps:"
echo "  1. Copy the cinematic-web skill to ~/.claude/skills/cinematic-web/"
echo "  2. Restart your gonzoclaw server: cd ~/openclaw/dashboard && python server.py"
echo "  3. Open http://localhost:7080 and click the CINEMA LAB tab"
echo "  4. Click TRIGGER BUILD to queue 5 builds"
echo ""
echo "For daily automated builds, add this to your crontab:"
echo "  0 9 * * * cd $OPENCLAW_ROOT && claude -p 'Run the cinema-lab daily build. Read the cinematic-web skill, pick 5 prompts from ~/openclaw/cinema-lab/prompt-bank.json based on the current tier in ~/openclaw/cinema-lab/index.json, build each one as a single HTML file, and save them to ~/openclaw/cinema-lab/builds/ with IDs matching the index. Update index.json with the new builds.'"
echo ""
