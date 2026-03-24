#!/usr/bin/env python3
"""Terminal Watch relay — captures tmux output, detects events, logs to JSONL."""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
OPENCLAW_ROOT = Path.home() / "openclaw"
LOGS_DIR = OPENCLAW_ROOT / "logs"
LOG_FILE = LOGS_DIR / "terminal-watch.jsonl"
PID_FILE = LOGS_DIR / "terminal-relay.pid"
ENV_FILE = OPENCLAW_ROOT / ".env"
POLL_INTERVAL = 2
STALL_TIMEOUT = 60
BUFFER_SIZE = 500
TAIL_SIZE = 50

# ── ANSI stripping ───────────────────────────────────────────────────────────
_ANSI_RE = re.compile(
    r"\x1b\[[0-9;]*[a-zA-Z]"       # CSI sequences (colors, cursor)
    r"|\x1b\].*?\x07"              # OSC sequences (title sets)
    r"|\x1b[()][AB012]"            # Character set selection
    r"|\x1b\[\??[0-9;]*[hl]"      # Mode set/reset
)


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


# ── Secret redaction ─────────────────────────────────────────────────────────
_SECRET_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),
    re.compile(r"key-[a-zA-Z0-9]{20,}"),
    re.compile(r"AKIA[A-Z0-9]{16}"),
    re.compile(r"Bearer\s+[a-zA-Z0-9._\-]+"),
    re.compile(r"eyJ[a-zA-Z0-9._\-]+"),
    re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----"),
]
_KEY_VALUE_RE = re.compile(
    r"([A-Z_]*(?:KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL)[A-Z_]*)=\S+"
)


def load_env_values() -> list:
    values = []
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                _, v = line.split("=", 1)
                v = v.strip().strip('"').strip("'")
                if len(v) >= 8:
                    values.append(v)
    return values


def redact_secrets(text: str, env_values: list = None) -> str:
    for pat in _SECRET_PATTERNS:
        text = pat.sub("[REDACTED]", text)
    text = _KEY_VALUE_RE.sub(r"\1=[REDACTED]", text)
    if env_values:
        for val in env_values:
            if len(val) >= 8 and val in text:
                text = text.replace(val, "[REDACTED]")
    return text


# ── Event detection ──────────────────────────────────────────────────────────
_ERROR_PATTERNS = [
    re.compile(r"Traceback \(most recent call last\)", re.IGNORECASE),
    re.compile(r"^Error:", re.MULTILINE),
    re.compile(r"^error:", re.MULTILINE),
    re.compile(r"FAILED"),
    re.compile(r"Exception:"),
]
_TEST_FAILURE_PATTERNS = [
    re.compile(r"FAIL(?:ED)?\s"),
    re.compile(r"Assert(?:ion)?Error"),
    re.compile(r"pytest.*failed", re.IGNORECASE),
    re.compile(r"FAILURES"),
    re.compile(r"Tests:\s+\d+\s+failed", re.IGNORECASE),
]
_BUILD_FAILURE_PATTERNS = [
    re.compile(r"Build failed", re.IGNORECASE),
    re.compile(r"SyntaxError:"),
    re.compile(r"ModuleNotFoundError:"),
    re.compile(r"ImportError:"),
    re.compile(r"compil(?:ation|er)?\s+error", re.IGNORECASE),
]


def detect_event_type(output: str) -> str | None:
    for p in _BUILD_FAILURE_PATTERNS:
        if p.search(output):
            return "build_failure"
    for p in _TEST_FAILURE_PATTERNS:
        if p.search(output):
            return "test_failure"
    for p in _ERROR_PATTERNS:
        if p.search(output):
            return "error"
    return None


def extract_summary(output: str, event_type: str) -> str:
    lines = output.strip().splitlines()
    if not lines:
        return ""
    if event_type in ("error", "build_failure"):
        for line in reversed(lines):
            if any(kw in line for kw in ("Error", "Exception", "FAILED", "failed")):
                return line.strip()[:200]
    if event_type == "test_failure":
        for line in reversed(lines):
            if any(kw in line for kw in ("FAIL", "assert", "Assert", "failed")):
                return line.strip()[:200]
    return lines[-1].strip()[:200]
