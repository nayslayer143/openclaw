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
                pass
            else:
                break

    return caps if caps else None
