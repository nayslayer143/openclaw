#!/usr/bin/env python3
"""
claude-usage-tracker.py — Track Claude Code token usage from session transcripts.
Returns JSON with usage stats for the current billing period.
"""
import json, os
from pathlib import Path
from datetime import datetime, timedelta

CLAUDE_DIR = Path.home() / ".claude"
PROJECTS_DIR = CLAUDE_DIR / "projects"

# Claude Code Max plan limits (configurable)
# Max plan: ~$200/mo, roughly 45M output tokens or equivalent per 5h window
# These are approximate - Claude doesn't publish exact limits
# The 5-hour rolling window is the real constraint
USAGE_CONFIG = CLAUDE_DIR / "usage-config.json"

def load_config():
    defaults = {
        "plan": "max",  # pro | max
        "billing_day": 1,  # day of month billing resets
        "window_hours": 5,  # rolling window for rate limits
    }
    if USAGE_CONFIG.exists():
        try:
            cfg = json.loads(USAGE_CONFIG.read_text())
            defaults.update(cfg)
        except:
            pass
    return defaults

def get_billing_period(billing_day):
    """Return (start, end) of current billing period."""
    now = datetime.now()
    if now.day >= billing_day:
        start = now.replace(day=billing_day, hour=0, minute=0, second=0, microsecond=0)
        if now.month == 12:
            end = start.replace(year=now.year+1, month=1)
        else:
            end = start.replace(month=now.month+1)
    else:
        if now.month == 1:
            start = now.replace(year=now.year-1, month=12, day=billing_day, hour=0, minute=0, second=0, microsecond=0)
        else:
            start = now.replace(month=now.month-1, day=billing_day, hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(day=billing_day, hour=0, minute=0, second=0, microsecond=0)
    return start, end

def scan_sessions(since):
    """Scan all session JSONL files modified since `since` datetime."""
    totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read": 0,
        "cache_create": 0,
        "sessions": 0,
        "messages": 0,
    }
    window_totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read": 0,
        "cache_create": 0,
        "messages": 0,
    }
    window_start = datetime.now() - timedelta(hours=5)

    if not PROJECTS_DIR.exists():
        return totals, window_totals

    since_ts = since.timestamp()

    for project in PROJECTS_DIR.iterdir():
        if not project.is_dir():
            continue
        for f in project.glob("*.jsonl"):
            try:
                if f.stat().st_mtime < since_ts:
                    continue
            except:
                continue

            totals["sessions"] += 1
            with open(f) as fh:
                for line in fh:
                    try:
                        d = json.loads(line)
                        if d.get("type") == "assistant" and "message" in d:
                            u = d["message"].get("usage", {})
                            inp = u.get("input_tokens", 0)
                            out = u.get("output_tokens", 0)
                            cr = u.get("cache_read_input_tokens", 0)
                            cc = u.get("cache_creation_input_tokens", 0)

                            totals["input_tokens"] += inp
                            totals["output_tokens"] += out
                            totals["cache_read"] += cr
                            totals["cache_create"] += cc
                            totals["messages"] += 1

                            # Check if this message is in the 5h window
                            ts = d.get("timestamp") or d["message"].get("created_at")
                            if ts:
                                try:
                                    if isinstance(ts, (int, float)):
                                        msg_time = datetime.fromtimestamp(ts / 1000 if ts > 1e12 else ts)
                                    else:
                                        msg_time = datetime.fromisoformat(ts.replace("Z", "+00:00").replace("+00:00", ""))
                                    if msg_time >= window_start:
                                        window_totals["input_tokens"] += inp
                                        window_totals["output_tokens"] += out
                                        window_totals["cache_read"] += cr
                                        window_totals["cache_create"] += cc
                                        window_totals["messages"] += 1
                                except:
                                    # If we can't parse timestamp, count it in window (conservative)
                                    window_totals["input_tokens"] += inp
                                    window_totals["output_tokens"] += out
                                    window_totals["cache_read"] += cr
                                    window_totals["cache_create"] += cc
                                    window_totals["messages"] += 1
                    except:
                        pass

            # Also scan subagents
            subagent_dir = f.parent / f.stem / "subagents"
            if subagent_dir.exists():
                for sf in subagent_dir.glob("*.jsonl"):
                    with open(sf) as sfh:
                        for line in sfh:
                            try:
                                d = json.loads(line)
                                if d.get("type") == "assistant" and "message" in d:
                                    u = d["message"].get("usage", {})
                                    totals["input_tokens"] += u.get("input_tokens", 0)
                                    totals["output_tokens"] += u.get("output_tokens", 0)
                                    totals["cache_read"] += u.get("cache_read_input_tokens", 0)
                                    totals["cache_create"] += u.get("cache_creation_input_tokens", 0)
                                    totals["messages"] += 1
                            except:
                                pass

    return totals, window_totals

def get_usage():
    config = load_config()
    period_start, period_end = get_billing_period(config["billing_day"])
    now = datetime.now()

    period_totals, window_totals = scan_sessions(period_start)

    # Calculate totals
    period_total = (period_totals["input_tokens"] + period_totals["output_tokens"]
                    + period_totals["cache_read"] + period_totals["cache_create"])
    window_total = (window_totals["input_tokens"] + window_totals["output_tokens"]
                    + window_totals["cache_read"] + window_totals["cache_create"])

    # Time until period resets
    remaining_seconds = int((period_end - now).total_seconds())
    remaining_hours = remaining_seconds // 3600
    remaining_days = remaining_hours // 24

    # Window reset: 5h rolling, next tokens free up when oldest window message ages out
    window_reset_time = (now + timedelta(hours=config["window_hours"])).isoformat()

    return {
        "plan": config["plan"],
        "period": {
            "start": period_start.isoformat(),
            "end": period_end.isoformat(),
            "days_remaining": remaining_days,
            "hours_remaining": remaining_hours % 24,
            "resets_at": period_end.isoformat(),
        },
        "period_usage": {
            "input_tokens": period_totals["input_tokens"],
            "output_tokens": period_totals["output_tokens"],
            "cache_read": period_totals["cache_read"],
            "cache_create": period_totals["cache_create"],
            "total_tokens": period_total,
            "sessions": period_totals["sessions"],
            "messages": period_totals["messages"],
        },
        "window": {
            "hours": config["window_hours"],
            "output_tokens": window_totals["output_tokens"],
            "total_tokens": window_total,
            "messages": window_totals["messages"],
        },
        "timestamp": now.isoformat(),
    }

if __name__ == "__main__":
    print(json.dumps(get_usage(), indent=2))
