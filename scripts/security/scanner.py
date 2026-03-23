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
