#!/bin/bash
# cron-daily-log.sh — Daily work log + GitHub commit
# Schedule: daily at 11:55pm (55 23 * * *)
# Writes daily/YYYY-MM-DD.md, syncs projects.json and memory, commits to clawmpson-logs

OPENCLAW_ROOT="${HOME}/openclaw"
LOGS_REPO="${OPENCLAW_ROOT}/clawmpson-logs"
TODAY=$(date +%Y-%m-%d)
NOW=$(date +"%H:%M")

set -a; source "${OPENCLAW_ROOT}/.env" 2>/dev/null || true; set +a

# ── Pull today's activity from logs ──────────────────────────────────────────
IDLE_LOG_ENTRIES=$(grep "${TODAY}" "${OPENCLAW_ROOT}/memory/IDLE_LOG.md" 2>/dev/null | tail -20 || echo "No entries today")
BUILD_RESULTS=$(ls "${OPENCLAW_ROOT}/build-results/"*/ 2>/dev/null | grep "${TODAY}" | head -10 || echo "None")
IDEA_BRIEF=$(ls "${OPENCLAW_ROOT}/outputs/ideas-${TODAY}"*.md 2>/dev/null | tail -1 | xargs head -5 2>/dev/null || echo "No idea brief today")
PENDING_QUEUE=$(find "${OPENCLAW_ROOT}/repo-queue" -name "task-*.json" 2>/dev/null | wc -l | tr -d ' ')
PENDING_IDEAS=$(find "${OPENCLAW_ROOT}/ideas" -name "idea-*.json" -exec grep -l '"status": "pending"' {} \; 2>/dev/null | wc -l | tr -d ' ')

# ── Synthesize with LLM ───────────────────────────────────────────────────────
SUMMARY=$(ollama run gemma4:e4b "You are Clawmpson writing your daily work log for Jordan.

Today's activity log:
${IDLE_LOG_ENTRIES}

Pending queue: ${PENDING_QUEUE} tasks
Pending ideas: ${PENDING_IDEAS}
Build results today: ${BUILD_RESULTS}
Today's idea brief preview: ${IDEA_BRIEF}

Write a concise daily log (200-300 words) covering:
1. ACCOMPLISHED TODAY — bullet list of what actually got done
2. STILL IN PROGRESS — what's mid-flight
3. QUEUE STATUS — how many tasks, any blockers
4. REVENUE UPDATE — any money earned or leads generated (be honest, say $0 if nothing)
5. TOP PRIORITY TOMORROW — one specific thing

Write in first person as Clawmpson. Be honest. No fluff." 2>/dev/null || echo "LLM unavailable — raw log follows:

${IDLE_LOG_ENTRIES}")

# ── Write daily log file ──────────────────────────────────────────────────────
DAILY_FILE="${LOGS_REPO}/daily/${TODAY}.md"
cat > "${DAILY_FILE}" << EOF
# Daily Log — ${TODAY}
> Written by Clawmpson at ${NOW}

${SUMMARY}

---

## Raw Activity
\`\`\`
${IDLE_LOG_ENTRIES}
\`\`\`

## Queue Snapshot
- Pending tasks: ${PENDING_QUEUE}
- Pending ideas: ${PENDING_IDEAS}
EOF

# ── Sync projects.json snapshot ───────────────────────────────────────────────
if [[ -f "${OPENCLAW_ROOT}/projects/projects.json" ]]; then
  cp "${OPENCLAW_ROOT}/projects/projects.json" "${LOGS_REPO}/projects/projects-${TODAY}.json"
  cp "${OPENCLAW_ROOT}/projects/projects.json" "${LOGS_REPO}/projects/projects-latest.json"
fi

# ── Sync memory snapshot ──────────────────────────────────────────────────────
if [[ -f "${OPENCLAW_ROOT}/memory/MEMORY.md" ]]; then
  cp "${OPENCLAW_ROOT}/memory/MEMORY.md" "${LOGS_REPO}/memory/MEMORY-${TODAY}.md"
  cp "${OPENCLAW_ROOT}/memory/MEMORY.md" "${LOGS_REPO}/memory/MEMORY-latest.md"
fi

# ── Git commit and push ───────────────────────────────────────────────────────
cd "${LOGS_REPO}"
git add -A
git commit -m "daily log ${TODAY} — queue:${PENDING_QUEUE} ideas:${PENDING_IDEAS}" 2>/dev/null || echo "Nothing to commit"
git push origin main 2>/dev/null || echo "Push failed — will retry tomorrow"

# ── Telegram notification ─────────────────────────────────────────────────────
PREVIEW=$(echo "${SUMMARY}" | head -8)
bash "${OPENCLAW_ROOT}/scripts/notify-telegram.sh" "Daily log committed to GitHub — ${TODAY}

${PREVIEW}

github.com/nayslayer143/clawmpson-logs" 2>/dev/null || true

echo "[${TODAY}] Daily log committed to clawmpson-logs" >> "${OPENCLAW_ROOT}/memory/IDLE_LOG.md"
