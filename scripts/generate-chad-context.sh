#!/bin/bash
# OPENCLAW CONTEXT GENERATOR FOR CHATGPT (CHAD)
# Outputs ~/openclaw/outputs/CHAD-CONTEXT.md — Usage: chad-context

OUTPUT="$HOME/openclaw/outputs/CHAD-CONTEXT.md"
TIMESTAMP=$(date -Iseconds)
MAX_DEPTH=2
MAX_CHARS=2000

# Directories to scan (only those that exist)
SCAN_DIRS=()
for d in "$HOME/openclaw" "$HOME/rivalclaw" "$HOME/arbclaw" "$HOME/quantumentalclaw" \
         "$HOME/doctor-claw" "$HOME/openclaw/doctor-claw" \
         "$HOME/punch-my-baby" "$HOME/openclaw/punch-my-baby" \
         "$HOME/shiny-new" "$HOME/openclaw/shiny-new" \
         "$HOME/cinema-lab" "$HOME/openclaw/cinema-lab"; do
    [ -d "$d" ] && SCAN_DIRS+=("$d")
done

EXCLUDES=(-not -path "*/.git/*" -not -path "*/node_modules/*" -not -path "*/dist/*" \
  -not -path "*/__pycache__/*" -not -path "*/venv/*" -not -path "*/.next/*" \
  -not -path "*/logs/*" -not -path "*/.env*" -not -path "*/build-results/*" \
  -not -path "*/repo-queue/*" -not -path "*/outputs/*" -not -path "*/archive/*" \
  -not -path "*/.claude/*" -not -path "*/chatgpt-mcp/*" -not -path "*/.mypy_cache/*" \
  -not -path "*/.pytest_cache/*" -not -path "*/coverage/*" -not -path "*/.DS_Store")

cat > "$OUTPUT" << HEADER
# OpenClaw Ecosystem — Master Context for ChatGPT

> Auto-generated $TIMESTAMP. Do not edit manually.
> For live code, use the GitHub MCP connector to read repos directly.

Generated: $TIMESTAMP
Machine: Jordan's MacBook Pro M2 Max (96GB)
User: nayslayer

HEADER

# ── System Overview ──
cat >> "$OUTPUT" << 'OVERVIEW'
## System Overview

OpenClaw is the operator shell for Jordan's web-based businesses. Claude Code is the build plane. Local Ollama models (14 models, ~264GB) handle inference at zero API cost. Three trading bots compete head-to-head:

| Bot | Path | Architecture | Status |
|-----|------|-------------|--------|
| Clawmpson | ~/openclaw/ | 4 strategies, 5 feeds, graduation engine, 13 agents | Active, Phase 5 |
| RivalClaw | ~/rivalclaw/ | 8 strategies + hedge engine, self-tuner, 3 feeds | Active, daily runs |
| ArbClaw | ~/arbclaw/ | Lean single-strategy arb, 5-min cycle | Not yet built |

**Gonzoclaw Dashboard:** FastAPI + HTML at localhost:7080, exposed via Cloudflare tunnel at https://www.asdfghjk.lol
**Database:** ~/.openclaw/clawmson.db (SQLite, 8 tables)
**GitHub:** https://github.com/nayslayer143/openclaw

OVERVIEW

# ── Directory Trees ──
echo "## Directory Structure" >> "$OUTPUT"
for dir in "${SCAN_DIRS[@]}"; do
    case "$dir" in "$HOME/openclaw/"*) continue ;; esac  # skip openclaw subdirs
    BASENAME=$(basename "$dir")
    echo -e "\n### $BASENAME ($dir)\n\`\`\`" >> "$OUTPUT"
    if [ "$dir" = "$HOME/openclaw" ]; then
        find "$dir" -maxdepth $MAX_DEPTH -type d "${EXCLUDES[@]}" 2>/dev/null
    else
        find "$dir" -maxdepth $MAX_DEPTH \( -type f -o -type d \) "${EXCLUDES[@]}" 2>/dev/null
    fi | sed "s|$HOME|~|g" | sort >> "$OUTPUT"
    echo '```' >> "$OUTPUT"
done

# ── CLAUDE.md Files ──
echo -e "\n## Project Instructions (CLAUDE.md files)" >> "$OUTPUT"
for dir in "${SCAN_DIRS[@]}"; do
    [ -f "$dir/CLAUDE.md" ] || continue
    REL=$(echo "$dir/CLAUDE.md" | sed "s|$HOME|~|g")
    echo -e "\n### $REL\n\`\`\`" >> "$OUTPUT"
    head -c $MAX_CHARS "$dir/CLAUDE.md" >> "$OUTPUT"
    echo -e "\n\`\`\`" >> "$OUTPUT"
done

# ── README Files (deduplicated) ──
echo -e "\n## README Files" >> "$OUTPUT"
TMP=$(mktemp)
for dir in "${SCAN_DIRS[@]}"; do
    find "$dir" -maxdepth 2 -name "README.md" -not -path "*/.git/*" -not -path "*/node_modules/*" 2>/dev/null
done | sort -u > "$TMP"
while read -r f; do
    REL=$(echo "$f" | sed "s|$HOME|~|g")
    echo -e "\n### $REL\n\`\`\`" >> "$OUTPUT"
    head -c $MAX_CHARS "$f" >> "$OUTPUT"
    echo -e "\n\`\`\`" >> "$OUTPUT"
done < "$TMP"
rm -f "$TMP"

# ── Tech Stack Fingerprint (deduplicated) ──
echo -e "\n## Tech Stack Fingerprint" >> "$OUTPUT"
TMP=$(mktemp)
for dir in "${SCAN_DIRS[@]}"; do
    find "$dir" -maxdepth 2 \( -name "package.json" -o -name "pyproject.toml" -o -name "requirements.txt" \) \
        -not -path "*/node_modules/*" 2>/dev/null
done | sort -u > "$TMP"
while read -r f; do
    REL=$(echo "$f" | sed "s|$HOME|~|g")
    echo -e "\n### $REL\n\`\`\`" >> "$OUTPUT"
    head -c 2000 "$f" >> "$OUTPUT"
    echo -e "\n\`\`\`" >> "$OUTPUT"
done < "$TMP"
rm -f "$TMP"

# ── Git Status ──
echo -e "\n## Git Status" >> "$OUTPUT"
for dir in "${SCAN_DIRS[@]}"; do
    [ -d "$dir/.git" ] || continue
    echo -e "\n### $(basename "$dir")\n\`\`\`" >> "$OUTPUT"
    (cd "$dir"
     echo "Branch: $(git branch --show-current 2>/dev/null)"
     echo "Last commit: $(git log -1 --oneline 2>/dev/null)"
     echo "Uncommitted files: $(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
     echo "Remote: $(git remote get-url origin 2>/dev/null)"
    ) >> "$OUTPUT"
    echo '```' >> "$OUTPUT"
done

# ── .env filenames (NOT values) ──
echo -e "\n## Environment Files (names only, NO values)\n\`\`\`" >> "$OUTPUT"
for dir in "${SCAN_DIRS[@]}"; do
    find "$dir" -maxdepth 2 -name ".env*" -not -path "*/node_modules/*" 2>/dev/null | sed "s|$HOME|~|g"
done >> "$OUTPUT"
echo '```' >> "$OUTPUT"

# ── Trading State ──
echo -e "\n## Trading State (if available)" >> "$OUTPUT"
if [ -f "$HOME/openclaw/trading/dashboard.json" ]; then
    echo -e "\n### Clawmpson Trading Dashboard\n\`\`\`json" >> "$OUTPUT"
    head -c 3000 "$HOME/openclaw/trading/dashboard.json" >> "$OUTPUT"
    echo -e "\n\`\`\`" >> "$OUTPUT"
fi

echo -e "\n---\nEnd of context. Generated $TIMESTAMP.\nFor live code, use GitHub MCP connector -> github.com/nayslayer143/openclaw" >> "$OUTPUT"

# ── Safety check ──
LEAKS=$(grep -cE '(sk-[a-zA-Z0-9]{20}|ghp_[a-zA-Z0-9]{36}|xoxb-|xoxp-|AKIA[A-Z0-9]{16})' "$OUTPUT" 2>/dev/null)
[ "${LEAKS:-0}" -gt 0 ] && echo "WARNING: $LEAKS potential secret patterns found. Review before uploading!"

# Report
LINES=$(wc -l < "$OUTPUT")
SIZE=$(wc -c < "$OUTPUT" | awk '{printf "%.1f", $1/1024}')
echo "Context generated: $OUTPUT"
echo "   $LINES lines, ${SIZE}KB"
echo "   Upload to ChatGPT Project or paste into conversation."
