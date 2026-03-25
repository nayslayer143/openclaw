# ChatGPT Context Layer — Claude Code Build Prompt

**Status:** Ready to execute.
**Goal:** Give Chad (ChatGPT web/app, $20 Plus) persistent knowledge of all OpenClaw repos, local file structure, and trading bot ecosystem so he can do research and strategy without constant re-uploading.
**Copy everything below the line into Claude Code.**

---

```
# ChatGPT Context Layer — Build Spec

Read ~/openclaw/CLAUDE.md before writing any code.

## What This Is

A context generation system that keeps ChatGPT (web interface, Plus account) informed about the full OpenClaw ecosystem — repos, file structures, trading bots, active builds, and project state. Three layers:

1. A local script that auto-generates a master context file from the real directory structure
2. A ChatGPT Project system prompt tuned to the OpenClaw ecosystem
3. A cron job that keeps the context fresh

This is NOT an API integration (that already exists at ~/openclaw/chatgpt-mcp/). This is about the ChatGPT web/app experience when Jordan chats with Chad directly.

## The 3 Trading Bots + Their Paths

1. **Clawmpson** — ~/openclaw/ (main system: 4-strategy brain + scanner, 5 feeds, SQLite, graduation engine, 13 agents, 14 Lobster workflows)
2. **ArbClaw** — ~/arbclaw/ (lean arb experiment, not yet built)
3. **RivalClaw** — ~/rivalclaw/ (Chad's instance: 8-strategy quant engine + hedge engine, self-tuner, Polymarket + Kalshi + CoinGecko, own SQLite DB)

## Other Active Projects on This Machine

Check for and include any of these if they exist:
- ~/doctor-claw/ or ~/openclaw/doctor-claw/ (AI medical app, Next.js)
- ~/punch-my-baby/ or ~/openclaw/punch-my-baby/ (document processing app, Next.js)
- ~/shiny-new/ or ~/openclaw/shiny-new/ (creative web experiences)
- ~/cinema-lab/ or ~/openclaw/cinema-lab/ (cinematic web build pipeline)

## Build 3 Things

### 1. Context Generator Script: ~/openclaw/scripts/generate-chad-context.sh

Shell script that scans the real directories and outputs a single consolidated context file.

```bash
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
         "$HOME/doctor-claw" "$HOME/punch-my-baby" "$HOME/shiny-new"; do
    [ -d "$d" ] && SCAN_DIRS+=("$d")
done

MAX_DEPTH=3
MAX_README_CHARS=3000

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

for dir in "${SCAN_DIRS[@]}"; do
    BASENAME=$(basename "$dir")
    echo "" >> "$OUTPUT"
    echo "### $BASENAME ($dir)" >> "$OUTPUT"
    echo '```' >> "$OUTPUT"
    find "$dir" -maxdepth $MAX_DEPTH \
        -not -path "*/node_modules/*" \
        -not -path "*/.git/*" \
        -not -path "*/dist/*" \
        -not -path "*/__pycache__/*" \
        -not -path "*/venv/*" \
        -not -path "*/.next/*" \
        -not -path "*/logs/*" \
        -not -path "*/.env*" \
        -type f \
        2>/dev/null | \
        sed "s|$HOME|~|g" | \
        sort >> "$OUTPUT"
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

for dir in "${SCAN_DIRS[@]}"; do
    find "$dir" -maxdepth 2 -name "README.md" \
        -not -path "*/node_modules/*" \
        -not -path "*/.git/*" \
        2>/dev/null | while read -r readme; do
        REL=$(echo "$readme" | sed "s|$HOME|~|g")
        echo "" >> "$OUTPUT"
        echo "### $REL" >> "$OUTPUT"
        echo '```' >> "$OUTPUT"
        head -c $MAX_README_CHARS "$readme" >> "$OUTPUT"
        echo "" >> "$OUTPUT"
        echo '```' >> "$OUTPUT"
    done
done

# ── SECTION 5: Tech Stack Fingerprint ──
echo "" >> "$OUTPUT"
echo "## Tech Stack Fingerprint" >> "$OUTPUT"

for dir in "${SCAN_DIRS[@]}"; do
    for pkgfile in $(find "$dir" -maxdepth 2 \( -name "package.json" -o -name "pyproject.toml" -o -name "requirements.txt" \) \
        -not -path "*/node_modules/*" 2>/dev/null); do
        REL=$(echo "$pkgfile" | sed "s|$HOME|~|g")
        echo "" >> "$OUTPUT"
        echo "### $REL" >> "$OUTPUT"
        echo '```' >> "$OUTPUT"
        head -c 2000 "$pkgfile" >> "$OUTPUT"
        echo "" >> "$OUTPUT"
        echo '```' >> "$OUTPUT"
    done
done

# ── SECTION 6: Git Status Summary ──
echo "" >> "$OUTPUT"
echo "## Git Status" >> "$OUTPUT"

for dir in "${SCAN_DIRS[@]}"; do
    if [ -d "$dir/.git" ]; then
        BASENAME=$(basename "$dir")
        echo "" >> "$OUTPUT"
        echo "### $BASENAME" >> "$OUTPUT"
        echo '```' >> "$OUTPUT"
        cd "$dir"
        echo "Branch: $(git branch --show-current 2>/dev/null)" >> "$OUTPUT"
        echo "Last commit: $(git log -1 --oneline 2>/dev/null)" >> "$OUTPUT"
        echo "Uncommitted files: $(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')" >> "$OUTPUT"
        echo "Remote: $(git remote get-url origin 2>/dev/null)" >> "$OUTPUT"
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
echo "For live code, use GitHub MCP connector → github.com/nayslayer143/openclaw" >> "$OUTPUT"

# Report
LINES=$(wc -l < "$OUTPUT")
SIZE=$(wc -c < "$OUTPUT" | awk '{printf "%.1f", $1/1024}')
echo "✅ Context generated: $OUTPUT"
echo "   $LINES lines, ${SIZE}KB"
echo "   Upload to ChatGPT Project or paste into conversation."
```

Make executable and add alias:
```bash
chmod +x ~/openclaw/scripts/generate-chad-context.sh
# Add alias to ~/.zshrc
grep -q 'chad-context' ~/.zshrc || echo 'alias chad-context="bash ~/openclaw/scripts/generate-chad-context.sh"' >> ~/.zshrc
```

### 2. ChatGPT Project System Prompt: ~/openclaw/outputs/chatgpt-project-instructions.md

Generate this file. Jordan will paste it into ChatGPT → Project → Edit → Project Instructions.

```markdown
You are Chad, a strategic research and architecture partner for Jordan (JMM),
working alongside Claude (who handles all code execution via Claude Code).

ROLE DIVISION:
- Chad (you): Strategy, research, architecture proposals, market analysis, competitive intelligence
- Claude: Code execution, implementation, file management, testing, deployment
- Jordan: Final approval on all decisions, Tier-3 gate for anything touching live systems

TRADING BOT ECOSYSTEM:
Three bots compete head-to-head. Jordan compares performance across all three.

1. Clawmpson (~/openclaw/) — Jordan's primary build, Claude-built
   - 4 strategies: single-venue arb, price-lag crypto arb, momentum, LLM analysis
   - 5 feeds: Polymarket (gamma API), Kalshi (REST v2), Unusual Whales, Crucix OSINT (29 sources), spot prices (Binance + Coinbase)
   - SQLite DB (clawmson.db), 8 tables, graduation engine (14 days, Sharpe >1.0, win rate >55%)
   - 13 agent configs, 14 Lobster workflows, FastAPI dashboard (Gonzoclaw)
   - Phase 5 complete, paper trading active

2. RivalClaw (~/rivalclaw/) — Your build, Chad-built
   - 8-strategy quant engine + hedge engine
   - 3 feeds: Polymarket, Kalshi (RSA auth), CoinGecko spot
   - Self-tuner (daily parameter optimization), graduation gates
   - Own SQLite DB (rivalclaw.db), daily reports
   - Strategy Lab being installed (bounded self-improvement system)

3. ArbClaw (~/arbclaw/) — Planned, not yet built
   - Lean single-strategy arb detector, 5-min cycle
   - Tests whether Clawmpson's complexity introduces execution lag
   - Target: 3 files, <500 lines total

INFRASTRUCTURE:
- Machine: M2 Max MacBook Pro, 96GB RAM
- 14 local Ollama models (~264GB storage), zero API cost for inference
- Gonzoclaw dashboard: FastAPI + HTML at https://www.asdfghjk.lol (Cloudflare tunnel)
- GitHub: github.com/nayslayer143/openclaw (Clawmpson), rivalclaw is separate
- Budget: $10/day hard cap on external API costs
- Approval tiers: Tier 1 (auto), Tier 2 (hold for Telegram DM), Tier 3 (explicit confirm)

OTHER ACTIVE PROJECTS:
- Doctor Claw: AI medical/diagnostic app (Next.js, Supabase)
- Punch My Baby: Document processing + feature building (Next.js, Stripe)
- SHINY.NEW: Creative web experiences (Three.js, GSAP, WebGL)
- Cinema Lab: Cinematic web build pipeline (tiered prompt system)

WHEN DOING RESEARCH FOR JORDAN:
1. Use the GitHub connector to check latest code state before making assumptions
2. Treat the MASTER-CONTEXT file (CHAD-CONTEXT.md) as the filesystem map
3. Remember: apparent edge ≠ executable edge ≠ realized edge
4. Strategy proposals should be concrete enough to turn into Claude Code prompts
5. Parked ideas live in ~/openclaw/ideas/ — check before proposing something that was already considered
6. DO NOT REBUILD existing systems — always extend, integrate, or patch
7. Cross-pollinate across projects when opportunities arise

KEY FILES TO REFERENCE:
- ~/openclaw/CLAUDE.md — Clawmpson project instructions + system map
- ~/openclaw/openclaw-v4.2-strategy.md — frozen strategy doc with phase plan
- ~/openclaw/CONSTRAINTS.md — non-negotiable operational rules
- ~/rivalclaw/CLAUDE.md — RivalClaw project instructions
- ~/openclaw/ideas/ — parked ideas (ArbClaw, Moltbook, RivalClaw v2, Strategy Lab, GitHub Intel Pipeline, Terminal Watch)

NAMING:
- "Chad" = you (ChatGPT)
- "Claude" = Claude Code / Cowork (the builder)
- "Clawmpson" or "Peter" = the main OpenClaw trading system
- "RivalClaw" = your rival trading instance
- "Gonzoclaw" = the web dashboard
- "Jordan" or "JMM" = the human in charge

Jordan signs off as "JMM" or "Jordan."
```

### 3. Cron: auto-refresh context daily

Add to crontab or launchctl:
```bash
# Refresh Chad's context every morning at 6am
0 6 * * * /bin/bash ~/openclaw/scripts/generate-chad-context.sh >> ~/openclaw/logs/chad-context.log 2>&1
```

## GitHub MCP Connector Setup (for ChatGPT Plus)

Provide Jordan with these step-by-step instructions as a separate output file ~/openclaw/outputs/chatgpt-github-setup.md:

1. Open ChatGPT → Settings → Connected apps (or Apps & Connectors)
2. Look for GitHub integration — ChatGPT Plus ($20) supports this
3. Click Connect → Authenticate with GitHub (nayslayer143)
4. Grant access to repos: openclaw (at minimum), or all repos
5. Once connected, Chad can browse repo files, read code, and search across repos on demand
6. Verify by asking Chad: "Using the GitHub connector, show me the file tree of nayslayer143/openclaw"

If the GitHub connector is not available in ChatGPT's current UI (it may be under a different name or behind a feature flag), document that and suggest alternatives:
- Alternative A: Upload CHAD-CONTEXT.md to a ChatGPT Project as a pinned file (20 file limit on Plus)
- Alternative B: Use the existing ~/openclaw/chatgpt-mcp/ API bridge for programmatic access
- Alternative C: Copy-paste the context at the start of each session

## What NOT To Do
- Do NOT put secrets, API keys, or .env values in the context file — filenames only
- Do NOT include raw database contents or trading state with real positions
- Do NOT scan node_modules, .git, venv, __pycache__, dist, .next
- Do NOT make the context file >50KB — ChatGPT will truncate it
- Do NOT modify any existing OpenClaw files — this is additive only

## Testing
- Run generate-chad-context.sh and verify output exists at ~/openclaw/outputs/CHAD-CONTEXT.md
- Verify it includes directory trees for openclaw and rivalclaw
- Verify it includes CLAUDE.md content for both projects
- Verify no secrets appear in the output (grep for 'sk-', 'ghp_', 'key', 'token', 'password')
- Verify file size is under 50KB
- Upload to ChatGPT and ask Chad: "What trading bots does Jordan run and what are their differences?" — verify Chad can answer from the context

## Line Budget
- generate-chad-context.sh: 150 lines max (it's a shell script, keep it clean)
- chatgpt-project-instructions.md: the system prompt above, as-is
- chatgpt-github-setup.md: 30 lines of setup instructions
- Total: under 200 lines of new content
```
