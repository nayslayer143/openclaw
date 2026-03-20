#!/usr/bin/env python3
"""
OpenClaw Telegram Dispatcher
Polls Telegram for messages from Jordan, converts them to task packets,
runs the build pipeline, and reports results back.

Run with: python3 ~/openclaw/scripts/telegram-dispatcher.py
Keep alive: launchd plist or startup.sh
"""

import os
import sys
import json
import time
import subprocess
import datetime
import re
import requests
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

OPENCLAW_ROOT = Path.home() / "openclaw"
ENV_FILE = OPENCLAW_ROOT / ".env"
QUEUE_DIR = OPENCLAW_ROOT / "repo-queue"
BUILD_RESULTS = OPENCLAW_ROOT / "build-results"
RUN_TASK = OPENCLAW_ROOT / "scripts" / "run-task.sh"
POLL_INTERVAL = 5  # seconds
OFFSET_FILE = Path("/tmp/openclaw-tg-offset.txt")

# Load .env
def load_env():
    if not ENV_FILE.exists():
        print(f"ERROR: .env not found at {ENV_FILE}")
        sys.exit(1)
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

load_env()

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ALLOWED_USERS = set()
raw = os.environ.get("TELEGRAM_ALLOWED_USERS", "")
try:
    parsed = json.loads(raw)
    ALLOWED_USERS = {str(x) for x in (parsed if isinstance(parsed, list) else [parsed])}
except Exception:
    ALLOWED_USERS = {raw.strip()}

API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Default repo for tasks (can be overridden in message)
DEFAULT_REPO = "EmergentWebActions"
DEFAULT_REPO_PATH = str(Path.home() / "projects" / "EmergentWebActions")

# ── Telegram helpers ───────────────────────────────────────────────────────────

def send(chat_id, text):
    try:
        requests.post(f"{API}/sendMessage", json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": ""
        }, timeout=10)
    except Exception as e:
        print(f"[send error] {e}")

def get_updates(offset=0):
    try:
        r = requests.get(f"{API}/getUpdates", params={
            "offset": offset,
            "timeout": 5,
            "allowed_updates": ["message"]
        }, timeout=15)
        return r.json().get("result", [])
    except Exception as e:
        print(f"[poll error] {e}")
        return []

def load_offset():
    if OFFSET_FILE.exists():
        try:
            return int(OFFSET_FILE.read_text().strip())
        except Exception:
            pass
    return 0

def save_offset(offset):
    OFFSET_FILE.write_text(str(offset))

# ── Task packet builder ────────────────────────────────────────────────────────

def build_task_packet(goal: str, repo: str = DEFAULT_REPO, repo_path: str = DEFAULT_REPO_PATH) -> Path:
    date = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    slug = re.sub(r"[^a-z0-9]+", "-", goal.lower())[:40].strip("-")
    task_id = f"build-{slug}-{date}"

    packet = {
        "task_id": task_id,
        "repo_path": repo_path,
        "repo": repo,
        "goal": goal,
        "acceptance_criteria": [
            "All existing tests still pass",
            "New functionality has at least one test",
            "No direct commits to main branch"
        ],
        "forbidden_operations": [
            "never touch main branch directly",
            "never commit .env",
            "never push --force"
        ],
        "time_budget_minutes": 30,
        "risk_level": "low",
        "output_location": str(BUILD_RESULTS / task_id)
    }

    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    packet_path = QUEUE_DIR / f"task-{slug}-{date}.json"
    packet_path.write_text(json.dumps(packet, indent=2))
    return packet_path

# ── Pipeline runner ────────────────────────────────────────────────────────────

def run_task(packet_path: Path, chat_id: str):
    """Run a task packet through run-task.sh and report result via Telegram."""
    send(chat_id, f"Task queued: {packet_path.name}\nStarting build pipeline...")

    try:
        result = subprocess.run(
            ["bash", str(RUN_TASK), str(packet_path)],
            capture_output=True, text=True, timeout=1800  # 30 min max
        )
        output = result.stdout + result.stderr

        # Extract status from output
        status = "unknown"
        if "Status: success" in output or "status\": \"success\"" in output:
            status = "success"
        elif "Status: blocked" in output or "status\": \"blocked\"" in output:
            status = "blocked"
        elif "Status: failed" in output or result.returncode != 0:
            status = "failed"

        # Find contract path
        contract_path = output.strip().split("\n")[-1].strip()
        contract_summary = ""
        if contract_path.endswith(".json") and Path(contract_path).exists():
            try:
                contract = json.loads(Path(contract_path).read_text())
                changed = contract.get("changed_files", [])
                tests = contract.get("tests_run", 0)
                passed = contract.get("tests_passed", 0)
                contract_summary = f"\nFiles changed: {len(changed)}\nTests: {passed}/{tests} passed"
            except Exception:
                pass

        icon = {"success": "✓", "blocked": "⚠", "failed": "✗"}.get(status, "?")
        msg = f"{icon} Build {status.upper()}: {packet_path.stem}{contract_summary}"
        send(chat_id, msg)

    except subprocess.TimeoutExpired:
        send(chat_id, "Build timed out after 30 minutes.")
    except Exception as e:
        send(chat_id, f"Dispatcher error: {e}")

# ── Command handlers ───────────────────────────────────────────────────────────

def handle_status(chat_id):
    results = sorted(BUILD_RESULTS.glob("*.json"))[-5:] if BUILD_RESULTS.exists() else []
    if not results:
        send(chat_id, "No build results yet.")
        return
    lines = ["Recent builds:"]
    for r in reversed(results):
        try:
            data = json.loads(r.read_text())
            status = data.get("status", "?")
            icon = {"success": "✓", "blocked": "⚠", "failed": "✗"}.get(status, "?")
            lines.append(f"{icon} {r.stem}")
        except Exception:
            lines.append(f"? {r.stem}")
    send(chat_id, "\n".join(lines))

def handle_queue(chat_id):
    pending = list(QUEUE_DIR.glob("task-*.json")) if QUEUE_DIR.exists() else []
    if not pending:
        send(chat_id, "Queue is empty.")
    else:
        names = "\n".join(f"• {p.name}" for p in pending[-10:])
        send(chat_id, f"Queued ({len(pending)}):\n{names}")

def handle_help(chat_id):
    send(chat_id, (
        "OpenClaw Dispatcher\n\n"
        "Commands:\n"
        "!status          — last 5 build results\n"
        "!queue           — pending task packets\n"
        "!help            — this message\n"
        "/approve <id>    — merge a passing build into main\n\n"
        "Anything else is treated as a build task.\n"
        "Example: add rate limiting to EmergentWebActions"
    ))

def handle_approve(task_id: str, chat_id: str):
    """Merge a passing build branch into main."""
    contract_path = BUILD_RESULTS / f"{task_id}.json"
    if not contract_path.exists():
        # Try matching by prefix
        matches = list(BUILD_RESULTS.glob(f"{task_id}*.json"))
        if matches:
            contract_path = matches[0]
        else:
            send(chat_id, f"No output contract found for: {task_id}")
            return

    try:
        contract = json.loads(contract_path.read_text())
    except Exception as e:
        send(chat_id, f"Could not read contract: {e}")
        return

    status = contract.get("status")
    if status != "success":
        send(chat_id, f"Cannot approve — build status is '{status}', not 'success'.")
        return

    # Derive branch name from task_id convention: feat/<task_id>
    branch = f"feat/{task_id}"
    repo_path = contract.get("repo_path") or DEFAULT_REPO_PATH

    send(chat_id, f"Merging {branch} into main...")
    try:
        result = subprocess.run(
            ["bash", "-c",
             f"cd {repo_path} && git checkout main && git merge --no-ff {branch} -m 'Merge {branch}' && git push origin main"],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            send(chat_id, f"Merged and pushed {branch} to main.")
        else:
            send(chat_id, f"Merge failed:\n{result.stderr[:300]}")
    except Exception as e:
        send(chat_id, f"Merge error: {e}")

def is_question_or_status(text: str, chat_id: str) -> bool:
    """Detect conversational messages that shouldn't become build tasks.
    Replies if it's a status question, else nudges toward proper usage.
    Returns True if handled (caller should skip build dispatch)."""
    t = text.strip().lower()

    # Hard question mark = not a build task
    if t.endswith("?"):
        status_words = ("working on", "eta", "status", "progress", "done", "finish",
                        "complete", "queue", "blocked", "running", "build", "next")
        if any(w in t for w in status_words):
            handle_status(chat_id)
            pending = list(QUEUE_DIR.glob("task-*.json")) if QUEUE_DIR.exists() else []
            if pending:
                send(chat_id, f"Queue: {len(pending)} task(s) pending\nSend !queue for full list")
        else:
            send(chat_id, "That looks like a question — I only take build tasks.\nSend !help for commands.")
        return True

    # Very short messages (1-2 words) that aren't commands
    words = text.split()
    if len(words) <= 2 and not any(c in text for c in ("/", "!", "#")):
        send(chat_id, f'"{text}" is too short to be a build task.\nDescribe what to build, e.g.:\n  add input validation to the login endpoint')
        return True

    return False


# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    print(f"[dispatcher] Starting. Allowed users: {ALLOWED_USERS}")
    print(f"[dispatcher] Default repo: {DEFAULT_REPO} @ {DEFAULT_REPO_PATH}")
    offset = load_offset()

    while True:
        updates = get_updates(offset)

        for update in updates:
            offset = update["update_id"] + 1
            save_offset(offset)

            msg = update.get("message", {})
            if not msg:
                continue

            chat_id = str(msg.get("chat", {}).get("id", ""))
            user_id = str(msg.get("from", {}).get("id", ""))
            text = msg.get("text", "").strip()

            # Security: only respond to allowed users
            if user_id not in ALLOWED_USERS:
                print(f"[dispatcher] Ignored message from non-allowed user {user_id}")
                continue

            if not text:
                continue

            print(f"[dispatcher] Message from {user_id}: {text[:80]}")

            # Commands
            if text.lower() in ("!status", "/status"):
                handle_status(chat_id)
            elif text.lower() in ("!queue", "/queue"):
                handle_queue(chat_id)
            elif text.lower() in ("!help", "/help", "/start"):
                handle_help(chat_id)
            elif text.lower().startswith("/approve"):
                # Handle both forms:
                #   /approve build-ewa-foo-20260320
                #   /approve-build-ewa-foo-20260320 (hyphenated, as bot suggests)
                #   /approve-build-ewa-foo-20260320 to merge (trailing words ignored)
                raw = text.strip()
                if raw.lower().startswith("/approve-"):
                    # Strip /approve- prefix, take first word only
                    task_id = raw[len("/approve-"):].split()[0].strip()
                else:
                    parts = raw.split(None, 1)
                    task_id = parts[1].split()[0].strip() if len(parts) > 1 else ""
                if not task_id:
                    send(chat_id, "Usage: /approve <task_id>\nExample: /approve build-ewa-version-endpoint-20260320")
                else:
                    handle_approve(task_id, chat_id)
            elif is_question_or_status(text, chat_id):
                pass  # handled inside the function
            else:
                # Treat as task goal
                packet_path = build_task_packet(text)
                print(f"[dispatcher] Created packet: {packet_path}")
                # Run in background so dispatcher keeps polling
                log_file = open(f"/tmp/openclaw-task-{packet_path.stem}.log", "w")
                subprocess.Popen(
                    ["bash", str(OPENCLAW_ROOT / "scripts" / "run-task-and-reply.sh"),
                     str(packet_path), chat_id],
                    stdout=log_file, stderr=log_file
                )

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
