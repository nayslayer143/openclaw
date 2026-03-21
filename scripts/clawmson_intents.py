#!/usr/bin/env python3
from __future__ import annotations
"""
Clawmson intent classifier.
Primary: LLM-based classification via local Ollama (qwen2.5:7b).
Fallback: regex/keyword matching if Ollama is unreachable.
Media (images/audio/docs) is handled upstream before classify() is called.
"""

import os
import re
import json
import requests

# ── Intent constants ─────────────────────────────────────────────────────────

CONVERSATION     = "CONVERSATION"
BUILD_TASK       = "BUILD_TASK"
REFERENCE_INGEST = "REFERENCE_INGEST"
STATUS_QUERY     = "STATUS_QUERY"
DIRECT_COMMAND   = "DIRECT_COMMAND"
UNCLEAR          = "UNCLEAR"

_VALID_INTENTS = {CONVERSATION, BUILD_TASK, REFERENCE_INGEST, STATUS_QUERY,
                  DIRECT_COMMAND, UNCLEAR}

# ── Config ───────────────────────────────────────────────────────────────────

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
CLASSIFY_MODEL  = os.environ.get("OLLAMA_CHAT_MODEL", "qwen2.5:7b")

_URL_RE = re.compile(r'https?://[^\s]+')

_CLASSIFY_SYSTEM_PROMPT = """\
You are an intent classifier for a Telegram bot. Given a user message (and optionally \
recent conversation context), return a JSON object with these fields:

- intent: one of BUILD_TASK, REFERENCE_INGEST, STATUS_QUERY, DIRECT_COMMAND, CONVERSATION, UNCLEAR
- project: detected project name or null
- action: the parsed verb (build, fix, check, study, etc.) or null
- target: what to act on (e.g. "contact form", "gonzoclaw site") or null
- attachments: list of URLs found in the message
- needs_clarification: true if the message is too vague to act on confidently
- suggested_question: a single short clarifying question if needs_clarification is true, else null
- confidence: float 0-1

Intent definitions:
- BUILD_TASK: user wants code written, deployed, fixed, refactored, committed, tested, or merged
- REFERENCE_INGEST: user is sharing a link or resource to study/save/remember (not a build task)
- STATUS_QUERY: user is asking about build status, queue, progress, what's running
- DIRECT_COMMAND: user wants a system command run (disk space, memory, uptime, ollama status, etc.)
- CONVERSATION: general chat, questions, discussion — not a task
- UNCLEAR: message is too ambiguous to classify — needs a follow-up question

Return ONLY valid JSON. No markdown, no explanation."""

# ── URL helpers ──────────────────────────────────────────────────────────────

def has_url(text: str) -> bool:
    return bool(_URL_RE.search(text))


def extract_urls(text: str) -> list:
    return _URL_RE.findall(text)


# ── LLM classifier ──────────────────────────────────────────────────────────

def classify_intent_llm(text: str, history=None) -> dict:
    """
    Send message + recent context to qwen2.5:7b for intent classification.
    Returns parsed dict with intent, project, action, target, etc.
    Raises on failure so caller can fall back to regex.
    """
    messages = [{"role": "system", "content": _CLASSIFY_SYSTEM_PROMPT}]

    # Include last 3 messages for context if available
    if history:
        for entry in history[-3:]:
            role = entry.get("role", "user")
            content = entry.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": text})

    resp = requests.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json={"model": CLASSIFY_MODEL, "messages": messages, "stream": False,
              "format": "json"},
        timeout=30
    )
    resp.raise_for_status()
    raw = resp.json().get("message", {}).get("content", "")
    result = json.loads(raw)

    # Normalize intent to our constants
    intent = result.get("intent", "CONVERSATION").upper()
    if intent not in _VALID_INTENTS:
        intent = CONVERSATION
    result["intent"] = intent

    # Ensure all expected fields exist
    result.setdefault("project", None)
    result.setdefault("action", None)
    result.setdefault("target", None)
    result.setdefault("attachments", extract_urls(text))
    result.setdefault("needs_clarification", False)
    result.setdefault("suggested_question", None)
    result.setdefault("confidence", 0.5)

    return result


# ── Regex fallback classifier ────────────────────────────────────────────────

_BUILD_STARTS = (
    "build ", "deploy ", "fix the ", "push ", "implement ",
    "refactor ", "add a test", "write a script", "write a function",
    "create a feature", "create a function", "create a class",
    "create a module", "create an endpoint", "add an endpoint",
    "add rate limit", "add input valid", "patch ", "update the code",
    "commit ", "revert ", "migrate ",
)

_BUILD_CONTAINS = (
    "fix the code", "push to", "deploy to", "merge branch",
    "open a pr", "create a pr", "write tests for", "add tests for",
    "update the ", "refactor the ",
)

_STATUS_KEYWORDS = (
    "status", "queue", "what's running", "any updates", "progress",
    "how's it going", "what are you doing", "build result",
    "last build", "recent build", "what did you", "done yet",
    "finished yet", "still running",
)

_REF_KEYWORDS = (
    "study this", "read this", "remember this", "save this",
    "store this", "ingest this", "bookmark this", "save the link",
    "add this to your memory",
)


def _classify_regex(text: str) -> dict:
    """Regex/keyword fallback. Returns same dict shape as LLM classifier."""
    lower = text.lower().strip()
    intent = CONVERSATION
    action = None

    for kw in _REF_KEYWORDS:
        if kw in lower:
            intent, action = REFERENCE_INGEST, kw.split()[0]
            break

    if intent == CONVERSATION and has_url(text):
        intent = REFERENCE_INGEST

    if intent == CONVERSATION:
        for kw in _STATUS_KEYWORDS:
            if kw in lower:
                intent, action = STATUS_QUERY, "check"
                break

    if intent == CONVERSATION:
        for trigger in SAFE_COMMANDS:
            if trigger in lower:
                intent, action = DIRECT_COMMAND, "run"
                break

    if intent == CONVERSATION:
        for prefix in _BUILD_STARTS:
            if lower.startswith(prefix):
                intent, action = BUILD_TASK, prefix.strip()
                break

    if intent == CONVERSATION:
        for phrase in _BUILD_CONTAINS:
            if phrase in lower:
                intent, action = BUILD_TASK, phrase.split()[0]
                break

    if intent == CONVERSATION:
        words = text.split()
        if len(words) > 12 and any(
            kw in lower for kw in ("endpoint", "function", "class", "module",
                                   "route", "api", "file", "the repo", "the codebase")
        ):
            intent, action = BUILD_TASK, "build"

    return {
        "intent": intent,
        "project": None,
        "action": action,
        "target": None,
        "attachments": extract_urls(text),
        "needs_clarification": False,
        "suggested_question": None,
        "confidence": 0.7 if intent != CONVERSATION else 0.5,
        "_source": "regex_fallback"
    }


# ── Public API ───────────────────────────────────────────────────────────────

def classify(text: str, history=None) -> dict:
    """
    Classify intent using LLM, falling back to regex on failure.
    Returns dict with intent, project, action, target, attachments,
    needs_clarification, suggested_question, confidence.
    """
    try:
        result = classify_intent_llm(text, history=history)
        result["_source"] = "llm"
        return result
    except Exception as e:
        print(f"[intents] LLM classify failed ({e}), using regex fallback")
        return _classify_regex(text)


def classify_simple(text: str) -> str:
    """Legacy compat — returns just the intent string."""
    return classify(text).get("intent", CONVERSATION)


# ── Safe commands (unchanged) ────────────────────────────────────────────────

SAFE_COMMANDS: dict = {
    "check disk space":   "df -h",
    "disk usage":         "df -h",
    "memory usage":       "free -h",
    "latest commit":      "git -C ~/openclaw log -1 --oneline",
    "uptime":             "uptime",
    "who am i":           "whoami",
    "running processes":  "ps aux | head -20",
    "system info":        "uname -a",
    "show logs":          "tail -n 30 /tmp/openclaw-dispatcher.log 2>/dev/null || echo 'no log'",
    "ollama models":      "ollama list",
    "ollama status":      "pgrep -x ollama && echo 'running' || echo 'not running'",
}


def get_safe_command(text: str):
    """Return shell command string if text matches a safe command, else None."""
    lower = text.lower().strip()
    for trigger, cmd in SAFE_COMMANDS.items():
        if trigger in lower:
            return cmd
    return None
