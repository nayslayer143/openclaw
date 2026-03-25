#!/bin/bash
# GitHub Intelligence — 24-hour continuous crawl
# Runs full-scan crawl + analyst every 3 hours for 24 hours (8 cycles)
# Each cycle uses --full-scan to maximize repo discovery
# Repos accumulate across runs — nothing is ever deleted

OPENCLAW=~/openclaw
LOG=$OPENCLAW/logs/github-intel-continuous.log
DATASET_DIR=$OPENCLAW/autoresearch/outputs/datasets
PID_FILE=$OPENCLAW/logs/github-intel-continuous.pid
CYCLE_INTERVAL=10800  # 3 hours in seconds
MAX_CYCLES=8          # 8 cycles × 3hr = 24 hours

mkdir -p "$OPENCLAW/logs" "$DATASET_DIR" "$OPENCLAW/autoresearch/github-intel"

# Record PID for monitoring
echo $$ > "$PID_FILE"

echo "========================================" >> "$LOG"
echo "[$(date -Iseconds)] CONTINUOUS CRAWL STARTED" >> "$LOG"
echo "  Cycles: $MAX_CYCLES × ${CYCLE_INTERVAL}s = 24 hours" >> "$LOG"
echo "  PID: $$" >> "$LOG"
echo "========================================" >> "$LOG"

for CYCLE in $(seq 1 $MAX_CYCLES); do
  echo "" >> "$LOG"
  echo "[$(date -Iseconds)] ── Cycle $CYCLE/$MAX_CYCLES ──" >> "$LOG"

  # Alternate between full-scan and trading-only to cover more ground
  if [ $((CYCLE % 2)) -eq 1 ]; then
    MODE="--full-scan"
    echo "[$(date -Iseconds)] Mode: full-scan (all keyword groups + topics)" >> "$LOG"
  else
    MODE="--trading-only"
    echo "[$(date -Iseconds)] Mode: trading-only (focused)" >> "$LOG"
  fi

  # Step 1: Crawl
  cd "$OPENCLAW"
  python3 scripts/github_crawler.py \
    $MODE \
    --min-stars 200 \
    --max-per-query 15 \
    --readmes \
    --output "$DATASET_DIR/crawl" \
    >> "$LOG" 2>&1

  # Step 2: Analyze via Ollama (accumulates — never overwrites)
  LATEST_JSON=$(ls -t "$DATASET_DIR"/crawl_*.json 2>/dev/null | head -1)
  if [ -z "$LATEST_JSON" ]; then
    LATEST_JSON=$(ls -t "$DATASET_DIR"/*.json 2>/dev/null | head -1)
  fi

  if [ -n "$LATEST_JSON" ]; then
    # Wait for any existing analyst to finish before starting a new one
    while pgrep -f "repo_analyst.py" > /dev/null 2>&1; do
      echo "[$(date -Iseconds)] Waiting for previous analyst to finish..." >> "$LOG"
      sleep 30
    done
    echo "[$(date -Iseconds)] Analyzing: $LATEST_JSON" >> "$LOG"
    python3 scripts/repo_analyst.py \
      --crawl-file "$LATEST_JSON" \
      --top 150 \
      >> "$LOG" 2>&1
    echo "[$(date -Iseconds)] Cycle $CYCLE complete" >> "$LOG"
  else
    echo "[$(date -Iseconds)] No crawl output found for cycle $CYCLE" >> "$LOG"
  fi

  # Wait for next cycle (skip wait on last cycle)
  if [ $CYCLE -lt $MAX_CYCLES ]; then
    echo "[$(date -Iseconds)] Sleeping ${CYCLE_INTERVAL}s until next cycle..." >> "$LOG"
    sleep $CYCLE_INTERVAL
  fi
done

echo "" >> "$LOG"
echo "========================================" >> "$LOG"
echo "[$(date -Iseconds)] CONTINUOUS CRAWL COMPLETE — 24 hours finished" >> "$LOG"
echo "========================================" >> "$LOG"

# Cleanup PID file
rm -f "$PID_FILE"
