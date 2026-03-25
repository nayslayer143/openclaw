# Terminal Watch — Claude Code Build Prompt

**Status:** Ready to execute after Phase 5 completion
**Copy everything below the line into Claude Code.**

---

```
# Gonzoclaw Terminal Watch — Build Spec

Read ~/openclaw/ideas/arbclaw-rival-instance-2026-03-23.md for context on why this exists.
Read ~/openclaw/CLAUDE.md and ~/openclaw/CONSTRAINTS.md before writing any code.

## What This Is

A new "Terminal Watch" subsystem inside Gonzoclaw (the existing FastAPI + single-file HTML dashboard at ~/openclaw/dashboard/). It captures terminal output from tmux sessions, detects events (errors, failures, completions), stores them locally, and packages context-rich analysis packets that can be sent to ChatGPT or Claude.

This is NOT a new app. It is new endpoints in dashboard/server.py + a new UI panel in dashboard/index.html + a small relay script.

## Existing Architecture (DO NOT REBUILD)

- Backend: ~/openclaw/dashboard/server.py (FastAPI, ~1105 lines, port 7080)
- Frontend: ~/openclaw/dashboard/index.html (single-file HTML, ~4019 lines, dark terminal aesthetic)
- Auth: JWT + GitHub OAuth (already working)
- Real-time: SSE pattern already exists (see /api/stream and /api/trading/stream)
- DB pattern: SQLite (see clawmson.db usage in the trading endpoints)
- Config: ~/openclaw/dashboard/.env + ~/openclaw/.env
- Tunnel: Cloudflare tunnel "gonzoclaw" → localhost:7080

Extend these. Do not create separate apps, frameworks, or build systems.

## Build 3 Things

### 1. Relay Script: ~/openclaw/scripts/terminal-relay.py

A standalone Python script (NOT inside server.py) that runs as a background process.

Responsibilities:
- Attach to a specified tmux session/pane via tmux capture-pane -p
- Poll every 2 seconds, diff against previous capture
- Strip ANSI escape sequences
- Detect events:
  - command_finished (prompt reappeared after output)
  - error (non-zero exit code, traceback pattern, "Error:", "FAILED", "error:" in output)
  - test_failure ("FAIL", "FAILED", "AssertionError", pytest/jest patterns)
  - build_failure ("Build failed", "SyntaxError", "ModuleNotFoundError", compilation errors)
  - stalled (no output change for 60+ seconds during active command)
  - user_snapshot (triggered via API call from Gonzoclaw UI)
- For each event, write a structured JSON record to ~/openclaw/logs/terminal-watch.jsonl:
  ```json
  {
    "timestamp": "ISO8601",
    "session": "openclaw-dev",
    "pane": "%3",
    "event_type": "error",
    "command": "python scripts/mirofish/simulator.py",
    "exit_code": 1,
    "duration_ms": 4200,
    "cwd": "/Users/jordan/openclaw",
    "branch": "feature/phase-5a",
    "output_tail": ["last 50 lines"],
    "summary": "ImportError in simulator.py line 42"
  }
  ```
- Also maintain a rolling buffer of last 500 lines in memory for snapshot requests
- On startup, write PID to ~/openclaw/logs/terminal-relay.pid (for watchdog integration)

Secret redaction (MANDATORY before any output leaves the script):
- Scan for patterns: API keys (sk-*, key-*, AKIA*), Bearer tokens, JWTs (eyJ*), .env KEY=VALUE patterns, SSH private key headers
- Replace with [REDACTED]
- Load additional redaction patterns from ~/openclaw/.env keys (redact any value that appears in output)

CLI interface:
```
python scripts/terminal-relay.py --session openclaw-dev          # attach to session
python scripts/terminal-relay.py --session openclaw-dev --pane 1 # specific pane
python scripts/terminal-relay.py --list                          # list available tmux sessions
python scripts/terminal-relay.py --stop                          # graceful shutdown via PID file
```

Dependencies: NONE beyond Python stdlib + subprocess calls to tmux and git. No pip installs.

### 2. Backend Endpoints: add to ~/openclaw/dashboard/server.py

Add these endpoints following the existing patterns in server.py (auth, error handling, path conventions):

```
GET  /api/terminal/sessions        → list available tmux sessions/panes
POST /api/terminal/start           → start relay on specified session/pane
POST /api/terminal/stop            → stop relay (kill PID)
GET  /api/terminal/status          → relay running? which session? event count?
GET  /api/terminal/events          → last N events from terminal-watch.jsonl (default 20)
GET  /api/terminal/stream          → SSE stream of new events (follow existing SSE pattern from /api/stream)
POST /api/terminal/snapshot        → trigger manual snapshot, return the packet
POST /api/terminal/packet          → build an analysis packet from last event or specified event_id
GET  /api/terminal/packet/preview  → preview packet before sending (show what would be sent)
```

The /api/terminal/packet endpoint should build a packet like this:
```json
{
  "context": {
    "repo": "openclaw",
    "branch": "feature/phase-5a",
    "cwd": "/Users/jordan/openclaw",
    "session": "openclaw-dev",
    "recent_commands": ["last 5 commands"],
    "git_diff_stat": "output of git diff --stat",
    "changed_files": ["list of modified files"]
  },
  "event": {
    "type": "error",
    "command": "python scripts/mirofish/simulator.py",
    "exit_code": 1,
    "output_tail": ["last 100 lines, redacted"],
    "duration_ms": 4200
  },
  "question": "Explain what failed and suggest a fix."
}
```

Add config constants at the top of server.py with the others:
```python
TERMINAL_RELAY   = OPENCLAW_ROOT / "scripts" / "terminal-relay.py"
TERMINAL_LOG     = LOGS_DIR / "terminal-watch.jsonl"
TERMINAL_PID     = LOGS_DIR / "terminal-relay.pid"
```

### 3. Frontend Panel: add to ~/openclaw/dashboard/index.html

Add a "Terminal Watch" panel to the existing dashboard. Follow the same styling patterns (dark terminal aesthetic, iridescent borders, neon indicators, halftone background).

Panel layout:

TOP BAR:
- Status indicator: OFF (gray) / WATCHING (green pulse) / ERROR (red)
- Session name display (e.g., "openclaw-dev:%0")
- Uptime counter when active

CONTROL ROW (buttons matching existing dashboard button style):
- [Attach] → opens session picker dropdown (fetches /api/terminal/sessions)
- [Start] → POST /api/terminal/start
- [Stop] → POST /api/terminal/stop
- [Snapshot] → POST /api/terminal/snapshot, shows result

EVENT FEED (scrollable, newest on top):
- Show last 20 events from /api/terminal/events
- Live-update via SSE from /api/terminal/stream
- Each event card shows: timestamp, event_type (color-coded), command, exit_code, summary
- Click event → expands to show output_tail

PACKET SECTION (bottom):
- [Preview Packet] → GET /api/terminal/packet/preview, shows formatted packet
- [Copy for ChatGPT] → copies packet to clipboard with "Analyze this terminal output:" prefix
- [Copy for Claude] → copies packet to clipboard with context-appropriate prefix
- [Copy for Both] → copies packet formatted for easy paste into either
- Optional text input: "Add your question:" (appended to packet's question field)

TOGGLE ROW:
- [ ] Auto-snapshot on error
- [ ] Include git diff
- [ ] Include recent command history
- [ ] Errors only (filter event feed)

Quick action button (prominent, centered):
- [Explain What Just Happened] → builds packet from most recent event + last 100 lines + git context, copies to clipboard

All toggles and preferences should persist in a JS object (NOT localStorage — use in-memory state, same pattern as rest of index.html).

## Integration Points

- Add Terminal Watch to the cron-tunnel-watchdog.sh: if relay PID exists but process is dead, clean up PID file
- Add terminal-relay.py to the "DO NOT REBUILD" list mentally — once built, extend only

## What NOT To Build
- No API integrations to OpenAI or Anthropic (clipboard-first, API routing is Phase 2)
- No side-by-side comparison view yet
- No auto-execute suggested commands
- No separate database — use the JSONL log file, it's enough for Phase 1
- No npm, no React, no build step — match the existing vanilla JS pattern
- No new Python dependencies beyond stdlib

## Testing
- Verify relay attaches to a tmux session and captures output
- Verify ANSI stripping produces clean text
- Verify secret redaction catches API keys and .env values
- Verify events appear in the dashboard via SSE
- Verify packet generation includes git context
- Verify clipboard copy works on both desktop and mobile Safari
- Run from ~/openclaw/dashboard/: python server.py — confirm Terminal Watch panel renders

## Line Budget
- terminal-relay.py: 300 lines max
- New server.py endpoints: 200 lines max (added to existing file)
- New index.html panel: 400 lines max (added to existing file)
- Total new code: under 900 lines
```
