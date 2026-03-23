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
    # English stop-words / programming filler (picked up by call/use/using patterns)
    "this", "that", "your", "case", "each", "then", "what", "some",
    "have", "will", "them", "they", "best", "just", "when", "make",
    "into", "more", "here", "next", "most", "such", "only", "very",
    "even", "back", "take", "want", "both", "give", "know", "like",
    "call", "with", "test", "type", "name", "path", "mode", "args",
    "size", "text", "port", "user", "send", "read", "load", "save",
    "open", "line", "docs", "func", "main", "base", "core", "util",
    "from", "also", "show", "work", "tell", "move", "live",
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
        if c.startswith('__'):                     # dunder names (__future__, __init__)
            continue
        if len(c) < 4:                             # min length: block os, re, io
            continue
        if c.lower() in _BLOCKLIST:               # blocklist: common false positives
            continue
        filtered.append(c)

    return filtered[:3]


def _lookup_chub(candidate: str) -> str:
    """
    Search chub registry for candidate. Returns formatted doc string or "".
    Uses check=False — non-zero exit codes are handled by inspecting returncode.
    """
    search = subprocess.run(
        ["chub", "search", candidate, "--json"],
        capture_output=True, timeout=3, check=False,
    )
    if search.returncode != 0:
        return ""
    try:
        data = json.loads(search.stdout)
    except json.JSONDecodeError:
        return ""
    if not isinstance(data, list) or not data:
        return ""
    top = data[0]
    name = top.get("name", "")
    if not (
        name.lower() == candidate.lower()
        or (name.lower().startswith(candidate.lower()) and len(candidate) >= 4)
    ):
        return ""
    result_id = top.get("id") or name or candidate
    doc = subprocess.run(
        ["chub", "get", result_id, "--lang", "py"],
        capture_output=True, timeout=5, check=False,
    )
    if doc.returncode != 0:
        return ""
    body = doc.stdout.decode("utf-8", errors="replace")[:_DOC_CAP]
    return f"[API DOCS: {result_id}]\n{body}"


def fetch_chub_context(prompt: str) -> str:
    """
    Detect library references in prompt, fetch docs via chub CLI.
    Returns "[API DOCS: {id}]\n{docs}" on success, "" on any failure.
    Never raises.
    """
    try:
        candidates = _extract_candidates(prompt)
        for candidate in candidates:
            doc = _lookup_chub(candidate)
            if doc:
                return doc
        return ""
    except Exception:
        return ""
