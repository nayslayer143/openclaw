# Security Auditor Agent

**Role:** Automated security gate for skills and MCP tools loaded into OpenClaw/Clawmson.

**Model:** `qwen3:30b` (debate engine) · `qwen3:32b` (fallback)

**Entry point:** `~/openclaw/scripts/skill_auditor.py`

**Module layout:**
```
scripts/security/
  scanner.py   — static analysis (7 pattern categories, SKILL.md capability check)
  scorer.py    — 0-100 trust score → TRUSTED/REVIEW/BLOCKED
  registry.py  — skill_registry table in ~/.openclaw/clawmson.db
  debate.py    — 3-agent Ollama debate for REVIEW-range skills
  reporter.py  — markdown audit reports
  auditor.py   — orchestrator
```

**Scan patterns:**

| Category | Severity |
|---|---|
| obfuscation (eval/exec/compile/base64) | CRITICAL |
| exfiltration (non-localhost POST/PUT) | CRITICAL |
| shell_injection (os.system, shell=True) | HIGH |
| network (import requests/urllib/httpx) | HIGH |
| credential_access (.env, os.environ, token vars) | MEDIUM |
| filesystem_write (open w, Path.write_*) | MEDIUM |
| dependency_risk (pip install in code) | MEDIUM |

**Trust scoring:**
- Start 100. CRITICAL −35, HIGH −15, MEDIUM −8, SKILL.md mismatch −20.
- Trust bonus +10 for verified `source_url` matching known-good prefix (source_url only — never path).
- TRUSTED ≥80, REVIEW 50–79, BLOCKED <50.

**Skill detection:** On-demand only. Cron scans `~/openclaw/skills/incoming/` daily.

**Directories:**
- `~/openclaw/skills/incoming/` — drop zone (unaudited)
- `~/openclaw/skills/active/` — TRUSTED or Jordan-approved
- `~/openclaw/skills/rejected/` — BLOCKED
- `~/openclaw/security/audits/` — markdown reports

**Telegram commands:**
- `/audit <name>` — run audit
- `/skills` — list registry
- `/approve <name>` — approve REVIEW skill (re-verifies hash before moving to active/)
- `/block <name>` — block a skill

**Cron integration:**
Add to `cron-nightly.sh`:
```bash
python3 ~/openclaw/scripts/skill_auditor.py verify
python3 ~/openclaw/scripts/skill_auditor.py summary
```
Add to daily scan cron:
```bash
python3 ~/openclaw/scripts/skill_auditor.py mcp
```

**Known limitation:** Hash verification runs on daily cron + at approval time. No loader hook at Python import level — deferred to future phase.
