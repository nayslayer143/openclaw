#!/usr/bin/env python3
from __future__ import annotations
"""
OpenClaw Telegram Dispatcher — Clawmson Edition
Full conversational AI assistant + build pipeline in one bot.
NLU-powered intent classification via local qwen2.5:7b.

Run with: python3 ~/openclaw/scripts/telegram-dispatcher.py
Keep alive: launchd plist or startup.sh

Message flow:
  1. Auth check
  2. !shortcut commands  →  handled immediately
  3. /slash commands     →  handled immediately (including new /forget /context /references)
  4. Media (photo/doc/audio/voice)  →  processed for content + has_image flag
  5. LLM intent classification (regex fallback if Ollama down)
  6. Route:
       UNCLEAR          → ask clarifying question, wait for reply, re-classify
       STATUS_QUERY     → handle_status / handle_queue
       DIRECT_COMMAND   → run safe shell command
       REFERENCE_INGEST → ingest URLs (thread) or treat as conversation with URL context
       BUILD_TASK       → existing build pipeline (subprocess)
       CONVERSATION     → Ollama chat (thread)
  7. Save conversation history
"""

import os
import sys
import json
import time
import threading
import subprocess
import datetime
import re
import requests
from pathlib import Path

# ── Add scripts dir to path so sibling modules are importable ────────────────

_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import clawmson_db as db
import clawmson_chat as llm
import clawmson_intents as intents
import clawmson_media as media
import clawmson_references as refs
import model_router as router
import clawmson_scout as scout
from autoresearch import scholar

# Security auditor (lazy import — scripts/ already in sys.path via lines 41-42)
try:
    from security import auditor as _security_auditor
    _SECURITY_AVAILABLE = True
except ImportError:
    _SECURITY_AVAILABLE = False

# Prefixes that indicate Ollama inference failed (from clawmson_chat.py error returns)
_OLLAMA_ERROR_PREFIXES = (
    "Ollama is not reachable",
    "Ollama timed out",
    "Ollama HTTP error",
    "Chat error",
)

import clawmson_memory as mem_module
_memory = mem_module.memory  # module-level singleton

import clawmson_fts as fts
import clawmson_sessions as sessions
import signal

CLAWMSON_SEARCH_LIMIT = int(os.environ.get("CLAWMSON_SEARCH_LIMIT", "10"))

_SESSION_KEY: str = ""                     # set on boot by start_session()
_resumed: set[str] = set()                # chat_ids already resumed this process run
_resumed_lock = threading.Lock()           # guards check-then-add on _resumed
_SHUTDOWN_REQUESTED = False                # set by signal handler, checked in main loop

# ── Config ────────────────────────────────────────────────────────────────────

OPENCLAW_ROOT  = Path.home() / "openclaw"
ENV_FILE       = OPENCLAW_ROOT / ".env"
QUEUE_DIR      = OPENCLAW_ROOT / "repo-queue"
BUILD_RESULTS  = OPENCLAW_ROOT / "build-results"
RUN_TASK       = OPENCLAW_ROOT / "scripts" / "run-task.sh"
CLAWTEAM       = OPENCLAW_ROOT / "scripts" / "clawteam.py"
POLL_INTERVAL  = 5   # seconds
_TWITTER_RE = scout.TWITTER_RE  # shared with clawmson_scout — single source of truth
OFFSET_FILE    = Path("/tmp/openclaw-tg-offset.txt")

# ── Claw relay inbox files (JSONL) ────────────────────────────────────────────
_CODEMONKEY_INBOX = Path("/tmp/codemonkey-inbox.jsonl")
_RIVALCLAW_INBOX  = Path("/tmp/rivalclaw-inbox.jsonl")
_QUANT_INBOX      = Path("/tmp/quant-inbox.jsonl")

DEFAULT_REPO      = "EmergentWebActions"
DEFAULT_REPO_PATH = str(Path.home() / "projects" / "EmergentWebActions")


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

BOT_TOKEN    = os.environ["TELEGRAM_BOT_TOKEN"]
ALLOWED_USERS = set()
_raw = os.environ.get("TELEGRAM_ALLOWED_USERS", "")
try:
    _parsed = json.loads(_raw)
    ALLOWED_USERS = {str(x) for x in (_parsed if isinstance(_parsed, list) else [_parsed])}
except Exception:
    ALLOWED_USERS = {_raw.strip()}

API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ── RivalClaw bot (@rivalclaw_bot) ────────────────────────────────────────────
RIVAL_BOT_TOKEN   = os.environ.get("RIVALCLAW_BOT_TOKEN", "").strip()
_RIVAL_ACTIVE     = bool(RIVAL_BOT_TOKEN and not RIVAL_BOT_TOKEN.startswith("PASTE"))
RIVAL_API         = f"https://api.telegram.org/bot{RIVAL_BOT_TOKEN}" if _RIVAL_ACTIVE else None
RIVAL_OFFSET_FILE = Path("/tmp/rivalclaw-tg-offset.txt")

# ── QuantumentalClaw bot (@QuantiusMaximus_bot) ───────────────────────────────
QUANT_BOT_TOKEN   = os.environ.get("QUANTCLAW_BOT_TOKEN", "").strip()
_QUANT_BOT_ACTIVE = bool(QUANT_BOT_TOKEN and not QUANT_BOT_TOKEN.startswith("PASTE"))
QUANT_API         = f"https://api.telegram.org/bot{QUANT_BOT_TOKEN}" if _QUANT_BOT_ACTIVE else None
QUANT_OFFSET_FILE = Path("/tmp/quantclaw-tg-offset.txt")

# ── CodeMonkeyClaw bot (@Codemonkeyclaw_bot) ──────────────────────────────────
MONKEY_BOT_TOKEN   = os.environ.get("CODEMONKEY_BOT_TOKEN", "").strip()
_MONKEY_BOT_ACTIVE = bool(MONKEY_BOT_TOKEN and not MONKEY_BOT_TOKEN.startswith("PASTE"))
MONKEY_API         = f"https://api.telegram.org/bot{MONKEY_BOT_TOKEN}" if _MONKEY_BOT_ACTIVE else None
MONKEY_OFFSET_FILE = Path("/tmp/codemonkeyclaw-tg-offset.txt")

# Init media module with bot token
media.init(BOT_TOKEN)

# ── Clarification state ──────────────────────────────────────────────────────
# Tracks when Clawmson asked a clarifying question and is waiting for a reply.
# Key: chat_id → {"original_text": str, "question": str, "timestamp": float}
_pending_clarifications: dict = {}


# ── Telegram helpers ──────────────────────────────────────────────────────────

def send(chat_id: str, text: str):
    if not text:
        return
    # Telegram message length cap is 4096; split if needed
    for chunk in _split_message(text):
        try:
            requests.post(f"{API}/sendMessage", json={
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": ""
            }, timeout=10)
        except Exception as e:
            print(f"[send error] {e}")


def _split_message(text: str, limit: int = 4000) -> list:
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        chunks.append(text[:limit])
        text = text[limit:]
    return chunks


def send_typing(chat_id: str):
    try:
        requests.post(f"{API}/sendChatAction",
                      json={"chat_id": chat_id, "action": "typing"}, timeout=5)
    except Exception:
        pass


def get_updates(offset: int = 0) -> list:
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


def load_offset() -> int:
    if OFFSET_FILE.exists():
        try:
            return int(OFFSET_FILE.read_text().strip())
        except Exception:
            pass
    return 0


def save_offset(offset: int):
    OFFSET_FILE.write_text(str(offset))


# ── RivalClaw bot helpers ─────────────────────────────────────────────────────

def send_rival(chat_id: str, text: str):
    """Send a message via the @rivalclaw_bot token."""
    if not RIVAL_API or not text:
        return
    for chunk in _split_message(text):
        try:
            requests.post(f"{RIVAL_API}/sendMessage", json={
                "chat_id": chat_id, "text": chunk, "parse_mode": ""
            }, timeout=10)
        except Exception as e:
            print(f"[rival send error] {e}")


def get_rival_updates(offset: int = 0) -> list:
    if not RIVAL_API:
        return []
    try:
        r = requests.get(f"{RIVAL_API}/getUpdates", params={
            "offset": offset, "timeout": 5, "allowed_updates": ["message"]
        }, timeout=15)
        return r.json().get("result", [])
    except Exception as e:
        print(f"[rival poll error] {e}")
        return []


def load_rival_offset() -> int:
    if RIVAL_OFFSET_FILE.exists():
        try:
            return int(RIVAL_OFFSET_FILE.read_text().strip())
        except Exception:
            pass
    return 0


def save_rival_offset(offset: int):
    RIVAL_OFFSET_FILE.write_text(str(offset))


# ── QuantumentalClaw bot helpers ──────────────────────────────────────────────

def send_quant(chat_id: str, text: str):
    """Send a message via the @QuantiusMaximus_bot token."""
    if not QUANT_API or not text:
        return
    for chunk in _split_message(text):
        try:
            requests.post(f"{QUANT_API}/sendMessage", json={
                "chat_id": chat_id, "text": chunk, "parse_mode": ""
            }, timeout=10)
        except Exception as e:
            print(f"[quant send error] {e}")


def get_quant_updates(offset: int = 0) -> list:
    if not QUANT_API:
        return []
    try:
        r = requests.get(f"{QUANT_API}/getUpdates", params={
            "offset": offset, "timeout": 5, "allowed_updates": ["message"]
        }, timeout=15)
        return r.json().get("result", [])
    except Exception as e:
        print(f"[quant poll error] {e}")
        return []


def load_quant_offset() -> int:
    if QUANT_OFFSET_FILE.exists():
        try:
            return int(QUANT_OFFSET_FILE.read_text().strip())
        except Exception:
            pass
    return 0


def save_quant_offset(offset: int):
    QUANT_OFFSET_FILE.write_text(str(offset))


def handle_quant_bot_message(msg: dict):
    """Handle messages sent to @QuantiusMaximus_bot — relay to inbox + respond via Ollama."""
    chat_id = str(msg.get("chat", {}).get("id", ""))
    user_id = str(msg.get("from", {}).get("id", ""))
    text    = msg.get("text", "").strip()
    msg_id  = msg.get("message_id")
    if user_id not in ALLOWED_USERS:
        print(f"[quant-bot] Ignored from non-allowed user {user_id}")
        return
    if not text:
        return
    _write_inbox(_QUANT_INBOX, chat_id, user_id, msg_id, text)
    print(f"[quant-bot] Message from {user_id}: {text[:80]}")
    try:
        requests.post(f"{QUANT_API}/sendChatAction",
                      json={"chat_id": chat_id, "action": "typing"}, timeout=5)
    except Exception:
        pass
    dispatch_sub_claw_response(chat_id, text, "quant", send_quant)


# ── CodeMonkeyClaw bot helpers ────────────────────────────────────────────────

def send_monkey(chat_id: str, text: str):
    """Send a message via the @Codemonkeyclaw_bot token."""
    if not MONKEY_API or not text:
        return
    for chunk in _split_message(text):
        try:
            requests.post(f"{MONKEY_API}/sendMessage", json={
                "chat_id": chat_id, "text": chunk, "parse_mode": ""
            }, timeout=10)
        except Exception as e:
            print(f"[monkey send error] {e}")


def get_monkey_updates(offset: int = 0) -> list:
    if not MONKEY_API:
        return []
    try:
        r = requests.get(f"{MONKEY_API}/getUpdates", params={
            "offset": offset, "timeout": 5, "allowed_updates": ["message"]
        }, timeout=15)
        return r.json().get("result", [])
    except Exception as e:
        print(f"[monkey poll error] {e}")
        return []


def load_monkey_offset() -> int:
    if MONKEY_OFFSET_FILE.exists():
        try:
            return int(MONKEY_OFFSET_FILE.read_text().strip())
        except Exception:
            pass
    return 0


def save_monkey_offset(offset: int):
    MONKEY_OFFSET_FILE.write_text(str(offset))


def handle_monkey_bot_message(msg: dict):
    """Handle messages sent to @Codemonkeyclaw_bot — relay to inbox + respond via Ollama."""
    chat_id = str(msg.get("chat", {}).get("id", ""))
    user_id = str(msg.get("from", {}).get("id", ""))
    text    = msg.get("text", "").strip()
    msg_id  = msg.get("message_id")
    if user_id not in ALLOWED_USERS:
        print(f"[monkey-bot] Ignored from non-allowed user {user_id}")
        return
    if not text:
        return
    _write_inbox(_CODEMONKEY_INBOX, chat_id, user_id, msg_id, text)
    print(f"[monkey-bot] Message from {user_id}: {text[:80]}")
    try:
        requests.post(f"{MONKEY_API}/sendChatAction",
                      json={"chat_id": chat_id, "action": "typing"}, timeout=5)
    except Exception:
        pass
    dispatch_sub_claw_response(chat_id, text, "monkey", send_monkey)


# ── Shared relay helpers ──────────────────────────────────────────────────────

def _write_inbox(inbox_path: Path, chat_id: str, user_id: str, msg_id, text: str):
    """Append a relay payload to a JSONL inbox file."""
    payload = json.dumps({
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "chat_id": chat_id, "user_id": user_id, "msg_id": msg_id, "text": text,
    })
    with open(inbox_path, "a") as f:
        f.write(payload + "\n")


def handle_claws(chat_id: str):
    """Show health status of all 4 claw instances."""
    state_file = Path.home() / ".openclaw" / "claw-sessions.json"
    try:
        state = json.loads(state_file.read_text()) if state_file.exists() else {}
    except Exception:
        state = {}
    claw_defs = [
        ("clawmpson", "🦞", "@ogdenclashbot"),
        ("rival",     "🥊", "@rivalclaw_bot" if _RIVAL_ACTIVE else "@rivalclaw_bot (no token)"),
        ("quant",     "🧪", "@QuantiusMaximus_bot" if _QUANT_BOT_ACTIVE else "@QuantiusMaximus_bot (no token)"),
        ("monkey",    "🐒", "@Codemonkeyclaw_bot" if _MONKEY_BOT_ACTIVE else "@Codemonkeyclaw_bot (no token)"),
    ]
    lines = ["Claw status:"]
    for name, icon, label in claw_defs:
        info    = state.get(name, {})
        status  = info.get("status", "unknown")
        pid     = info.get("pid") or "—"
        reboots = info.get("reboots", 0)
        s_icon  = "🟢" if status == "running" else ("🟡" if status in ("starting", "restarting") else "🔴")
        lines.append(f"{s_icon} {icon} {name} ({label}): {status} | pid={pid} | boots={reboots}")
    for name, inbox_file in [("rival", _RIVALCLAW_INBOX), ("quant", _QUANT_INBOX), ("monkey", _CODEMONKEY_INBOX)]:
        if inbox_file.exists():
            try:
                age = int(time.time() - inbox_file.stat().st_mtime)
                lines.append(f"  📬 {name} inbox: last activity {age // 60}m ago")
            except Exception:
                pass
    send(chat_id, "\n".join(lines))


def handle_rival_bot_message(msg: dict):
    """Handle messages sent to @rivalclaw_bot — relay to inbox + respond via Ollama."""
    chat_id = str(msg.get("chat", {}).get("id", ""))
    user_id = str(msg.get("from", {}).get("id", ""))
    text    = msg.get("text", "").strip()
    msg_id  = msg.get("message_id")
    if user_id not in ALLOWED_USERS:
        print(f"[rival-bot] Ignored from non-allowed user {user_id}")
        return
    if not text:
        return
    _write_inbox(_RIVALCLAW_INBOX, chat_id, user_id, msg_id, text)
    print(f"[rival-bot] Message from {user_id}: {text[:80]}")
    # Send typing indicator then generate real response
    try:
        requests.post(f"{RIVAL_API}/sendChatAction",
                      json={"chat_id": chat_id, "action": "typing"}, timeout=5)
    except Exception:
        pass
    dispatch_sub_claw_response(chat_id, text, "rival", send_rival)


# ── Sub-claw response engine ─────────────────────────────────────────────────
# Each sub-claw (rival, quant, monkey) gets its own Ollama chat loop with
# claw-specific context, exactly like Clawmpson does for itself.

# Per-claw conversation history: {claw_name: {chat_id: [{"role":..,"content":..}]}}
_SUB_CLAW_HISTORIES: dict = {}
_SUB_CLAW_HISTORY_LOCK = threading.Lock()
_HISTORY_MAX = 20  # entries per (claw, chat_id)

_CLAW_ROOTS = {
    "rival":  Path.home() / "rivalclaw",
    "quant":  Path.home() / "quantumentalclaw",
    "monkey": Path.home() / "codemonkeyclaw",
}

_CLAW_ICONS = {"rival": "🥊", "quant": "🧪", "monkey": "🐒"}

_CLAW_SEND_FNS: dict = {}  # populated after functions are defined (see below)


def _load_claw_context(claw_name: str) -> str:
    """Load CLAUDE.md + latest daily report for claw — injected as memory context."""
    root = _CLAW_ROOTS.get(claw_name)
    if not root:
        return ""
    parts = []
    # 1. CLAUDE.md (identity + mission)
    claude_md = root / "CLAUDE.md"
    if claude_md.exists():
        text = claude_md.read_text()[:3000]
        parts.append(f"=== {claw_name} CLAUDE.md ===\n{text}")
    # 2. Latest daily report
    daily_dir = root / "daily"
    if daily_dir.exists():
        reports = sorted(daily_dir.glob("*.md"), reverse=True) or sorted(daily_dir.glob("*.txt"), reverse=True)
        if reports:
            text = reports[0].read_text()[-2500:]
            parts.append(f"=== Latest daily report ({reports[0].name}) ===\n{text}")
    return "\n\n".join(parts)


def _get_claw_history(claw_name: str, chat_id: str) -> list:
    with _SUB_CLAW_HISTORY_LOCK:
        return list(_SUB_CLAW_HISTORIES.get(claw_name, {}).get(chat_id, []))


def _save_claw_history(claw_name: str, chat_id: str, role: str, content: str):
    with _SUB_CLAW_HISTORY_LOCK:
        claw_hist = _SUB_CLAW_HISTORIES.setdefault(claw_name, {})
        hist = claw_hist.setdefault(chat_id, [])
        hist.append({"role": role, "content": content})
        if len(hist) > _HISTORY_MAX:
            claw_hist[chat_id] = hist[-_HISTORY_MAX:]


def _sub_claw_response_thread(chat_id: str, text: str,
                              claw_name: str, send_fn):
    """Generate an Ollama response for a sub-claw and send it back."""
    try:
        context  = _load_claw_context(claw_name)
        history  = _get_claw_history(claw_name, chat_id)
        icon     = _CLAW_ICONS.get(claw_name, "")
        # Use fast model — sub-claws don't need the heavy 32b model for chat
        reply    = llm.chat(history, text, model="qwen2.5:7b",
                            memory_context=context)
        _save_claw_history(claw_name, chat_id, "user",      text)
        _save_claw_history(claw_name, chat_id, "assistant", reply)
        send_fn(chat_id, reply)
        print(f"[{claw_name}-bot] Responded ({len(reply)} chars)")
    except Exception as e:
        print(f"[{claw_name}-bot] Response error: {e}")
        try:
            send_fn(chat_id, f"Error generating response: {e}")
        except Exception:
            pass


def dispatch_sub_claw_response(chat_id: str, text: str,
                               claw_name: str, send_fn):
    """Start a background thread to generate and send a sub-claw response."""
    t = threading.Thread(
        target=_sub_claw_response_thread,
        args=(chat_id, text, claw_name, send_fn),
        daemon=True,
    )
    t.start()


# ── Task packet builder ───────────────────────────────────────────────────────

def build_task_packet(goal: str, classification=None,
                      repo: str = DEFAULT_REPO,
                      repo_path: str = DEFAULT_REPO_PATH) -> Path:
    date    = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    slug    = re.sub(r"[^a-z0-9]+", "-", goal.lower())[:40].strip("-")
    task_id = f"tsk-{slug}-{date}"

    # Structured packet — enriched by LLM classification when available
    parsed = {}
    if classification:
        parsed = {
            "action": classification.get("action"),
            "target": classification.get("target"),
            "project": classification.get("project"),
        }

    packet  = {
        "task_id": task_id,
        "source": "telegram",
        "repo_path": repo_path,
        "repo": repo,
        "goal": goal,
        "parsed": parsed,
        "attachments": classification.get("attachments", []) if classification else [],
        "clarification": classification.get("_clarification_context") if classification else None,
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
        "priority": "normal",
        "time_budget_minutes": 30,
        "risk_level": "low",
        "model": "qwen2.5:7b",
        "timestamp": datetime.datetime.now().isoformat(),
        "output_location": str(BUILD_RESULTS / task_id)
    }
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    packet_path = QUEUE_DIR / f"task-{slug}-{date}.json"
    packet_path.write_text(json.dumps(packet, indent=2))
    return packet_path


# ── Existing command handlers (unchanged) ─────────────────────────────────────

def handle_status(chat_id: str):
    results = sorted(BUILD_RESULTS.glob("*.json"))[-5:] if BUILD_RESULTS.exists() else []
    if not results:
        send(chat_id, "No build results yet.")
        return
    lines = ["Recent builds:"]
    for r in reversed(results):
        try:
            data   = json.loads(r.read_text())
            status = data.get("status", "?")
            icon   = {"success": "✓", "blocked": "⚠", "failed": "✗"}.get(status, "?")
            lines.append(f"{icon} {r.stem}")
        except Exception:
            lines.append(f"? {r.stem}")
    send(chat_id, "\n".join(lines))


def handle_queue(chat_id: str):
    pending = list(QUEUE_DIR.glob("task-*.json")) if QUEUE_DIR.exists() else []
    if not pending:
        send(chat_id, "Queue is empty.")
    else:
        names = "\n".join(f"• {p.name}" for p in pending[-10:])
        send(chat_id, f"Queued ({len(pending)}):\n{names}")


def handle_help(chat_id: str):
    send(chat_id, (
        "Clawmson — OpenClaw AI Assistant\n\n"
        "Shortcuts:\n"
        "!status          — last 5 build results\n"
        "!claws           — health of all 4 claw instances\n"
        "!queue           — pending task packets\n"
        "!help            — this message\n\n"
        "Claw Relay:\n"
        "🐒 <msg> or /monkey <msg>  — @Codemonkeyclaw_bot\n"
        "🥊 <msg> or /rival <msg>   — @rivalclaw_bot\n"
        "🧪 <msg> or /quant <msg>   — @QuantiusMaximus_bot\n\n"
        "Commands:\n"
        "/claws           — status of all 4 claws\n"
        "/approve <id>    — merge a passing build into main\n"
        "/forget          — clear conversation history\n"
        "/context         — show persistent notes\n"
        "/references      — list saved links\n"
        "/scout           — digest of recently scouted Twitter links\n"
        "/audit <name>    — security audit a skill\n"
        "/skills          — list registered skills with trust scores\n"
        "/block <name>    — manually block a skill\n\n"
        "Anything else: just talk to me.\n"
        "Send a URL and I'll read and summarize it.\n"
        "Send a photo, file, or voice note and I'll process it.\n"
        "Describe a code task and I'll queue a build."
    ))


def handle_approve(task_id: str, chat_id: str):
    """Merge a passing build branch into main (unchanged from original)."""
    # Route to skill approval if this matches a registered skill name
    if _SECURITY_AVAILABLE:
        from security import registry as _reg
        if _reg.get(task_id):
            def _notify(msg: str):
                send(chat_id, msg)
            result = _security_auditor.handle_approval(task_id, notify_fn=_notify)
            send(chat_id, result)
            return
    contract_path = BUILD_RESULTS / f"{task_id}.json"
    if not contract_path.exists():
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

    branch    = f"feat/{task_id}"
    repo_path = contract.get("repo_path") or DEFAULT_REPO_PATH
    send(chat_id, f"Merging {branch} into main...")
    try:
        result = subprocess.run(
            ["bash", "-c",
             f"cd {repo_path} && git checkout main && "
             f"git merge --no-ff {branch} -m 'Merge {branch}' && "
             f"git push origin main"],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            send(chat_id, f"Merged and pushed {branch} to main.")
        else:
            send(chat_id, f"Merge failed:\n{result.stderr[:300]}")
    except Exception as e:
        send(chat_id, f"Merge error: {e}")


# ── New command handlers ──────────────────────────────────────────────────────

def handle_forget(chat_id: str):
    db.clear_history(chat_id)
    send(chat_id, "Conversation history cleared.")


def handle_context(chat_id: str):
    ctx = db.get_context(chat_id)
    if not ctx:
        send(chat_id, "No persistent context stored.")
    else:
        lines = ["Persistent context:"]
        for k, v in ctx.items():
            lines.append(f"• {k}: {v}")
        send(chat_id, "\n".join(lines))


def handle_references(chat_id: str):
    ref_list = db.list_references(chat_id, limit=20)
    send(chat_id, refs.format_references(ref_list))


def handle_research(chat_id: str, topic: str):
    """Run last30days deep research on a topic and return compact report."""
    if not topic:
        send(chat_id, "Usage: /research <topic>\nExample: /research Polymarket AI election")
        return
    send_typing(chat_id)
    send(chat_id, f"Researching '{topic}' across Reddit, X, HN, YouTube… (~60-90s)")
    parsed = intents.parse_last30days_command(f"/research {topic}")
    if not parsed:
        send(chat_id, "Could not build last30days command.")
        return
    try:
        result = subprocess.run(
            parsed["command"],
            shell=True,
            capture_output=True,
            text=True,
            timeout=180,
        )
        output = result.stdout.strip() or result.stderr.strip() or "No output."
        # Telegram message limit ~4096 chars
        if len(output) > 3800:
            output = output[:3800] + "\n…[truncated]"
        send(chat_id, output)
    except subprocess.TimeoutExpired:
        send(chat_id, f"Research timed out for '{topic}'. Try /buzz for a faster check.")
    except Exception as e:
        send(chat_id, f"Research error: {e}")


def handle_buzz(chat_id: str, topic: str):
    """Quick social pulse check via last30days (Reddit + X + HN only, ~15s)."""
    if not topic:
        send(chat_id, "Usage: /buzz <topic>\nExample: /buzz Bitcoin ETF approval")
        return
    send_typing(chat_id)
    send(chat_id, f"Quick buzz check for '{topic}'…")
    parsed = intents.parse_last30days_command(f"/buzz {topic}")
    if not parsed:
        send(chat_id, "Could not build last30days command.")
        return
    try:
        result = subprocess.run(
            parsed["command"],
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = result.stdout.strip() or result.stderr.strip() or "No results found."
        if len(output) > 3800:
            output = output[:3800] + "\n…[truncated]"
        send(chat_id, output)
    except subprocess.TimeoutExpired:
        send(chat_id, f"Buzz check timed out for '{topic}'.")
    except Exception as e:
        send(chat_id, f"Buzz error: {e}")


def handle_papers(chat_id: str, topic: str):
    """Discover and summarize top 5 papers on a topic."""
    send_typing(chat_id)
    try:
        results = scholar.discover(query=topic or None, limit=5)
    except Exception as e:
        send(chat_id, f"Paper search failed: {e}")
        return
    if not results:
        send(chat_id, f"No papers found for '{topic}'." if topic else "No trending papers found.")
        return
    lines = [f"Top papers{' on ' + topic if topic else ' (trending)'}:\n"]
    for i, p in enumerate(results, 1):
        score = p.get("relevance_score", 0)
        lines.append(f"{i}. {p['title']} (relevance: {score:.2f})\n"
                     f"   {p.get('url', '')}\n")
    send(chat_id, "".join(lines))


def handle_digest(chat_id: str, paper_id: str):
    """Deep-dive digest a specific paper."""
    if not paper_id:
        send(chat_id, "Usage: /digest <paper_id>")
        return
    send_typing(chat_id)
    try:
        result = scholar.digest_paper(paper_id)
    except Exception as e:
        send(chat_id, f"Digest failed: {e}")
        return
    if "error" in result:
        if result["error"] == "unknown_paper":
            send(chat_id, f"Paper {paper_id} not found. Try /papers [topic] to discover it first.")
        else:
            send(chat_id, f"Digest failed: {result['error']}")
        return
    lines = [
        f"Digest: {paper_id}\n",
        f"Priority: {result.get('priority', '?')}\n\n",
        "Key Findings:\n",
    ]
    for f in result.get("key_findings", []):
        lines.append(f"• {f}\n")
    techniques = result.get("implementable_techniques", [])
    if techniques:
        lines.append("\nImplementable:\n")
        for t in techniques:
            lines.append(f"• {t}\n")
    relevance = result.get("relevance_to_builds", "")
    if relevance:
        lines.append(f"\nRelevance: {relevance}\n")
    actions = result.get("actions", [])
    if actions:
        lines.append(f"\nActions taken: {', '.join(actions)}\n")
    send(chat_id, "".join(lines))


def handle_scholar(chat_id: str, subcommand: str):
    """Handle /scholar [subcommand]."""
    sub = subcommand.strip().lower()
    if sub == "status" or sub == "":
        try:
            summary = scholar.get_recent_papers(days=7)
        except Exception as e:
            send(chat_id, f"Scholar status failed: {e}")
            return
        lines = [
            f"AutoScholar — last 7 days\n",
            f"Discovered: {summary.get('total', 0)} papers\n",
            f"Digested: {summary.get('digested', 0)} papers\n",
        ]
        if summary.get("top_titles"):
            lines.append("\nTop digested:\n")
            for t in summary["top_titles"]:
                lines.append(f"• {t}\n")
        send(chat_id, "".join(lines))
    else:
        send(chat_id, "Usage:\n/scholar status — recent activity\n"
                      "/papers [topic] — search papers\n"
                      "/digest [paper_id] — deep dive a paper")


def handle_memory(chat_id: str, query: str = ""):
    """Show current memory context for this chat."""
    ctx = _memory.retrieve(chat_id, query)
    send(chat_id, ctx if ctx else "Memory is empty.")


def handle_memory_stats(chat_id: str):
    """Show counts per memory layer."""
    stats = _memory.stats(chat_id)
    lines = ["Memory stats:"]
    for layer, count in stats.items():
        lines.append(f"  {layer}: {count}")
    send(chat_id, "\n".join(lines))


def handle_forget_memory(chat_id: str, layer: str = "all"):
    """Clear one or all memory layers."""
    valid_layers = {"all", "stm", "episodic", "semantic", "procedural"}
    if layer not in valid_layers:
        send(chat_id, f"Unknown layer '{layer}'. Valid: {', '.join(sorted(valid_layers))}")
        return
    _memory.clear(chat_id, layer=layer)
    send(chat_id, f"Memory layer '{layer}' cleared.")


def handle_remember(chat_id: str, args: str):
    """Store an explicit semantic fact. Usage: /remember key: value"""
    if ":" not in args:
        send(chat_id, "Usage: /remember <key>: <value>")
        return
    key, _, value = args.partition(":")
    key   = key.strip()
    value = value.strip()
    if not key or not value:
        send(chat_id, "Usage: /remember <key>: <value>")
        return
    _memory._semantic.ingest_explicit(chat_id, key, value)
    send(chat_id, f"Remembered: {key} = {value}")


def handle_approve_proc(chat_id: str, proc_id_str: str):
    """Approve a proposed procedure. Usage: /approve-proc <id>"""
    try:
        proc_id = int(proc_id_str.strip())
    except ValueError:
        send(chat_id, "Usage: /approve-proc <id>")
        return
    _memory.approve_procedure(chat_id, proc_id)
    send(chat_id, f"Procedure {proc_id} approved.")


def handle_reject_proc(chat_id: str, proc_id_str: str):
    """Reject a proposed procedure. Usage: /reject-proc <id>"""
    try:
        proc_id = int(proc_id_str.strip())
    except ValueError:
        send(chat_id, "Usage: /reject-proc <id>")
        return
    _memory.reject_procedure(chat_id, proc_id)
    send(chat_id, f"Procedure {proc_id} rejected.")


# ── Mirofish paper trading commands ──────────────────────────────────────────
def handle_portfolio(chat_id: str):
    try:
        import scripts.mirofish.dashboard as dash
        send(chat_id, dash.format_portfolio_message())
    except Exception as e:
        send(chat_id, f"Portfolio error: {e}")


def handle_pnl(chat_id: str):
    try:
        import scripts.mirofish.dashboard as dash
        send(chat_id, dash.format_pnl_message())
    except Exception as e:
        send(chat_id, f"P&L error: {e}")


def handle_trades(chat_id: str):
    try:
        import scripts.mirofish.dashboard as dash
        send(chat_id, dash.format_trades_message())
    except Exception as e:
        send(chat_id, f"Trades error: {e}")


def handle_bet(chat_id: str, text: str):
    """
    /bet [market_id] [YES|NO] [amount]
    Example: /bet 0xabc123 YES 50
    """
    parts = text.split()
    if len(parts) < 3:
        send(chat_id, "Usage: /bet [market_id] [YES|NO] [amount]\nExample: /bet 0xabc YES 50")
        return
    market_id = parts[0]
    direction = parts[1].upper()
    if direction not in ("YES", "NO"):
        send(chat_id, "Direction must be YES or NO")
        return
    try:
        amount = float(parts[2])
    except ValueError:
        send(chat_id, f"Invalid amount: {parts[2]}")
        return

    try:
        import scripts.mirofish.paper_wallet as pw
        import scripts.mirofish.polymarket_feed as feed
        from types import SimpleNamespace

        prices = feed.get_latest_prices()
        p = prices.get(market_id, {})
        if direction == "YES":
            entry_price = p.get("yes_price", 0.50)
        else:
            entry_price = p.get("no_price", 0.50)

        shares = amount / entry_price if entry_price > 0 else 0

        decision = SimpleNamespace(
            market_id=market_id,
            question=f"Manual bet on {market_id}",
            direction=direction,
            amount_usd=amount,
            entry_price=entry_price,
            shares=shares,
            confidence=1.0,
            reasoning="manual via /bet",
            strategy="manual",
        )
        result = pw.execute_trade(decision)
        if result:
            send(chat_id,
                 f"Paper trade executed\n"
                 f"{direction} ${amount:.2f} on {market_id}\n"
                 f"Entry: ${entry_price:.3f} | Shares: {shares:.1f}")
        else:
            state = pw.get_state()
            cap = state["balance"] * 0.10
            send(chat_id,
                 f"Trade rejected — ${amount:.2f} exceeds 10% position cap "
                 f"(max ${cap:.2f} at current balance ${state['balance']:.2f})")
    except Exception as e:
        send(chat_id, f"Bet error: {e}")


# ── Security audit handlers ───────────────────────────────────────────────────

def handle_audit_skill(chat_id: str, skill_name_or_path: str):
    if not _SECURITY_AVAILABLE:
        send(chat_id, "Security auditor not available.")
        return
    if not skill_name_or_path:
        send(chat_id, "Usage: /audit <skill_name_or_path>")
        return
    # Resolve name to path: try literal path first, then incoming/ dir
    target = Path(skill_name_or_path)
    if not target.exists():
        target = Path.home() / "openclaw" / "skills" / "incoming" / skill_name_or_path
    send(chat_id, f"Auditing {skill_name_or_path}...")

    def _notify(msg: str):
        send(chat_id, msg)

    try:
        result = _security_auditor.audit_skill(
            str(target), notify_fn=_notify
        )
        send(chat_id, f"Audit complete: {result.skill_name} — {result.category} "
                      f"({result.score}/100)")
    except Exception as e:
        send(chat_id, f"Audit error: {e}")


def handle_skills_list(chat_id: str):
    if not _SECURITY_AVAILABLE:
        send(chat_id, "Security auditor not available.")
        return
    from security import registry as _reg
    rows = _reg.get_all()
    if not rows:
        send(chat_id, "No skills registered.")
        return
    lines = ["Registered skills:"]
    for r in rows:
        lines.append(
            f"• {r['skill_name']}: {r['trust_score']}/100 [{r['category']}] "
            f"approved={r.get('approved_by') or '—'}"
        )
    send(chat_id, "\n".join(lines))


def handle_skill_block(chat_id: str, skill_name: str):
    if not _SECURITY_AVAILABLE:
        send(chat_id, "Security auditor not available.")
        return
    if not skill_name:
        send(chat_id, "Usage: /block <skill_name>")
        return

    def _notify(msg: str):
        send(chat_id, msg)

    result = _security_auditor.handle_block(skill_name, notify_fn=_notify)
    send(chat_id, result)


def handle_search(chat_id: str, query: str):
    """FTS5 keyword search across all memory layers. Usage: /search <query>"""
    results = fts.search(chat_id, query, limit=CLAWMSON_SEARCH_LIMIT)
    send(chat_id, fts.format_results(results))


def handle_browse(chat_id: str, url: str):
    """Open URL, extract text, send summary to user."""
    import sys as _sys
    _sys.path.insert(0, str(_SCRIPTS_DIR))
    try:
        from browser.browser_tools import browser_open
    except ImportError as e:
        send(chat_id, f"Browser module not available: {e}")
        return

    if not url.startswith("http"):
        send(chat_id, "Usage: /browse <url> — URL must start with http:// or https://")
        return

    send(chat_id, f"Opening {url}...")
    send_typing(chat_id)

    result = browser_open(url, extract="dom")
    if not result["ok"]:
        send(chat_id, f"Browse failed: {result['error']}")
        return

    title = result.get("title", "No title")
    content = result.get("content", "")[:2000]
    links = result.get("links", [])[:5]
    link_lines = "\n".join(f"  • {l['text'][:50]}: {l['href']}" for l in links if l.get("href"))

    reply = f"{title}\n{url}\n\n{content}"
    if link_lines:
        reply += f"\n\nLinks:\n{link_lines}"
    send(chat_id, reply)


def handle_screenshot_url(chat_id: str, url: str):
    """Take screenshot of URL and send as photo."""
    import sys as _sys, os as _os, tempfile
    _sys.path.insert(0, str(_SCRIPTS_DIR))
    try:
        from browser.browser_tools import browser_screenshot
    except ImportError as e:
        send(chat_id, f"Browser module not available: {e}")
        return

    if not url.startswith("http"):
        send(chat_id, "Usage: /screenshot <url>")
        return

    send(chat_id, f"Taking screenshot of {url}...")
    send_typing(chat_id)

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name

    result = browser_screenshot(url, save_path=tmp_path)
    if not result["ok"]:
        send(chat_id, f"Screenshot failed: {result['error']}")
        return

    try:
        with open(tmp_path, "rb") as f:
            requests.post(
                f"{API}/sendPhoto",
                data={"chat_id": chat_id, "caption": url[:200]},
                files={"photo": f},
                timeout=30,
            )
    except Exception as e:
        send(chat_id, f"Screenshot taken but send failed: {e}")
    finally:
        _os.unlink(tmp_path)


# ── Direct command execution ──────────────────────────────────────────────────

def handle_direct_command(chat_id: str, text: str):
    cmd = intents.get_safe_command(text)
    if not cmd:
        send(chat_id, "Unknown command.")
        return
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=30
        )
        output = (result.stdout + result.stderr).strip()
        reply  = output[:3000] if output else "(no output)"
    except subprocess.TimeoutExpired:
        reply = "Command timed out."
    except Exception as e:
        reply = f"Command error: {e}"
    send(chat_id, reply)
    db.save_message(chat_id, "assistant", reply)


# ── Conversation handler (runs in thread) ─────────────────────────────────────

def _conversation_thread(chat_id: str, effective_text: str,
                         has_image: bool, intent: str = None):
    """Called in a background thread. Fetches Ollama reply and sends it."""
    send_typing(chat_id)

    # Session tracking
    if _SESSION_KEY:
        sessions.ensure_session(_SESSION_KEY, chat_id)

    history        = _memory.sensory(chat_id)
    memory_context = _memory.retrieve(chat_id, effective_text)

    # Resume injection: first post-restart message per chat_id gets previous session context
    if _SESSION_KEY:
        with _resumed_lock:
            already_resumed = chat_id in _resumed
            if not already_resumed:
                _resumed.add(chat_id)
        if not already_resumed:
            resume = sessions.get_resume_context(chat_id, _SESSION_KEY)
            if resume:
                memory_context = resume + "\n\n" + memory_context

    model_name = router.route(effective_text, intent=intent, has_image=has_image)
    t0    = time.monotonic()
    reply = llm.chat(history, effective_text, has_image=has_image,
                     model=model_name, memory_context=memory_context)
    elapsed_ms = (time.monotonic() - t0) * 1000

    success = not any(reply.startswith(e) for e in _OLLAMA_ERROR_PREFIXES)
    task_type = "vision" if has_image else (
        router.INTENT_TO_TASK.get(intent, "chat") if intent else "chat"
    )
    router.record_result(model_name, task_type, elapsed_ms, success=success)

    send(chat_id, reply)
    _memory.ingest_async(chat_id, "assistant", reply)


def dispatch_conversation(chat_id: str, effective_text: str,
                          has_image: bool = False, intent: str = None):
    t = threading.Thread(
        target=_conversation_thread,
        args=(chat_id, effective_text, has_image, intent),
        daemon=True
    )
    t.start()


# ── Reference ingest handler (runs in thread) ─────────────────────────────────

def _reference_thread(chat_id: str, text: str):
    """Ingest URLs found in text, send summaries, then do a conversational follow-up."""
    summaries = refs.ingest_urls_in_message(chat_id, text)
    for summary in summaries:
        send(chat_id, summary)
        db.save_message(chat_id, "assistant", summary)

    # If there was also a question beyond just the URL, answer it
    url_stripped = re.sub(r'https?://[^\s]+', '', text).strip()
    if url_stripped and len(url_stripped) > 10:
        # User said something alongside the URL — answer conversationally
        context_note = f"[Reference ingested from URL in message]\n{url_stripped}"
        dispatch_conversation(chat_id, context_note)


def dispatch_reference_ingest(chat_id: str, text: str):
    t = threading.Thread(
        target=_reference_thread,
        args=(chat_id, text),
        daemon=True
    )
    t.start()


def _scout_thread(chat_id: str, text: str):
    """Background thread for Twitter scout pipeline."""
    scout.handle_scout_links(chat_id, text, send)


# ── Build task dispatcher ─────────────────────────────────────────────────────

def dispatch_build_task(chat_id: str, text: str, classification=None):
    packet_path = build_task_packet(text, classification=classification)
    print(f"[dispatcher] Created packet: {packet_path}")
    send(chat_id, f"Build task queued: {packet_path.stem}\nStarting pipeline...")
    db.save_message(chat_id, "assistant",
                    f"Build task queued: {packet_path.stem}")
    log_file = open(f"/tmp/openclaw-task-{packet_path.stem}.log", "w")
    subprocess.Popen(
        ["bash", str(OPENCLAW_ROOT / "scripts" / "run-task-and-reply.sh"),
         str(packet_path), chat_id],
        stdout=log_file, stderr=log_file
    )


# ── Main message handler ──────────────────────────────────────────────────────

def handle_message(msg: dict):
    chat_id  = str(msg.get("chat", {}).get("id", ""))
    user_id  = str(msg.get("from", {}).get("id", ""))
    text     = msg.get("text", "").strip()
    msg_id   = msg.get("message_id")

    if user_id not in ALLOWED_USERS:
        print(f"[dispatcher] Ignored from non-allowed user {user_id}")
        return

    # ── CodeMonkeyClaw relay (🐒 prefix or /monkey command) ─────────────────
    if text and (text.startswith("\U0001f412") or text.lower().startswith("/monkey ")):
        relay_text = text[1:].strip() if text.startswith("\U0001f412") else text[8:].strip()
        _write_inbox(_CODEMONKEY_INBOX, chat_id, user_id, msg_id, relay_text or text)
        print(f"[dispatcher] CodeMonkeyClaw relay: {(relay_text or text)[:80]}")
        ack = "🐒 Relayed to CodeMonkeyClaw."
        if _MONKEY_BOT_ACTIVE:
            send_monkey(chat_id, ack)
        else:
            send(chat_id, ack)
        return

    # ── RivalClaw relay (🥊 prefix or /rival command) ────────────────────────
    if text and (text.startswith("\U0001f94a") or text.lower().startswith("/rival ")):
        relay_text = text[1:].strip() if text.startswith("\U0001f94a") else text[7:].strip()
        _write_inbox(_RIVALCLAW_INBOX, chat_id, user_id, msg_id, relay_text or text)
        print(f"[dispatcher] RivalClaw relay: {(relay_text or text)[:80]}")
        send(chat_id, "🥊 Relayed to RivalClaw.")
        return

    # ── QuantumentalClaw relay (🧪 prefix or /quant command) ─────────────────
    if text and (text.startswith("\U0001f9ea") or text.lower().startswith("/quant ")):
        relay_text = text[1:].strip() if text.startswith("\U0001f9ea") else text[7:].strip()
        _write_inbox(_QUANT_INBOX, chat_id, user_id, msg_id, relay_text or text)
        print(f"[dispatcher] QuantumentalClaw relay: {(relay_text or text)[:80]}")
        send(chat_id, "🧪 Relayed to QuantumentalClaw.")
        return

    # ── 0. Twitter/X scout pre-route (runs before all other routing) ─────────
    if text and _TWITTER_RE.search(text):
        db.save_message(chat_id, "user", text, message_id=msg_id)
        t = threading.Thread(target=_scout_thread, args=(chat_id, text), daemon=True)
        t.start()
        return

    # ── 1. Existing ! shortcut commands (fast path, no DB save) ──────────────
    if text:
        lower = text.lower()
        if text.startswith("!swarm "):
            raw = text[7:].strip()
            task = re.sub(r'[\x00-\x1f\x7f]', '', raw)[:500]
            if not task:
                send(chat_id, "Usage: !swarm <task description>")
                return
            log_path = OPENCLAW_ROOT / "logs" / f"clawteam-{datetime.date.today()}.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a") as log_file:
                subprocess.Popen(
                    [sys.executable, str(CLAWTEAM), "--task", task, "--notify"],
                    stdout=log_file, stderr=log_file,
                    close_fds=True
                )
            send(chat_id, f"Swarm started. I'll ping you when it's done.\nTask: {task[:80]}...")
            return
        if text.startswith("!simulate "):
            topic = text[10:].strip()[:500]
            if not topic:
                send(chat_id, "Usage: !simulate <question>\nE.g. !simulate Should we enter the Open WebUI consulting market?")
                return
            send(chat_id, f"Running MiroFish simulation... ~3 min.\nTopic: {topic[:80]}")
            sim_script = str(OPENCLAW_ROOT / "scripts" / "mirofish-simulate.py")
            log_path = OPENCLAW_ROOT / "logs" / f"mirofish-{datetime.date.today()}.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a") as log_file:
                subprocess.Popen(
                    [sys.executable, sim_script, topic, "--notify"],
                    stdout=log_file, stderr=log_file,
                    close_fds=True
                )
            return
        if lower in ("!status", "/status"):
            handle_status(chat_id)
            return
        if lower in ("!claws", "/claws"):
            handle_claws(chat_id)
            return
        if lower in ("!queue", "/queue"):
            handle_queue(chat_id)
            return
        if lower in ("!help", "/help", "/start"):
            handle_help(chat_id)
            return

    # ── 2. /slash commands ────────────────────────────────────────────────────
    if text:
        lower = text.lower()
        if lower == "/forget":
            handle_forget(chat_id)
            return
        if lower == "/context":
            handle_context(chat_id)
            return
        if lower == "/references":
            handle_references(chat_id)
            return
        if lower == "/scout":
            send(chat_id, scout.generate_digest(chat_id))
            return
        if lower == "/scout clear":
            send(chat_id, "Scout queue clear is not yet implemented.")
            return
        if lower.startswith("/search"):
            query = text[len("/search"):].strip()
            if not query:
                send(chat_id, "Usage: /search <query>")
            else:
                handle_search(chat_id, query)
            return
        if lower.startswith("/browse ") or lower == "/browse":
            url = text[len("/browse"):].strip()
            if not url:
                send(chat_id, "Usage: /browse <url>")
            else:
                threading.Thread(target=handle_browse, args=(chat_id, url), daemon=True).start()
            return
        if lower.startswith("/screenshot ") or lower == "/screenshot":
            url = text[len("/screenshot"):].strip()
            if not url:
                send(chat_id, "Usage: /screenshot <url>")
            else:
                threading.Thread(target=handle_screenshot_url, args=(chat_id, url), daemon=True).start()
            return
        if lower == "/memory-stats":
            handle_memory_stats(chat_id)
            return
        if lower.startswith("/memory"):
            query = text[len("/memory"):].strip()
            handle_memory(chat_id, query)
            return
        if lower.startswith("/forget-memory"):
            layer = text[len("/forget-memory"):].strip() or "all"
            handle_forget_memory(chat_id, layer)
            return
        if lower.startswith("/remember "):
            args = text[len("/remember "):].strip()
            handle_remember(chat_id, args)
            return
        if lower.startswith("/audit "):
            skill_arg = text[len("/audit "):].strip()
            handle_audit_skill(chat_id, skill_arg)
            return
        if lower == "/skills":
            handle_skills_list(chat_id)
            return
        if lower.startswith("/block "):
            skill_arg = text[len("/block "):].strip()
            handle_skill_block(chat_id, skill_arg)
            return
        if lower.startswith("/approve-proc"):
            proc_id_str = text[len("/approve-proc"):].strip()
            handle_approve_proc(chat_id, proc_id_str)
            return
        if lower.startswith("/reject-proc"):
            proc_id_str = text[len("/reject-proc"):].strip()
            handle_reject_proc(chat_id, proc_id_str)
            return
        if lower.startswith("/approve"):
            raw = text.strip()
            if raw.lower().startswith("/approve-"):
                task_id = raw[len("/approve-"):].split()[0].strip()
            else:
                parts   = raw.split(None, 1)
                task_id = parts[1].split()[0].strip() if len(parts) > 1 else ""
            if not task_id:
                send(chat_id, "Usage: /approve <task_id>")
            else:
                handle_approve(task_id, chat_id)
            return
        if lower.startswith("/papers"):
            topic = text[len("/papers"):].strip()
            handle_papers(chat_id, topic)
            return
        if lower.startswith("/digest ") or lower == "/digest":
            paper_id = text[len("/digest"):].strip()
            handle_digest(chat_id, paper_id)
            return
        if lower.startswith("/scholar"):
            subcommand = text[len("/scholar"):].strip()
            handle_scholar(chat_id, subcommand)
            return
        if lower == "/portfolio":
            handle_portfolio(chat_id)
            return
        if lower == "/pnl":
            handle_pnl(chat_id)
            return
        if lower == "/trades":
            handle_trades(chat_id)
            return
        if lower.startswith("/bet ") or lower == "/bet":
            bet_args = text[len("/bet"):].strip()
            handle_bet(chat_id, bet_args)
            return
        if lower.startswith("/research ") or lower == "/research":
            topic = text[len("/research"):].strip()
            handle_research(chat_id, topic)
            return
        if lower.startswith("/buzz ") or lower == "/buzz":
            topic = text[len("/buzz"):].strip()
            handle_buzz(chat_id, topic)
            return
        if lower.startswith("/r30 ") or lower == "/r30":
            topic = text[len("/r30"):].strip()
            handle_research(chat_id, topic)
            return
        if lower.startswith("/last30 ") or lower == "/last30":
            topic = text[len("/last30"):].strip()
            handle_buzz(chat_id, topic)
            return

    # ── 3. Process media if present ───────────────────────────────────────────
    media_path, media_content, has_image = media.handle_message_media(msg)

    # Skip entirely if no text and no media
    if not text and not media_content:
        return

    # Build effective message from text + media content
    parts = []
    if text:
        parts.append(text)
    if media_content:
        parts.append(f"[Attached content]:\n{media_content}")
    effective_text = "\n\n".join(parts)
    display_text   = text or f"[Media: {media_path or 'attached'}]"

    print(f"[dispatcher] {user_id}: {display_text[:80]}")

    # ── 4. Save user message ──────────────────────────────────────────────────
    media_type = None
    if "photo" in msg:
        media_type = "photo"
    elif "document" in msg:
        media_type = "document"
    elif "voice" in msg:
        media_type = "voice"
    elif "audio" in msg:
        media_type = "audio"

    db.save_message(chat_id, "user", effective_text,
                    message_id=msg_id, media_type=media_type)
    _memory._sensory.push(chat_id, "user", effective_text)

    # ── 5. Classify and route (LLM-powered, regex fallback) ─────────────────
    # Media messages (image/audio/doc content) always go to conversation,
    # with the extracted content as context.
    if media_content and not intents.has_url(text):
        dispatch_conversation(chat_id, effective_text, has_image=has_image)
        return

    # Check if this is a reply to a pending clarification
    pending = _pending_clarifications.pop(chat_id, None)
    if pending:
        # Combine original message + this reply for re-classification
        combined = f"{pending['original_text']}\n[Clarification: {effective_text}]"
        history = db.get_history(chat_id, limit=3)
        result = intents.classify(combined, history=history)
        result["_clarification_context"] = effective_text
        # If still unclear, just treat as conversation — don't loop
        if result["intent"] == intents.UNCLEAR:
            result["intent"] = intents.CONVERSATION
        effective_text = combined
    else:
        history = db.get_history(chat_id, limit=3)
        result = intents.classify(effective_text, history=history)

    intent = result["intent"]
    print(f"[dispatcher] intent={intent} confidence={result.get('confidence', '?')} "
          f"source={result.get('_source', '?')}")

    # Track procedure candidates for auto-learning
    action = result.get("action")
    if intent == intents.BUILD_TASK and action:
        _memory.track_procedure_candidate(
            chat_id, intent, action, effective_text[:100]
        )

    # ── UNCLEAR: ask one clarifying question, then wait ───────────────────
    if intent == intents.UNCLEAR and result.get("needs_clarification"):
        question = result.get("suggested_question", "Can you be more specific?")
        send(chat_id, question)
        db.save_message(chat_id, "assistant", question)
        _pending_clarifications[chat_id] = {
            "original_text": effective_text,
            "question": question,
            "timestamp": time.time()
        }
        return

    # ── Route by intent ───────────────────────────────────────────────────
    if intent == intents.STATUS_QUERY:
        handle_status(chat_id)
        pending_tasks = list(QUEUE_DIR.glob("task-*.json")) if QUEUE_DIR.exists() else []
        if pending_tasks:
            send(chat_id, f"Queue: {len(pending_tasks)} task(s) pending. Send !queue for details.")
        return

    if intent == intents.DIRECT_COMMAND:
        handle_direct_command(chat_id, effective_text)
        return

    if intent == intents.BROWSER_TASK:
        url_list = result.get("attachments", [])
        target = result.get("target", "")
        url = url_list[0] if url_list else (target if target and target.startswith("http") else None)
        if url:
            threading.Thread(target=handle_browse, args=(chat_id, url), daemon=True).start()
        else:
            send(chat_id, "I can browse websites for you — what URL should I visit?")
        return

    if intent == intents.REFERENCE_INGEST:
        dispatch_reference_ingest(chat_id, effective_text)
        return

    if intent == intents.BUILD_TASK:
        dispatch_build_task(chat_id, effective_text, classification=result)
        return

    # Default: CONVERSATION
    dispatch_conversation(chat_id, effective_text, has_image=has_image, intent=intent)


# ── RivalClaw bot poll loop ───────────────────────────────────────────────────

def _monkey_bot_loop():
    """Background thread: poll @Codemonkeyclaw_bot and relay messages to CodeMonkeyClaw inbox."""
    if not _MONKEY_BOT_ACTIVE:
        print("[dispatcher] CODEMONKEY_BOT_TOKEN not set — monkey bot thread idle")
        return
    print("[dispatcher] CodeMonkeyClaw bot poll thread started")
    offset = load_monkey_offset()
    while True:
        if _SHUTDOWN_REQUESTED:
            return
        updates = get_monkey_updates(offset)
        for update in updates:
            offset = update["update_id"] + 1
            save_monkey_offset(offset)
            msg = update.get("message", {})
            if msg:
                try:
                    handle_monkey_bot_message(msg)
                except Exception as e:
                    print(f"[monkey-bot] Unhandled error: {e}")
        time.sleep(POLL_INTERVAL)


def _quant_bot_loop():
    """Background thread: poll @QuantiusMaximus_bot and relay messages to QuantumentalClaw inbox."""
    if not _QUANT_BOT_ACTIVE:
        print("[dispatcher] QUANTCLAW_BOT_TOKEN not set — quant bot thread idle")
        return
    print("[dispatcher] QuantumentalClaw bot poll thread started")
    offset = load_quant_offset()
    while True:
        if _SHUTDOWN_REQUESTED:
            return
        updates = get_quant_updates(offset)
        for update in updates:
            offset = update["update_id"] + 1
            save_quant_offset(offset)
            msg = update.get("message", {})
            if msg:
                try:
                    handle_quant_bot_message(msg)
                except Exception as e:
                    print(f"[quant-bot] Unhandled error: {e}")
        time.sleep(POLL_INTERVAL)


def _rival_bot_loop():
    """Background thread: poll @rivalclaw_bot and relay messages to RivalClaw inbox."""
    if not _RIVAL_ACTIVE:
        print("[dispatcher] RIVALCLAW_BOT_TOKEN not set — rival bot thread idle")
        return
    print("[dispatcher] RivalClaw bot poll thread started")
    offset = load_rival_offset()
    while True:
        if _SHUTDOWN_REQUESTED:
            return
        updates = get_rival_updates(offset)
        for update in updates:
            offset = update["update_id"] + 1
            save_rival_offset(offset)
            msg = update.get("message", {})
            if msg:
                try:
                    handle_rival_bot_message(msg)
                except Exception as e:
                    print(f"[rival-bot] Unhandled error: {e}")
        time.sleep(POLL_INTERVAL)


# ── Main loop ─────────────────────────────────────────────────────────────────

def _signal_handler(sig, frame):
    """Set shutdown flag — called from signal handler context (async-signal-safe)."""
    global _SHUTDOWN_REQUESTED
    _SHUTDOWN_REQUESTED = True


def _shutdown():
    """Clean shutdown: end all sessions, then exit. Called from main thread only."""
    if _SESSION_KEY:
        sessions.end_all_sessions(_SESSION_KEY)
    sys.exit(0)


def main():
    global _SESSION_KEY
    _SESSION_KEY = sessions.start_session()
    print(f"[dispatcher] Session key: {_SESSION_KEY}")

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT,  _signal_handler)

    print(f"[dispatcher] Starting Clawmson. Allowed users: {ALLOWED_USERS}")
    print(f"[dispatcher] Default repo: {DEFAULT_REPO} @ {DEFAULT_REPO_PATH}")
    print(f"[dispatcher] Ollama: {os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434')}"
          f" / model routing active")
    rival_status = "active" if _RIVAL_ACTIVE else "no token (set RIVALCLAW_BOT_TOKEN in .env)"
    quant_status   = "active" if _QUANT_BOT_ACTIVE else "no token (set QUANTCLAW_BOT_TOKEN in .env)"
    monkey_status  = "active" if _MONKEY_BOT_ACTIVE else "no token (set CODEMONKEY_BOT_TOKEN in .env)"
    print(f"[dispatcher] RivalClaw bot (@rivalclaw_bot): {rival_status}")
    print(f"[dispatcher] QuantumentalClaw bot (@QuantiusMaximus_bot): {quant_status}")
    print(f"[dispatcher] CodeMonkeyClaw bot (@Codemonkeyclaw_bot): {monkey_status}")

    # Start sub-bot polling threads (one per claw)
    threading.Thread(target=_rival_bot_loop,  daemon=True, name="rival-bot-poll").start()
    threading.Thread(target=_quant_bot_loop,  daemon=True, name="quant-bot-poll").start()
    threading.Thread(target=_monkey_bot_loop, daemon=True, name="monkey-bot-poll").start()

    offset = load_offset()

    while True:
        if _SHUTDOWN_REQUESTED:
            _shutdown()
        updates = get_updates(offset)
        for update in updates:
            offset = update["update_id"] + 1
            save_offset(offset)
            msg = update.get("message", {})
            if msg:
                try:
                    handle_message(msg)
                except Exception as e:
                    print(f"[dispatcher] Unhandled error: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
