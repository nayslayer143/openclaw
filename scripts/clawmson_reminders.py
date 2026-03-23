#!/usr/bin/env python3
from __future__ import annotations
"""
Clawmson reminder scheduler.
Parses natural-language reminder requests, stores them, fires them via Telegram.

Usage:
  parse_reminder("remind me at 9am to check the brief") -> stores reminder
  check_and_fire(chat_id, send_fn) -> called every 60s in a background thread
"""

import json
import re
import time
import datetime
from pathlib import Path
from typing import Optional

REMINDERS_FILE = Path.home() / "openclaw" / "memory" / "reminders.json"


# ── Storage ──────────────────────────────────────────────────────────────────

def _load() -> list:
    if REMINDERS_FILE.exists():
        try:
            return json.loads(REMINDERS_FILE.read_text())
        except Exception:
            pass
    return []


def _save(reminders: list):
    REMINDERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    REMINDERS_FILE.write_text(json.dumps(reminders, indent=2))


# ── Time parser ───────────────────────────────────────────────────────────────

def _parse_time(text: str) -> Optional[datetime.datetime]:
    """
    Parse natural-language time expressions. Returns a future datetime or None.
    Handles:
      - "in 30 minutes", "in 2 hours", "in 1 hour 30 minutes"
      - "at 9am", "at 9:30pm", "at 14:00"
      - "tomorrow at 9am"
      - "in 5 mins"
    """
    now = datetime.datetime.now()
    text_l = text.lower().strip()

    # "in X minutes/hours"
    in_match = re.search(
        r'in\s+(?:(\d+)\s*h(?:ours?)?)?\s*(?:(\d+)\s*m(?:ins?|inutes?)?)?',
        text_l
    )
    if in_match and (in_match.group(1) or in_match.group(2)):
        hours = int(in_match.group(1) or 0)
        mins  = int(in_match.group(2) or 0)
        if hours or mins:
            return now + datetime.timedelta(hours=hours, minutes=mins)

    # "at HH:MM" or "at Xam/pm"
    at_match = re.search(
        r'at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?',
        text_l
    )
    if at_match:
        hour   = int(at_match.group(1))
        minute = int(at_match.group(2) or 0)
        ampm   = at_match.group(3)
        if ampm == "pm" and hour != 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0

        tomorrow = "tomorrow" in text_l
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if tomorrow or target <= now:
            target += datetime.timedelta(days=1)
        return target

    return None


def _parse_message(text: str) -> str:
    """
    Strip the timing portion from the reminder text to get just the message.

    Handles both forms:
      "remind me at 9am to check the brief"  -> "check the brief"
      "at 9am to check the brief"            -> "check the brief"  (after /remind strips prefix)
      "in 30 minutes to do the thing"        -> "do the thing"
    """
    t = text.strip()
    # Strip "remind me" prefix if present
    t = re.sub(r'^remind\s+me\s+', '', t, flags=re.IGNORECASE).strip()
    # Strip time expressions: "at HH[:MM][am/pm]", "in N hours/minutes", "tomorrow at ..."
    t = re.sub(
        r'^(?:tomorrow\s+)?(?:at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?|in\s+\d+\s*(?:hours?|h|minutes?|mins?|m)(?:\s+\d+\s*(?:minutes?|mins?|m))?)\s*',
        '', t, flags=re.IGNORECASE
    ).strip()
    # Strip leading "to "
    t = re.sub(r'^to\s+', '', t, flags=re.IGNORECASE).strip()
    return t or text.strip()


# ── Public API ────────────────────────────────────────────────────────────────

def add_reminder(chat_id: str, text: str) -> str:
    """
    Parse and store a reminder from natural language.
    Returns a confirmation string for Telegram, or an error message.
    """
    fire_at = _parse_time(text)
    if not fire_at:
        return (
            "Couldn't parse the time. Try:\n"
            "  /remind in 30 minutes to check the queue\n"
            "  /remind at 9am to review idea brief\n"
            "  /remind tomorrow at 8am to check emails"
        )

    message = _parse_message(text)
    reminders = _load()
    reminders.append({
        "chat_id": chat_id,
        "message": message,
        "fire_at": fire_at.isoformat(),
        "created_at": datetime.datetime.now().isoformat(),
        "fired": False,
    })
    _save(reminders)

    # Human-readable confirmation
    now = datetime.datetime.now()
    delta = fire_at - now
    total_mins = int(delta.total_seconds() / 60)
    if total_mins < 60:
        when_str = f"in {total_mins} min" + ("s" if total_mins != 1 else "")
    elif total_mins < 1440:
        when_str = fire_at.strftime("at %-I:%M %p")
    else:
        when_str = fire_at.strftime("tomorrow at %-I:%M %p")

    return f"Got it. I'll remind you {when_str}: {message}"


def list_reminders(chat_id: str) -> str:
    """Return a formatted list of pending reminders for this chat."""
    reminders = [r for r in _load()
                 if r.get("chat_id") == chat_id and not r.get("fired")]
    if not reminders:
        return "No pending reminders."
    lines = ["Pending reminders:"]
    for r in sorted(reminders, key=lambda x: x["fire_at"]):
        fire_at = datetime.datetime.fromisoformat(r["fire_at"])
        lines.append(f"  {fire_at.strftime('%-I:%M %p')} — {r['message']}")
    return "\n".join(lines)


def clear_reminders(chat_id: str) -> str:
    """Clear all pending reminders for this chat."""
    reminders = _load()
    remaining = [r for r in reminders if r.get("chat_id") != chat_id]
    _save(remaining)
    cleared = len(reminders) - len(remaining)
    return f"Cleared {cleared} reminder(s)."


def check_and_fire(send_fn) -> int:
    """
    Check for due reminders and fire them. Call this every 60s.
    send_fn(chat_id, text) — the Telegram send function.
    Returns number of reminders fired.
    """
    now = datetime.datetime.now()
    reminders = _load()
    fired_count = 0

    for r in reminders:
        if r.get("fired"):
            continue
        fire_at = datetime.datetime.fromisoformat(r["fire_at"])
        if fire_at <= now:
            try:
                send_fn(r["chat_id"], f"Reminder: {r['message']}")
                r["fired"] = True
                fired_count += 1
            except Exception as e:
                print(f"[reminders] Failed to send reminder: {e}")

    if fired_count:
        _save(reminders)

    return fired_count
