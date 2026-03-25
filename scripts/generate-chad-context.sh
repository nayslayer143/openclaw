#!/bin/bash
# ============================================================
# OPENCLAW CONTEXT GENERATOR FOR CHATGPT (CHAD)
# Scans all claw instances + projects on Jordan's Mac
# Outputs: ~/openclaw/outputs/CHAD-CONTEXT.md
# Usage: chad-context (alias) or bash ~/openclaw/scripts/generate-chad-context.sh
# ============================================================

OUTPUT="$HOME/openclaw/outputs/CHAD-CONTEXT.md"
TIMESTAMP=$(date -Iseconds)

# Directories to scan (add any that exist)
SCAN_DIRS=()
for d in "$HOME/openclaw" "$HOME/rivalclaw" "$HOME/arbclaw" \
         "$HOME/quantumentalclaw" \
         "$HOME/doctor-claw" "$HOME/openclaw/doctor-claw" \
         "$HOME/punch-my-baby" "$HOME/openclaw/punch-my-baby" \
         "$HOME/shiny-new" "$HOME/openclaw/shiny-new" \
         "$HOME/cinema-lab" "$HOME/openclaw/cinema-lab"; do
    [ -d "$d" ] && SCAN_DIRS+=("$d")
done

MAX_DEPTH=2
MAX_README_CHARS=2000

cat > "$OUTPUT" << 'HEADER'
# OpenClaw Ecosystem — Master Context for ChatGPT

> This file is auto-generated. Do not edit manually.
> Use as orientation for research sessions, not as source of truth for live code.
> For live code, use the GitHub MCP connector to read repos directly.

HEADER

echo "Generated: $TIMESTAMP" >> "$OUTPUT"
echo "Machine: Jordan's MacBook Pro M2 Max (96GB)" >> "$OUTPUT"
echo "User: nayslayer" >> "$OUTPUT"
echo "" >> "$OUTPUT"

# ── SECTION 1: System Overview ──
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

# ── SECTION 2: Directory Trees ──
echo "" >> "$OUTPUT"
echo "## Directory Structure" >> "$OUTPUT"

EXCLUDE_ARGS=(
    -not -path "*/node_modules/*" -not -path "*/.git/*"
    -not -path "*/dist/*" -not -path "*/__pycache__/*"
    -not -path "*/venv/*" -not -path "*/.next/*"
    -not -path "*/logs/*" -not -path "*/.env*"
    -not -path "*/build-results/*" -not -path "*/repo-queue/*"
    -not -path "*/outputs/*" -not -path "*/archive/*"
    -not -path "*/.claude/*" -not -path "*/chatgpt-mcp/*"
    -not -path "*/.mypy_cache/*" -not -path "*/.pytest_cache/*"
    -not -path "*/coverage/*" -not -path "*/.DS_Store"
)

for dir in "${SCAN_DIRS[@]}"; do
    BASENAME=$(basename "$dir")
    # Skip subdirs of openclaw that are separate SCAN_DIRS entries
    case "$dir" in
        "$HOME/openclaw/"*) continue ;;
    esac
    echo "" >> "$OUTPUT"
    echo "### $BASENAME ($dir)" >> "$OUTPUT"
    echo '```' >> "$OUTPUT"
    if [ "$dir" = "$HOME/openclaw" ]; then
        # For the main openclaw dir, list only directories (too many files)
        find "$dir" -maxdepth $MAX_DEPTH -type d \
            "${EXCLUDE_ARGS[@]}" \
            2>/dev/null | \
            sed "s|$HOME|~|g" | \
            sort >> "$OUTPUT"
    else
        find "$dir" -maxdepth $MAX_DEPTH \
            "${EXCLUDE_ARGS[@]}" \
            \( -type f -o -type d \) \
            2>/dev/null | \
            sed "s|$HOME|~|g" | \
            sort >> "$OUTPUT"
    fi
    echo '```' >> "$OUTPUT"
done

# ── SECTION 3: CLAUDE.md Files ──
echo "" >> "$OUTPUT"
echo "## Project Instructions (CLAUDE.md files)" >> "$OUTPUT"

for dir in "${SCAN_DIRS[@]}"; do
    if [ -f "$dir/CLAUDE.md" ]; then
        REL=$(echo "$dir/CLAUDE.md" | sed "s|$HOME|~|g")
        echo "" >> "$OUTPUT"
        echo "### $REL" >> "$OUTPUT"
        echo '```' >> "$OUTPUT"
        head -c $MAX_README_CHARS "$dir/CLAUDE.md" >> "$OUTPUT"
        echo "" >> "$OUTPUT"
        echo '```' >> "$OUTPUT"
    fi
done

# ── SECTION 4: README Files ──
echo "" >> "$OUTPUT"
echo "## README Files" >> "$OUTPUT"

# Collect all READMEs, deduplicate by realpath
TMPREADMES=$(mktemp)
for dir in "${SCAN_DIRS[@]}"; do
    find "$dir" -maxdepth 2 -name "README.md" \
        -not -path "*/node_modules/*" \
        -not -path "*/.git/*" \
        2>/dev/null
done | sort -u > "$TMPREADMES"

while read -r readme; do
    REL=$(echo "$readme" | sed "s|$HOME|~|g")
    echo "" >> "$OUTPUT"
    echo "### $REL" >> "$OUTPUT"
    echo '```' >> "$OUTPUT"
    head -c $MAX_README_CHARS "$readme" >> "$OUTPUT"
    echo "" >> "$OUTPUT"
    echo '```' >> "$OUTPUT"
done < "$TMPREADMES"
rm -f "$TMPREADMES"

# ── SECTION 5: Tech Stack Fingerprint ──
echo "" >> "$OUTPUT"
echo "## Tech Stack Fingerprint" >> "$OUTPUT"

TMPPKGS=$(mktemp)
for dir in "${SCAN_DIRS[@]}"; do
    find "$dir" -maxdepth 2 \( -name "package.json" -o -name "pyproject.toml" -o -name "requirements.txt" \) \
        -not -path "*/node_modules/*" 2>/dev/null
done | sort -u > "$TMPPKGS"

while read -r pkgfile; do
    REL=$(echo "$pkgfile" | sed "s|$HOME|~|g")
    echo "" >> "$OUTPUT"
    echo "### $REL" >> "$OUTPUT"
    echo '```' >> "$OUTPUT"
    head -c 2000 "$pkgfile" >> "$OUTPUT"
    echo "" >> "$OUTPUT"
    echo '```' >> "$OUTPUT"
done < "$TMPPKGS"
rm -f "$TMPPKGS"

# ── SECTION 6: Git Status Summary ──
echo "" >> "$OUTPUT"
echo "## Git Status" >> "$OUTPUT"

for dir in "${SCAN_DIRS[@]}"; do
    if [ -d "$dir/.git" ]; then
        BASENAME=$(basename "$dir")
        echo "" >> "$OUTPUT"
        echo "### $BASENAME" >> "$OUTPUT"
        echo '```' >> "$OUTPUT"
        (
            cd "$dir"
            echo "Branch: $(git branch --show-current 2>/dev/null)"
            echo "Last commit: $(git log -1 --oneline 2>/dev/null)"
            echo "Uncommitted files: $(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
            echo "Remote: $(git remote get-url origin 2>/dev/null)"
        ) >> "$OUTPUT"
        echo '```' >> "$OUTPUT"
    fi
done

# ── SECTION 7: Active .env filenames (NOT values — safety) ──
echo "" >> "$OUTPUT"
echo "## Environment Files (names only, NO values)" >> "$OUTPUT"
echo '```' >> "$OUTPUT"
for dir in "${SCAN_DIRS[@]}"; do
    find "$dir" -maxdepth 2 -name ".env*" \
        -not -path "*/node_modules/*" \
        2>/dev/null | sed "s|$HOME|~|g"
done >> "$OUTPUT"
echo '```' >> "$OUTPUT"

# ── SECTION 8: Trading State Snapshot ──
echo "" >> "$OUTPUT"
echo "## Trading State (if available)" >> "$OUTPUT"

if [ -f "$HOME/openclaw/trading/dashboard.json" ]; then
    echo "" >> "$OUTPUT"
    echo "### Clawmpson Trading Dashboard" >> "$OUTPUT"
    echo '```json' >> "$OUTPUT"
    head -c 3000 "$HOME/openclaw/trading/dashboard.json" >> "$OUTPUT"
    echo "" >> "$OUTPUT"
    echo '```' >> "$OUTPUT"
fi

echo "" >> "$OUTPUT"
echo "---" >> "$OUTPUT"
echo "End of context. Generated $TIMESTAMP." >> "$OUTPUT"
echo "For live code, use GitHub MCP connector -> github.com/nayslayer143/openclaw" >> "$OUTPUT"

# ── Safety check: no secrets leaked ──
LEAKS=$(grep -cE '(sk-[a-zA-Z0-9]{20}|ghp_[a-zA-Z0-9]{36}|xoxb-|xoxp-|AKIA[A-Z0-9]{16}|password=[^ ]+|token=[^ ]+)' "$OUTPUT" 2>/dev/null)
LEAKS=${LEAKS:-0}
if [ "$LEAKS" -gt 0 ]; then
    echo "WARNING: $LEAKS potential secret patterns found in output. Review before uploading!"
fi

# Report
LINES=$(wc -l < "$OUTPUT")
SIZE=$(wc -c < "$OUTPUT" | awk '{printf "%.1f", $1/1024}')
echo "Context generated: $OUTPUT"
echo "   $LINES lines, ${SIZE}KB"
echo "   Upload to ChatGPT Project or paste into conversation."
