#!/bin/bash
# =============================================================================
# cron-autonomous-work.sh — Autonomous Work Dispatcher
# Runs every 2 hours. Makes Scout, Wave, and Forge agents DO work.
# Crontab: 0 */2 * * * /Users/nayslayer/openclaw/scripts/cron-autonomous-work.sh
# =============================================================================
set -o pipefail
OC="${HOME}/openclaw"
set -a; source "${OC}/.env" 2>/dev/null || true; set +a

DATE=$(date +%Y-%m-%d)
EPOCH=$(date +%s)
SUMMARY=""
SCOUT_STATUS="idle" WAVE_STATUS="idle" FORGE_STATUS="idle"
SCOUT_TASK="" WAVE_TASK="" FORGE_TASK=""
SCOUT_ERR=0 WAVE_ERR=0 FORGE_ERR=0

# Ensure output dirs exist
mkdir -p "${OC}/autoresearch/outputs/briefs" "${OC}/outputs" "${OC}/logs"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $1" >> "${OC}/logs/cron-autonomous-work.log"; }
log "=== Autonomous work cycle starting ==="

# --- Health check: is Ollama running? ---
ollama_ok() {
  ollama list >/dev/null 2>&1
}

if ! ollama_ok; then
  log "ERROR: Ollama not responding. Attempting restart."
  ollama serve >/dev/null 2>&1 &
  sleep 5
  if ! ollama_ok; then
    log "FATAL: Ollama still down after restart. Aborting cycle."
    bash "${OC}/scripts/notify-telegram.sh" "[Autonomous Work] Ollama is down. All agents skipped." 2>/dev/null
    exit 1
  fi
fi

# Helper: call Ollama with a prompt, return stdout
ask_llm() {
  local prompt="$1"
  local result
  result=$(echo "$prompt" | ollama run qwen3:30b 2>/dev/null | sed '/^<think>/,/<\/think>/d')
  echo "$result"
}

# =============================================================================
# 1. SCOUT — Pick a pending idea and research it
# =============================================================================
run_scout() {
  log "SCOUT: Starting"
  SCOUT_STATUS="working"

  # Find most recent ideas file with actual content (has "## " headings)
  local ideas_file
  ideas_file=$(ls -t "${OC}"/outputs/ideas-*.md 2>/dev/null | while read -r f; do
    grep -q '^## ' "$f" && echo "$f" && break
  done)

  if [[ -z "$ideas_file" ]]; then
    log "SCOUT: No ideas file with content found. Skipping."
    SCOUT_STATUS="idle"; SCOUT_TASK="no ideas found"; return 1
  fi

  local ideas_content
  ideas_content=$(cat "$ideas_file")

  # Find already-researched slugs
  local existing_briefs
  existing_briefs=$(ls "${OC}/autoresearch/outputs/briefs/scout-"*.md 2>/dev/null | sed 's/.*scout-//;s/-[0-9].*//')

  # Ask LLM to pick the most promising unresearched idea
  local pick_prompt="You are a business research analyst. Below are business ideas. Already researched: ${existing_briefs:-none}.
Pick ONE idea from the list that has NOT been researched yet. Choose the one with highest revenue potential and fastest time-to-first-dollar.
Reply with ONLY the idea title (the text after **) on a single line, nothing else. No explanation.

${ideas_content}"

  local chosen
  chosen=$(ask_llm "$pick_prompt" | head -1 | sed 's/^[*# ]*//' | sed 's/[*]*$//')

  if [[ -z "$chosen" || ${#chosen} -gt 100 ]]; then
    log "SCOUT: LLM returned bad pick: '${chosen:0:50}'. Skipping."
    SCOUT_STATUS="error"; SCOUT_ERR=1; return 1
  fi

  local slug
  slug=$(echo "$chosen" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g' | sed 's/--*/-/g' | sed 's/^-//;s/-$//' | cut -c1-40)
  local brief_path="${OC}/autoresearch/outputs/briefs/scout-${slug}-${DATE}.md"

  # Serper search for market data
  local search_results=""
  if [[ -n "${SERPER_API_KEY:-}" ]]; then
    local query
    query=$(echo "$chosen" | cut -c1-60)
    search_results=$(curl -s -X POST 'https://google.serper.dev/search' \
      -H "X-API-KEY: ${SERPER_API_KEY}" \
      -H 'Content-Type: application/json' \
      -d "{\"q\": \"${query} market size competitors 2026\", \"num\": 5}" 2>/dev/null \
      | python3 -c "
import json,sys
try:
    d=json.loads(sys.stdin.read())
    for r in d.get('organic',[])[:5]:
        print(f\"- {r.get('title','')}: {r.get('snippet','')}\")
except: pass
" 2>/dev/null) || true
  fi

  # Generate research brief
  local brief_prompt="Write a 200-word research brief for this business idea: ${chosen}

Market research findings:
${search_results:-No external search data available.}

Structure:
# Scout Brief: ${chosen}
## Opportunity
## Market Size & Competitors
## Risks
## Recommended Next Step
## Verdict (GO / NO-GO / NEEDS-MORE-DATA)

Be specific and actionable. Reference the search findings where available."

  local brief
  brief=$(ask_llm "$brief_prompt")

  if [[ -z "$brief" || ${#brief} -lt 50 ]]; then
    log "SCOUT: LLM returned empty brief. Skipping."
    SCOUT_STATUS="error"; SCOUT_ERR=1; return 1
  fi

  echo "$brief" > "$brief_path"

  # Log to JSONL
  echo "{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"agent\":\"scout\",\"action\":\"research\",\"idea\":\"${chosen}\",\"slug\":\"${slug}\",\"brief\":\"${brief_path}\",\"serper\":$([ -n "$search_results" ] && echo true || echo false)}" \
    >> "${OC}/logs/scout-${DATE}.jsonl"

  SCOUT_STATUS="idle"
  SCOUT_TASK="Researched: ${chosen}"
  SUMMARY="${SUMMARY}Scout researched '${chosen}'\n"
  log "SCOUT: Done — ${brief_path}"
}

# =============================================================================
# 2. WAVE — Draft social media content
# =============================================================================
run_wave() {
  log "WAVE: Starting"
  WAVE_STATUS="working"

  # Find latest research brief or ideas file for content seed
  local seed_file
  seed_file=$(ls -t "${OC}/autoresearch/outputs/briefs/scout-"*.md 2>/dev/null | head -1)
  if [[ -z "$seed_file" ]]; then
    seed_file=$(ls -t "${OC}"/outputs/ideas-*.md 2>/dev/null | head -1)
  fi

  if [[ -z "$seed_file" ]]; then
    log "WAVE: No seed content found. Skipping."
    WAVE_STATUS="idle"; WAVE_TASK="no seed content"; return 1
  fi

  local seed_content
  seed_content=$(head -40 "$seed_file")
  local output_path="${OC}/outputs/social-drafts-${DATE}.md"

  local social_prompt="You are a social media marketer for Omega MegaCorp, a tech company building AI-powered tools and services (InformationCube, xyz.cards NFC business cards, meOS).

Based on this content:
${seed_content}

Generate:

# Social Drafts — ${DATE}

## X/Twitter Thread (5 tweets)
Write a 5-tweet thread. Each tweet under 280 chars. Use hooks, value, and a CTA. Number them 1/5 through 5/5.

## LinkedIn Post
Write one professional LinkedIn post (150-200 words). Include a hook, insight, and call-to-action.

Keep the tone sharp, confident, and founder-friendly. No hashtag spam (max 3 per post)."

  local drafts
  drafts=$(ask_llm "$social_prompt")

  if [[ -z "$drafts" || ${#drafts} -lt 50 ]]; then
    log "WAVE: LLM returned empty drafts. Skipping."
    WAVE_STATUS="error"; WAVE_ERR=1; return 1
  fi

  echo "$drafts" > "$output_path"

  echo "{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"agent\":\"wave\",\"action\":\"social-drafts\",\"seed\":\"$(basename "$seed_file")\",\"output\":\"${output_path}\"}" \
    >> "${OC}/logs/wave-${DATE}.jsonl"

  WAVE_STATUS="idle"
  WAVE_TASK="Drafted social content from $(basename "$seed_file")"
  SUMMARY="${SUMMARY}Wave drafted social content\n"
  log "WAVE: Done — ${output_path}"
}

# =============================================================================
# 3. FORGE — Generate a Fiverr gig listing
# =============================================================================
run_forge() {
  log "FORGE: Starting"
  FORGE_STATUS="working"

  local output_path="${OC}/outputs/gig-listings-${DATE}.md"

  local gig_prompt="You are a Fiverr gig listing expert. Write a complete, compelling Fiverr gig listing for this seller:

Capabilities: AI-powered research, automation, content generation. Python, JavaScript, Swift. Full-stack web and mobile development. LLM integration, API development, data analysis.

Company: Omega MegaCorp

Generate in this format:

# Fiverr Gig Listing — ${DATE}

## Gig Title (max 80 chars, keyword-rich)

## Category & Subcategory

## Description (300 words)
Include: what you deliver, tech stack, turnaround time, what makes you different.

## 3 Pricing Tiers
Basic / Standard / Premium with deliverables and price.

## 5 FAQ Questions & Answers

## Tags (5 keywords)

Make it conversion-optimized and professional."

  local listing
  listing=$(ask_llm "$gig_prompt")

  if [[ -z "$listing" || ${#listing} -lt 50 ]]; then
    log "FORGE: LLM returned empty listing. Skipping."
    FORGE_STATUS="error"; FORGE_ERR=1; return 1
  fi

  echo "$listing" > "$output_path"

  echo "{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"agent\":\"forge\",\"action\":\"gig-listing\",\"output\":\"${output_path}\"}" \
    >> "${OC}/logs/forge-${DATE}.jsonl"

  FORGE_STATUS="idle"
  FORGE_TASK="Generated Fiverr gig listing"
  SUMMARY="${SUMMARY}Forge generated Fiverr gig listing\n"
  log "FORGE: Done — ${output_path}"
}

# =============================================================================
# Run all agents (each independent — failures don't block others)
# =============================================================================
run_scout || true
run_wave  || true
run_forge || true

# =============================================================================
# 4. Update agent status file
# =============================================================================
read_tasks_today() {
  local agent="$1"
  grep -c "\"agent\":\"${agent}\"" "${OC}/logs/${agent}-${DATE}.jsonl" 2>/dev/null || echo 0
}

cat > "${OC}/logs/agent-status.json" <<STATUSEOF
{
  "scout": {"status": "${SCOUT_STATUS}", "last_task": "${SCOUT_TASK}", "last_seen": ${EPOCH}, "tasks_today": $(read_tasks_today scout), "errors_today": ${SCOUT_ERR}},
  "wave":  {"status": "${WAVE_STATUS}",  "last_task": "${WAVE_TASK}",  "last_seen": ${EPOCH}, "tasks_today": $(read_tasks_today wave),  "errors_today": ${WAVE_ERR}},
  "forge": {"status": "${FORGE_STATUS}", "last_task": "${FORGE_TASK}", "last_seen": ${EPOCH}, "tasks_today": $(read_tasks_today forge), "errors_today": ${FORGE_ERR}}
}
STATUSEOF

log "Agent status updated"

# =============================================================================
# 5. Telegram notification
# =============================================================================
if [[ -n "$SUMMARY" ]]; then
  NOTIFY_MSG="[Autonomous Work ${DATE}]
$(echo -e "$SUMMARY")
Status: scout=${SCOUT_STATUS} wave=${WAVE_STATUS} forge=${FORGE_STATUS}"
  bash "${OC}/scripts/notify-telegram.sh" "$NOTIFY_MSG" 2>/dev/null || log "WARN: Telegram notify failed"
else
  log "No work completed this cycle — skipping Telegram notification"
fi

log "=== Autonomous work cycle complete ==="
