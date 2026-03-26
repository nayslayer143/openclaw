"""
Inspector Gadget — Repo Scanner (Task 8).

Scan git history for suspicious changes to trading logic files that
coincide with performance anomalies.

Looks for:
  - Recent commits (last 7 days by default) touching critical files
  - Added lines in those commits that match SUSPICIOUS_PATTERNS
    (retroactive P&L edits, balance rewrites, etc.)

Findings written to code_findings table in inspector_gadget.db.
"""

from __future__ import annotations

import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from inspector.inspector_db import InspectorDB

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path("~/openclaw").expanduser()

CRITICAL_FILES = [
    "scripts/mirofish/paper_wallet.py",
    "scripts/mirofish/trading_brain.py",
    "scripts/trading-bot.py",
]

SUSPICIOUS_PATTERNS = [
    r'pnl\s*=',
    r'exit_price\s*=',
    r'closed_win',
    r'closed_loss',
    r'balance\s*=',
]

_COMPILED_PATTERNS = [re.compile(p) for p in SUSPICIOUS_PATTERNS]


# ---------------------------------------------------------------------------
# RepoScanner
# ---------------------------------------------------------------------------

class RepoScanner:
    def __init__(self, db: InspectorDB) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Git helpers
    # ------------------------------------------------------------------

    def _git(self, *args) -> str:
        """
        Run git -C {repo_root} {args} with a 30-second timeout.
        Returns stdout as a string. Returns "" on any error.
        """
        try:
            result = subprocess.run(
                ["git", "-C", str(REPO_ROOT)] + list(args),
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.stdout
        except Exception:
            return ""

    def _get_recent_commits(self, days: int = 7) -> list:
        """
        Return commits from the last N days that touch any CRITICAL_FILES.

        Uses: git log --since="{days} days ago" --format="%H|%ai|%s" -- <files>

        Returns list of {"hash": str, "date": str, "message": str}.
        """
        since_arg = f"{days} days ago"
        output = self._git(
            "log",
            f"--since={since_arg}",
            "--format=%H|%ai|%s",
            "--",
            *CRITICAL_FILES,
        )

        commits = []
        for line in output.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("|", 2)
            if len(parts) < 3:
                continue
            commits.append({
                "hash":    parts[0].strip(),
                "date":    parts[1].strip(),
                "message": parts[2].strip(),
            })
        return commits

    def _check_commit_diff(self, commit_hash: str, filepath: str) -> list:
        """
        Run git show {commit_hash} -- {filepath} and check each added line
        (lines starting with '+' but not '+++') against SUSPICIOUS_PATTERNS.

        Returns a list of finding dicts with type retroactive_pnl_change/high.
        """
        output = self._git("show", commit_hash, "--", filepath)
        if not output:
            return []

        findings = []
        found_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        lines = output.splitlines()

        for i, line in enumerate(lines):
            # Only look at added lines ('+' prefix, not '+++ b/...' header)
            if not line.startswith("+") or line.startswith("+++"):
                continue

            code_line = line[1:]  # strip leading '+'
            for pattern in _COMPILED_PATTERNS:
                if pattern.search(code_line):
                    findings.append({
                        "file_path":    filepath,
                        "line_number":  i + 1,   # line number within diff output
                        "finding_type": "retroactive_pnl_change",
                        "severity":     "high",
                        "description":  (
                            f"Commit {commit_hash[:8]} modifies trading-critical "
                            f"field matching pattern '{pattern.pattern}' in {filepath}"
                        ),
                        "snippet":      code_line.strip()[:200],
                        "found_at":     found_at,
                    })
                    break  # one finding per line — avoid duplicate patterns

        return findings

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self) -> dict:
        """
        Scan recent commits across all CRITICAL_FILES, insert findings to
        code_findings, and return a summary dict.
        """
        commits = self._get_recent_commits()
        total_findings = 0

        for commit in commits:
            for filepath in CRITICAL_FILES:
                try:
                    findings = self._check_commit_diff(commit["hash"], filepath)
                    for finding in findings:
                        try:
                            self.db.insert("code_findings", finding)
                            total_findings += 1
                        except Exception:
                            continue
                except Exception:
                    continue

        return {
            "commits_scanned": len(commits),
            "findings": total_findings,
        }
