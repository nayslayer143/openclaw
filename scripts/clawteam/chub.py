#!/usr/bin/env python3
"""
chub.py — FORGE context injection via chub CLI.
Detects library references in prompts and prepends verified API docs.
Never raises. Returns "" on any failure.
"""
from __future__ import annotations
import json
import re
import subprocess

_BLOCKLIST = {
    "python", "code", "function", "data", "file", "string", "list", "dict",
    "api", "json", "http", "re", "os", "io", "sys", "time", "math", "csv",
    "abc", "ast", "uuid", "enum", "copy", "ssl", "xml", "url", "app", "sql",
    "log", "cli", "db",
}

_PATTERNS = [
    r'`([^`]+)`',                                        # `library`
    r'\bimport\s+(\w+)',                                 # import X
    r'\bfrom\s+(\w+)\s+import',                         # from X import
    r'\busing\s+(\w+)',                                  # using X
    r'\bwith\s+(?:the\s+)?(\w+)\s+[Aa][Pp][Ii]',       # with X API
    r'\b(?:call|use)\s+(\w+)',                           # call X / use X
]

_DOC_CAP = 3000


def _extract_candidates(prompt: str) -> list[str]:
    """
    Extract up to 3 valid library candidate names from prompt.
    Pipeline: deduplicate → filter (shape + length + blocklist) → cap at 3.
    """
    seen: list[str] = []
    seen_set: set[str] = set()
    for pattern in _PATTERNS:
        for match in re.finditer(pattern, prompt):
            name = match.group(1)
            if name not in seen_set:
                seen.append(name)
                seen_set.add(name)

    filtered = []
    for c in seen:
        if not re.match(r'^[\w][\w.\-]*$', c):   # shape: no spaces, valid chars
            continue
        if len(c) < 4:                             # min length: block os, re, io
            continue
        if c.lower() in _BLOCKLIST:               # blocklist: common false positives
            continue
        filtered.append(c)

    return filtered[:3]
