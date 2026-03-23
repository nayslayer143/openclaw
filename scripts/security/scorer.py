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

# source_url prefixes that earn a trust bonus.
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
