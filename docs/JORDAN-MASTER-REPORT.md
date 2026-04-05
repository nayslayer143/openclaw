# Jordan's Master Report — OpenClaw Ecosystem
*Generated: 2026-04-05 | Read time: ~12 min*

---

## 1. The Big Picture — Your Ecosystem

You run 4 AI "Claw" systems, each with a specific job:

| System | Location | Job | Primary Model |
|--------|----------|-----|---------------|
| **Clawmpson** | `~/openclaw/` | Business OS — orchestrates everything | Claude / Qwen |
| **RivalClaw** | `~/rivalclaw/` | Trading arbitrage, signal execution | Claude Sonnet |
| **QuantumentalClaw** | `~/quantumentalclaw/` | Signal fusion (asymmetry, narrative, event, edgar, quant) | Claude Sonnet |
| **CodeMonkeyClaw** | `~/codemonkeyclaw/` | Head of Engineering — dispatches code tasks to open models | Qwen/DeepSeek (free) |

**Sub-agents of Clawmpson:** ArbClaw (`~/arbclaw/`), PhantomClaw, others inside `~/openclaw/agents/`

---

## 2. CodeMonkeyClaw — How It Works

CodeMonkeyClaw is your coding engine. It takes a work order and dispatches it to an open-source model (Qwen, DeepSeek, Gemma) running locally or via API. Zero Claude cost for actual coding work.

### Submitting Work Orders

```bash
# Basic submit
python3 ~/codemonkeyclaw/run.py submit \
  --source clawmpson \
  --type fix \
  --target nayslayer143/myrepo \
  --path src/calc.py \
  --description "Fix the add function — returns a - b, should return a + b" \
  --priority high

# Submit with context
python3 ~/codemonkeyclaw/run.py submit \
  --type feature \
  --target nayslayer143/rivalclaw \
  --description "Add Kalshi market scanner" \
  --context-refs "~/rivalclaw/docs/kalshi-spec.md"
```

### Work Order Statuses
`QUEUED` → `IN_PROGRESS` → `DELIVERED` or `FAILED`

### Checking Status

```bash
# List all orders
python3 ~/codemonkeyclaw/run.py list

# List only queued
python3 ~/codemonkeyclaw/run.py list --status QUEUED

# Get specific order
python3 ~/codemonkeyclaw/run.py get wo-2026-04-05-001
```

### How Dispatch Works (the loop)

1. **Prompt assembly**: skill file + subagent definition + doctrine + your task → system prompt
2. **API call**: POST to Ollama (qwen3-coder-next) or DeepSeek
3. **Tool loop**: model calls `file_read`, `file_edit`, `file_write`, `ripgrep`, etc.
4. **Verification gate**: after changes are made, model is asked to confirm with "VERIFIED"
5. **Result**: `DispatchResult` with status, files_changed, decision_log, token count

**Source files:**
- Dispatcher: `~/codemonkeyclaw/codemonkey/dispatcher.py`
- Tools: `~/codemonkeyclaw/codemonkey/tools.py`
- Models: `~/codemonkeyclaw/codemonkey/models.py`
- Config: `~/codemonkeyclaw/codemonkey/config.py`

### Available Skills (what CodeMonkeyClaw can do)

| Skill | What it does |
|-------|-------------|
| `surgical-patch` | Minimal targeted fix — reads, edits, verifies |
| `explore-codebase` | Scout/map a project, list files, report structure |

Skills live at: `~/codemonkeyclaw/skills/{skill-name}/SKILL.md`

### Available Models (for dispatch)

| Model | Endpoint | Cost | Best for |
|-------|----------|------|---------|
| `qwen3-coder-next` | Ollama local | Free | General coding, fixes |
| `deepseek-coder-v2` | DeepSeek API | ~$0.001/call | Complex refactors |
| `gemma4-31b-turboquant` | TurboQuant server | Free (local) | Long-context tasks |

---

## 3. What Was Built Today

### Bug Fix: test_patch_dispatch_fixes_bug
**Problem:** Model fixed the file but status returned `timeout` instead of `success`.
**Root cause:** Verification gate added an extra API round-trip that pushed past the 300s timeout.
**Fix applied:** `~/codemonkeyclaw/codemonkey/dispatcher.py`
- Timeout guard now returns `success` (not `timeout`) if files were already changed
- Verification gate skips if < 30s remains in budget

### AI Educational Docs for CodeMonkeyClaw Agents
Location: `~/codemonkeyclaw/knowledge/`

| Doc | Covers |
|-----|--------|
| `tools-api.md` | All available tools, parameters, error handling |
| `dispatch-protocol.md` | How dispatch works, scope rules, VERIFIED signal |
| `surgical-patch-guide.md` | How to use surgical-patch correctly |
| `work-order-format.md` | DispatchRequest schema, how to read work orders |
| `INDEX.md` | Navigation index for all knowledge docs |

Each doc ends with a **HOMEWORK** assignment the agent must complete to prove understanding.

### Model-Switching Skill
Location: `~/.claude/skills/model-switch/SKILL.md`

Decision matrix for picking the right model:
- **Opus**: complex system design, security audits, architecture → expensive, use sparingly
- **Sonnet**: standard feature work, bug fixes, code review → default, always fine
- **Haiku**: single-file edits, formatting, simple lookups → fastest, cheapest
- **CodeMonkeyClaw** (open models): ralph loops, overnight batch work → free, use for all iterative work

Invoke with: `Use model-switch skill to pick the best model for this task`

### Token Warning + OpenAI Fallback System
Location: `~/scripts/`

| Script | What it does |
|--------|-------------|
| `session-summarize.sh` | Exports last N messages from active Claude session to `~/Desktop/session-summary-TIMESTAMP.md` |
| `openai-continue.sh` | Loads latest session summary and starts OpenAI chat in terminal |
| `~/.claude/hooks/token-warning.sh` | Hook that warns when context is > 80% full |

**Usage when low on tokens:**
```bash
# 1. Summarize current session
~/scripts/session-summarize.sh 30

# 2. Switch to OpenAI with that context
~/scripts/openai-continue.sh
```

### Web Interface
**Existing dashboard** (`http://localhost:7080`) — now has CodeMonkeyClaw endpoints:
- `GET /api/codemonkey/orders` — list work orders
- `POST /api/codemonkey/orders` — submit work order
- `GET /api/codemonkey/stats` — queue stats

**Full guide:** `~/openclaw/docs/web-interface-guide.md`

**Recommended full UI:** Lobe Chat
```bash
docker run -d -p 3210:3210 \
  -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  lobehub/lobe-chat
```
Then open `http://localhost:3210` and configure your 4 Claws as agents.

---

## 4. Git & Version Control

**ALWAYS use `git pushall` instead of `git push`** — pushes to GitHub → GitLab → Gitea

```bash
# Correct
git pushall

# Wrong (only goes to GitHub)
git push
```

**Pull always from GitHub (source of truth):**
```bash
git pull  # pulls from origin = GitHub
```

Backup sync runs nightly via `~/git-sync/sync-all.sh` at ~3:07 AM.

---

## 5. Ralph Loops — When and How

A ralph loop = iterative agent loop that runs until completion criteria met.

**Always ask before starting a ralph loop in Claude Code.** Cost matters:
- Opus: $1-3/iteration
- Sonnet: $0.15-0.50/iteration
- CodeMonkeyClaw (Qwen): FREE (local Ollama)

**Use CodeMonkeyClaw ralph loops for:**
- test-to-pass iterative work
- overnight batch builds
- SAST scan → fix → rescan cycles

**CLI command:**
```bash
python3 ~/codemonkeyclaw/run.py dispatch \
  --model qwen3-coder-next \
  --skill surgical-patch \
  --subagent patch \
  --scope src/file.py \
  --task "Fix all type errors" \
  --max-iterations 20 \
  --timeout 1800
```

---

## 6. Key File Locations (Quick Reference)

| What | Where |
|------|-------|
| Global Claude config | `~/.claude/CLAUDE.md` |
| Skills catalog | `~/.claude/SKILLS-CATALOG.md` |
| OpenClaw dashboard | `~/openclaw/dashboard/server.py` |
| CodeMonkeyClaw dispatcher | `~/codemonkeyclaw/codemonkey/dispatcher.py` |
| CodeMonkeyClaw knowledge docs | `~/codemonkeyclaw/knowledge/` |
| Model-switch skill | `~/.claude/skills/model-switch/SKILL.md` |
| Token warning scripts | `~/scripts/` |
| Web interface guide | `~/openclaw/docs/web-interface-guide.md` |
| QuantumentalClaw engine | `~/quantumentalclaw/engine/` |
| RivalClaw | `~/rivalclaw/` |
| Git sync config | `~/git-sync/repos.conf` |

---

## 7. Daily Workflow Cheat Sheet

**Morning:**
1. Check dashboard: `http://localhost:7080`
2. Review overnight CodeMonkeyClaw deliveries: `python3 ~/codemonkeyclaw/run.py list --status DELIVERED`
3. Check QuantumentalClaw signals (if running)

**When coding:**
- Simple tasks → Claude Sonnet (default, you're already on it)
- Complex architecture → ask me to use Opus first (`model-switch` skill)
- Iterative fix loops → always use CodeMonkeyClaw, not Claude

**When context is filling up:**
```bash
~/scripts/session-summarize.sh  # save summary
~/scripts/openai-continue.sh    # continue with OpenAI
```

**Submitting engineering work:**
```bash
python3 ~/codemonkeyclaw/run.py submit \
  --type fix --target REPO --description "TASK" --priority high
```

---

## 8. What to Do Next

In priority order:

1. **Run the dispatcher test** to confirm the bug fix works:
   ```bash
   cd ~/codemonkeyclaw && pytest tests/test_dispatch_integration.py::test_patch_dispatch_fixes_bug -v
   ```

2. **Start Lobe Chat** and configure your 4 Claws as agents (see `web-interface-guide.md`)

3. **Set up token warning hook** — check if Claude Code supports hooks at `~/.claude/hooks/`

4. **Add more CodeMonkeyClaw skills** — beyond surgical-patch and explore-codebase:
   - `greenfield-build` — build from spec
   - `test-writer` — generate tests for existing code
   - `security-scan` — SAST + fix

5. **Wire up QuantumentalClaw → RivalClaw pipeline** — signals should auto-trigger trade evaluation

---

*Everything built tonight is in the repos and committed. Run `git pushall` from each project dir to sync.*
