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
