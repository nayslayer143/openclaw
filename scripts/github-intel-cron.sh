#!/bin/bash
# GitHub Intelligence Pipeline — runs every 6 hours
# Crontab: 0 */6 * * * ~/openclaw/scripts/github-intel-cron.sh
# LaunchAgent: ~/Library/LaunchAgents/com.openclaw.github-intel.plist

OPENCLAW=~/openclaw
LOG=$OPENCLAW/logs/github-intel.log
DATASET_DIR=$OPENCLAW/autoresearch/outputs/datasets

mkdir -p "$OPENCLAW/logs" "$DATASET_DIR" "$OPENCLAW/autoresearch/github-intel"

echo "[$(date -Iseconds)] Starting GitHub Intelligence crawl" >> "$LOG"

# Step 1: Run crawler (no tokens needed beyond GitHub API)
cd "$OPENCLAW"
python3 scripts/github_crawler.py \
  --trading-only \
  --min-stars 300 \
  --readmes \
  --output "$DATASET_DIR/crawl" \
  >> "$LOG" 2>&1

# Step 2: Run analyst (uses local Ollama, zero API cost)
LATEST_JSON=$(ls -t "$DATASET_DIR"/crawl_*.json 2>/dev/null | head -1)
if [ -z "$LATEST_JSON" ]; then
  LATEST_JSON=$(ls -t "$DATASET_DIR"/*.json 2>/dev/null | head -1)
fi

if [ -n "$LATEST_JSON" ]; then
  # Use small fast model for background analysis — keeps big models free for
  # foreground work like PSE vision digest and on-demand Claw tasks.
  python3 scripts/repo_analyst.py --crawl-file "$LATEST_JSON" --top 150 --model gemma4:e4b >> "$LOG" 2>&1
  echo "[$(date -Iseconds)] Analysis complete" >> "$LOG"
else
  echo "[$(date -Iseconds)] No crawl output found" >> "$LOG"
fi
