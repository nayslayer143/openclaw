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

# ── Config ────────────────────────────────────────────────────────────────────

OPENCLAW_ROOT  = Path.home() / "openclaw"
ENV_FILE       = OPENCLAW_ROOT / ".env"
QUEUE_DIR      = OPENCLAW_ROOT / "repo-queue"
BUILD_RESULTS  = OPENCLAW_ROOT / "build-results"
RUN_TASK       = OPENCLAW_ROOT / "scripts" / "run-task.sh"
POLL_INTERVAL  = 5   # seconds
_TWITTER_RE = scout.TWITTER_RE  # shared with clawmson_scout — single source of truth
OFFSET_FILE    = Path("/tmp/openclaw-tg-offset.txt")

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
        "!queue           — pending task packets\n"
        "!help            — this message\n\n"
        "Commands:\n"
        "/approve <id>    — merge a passing build into main\n"
        "/forget          — clear conversation history\n"
        "/context         — show persistent notes\n"
        "/references      — list saved links\n"
        "/scout              — digest of recently scouted Twitter links\n"
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
    history        = _memory.sensory(chat_id)
    memory_context = _memory.retrieve(chat_id, effective_text)
    model_name     = router.route(effective_text, intent=intent, has_image=has_image)
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

    # ── 0. Twitter/X scout pre-route (runs before all other routing) ─────────
    if text and _TWITTER_RE.search(text):
        db.save_message(chat_id, "user", text, message_id=msg_id)
        t = threading.Thread(target=_scout_thread, args=(chat_id, text), daemon=True)
        t.start()
        return

    # ── 1. Existing ! shortcut commands (fast path, no DB save) ──────────────
    if text:
        lower = text.lower()
        if lower in ("!status", "/status"):
            handle_status(chat_id)
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

    if intent == intents.REFERENCE_INGEST:
        dispatch_reference_ingest(chat_id, effective_text)
        return

    if intent == intents.BUILD_TASK:
        dispatch_build_task(chat_id, effective_text, classification=result)
        return

    # Default: CONVERSATION
    dispatch_conversation(chat_id, effective_text, has_image=has_image, intent=intent)


# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    print(f"[dispatcher] Starting Clawmson. Allowed users: {ALLOWED_USERS}")
    print(f"[dispatcher] Default repo: {DEFAULT_REPO} @ {DEFAULT_REPO_PATH}")
    print(f"[dispatcher] Ollama: {os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434')}"
          f" / model routing active")
    offset = load_offset()

    while True:
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
