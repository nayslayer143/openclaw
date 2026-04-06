"""
Inspector Gadget — Logic Analyzer (Task 7).

Two-stage analysis of trading bot source code:
  1. Deterministic checks: fast AST/regex scan without LLM
  2. LLM analysis: send source to gemma4:26b-A4B (MoE) at localhost:11434 for logic review

Source is truncated to 8000 chars for LLM calls (documented limitation).
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from inspector.inspector_db import InspectorDB

# ---------------------------------------------------------------------------
# Target files
# ---------------------------------------------------------------------------

TARGET_FILES = [
    "~/openclaw/scripts/mirofish/trading_brain.py",
    "~/openclaw/scripts/mirofish/paper_wallet.py",
    "~/openclaw/scripts/mirofish/polymarket_feed.py",
    "~/openclaw/scripts/trading-bot.py",
]

# ---------------------------------------------------------------------------
# Regex patterns for deterministic checks
# ---------------------------------------------------------------------------

_TODO_RE = re.compile(r"(TODO|FIXME|HACK)", re.IGNORECASE)
_TRADING_CONTEXT_RE = re.compile(r"(pnl|price|trade|wallet|kelly)", re.IGNORECASE)
_TEST_LEAK_RE = re.compile(
    r"(test_price|mock_price|hardcoded|fake_price)\s*=\s*[0-9]",
    re.IGNORECASE,
)

_OLLAMA_URL = "http://localhost:11434/api/chat"
_OLLAMA_MODEL = "gemma4:26b"
_OLLAMA_TIMEOUT = 180
_SOURCE_TRUNCATE = 8000

_LLM_PROMPT = """\
You are an expert code auditor reviewing Python trading bot source code.

Find bugs and logic errors in the following categories:
1. Off-by-one errors in array indexing, loop bounds, or date ranges
2. Rounding errors in P&L, price, or percentage calculations
3. Kelly criterion math errors (wrong formula, missing cap, negative values)
4. Stop-loss or take-profit logic operating on stale/incorrect price data
5. Division-by-zero risks (dividing by balance, price, shares, std dev, etc.)
6. P&L calculation mismatches (exit - entry order wrong, missing fee handling)

For each issue found, respond with a JSON array (and nothing else) using this schema:
[
  {
    "line_number": <int or null>,
    "finding_type": "<short_type>",
    "severity": "<critical|high|medium|low>",
    "description": "<one sentence explanation>",
    "snippet": "<relevant code line or fragment>"
  }
]

If no issues are found, respond with an empty JSON array: []

Source code:
"""


# ---------------------------------------------------------------------------
# LogicAnalyzer
# ---------------------------------------------------------------------------

class LogicAnalyzer:
    def __init__(self, db: InspectorDB, target_files: Optional[List[str]] = None) -> None:
        self.db = db
        self.target_files = target_files or list(TARGET_FILES)

    # ------------------------------------------------------------------
    # Deterministic checks
    # ------------------------------------------------------------------

    def _deterministic_checks(self, filepath: str, source: str) -> List[dict]:
        """
        Scan source for:
          - TODO/FIXME/HACK comments near trading-relevant context → todo_critical/medium
          - Hardcoded test price assignments → test_leak/high

        Returns a list of finding dicts.
        """
        findings: List[dict] = []
        lines = source.splitlines()
        found_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        for i, line in enumerate(lines):
            # --- TODO/FIXME/HACK check ---
            if _TODO_RE.search(line):
                # Check surrounding ±3 lines for trading context
                context_start = max(0, i - 3)
                context_end   = min(len(lines), i + 4)
                context_block = "\n".join(lines[context_start:context_end])
                if _TRADING_CONTEXT_RE.search(context_block):
                    findings.append({
                        "file_path":    filepath,
                        "line_number":  i + 1,
                        "finding_type": "todo_critical",
                        "severity":     "medium",
                        "description":  (
                            f"TODO/FIXME/HACK marker near trading logic "
                            f"at line {i + 1}"
                        ),
                        "snippet":      line.strip()[:200],
                        "found_at":     found_at,
                    })

            # --- Test/hardcoded price leak check ---
            if _TEST_LEAK_RE.search(line):
                findings.append({
                    "file_path":    filepath,
                    "line_number":  i + 1,
                    "finding_type": "test_leak",
                    "severity":     "high",
                    "description":  (
                        f"Hardcoded/mock price value assigned at line {i + 1} "
                        f"— test data may have leaked into production code"
                    ),
                    "snippet":      line.strip()[:200],
                    "found_at":     found_at,
                })

        return findings

    # ------------------------------------------------------------------
    # LLM analysis
    # ------------------------------------------------------------------

    def _llm_analysis(self, filepath: str, source: str) -> List[dict]:
        """
        Send source (truncated to 8000 chars) to gemma4:26b-A4B (MoE) for logic review.

        Returns a list of finding dicts, or a single analysis_error finding
        if Ollama is unavailable or returns an unparseable response.
        """
        truncated = source[:_SOURCE_TRUNCATE]
        found_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        try:
            payload = {
                "model": _OLLAMA_MODEL,
                "stream": False,
                "messages": [
                    {
                        "role": "user",
                        "content": _LLM_PROMPT + truncated,
                    }
                ],
                "options": {"num_ctx": int(os.environ.get("OPENCLAW_NUM_CTX", "16384"))},
            }
            resp = httpx.post(_OLLAMA_URL, json=payload, timeout=_OLLAMA_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            content = data.get("message", {}).get("content", "")

            # Extract JSON array from response (handles markdown code fences etc.)
            match = re.search(r"\[.*\]", content, re.DOTALL)
            if not match:
                return []

            raw_findings = json.loads(match.group(0))
            if not isinstance(raw_findings, list):
                return []

            findings = []
            for item in raw_findings:
                if not isinstance(item, dict):
                    continue
                severity = item.get("severity", "low")
                if severity not in ("critical", "high", "medium", "low"):
                    severity = "low"
                findings.append({
                    "file_path":    filepath,
                    "line_number":  item.get("line_number"),
                    "finding_type": item.get("finding_type", "llm_finding"),
                    "severity":     severity,
                    "description":  item.get("description", ""),
                    "snippet":      str(item.get("snippet", ""))[:200],
                    "found_at":     found_at,
                })
            return findings

        except Exception as exc:
            # Ollama down or response parse failure — return a low-severity flag
            return [{
                "file_path":    filepath,
                "line_number":  None,
                "finding_type": "analysis_error",
                "severity":     "low",
                "description":  f"LLM analysis unavailable: {exc}",
                "snippet":      "",
                "found_at":     found_at,
            }]

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def analyze_file(self, filepath: str) -> List[dict]:
        """
        Expand path, read source, run deterministic + LLM analysis.

        Returns [] if file does not exist.
        """
        path = Path(filepath).expanduser()
        if not path.exists():
            return []

        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return []

        findings = self._deterministic_checks(str(path), source)
        findings.extend(self._llm_analysis(str(path), source))
        return findings

    def run(self) -> dict:
        """
        Analyze all TARGET_FILES, insert findings to code_findings,
        return summary dict.
        """
        total = 0
        by_severity: Dict[str, int] = {}

        for filepath in self.target_files:
            findings = self.analyze_file(filepath)
            for finding in findings:
                try:
                    # Build row — only include columns that exist in the table schema
                    row = {
                        "file_path":    finding.get("file_path"),
                        "line_number":  finding.get("line_number"),
                        "finding_type": finding.get("finding_type"),
                        "severity":     finding.get("severity", "low"),
                        "description":  finding.get("description"),
                        "snippet":      finding.get("snippet"),
                        "found_at":     finding.get("found_at"),
                    }
                    self.db.insert("code_findings", row)
                    sev = finding.get("severity", "low")
                    by_severity[sev] = by_severity.get(sev, 0) + 1
                    total += 1
                except Exception:
                    continue

        return {"total_findings": total, "by_severity": by_severity}
