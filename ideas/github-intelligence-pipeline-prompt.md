# GitHub Intelligence Pipeline — Claude Code Build Prompt

**Status:** Ready to execute after Phase 5 completion
**Copy everything below the line into Claude Code.**

---

```
# GitHub Intelligence Pipeline — Build Spec

Read ~/openclaw/CLAUDE.md and ~/openclaw/CONSTRAINTS.md before writing any code.
Read ~/openclaw/scripts/github_crawler.py — this is the existing crawler, already working.
Read ~/openclaw/dashboard/server.py — understand existing endpoint patterns, auth, SSE, and ideas API.
Read ~/openclaw/dashboard/index.html — understand existing UI patterns, panel layouts, button styles.

## What This Is

A continuous GitHub repo intelligence pipeline that:
1. Crawls GitHub on a schedule (cron, zero AI tokens)
2. Runs results through a local Ollama LLM for analysis (zero API tokens)
3. Surfaces recommendations on a Gonzoclaw dashboard page for Jordan to review
4. On approval, auto-dispatches implementation tasks to Claude Code, targeted at specific trading bot(s)

This is NOT a one-shot scanner. It is a persistent intelligence layer inside OpenClaw.

## Architecture Overview

```
Cron (every 6 hours)
  → github_crawler.py --trading-only --min-stars 300 --readmes --output ~/openclaw/autoresearch/outputs/datasets/crawl
  → results land as CSV + JSON in autoresearch/outputs/datasets/

Cron (after crawl completes)
  → repo_analyst.py reads latest crawl JSON
  → sends each repo to Ollama (qwen3:30b — research/planning model per CLAUDE.md)
  → LLM scores: integration_value (1-10), complexity (1-10), relevance per bot, risk assessment
  → writes structured recommendations to ~/openclaw/autoresearch/github-intel/recommendations.json
  → new recommendations trigger SSE event to Gonzoclaw

Gonzoclaw /intel page
  → shows recommendation cards with LLM analysis
  → Jordan reviews: Approve / Reject / Bookmark
  → on Approve: select target bot(s) → dispatches task to queue

Queue → Claude Code
  → approved tasks land in ~/openclaw/queue/pending.json (existing pattern)
  → task includes: repo URL, LLM analysis, target bot(s), implementation brief
  → Claude Code picks up task, implements, opens PR
  → Jordan reviews PR as final gate
```

## The 3 Trading Bots (targets for upgrades)

1. **Clawmpson** — ~/openclaw/scripts/mirofish/ + ~/openclaw/scripts/trading-bot.py (main trading system: 4-strategy brain + fast scanner, 5 feeds, SQLite, graduation engine)
2. **ArbClaw** — ~/arbclaw/ (lean single-strategy arb detector, 5-min cycle, 3 files — not yet built, include as target option anyway)
3. **RivalClaw** — ~/rivalclaw/ (Chad's rival instance: 8-strategy quant engine + hedge engine, Polymarket + Kalshi + CoinGecko feeds, self-tuner, graduation gates, separate SQLite DB — fully independent repo/DB/state)

When Jordan approves a recommendation, they pick which bot(s) get the upgrade: Clawmpson, ArbClaw, RivalClaw, or any combination.

## Build 4 Things

### 1. Repo Analyst Script: ~/openclaw/scripts/repo_analyst.py

Standalone Python script that reads crawler output and generates LLM-scored recommendations.

Input: latest crawl JSON from ~/openclaw/autoresearch/outputs/datasets/
Output: ~/openclaw/autoresearch/github-intel/recommendations.json

For each repo in the top 40 by signal_score, send to Ollama:

```python
prompt = f"""You are a trading systems architect reviewing open-source repos for potential integration into a prediction market trading bot stack.

The stack has 3 bots:
- Clawmpson: main trading system with 4 strategies (arb, price-lag, momentum, LLM), 5 feeds, graduation engine (Python, 10+ modules, SQLite)
- ArbClaw: lean single-strategy arb detector, 5-min cycle (Python, 3 files, not yet built)
- RivalClaw: Chad's rival instance at ~/rivalclaw/ — 8-strategy quant engine + hedge engine, Polymarket + Kalshi + CoinGecko, self-tuner, own SQLite DB

Repo: {repo['name']}
URL: {repo['url']}
Stars: {repo['stars']} | Forks: {repo['forks']} | Language: {repo['language']}
Last updated: {repo['last_updated']}
Description: {repo['description']}
Topics: {repo['topics']}
README snippet: {repo['readme_snippet']}

Score this repo:
1. integration_value (1-10): how useful would integrating patterns/code from this repo be?
2. complexity (1-10): how hard is the integration? (1=drop-in, 10=massive refactor)
3. clawmpson_relevance (1-10): relevance to Clawmpson (main multi-strategy system)
4. arbclaw_relevance (1-10): relevance to ArbClaw (lean arb detector)
5. rivalclaw_relevance (1-10): relevance to RivalClaw (rival strategy comparison)
6. what_to_take: 1-2 sentence description of what specifically to extract/integrate
7. risk: any risks or concerns (license, maintenance, complexity)
8. verdict: INTEGRATE / STUDY / SKIP

Respond in JSON only, no markdown."""
```

Call Ollama via HTTP (localhost:11434/api/generate, model: qwen3:30b).
Parse the JSON response. Write to recommendations.json with this structure:

```json
{
  "crawl_date": "2026-03-24",
  "analyzed_at": "2026-03-24T04:00:00",
  "model": "qwen3:30b",
  "total_analyzed": 40,
  "recommendations": [
    {
      "id": "uuid",
      "repo_name": "hummingbot/hummingbot",
      "repo_url": "https://github.com/hummingbot/hummingbot",
      "stars": 17821,
      "language": "Python",
      "signal_score": 1.249,
      "integration_value": 8,
      "complexity": 7,
      "clawmpson_relevance": 9,
      "arbclaw_relevance": 8,
      "rivalclaw_relevance": 6,
      "what_to_take": "Market making strategy patterns and cross-exchange arb detection logic",
      "risk": "Large codebase, GPL license may conflict",
      "verdict": "STUDY",
      "status": "pending",
      "approved_for": [],
      "approved_at": null,
      "task_id": null
    }
  ]
}
```

CLI:
```
python repo_analyst.py                          # analyze latest crawl
python repo_analyst.py --crawl-file path.json   # analyze specific crawl
python repo_analyst.py --top 20                 # only top N repos (default 40)
python repo_analyst.py --model qwen3:30b        # specify model (default qwen3:30b)
```

Dependencies: NONE beyond stdlib. Ollama is called via urllib (HTTP to localhost:11434).
Must handle: Ollama not running (skip gracefully), malformed LLM responses (retry once, then mark as "analysis_failed"), rate limiting (1 req/sec to Ollama).

### 2. Cron Setup: ~/openclaw/scripts/github-intel-cron.sh

Shell script that runs the full pipeline:

```bash
#!/bin/bash
# GitHub Intelligence Pipeline — runs every 6 hours
# Crontab: 0 */6 * * * ~/openclaw/scripts/github-intel-cron.sh

OPENCLAW=~/openclaw
LOG=$OPENCLAW/logs/github-intel.log
DATASET_DIR=$OPENCLAW/autoresearch/outputs/datasets

echo "[$(date -Iseconds)] Starting GitHub Intelligence crawl" >> $LOG

# Step 1: Run crawler (no tokens needed, just GitHub API)
cd $OPENCLAW
python3 scripts/github_crawler.py \
  --trading-only \
  --min-stars 300 \
  --readmes \
  --output $DATASET_DIR/crawl \
  >> $LOG 2>&1

# Step 2: Run analyst (uses local Ollama, zero API cost)
LATEST_JSON=$(ls -t $DATASET_DIR/crawl_*.json 2>/dev/null | head -1)
if [ -n "$LATEST_JSON" ]; then
  python3 scripts/repo_analyst.py --crawl-file "$LATEST_JSON" >> $LOG 2>&1
  echo "[$(date -Iseconds)] Analysis complete" >> $LOG
else
  echo "[$(date -Iseconds)] No crawl output found" >> $LOG
fi
```

Also provide the crontab line and launchctl plist for macOS.

### 3. Backend Endpoints: add to ~/openclaw/dashboard/server.py

Add these endpoints following existing patterns (auth, error handling, etc.):

```
GET  /api/intel                     → latest recommendations (from recommendations.json)
GET  /api/intel/history             → list of past crawl dates with counts
GET  /api/intel/repo/{id}           → full detail for one recommendation
POST /api/intel/approve             → approve recommendation, select target bot(s)
POST /api/intel/reject              → reject recommendation (mark as "rejected")
POST /api/intel/bookmark            → bookmark for later review
POST /api/intel/run-crawl           → trigger crawl + analysis manually (fire-and-forget)
GET  /api/intel/stream              → SSE stream for new recommendations
GET  /api/intel/stats               → aggregate stats (total crawled, approved, rejected, pending)
```

**POST /api/intel/approve** body:
```json
{
  "id": "recommendation-uuid",
  "targets": ["clawmpson", "arbclaw", "rivalclaw"],
  "notes": "optional jordan notes"
}
```

On approve:
1. Update recommendation status to "approved", set approved_for and approved_at
2. Generate a task and add to ~/openclaw/queue/pending.json:
```json
{
  "id": "task-uuid",
  "type": "github-intel-integration",
  "title": "Integrate [what_to_take] from [repo_name]",
  "description": "LLM analysis + repo details + jordan's notes",
  "source_repo": "https://github.com/...",
  "targets": ["clawmpson", "arbclaw"],
  "priority": "medium",
  "status": "pending",
  "created_at": "ISO8601",
  "approved_by": "jordan",
  "recommendation_id": "rec-uuid"
}
```
3. Link task_id back to the recommendation

Add config constants at top of server.py:
```python
INTEL_DIR        = OPENCLAW_ROOT / "autoresearch" / "github-intel"
INTEL_RECS       = INTEL_DIR / "recommendations.json"
INTEL_CRAWL_SCRIPT = OPENCLAW_ROOT / "scripts" / "github-intel-cron.sh"
```

### 4. Frontend Panel: add "Intel" page to ~/openclaw/dashboard/index.html

Add a new navigable section/page called "Intel" to the existing dashboard. Follow existing styling (dark terminal aesthetic, iridescent borders, neon indicators).

**Top Stats Bar:**
- Total repos crawled (lifetime)
- Pending review count (badge, highlighted if > 0)
- Approved count
- Last crawl timestamp
- [Run Crawl Now] button → POST /api/intel/run-crawl

**Filter/Sort Bar:**
- Filter: All | INTEGRATE | STUDY | SKIP | Pending | Approved | Rejected | Bookmarked
- Sort: Signal Score | Integration Value | Complexity | Stars | Recency
- Language filter dropdown

**Recommendation Cards (scrollable list):**
Each card shows:
- Repo name + link (opens in new tab)
- Stars / Language / Last updated
- Signal score badge + Integration value badge + Complexity badge
- LLM verdict: INTEGRATE (green) / STUDY (yellow) / SKIP (gray)
- what_to_take text (the key insight)
- Relevance bars: Clawmpson [█████] 9/10 | ArbClaw [████░] 8/10 | RivalClaw [███░░] 6/10
- risk text (collapsible)
- README snippet (collapsible)

**Card Actions:**
- [Approve] → opens target selector:
  - Checkboxes: ☐ Clawmpson  ☐ ArbClaw  ☐ RivalClaw
  - Optional notes text input
  - [Confirm & Dispatch] → POST /api/intel/approve
- [Reject] → POST /api/intel/reject (with optional reason)
- [Bookmark] → POST /api/intel/bookmark
- [View on GitHub] → opens repo URL

**Approved Items Section (bottom):**
- List of approved recommendations with target bot tags
- Status: Queued → In Progress → Implemented
- Link to task in queue

**Target Bot Selector UX:**
When Jordan clicks Approve, show a mini-modal or inline expansion:
```
┌─────────────────────────────────────┐
│ Deploy to:                          │
│  ☐ Clawmpson (main system)         │
│  ☐ ArbClaw (lean arb)             │
│  ☐ RivalClaw (rival instance)     │
│                                     │
│ Notes: [________________]           │
│                                     │
│ [Confirm & Dispatch]  [Cancel]      │
└─────────────────────────────────────┘
```

**Navigation:**
Add "Intel" to the existing nav/tab system in index.html. Should be accessible as a tab or route alongside existing dashboard views.

## Integration Points

- github-intel-cron.sh should be added to cron-tunnel-watchdog.sh awareness (log if it hasn't run in 12+ hours)
- Approved tasks use the SAME queue format as existing ~/openclaw/queue/pending.json tasks
- SSE events for new recommendations should use the existing SSE pattern from /api/stream
- The /api/intel/run-crawl endpoint should subprocess the cron script (fire-and-forget, return immediately)

## What NOT To Build
- No auto-implementation without Jordan's approval — every integration goes through the Gonzoclaw review page
- No external API calls for analysis — Ollama only (qwen3:30b, localhost:11434)
- No new databases — use JSON files (recommendations.json, pending.json)
- No new frameworks — extend existing FastAPI + vanilla JS
- No GitHub token management UI — token is set via env var
- Don't touch the crawler scoring logic — it works, extend the analyst layer instead

## File Budget
- repo_analyst.py: 250 lines max
- github-intel-cron.sh: 30 lines max
- New server.py endpoints: 200 lines max
- New index.html Intel page: 500 lines max
- Total new code: under 1000 lines

## Testing
- Verify repo_analyst.py handles Ollama being offline (graceful skip)
- Verify repo_analyst.py handles malformed LLM responses (retry + fallback)
- Verify /api/intel returns recommendations sorted by integration_value
- Verify /api/intel/approve creates task in pending.json with correct format
- Verify Intel page renders recommendation cards with all fields
- Verify target selector allows 1, 2, or all 3 bots
- Verify SSE stream pushes new recommendation events
- Run from ~/openclaw/dashboard/: python server.py — confirm Intel page accessible

## Data Flow Diagram

```
github_crawler.py (cron, 4x daily)
    ↓ CSV + JSON
autoresearch/outputs/datasets/crawl_*.json
    ↓ read by
repo_analyst.py (cron, after crawl)
    ↓ Ollama qwen3:30b analysis
autoresearch/github-intel/recommendations.json
    ↓ served by
/api/intel → Gonzoclaw Intel page
    ↓ Jordan approves, picks targets
/api/intel/approve → queue/pending.json
    ↓ Claude Code picks up task
Implementation PR → Jordan reviews → merge
```
```
