#!/bin/bash
# =============================================================================
# cron-design-intel-scout.sh — Design Intelligence Scout
# Schedule: daily at 6:00am (0 6 * * *)
# Implements: lobster-workflows/design-intel-scout.lobster
#
# Pipeline:
#   1. Load existing KB (for duplicate checking)
#   2. Run Claude Code with WebSearch to scout world-class design sites
#   3. Validate + merge new entries into design-kb-current.json
#   4. Write scout brief to ~/openclaw/outputs/design-intel-scout-{date}.md
#   5. Telegram Tier-1 notification (auto-deliver, no hold)
#   6. Log to IDLE_LOG.md
# =============================================================================

export PATH="/Users/nayslayer/.local/bin:/usr/local/bin:/opt/homebrew/bin:${PATH}"

OPENCLAW_ROOT="${HOME}/openclaw"
TODAY=$(date +%Y-%m-%d)
TIMESTAMP=$(date +%H:%M)
KB_PATH="${OPENCLAW_ROOT}/autoresearch/outputs/datasets/design-kb-current.json"
BRIEF_OUT="${OPENCLAW_ROOT}/outputs/design-intel-scout-${TODAY}.md"
LOG_FILE="${OPENCLAW_ROOT}/logs/cron-design-intel.log"
IDLE_LOG="${OPENCLAW_ROOT}/memory/IDLE_LOG.md"

# Load .env
set -a
source "${OPENCLAW_ROOT}/.env" 2>/dev/null || true
set +a

mkdir -p "${OPENCLAW_ROOT}/logs"
mkdir -p "$(dirname "${KB_PATH}")"

echo "[$(date)] design-intel-scout start" >> "$LOG_FILE"

# =============================================================================
# Step 1: Load existing KB — extract URLs for dedup prompt
# =============================================================================
EXISTING_URLS=$(python3 -c "
import json, sys
try:
    with open('${KB_PATH}') as f:
        data = json.load(f)
    urls = [e.get('url','') for e in data.get('entries', [])]
    print('\n'.join(urls))
except Exception:
    print('')
" 2>/dev/null || echo "")

EXISTING_COUNT=$(python3 -c "
import json
try:
    with open('${KB_PATH}') as f:
        data = json.load(f)
    print(len(data.get('entries', [])))
except Exception:
    print(0)
" 2>/dev/null || echo "0")

echo "[$(date)] Existing KB entries: ${EXISTING_COUNT}" >> "$LOG_FILE"

# =============================================================================
# Step 2: Scout the web via Claude Code (WebSearch + WebFetch)
# =============================================================================
SCOUT_PROMPT="You are the design intelligence scout for Omega MegaCorp.

Search the web for today's most compelling, boundary-pushing websites and digital experiences.

Search these sources:
- awwwards.com (Site of the Day, recent Honorable Mentions)
- godly.website (new additions)
- siteinspire.com (recent picks)
- cssdesignawards.com (WOTD/WOTW)
- thefwa.com (recent FWA picks)

Selection criteria (strict):
- Art-directed, not just pretty UI
- Something technically OR aesthetically unexpected
- Would make a skilled designer stop scrolling
- NOT: SaaS dashboards, generic agency sites, Bootstrap templates

For each entry you find, extract ALL fields exactly:
{
  \"url\": \"full URL\",
  \"name\": \"site or studio name\",
  \"discovered\": \"${TODAY}\",
  \"source\": \"awwwards|godly|siteinspire|cssawards|fwa|other\",
  \"what_makes_it_special\": \"specific technique or decision, not vibe\",
  \"techniques\": [\"array\", \"of\", \"css/js/visual\", \"techniques\"],
  \"aesthetic_tags\": [\"array\", \"of\", \"aesthetic\", \"descriptors\"],
  \"intensity\": 8,
  \"applicable_to\": [\"landing\", \"portfolio\", \"product\", \"experience\", \"editorial\"],
  \"the_unexpected\": \"the one thing you didn't see coming\",
  \"brief_injection\": \"one sentence usable verbatim in a design brief\"
}

Return 3-5 entries maximum. Quality floor: intensity >= 6 or genuinely novel technique.
Output ONLY a valid JSON array. No prose, no markdown, no commentary.

Already in KB (skip these URLs):
${EXISTING_URLS}"

echo "[$(date)] Running Claude Code web scout..." >> "$LOG_FILE"

SCOUT_RAW=$(echo "$SCOUT_PROMPT" | claude --print \
  --allowedTools "WebSearch,WebFetch,Read" 2>&1) || SCOUT_EXIT=$?

SCOUT_EXIT="${SCOUT_EXIT:-0}"

echo "[$(date)] Claude Code scout complete (exit: ${SCOUT_EXIT})" >> "$LOG_FILE"

# =============================================================================
# Step 3: Parse + validate new entries from scout output
# =============================================================================
NEW_ENTRIES=$(python3 -c "
import json, re, sys

raw = '''${SCOUT_RAW}'''

# Extract JSON array from Claude output
# Try to find first [...] block
match = re.search(r'\[[\s\S]*\]', raw)
if not match:
    print('[]')
    sys.exit(0)

try:
    entries = json.loads(match.group(0))
except json.JSONDecodeError:
    print('[]')
    sys.exit(0)

# Validate each entry has required fields
required = ['url', 'name', 'discovered', 'source', 'what_makes_it_special',
            'techniques', 'aesthetic_tags', 'intensity', 'applicable_to',
            'the_unexpected', 'brief_injection']

valid = []
for e in entries:
    if not isinstance(e, dict):
        continue
    missing = [f for f in required if f not in e]
    if missing:
        continue
    # brief_injection must be specific (not just 'beautiful' etc)
    bi = e.get('brief_injection', '')
    if len(bi) < 20 or bi.lower() in ('beautiful typography', 'beautiful design', 'minimal design'):
        continue
    # intensity must be a number
    try:
        e['intensity'] = int(e['intensity'])
    except (ValueError, TypeError):
        e['intensity'] = 6
    # enforce floor
    if e['intensity'] < 6:
        continue
    valid.append(e)

print(json.dumps(valid, indent=2))
" 2>/dev/null || echo "[]")

NEW_COUNT=$(python3 -c "import json; print(len(json.loads('''${NEW_ENTRIES}''')))" 2>/dev/null || echo "0")
echo "[$(date)] Valid new entries: ${NEW_COUNT}" >> "$LOG_FILE"

# =============================================================================
# Step 4: Merge into KB (dedup by URL, trim to 90 days / 200 entries)
# =============================================================================
python3 << PYEOF
import json
from datetime import datetime, timedelta
from pathlib import Path

KB_PATH = Path('${KB_PATH}')
TODAY = '${TODAY}'
CUTOFF = (datetime.strptime(TODAY, '%Y-%m-%d') - timedelta(days=90)).strftime('%Y-%m-%d')

# Load existing KB
try:
    with open(KB_PATH) as f:
        kb_data = json.load(f)
    existing = kb_data.get('entries', [])
    meta = kb_data.get('_meta', {})
except Exception:
    existing = []
    meta = {}

# New entries
try:
    new_entries = json.loads('''${NEW_ENTRIES}''')
except Exception:
    new_entries = []

# Build URL index from existing (new entries take precedence)
existing_by_url = {e['url']: e for e in existing}
for e in new_entries:
    existing_by_url[e['url']] = e

merged = list(existing_by_url.values())

# Remove entries older than 90 days
merged = [e for e in merged if e.get('discovered', TODAY) >= CUTOFF]

# If still > 200, drop lowest intensity first
if len(merged) > 200:
    merged.sort(key=lambda e: e.get('intensity', 0))
    merged = merged[len(merged)-200:]

# Update meta
meta.update({
    'description': 'Omega MegaCorp Design Intelligence Knowledge Base',
    'schema_version': '1.0',
    'max_entries': 200,
    'max_age_days': 90,
    'last_trimmed': TODAY,
    'inject_script': 'agents/tools/design-inject.py'
})

output = {'_meta': meta, 'entries': merged}

KB_PATH.parent.mkdir(parents=True, exist_ok=True)
with open(KB_PATH, 'w') as f:
    json.dump(output, f, indent=2)

print(f'KB written: {len(merged)} entries')
PYEOF

FINAL_COUNT=$(python3 -c "
import json
try:
    with open('${KB_PATH}') as f:
        data = json.load(f)
    print(len(data.get('entries', [])))
except Exception:
    print('?')
" 2>/dev/null || echo "?")

echo "[$(date)] KB updated: ${FINAL_COUNT} total entries" >> "$LOG_FILE"

# =============================================================================
# Step 5: Write scout brief (picked up by daily-intel-lite at 7:03am)
# =============================================================================
if [[ "$NEW_COUNT" -gt "0" ]]; then
  TOP_ENTRY=$(python3 -c "
import json
try:
    entries = json.loads('''${NEW_ENTRIES}''')
    if entries:
        top = max(entries, key=lambda e: e.get('intensity', 0))
        print(top.get('name', 'Unknown'))
        print('---')
        print(top.get('what_makes_it_special', ''))
        print('---')
        print(top.get('brief_injection', ''))
    else:
        print('None\n---\n---')
except Exception:
    print('None\n---\n---')
" 2>/dev/null || echo "None
---

---
")

  TOP_NAME=$(echo "$TOP_ENTRY" | sed -n '1p')
  TOP_SPECIAL=$(echo "$TOP_ENTRY" | sed -n '3p')
  TOP_INJECTION=$(echo "$TOP_ENTRY" | sed -n '5p')

  BRIEF_PROMPT="Write a concise design intelligence scout report. Under 150 words. Signal only.

New sites found today: ${NEW_COUNT}
Top pick: ${TOP_NAME} — ${TOP_SPECIAL}
Brief injection: ${TOP_INJECTION}
Total KB entries: ${FINAL_COUNT}

Format exactly:
# design-intel-scout-${TODAY}

**Today's finds:** [N] sites — [1-sentence aesthetic range summary]

**Standout:** [site name] — [what makes it special]

**Brief injection ready:** \"[brief_injection from top entry]\"

**Full KB:** ${FINAL_COUNT} entries"

  BRIEF_BODY=$(echo "$BRIEF_PROMPT" | ollama run qwen2.5:7b 2>/dev/null || cat << FALLBACK
# design-intel-scout-${TODAY}

**Today's finds:** ${NEW_COUNT} sites — curated from Awwwards, Godly, Siteinspire

**Standout:** ${TOP_NAME} — ${TOP_SPECIAL}

**Brief injection ready:** "${TOP_INJECTION}"

**Full KB:** ${FINAL_COUNT} entries
FALLBACK
)

  echo "$BRIEF_BODY" > "$BRIEF_OUT"
  echo "[$(date)] Scout brief written: ${BRIEF_OUT}" >> "$LOG_FILE"

else
  # No new entries — write a minimal brief so intel-scan doesn't skip silently
  cat > "$BRIEF_OUT" << NOBRIEFEOF
# design-intel-scout-${TODAY}

**Today's finds:** 0 sites — no new qualifying entries found

**KB status:** ${FINAL_COUNT} entries (no change)

**Sources checked:** awwwards, godly, siteinspire, cssdesignawards, fwa
NOBRIEFEOF
  echo "[$(date)] No new entries — stub brief written" >> "$LOG_FILE"
fi

# =============================================================================
# Step 6: Telegram notification (Tier-1 — auto-deliver, no approval hold)
# =============================================================================
if [[ "$NEW_COUNT" -gt "0" ]]; then
  TG_MSG="🎨 Design Scout — ${TODAY}
${NEW_COUNT} new site(s) in KB (total: ${FINAL_COUNT})

Standout: ${TOP_NAME:-unknown}
\"${TOP_INJECTION:-see brief}\"

Brief: ~/openclaw/outputs/design-intel-scout-${TODAY}.md"
else
  TG_MSG="🎨 Design Scout — ${TODAY}
No new qualifying sites found today.
KB stable at ${FINAL_COUNT} entries."
fi

bash "${OPENCLAW_ROOT}/scripts/notify-telegram.sh" "$TG_MSG" 2>/dev/null || \
  echo "[$(date)] Telegram notification failed (non-fatal)" >> "$LOG_FILE"

# =============================================================================
# Step 7: Log to IDLE_LOG.md
# =============================================================================
cat >> "$IDLE_LOG" << LOGENTRY

### Design Intel Scout — ${TODAY} 06:00
- New sites found: ${NEW_COUNT}
- KB total: ${FINAL_COUNT} entries
- Sources checked: awwwards, godly, siteinspire, cssdesignawards, fwa
- Brief: outputs/design-intel-scout-${TODAY}.md
LOGENTRY

echo "[$(date)] design-intel-scout complete" >> "$LOG_FILE"
