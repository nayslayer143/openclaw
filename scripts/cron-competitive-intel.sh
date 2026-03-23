#!/bin/bash
# cron-competitive-intel.sh — Weekly Competitive Intelligence Scanner
# Schedule: every Monday at 7am (0 7 * * 1)
# Reads memory/competitive-scan-list.json, runs research per project, Telegrams brief

OPENCLAW_ROOT="${HOME}/openclaw"
TODAY=$(date +%Y-%m-%d)

set -a; source "${OPENCLAW_ROOT}/.env" 2>/dev/null || true; set +a

SCAN_LIST="${OPENCLAW_ROOT}/memory/competitive-scan-list.json"
if [[ ! -f "$SCAN_LIST" ]]; then
  echo "[${TODAY}] No competitive scan list found — skipping" >> "${OPENCLAW_ROOT}/memory/IDLE_LOG.md"
  exit 0
fi

PROJECTS=$(python3 -c "
import json
data = json.load(open('${SCAN_LIST}'))
for p in data:
    print(p.get('name','') + '|' + p.get('slug',''))
" 2>/dev/null)

if [[ -z "$PROJECTS" ]]; then
  echo "[${TODAY}] Competitive scan list empty — skipping" >> "${OPENCLAW_ROOT}/memory/IDLE_LOG.md"
  exit 0
fi

BRIEF_DIR="${OPENCLAW_ROOT}/autoresearch/outputs/briefs"
mkdir -p "$BRIEF_DIR"

SUMMARY="Weekly Competitive Intel — ${TODAY}"$'\n'$'\n'

while IFS='|' read -r PROJECT_NAME SLUG; do
  [[ -z "$PROJECT_NAME" ]] && continue
  echo "[${TODAY}] Scanning: ${PROJECT_NAME}"

  # Search for recent competitor news
  SEARCH_RESULTS=$(python3 -c "
import requests, json, os
key = os.environ.get('SERPER_API_KEY','')
if not key:
    print('No Serper key')
    exit()
r = requests.post('https://google.serper.dev/search',
    headers={'X-API-KEY': key, 'Content-Type': 'application/json'},
    json={'q': '${PROJECT_NAME} competitors pricing 2026', 'num': 5}, timeout=15)
results = r.json().get('organic', [])
for x in results[:5]:
    print(x.get('title','') + ': ' + x.get('snippet',''))
" 2>/dev/null || echo "Search unavailable")

  ANALYSIS=$(ollama run qwen3:32b "You are Clawmpson monitoring competitive intelligence for '${PROJECT_NAME}'.

Recent search results:
${SEARCH_RESULTS}

Write a 150-word competitive intelligence update:
1. Any NEW competitors or pricing changes this week?
2. Any market shifts or opportunities?
3. One specific action we should take based on this intel.

Be specific and actionable. No vague statements." 2>/dev/null || echo "Ollama unavailable")

  OUTPUT_FILE="${BRIEF_DIR}/competitive-${SLUG}-${TODAY}.md"
  cat > "$OUTPUT_FILE" << MDEOF
# Competitive Intel: ${PROJECT_NAME} — ${TODAY}

${ANALYSIS}

---
*Sources:*
${SEARCH_RESULTS}
MDEOF

  SUMMARY="${SUMMARY}## ${PROJECT_NAME}"$'\n'"${ANALYSIS}"$'\n\n'

  echo "[${TODAY}] Wrote: ${OUTPUT_FILE}"

done <<< "$PROJECTS"

# Telegram notification
bash "${OPENCLAW_ROOT}/scripts/notify-telegram.sh" "$SUMMARY" 2>/dev/null || true

echo "[${TODAY}] Competitive intel scan complete" >> "${OPENCLAW_ROOT}/memory/IDLE_LOG.md"
