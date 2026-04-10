#!/usr/bin/env python3
"""
claw-session-manager.py — Daemon that monitors claw tmux sessions.

Runs every 5 seconds, checks health of each claw instance, auto-reboots
on token exhaustion / crash / stall / tmux death. Writes state to
~/.openclaw/claw-sessions.json and health events to
~/.openclaw/claw-health-log.jsonl.

PID file: ~/.openclaw/claw-session-manager.pid
"""

import json
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

HOME = Path.home()
STATE_DIR = HOME / ".openclaw"
STATE_FILE = STATE_DIR / "claw-sessions.json"
HEALTH_LOG = STATE_DIR / "claw-health-log.jsonl"
SNAPSHOT_DIR = STATE_DIR / "snapshots"
PID_FILE = STATE_DIR / "claw-session-manager.pid"

POLL_INTERVAL = 5        # seconds
STALL_TIMEOUT = 14400    # 4 hours — Claude Code idles silently; never kill a healthy session
STALL_PROBE_WAIT = 600   # 10 minutes after probe before kill

# Hardcoded claw definitions: session_name -> workdir
CLAWS = {
    "claw-clawmpson": str(HOME / "openclaw"),
    "claw-rival":     str(HOME / "rivalclaw"),
    "claw-quant":     str(HOME / "quantumentalclaw"),
    "claw-monkey":    str(HOME / "codemonkeyclaw"),
}

# Map session names to friendly names (for state file keys)
SESSION_TO_NAME = {
    "claw-clawmpson": "clawmpson",
    "claw-rival":     "rival",
    "claw-quant":     "quant",
    "claw-monkey":    "monkey",
}

# ---------------------------------------------------------------------------
# PATH fix — ensure homebrew bin is reachable when started with minimal env
# (e.g. via nohup/launchd which provides only PATH=/usr/bin:/bin)
# ---------------------------------------------------------------------------

for _p in ("/opt/homebrew/bin", "/usr/local/bin"):
    if _p not in os.environ.get("PATH", "").split(":"):
        os.environ["PATH"] = _p + ":" + os.environ.get("PATH", "")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_DIR = HOME / "openclaw" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        # FileHandler only — no StreamHandler to avoid duplicate lines when
        # the process stdout is also redirected to this same log file by nohup.
        logging.FileHandler(LOG_DIR / "session-manager.log"),
    ],
)
log = logging.getLogger("claw-session-manager")

# ---------------------------------------------------------------------------
# Globals for graceful shutdown
# ---------------------------------------------------------------------------

running = True


def handle_signal(signum, frame):
    global running
    sig_name = signal.Signals(signum).name
    log.info(f"Received {sig_name} — shutting down gracefully")
    running = False


signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_cmd(cmd, timeout=10):
    """Run a shell command, return (returncode, stdout)."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return result.returncode, result.stdout.strip()
    except subprocess.TimeoutExpired:
        return -1, ""
    except Exception as e:
        return -1, str(e)


def tmux_session_exists(session):
    rc, _ = run_cmd(f"tmux has-session -t {session} 2>/dev/null")
    return rc == 0


def get_pane_pid(session):
    """Get the shell PID of pane 0 in the given tmux session."""
    rc, out = run_cmd(
        f"tmux list-panes -t {session} -F '#{{pane_pid}}' 2>/dev/null"
    )
    if rc == 0 and out:
        return out.split("\n")[0].strip()
    return None


def find_claude_pid(pane_pid):
    """Detect whether claude is running in the pane.

    Uses two complementary checks:
    1. pgrep on the pane PID's direct children AND grandchildren — covers the
       typical shell → wrapper → claude-electron tree.
    2. Falls back to checking the pane's current foreground command via the
       pane_pid → pane_id mapping (reliable even if claude re-execs).

    Returns a truthy string (PID) if claude is found, None otherwise.
    """
    if not pane_pid:
        return None

    # Direct children first (fast path, works when shell directly execs claude)
    rc, out = run_cmd(f"pgrep -P {pane_pid} -f claude 2>/dev/null")
    if rc == 0 and out:
        return out.split("\n")[0].strip()

    # Grandchildren — covers shell → node/wrapper → claude-electron
    rc2, children = run_cmd(f"pgrep -P {pane_pid} 2>/dev/null")
    if rc2 == 0 and children:
        for child in children.split("\n"):
            child = child.strip()
            if not child:
                continue
            rc3, out3 = run_cmd(f"pgrep -P {child} -f claude 2>/dev/null")
            if rc3 == 0 and out3:
                return out3.split("\n")[0].strip()

    # Last resort: ask tmux what the foreground command is for this pane_pid
    rc4, pane_id = run_cmd(
        f"tmux list-panes -a -F '#{{pane_pid}} #{{pane_id}}' 2>/dev/null"
        f" | awk '$1==\"{pane_pid}\" {{print $2; exit}}'"
    )
    if rc4 == 0 and pane_id:
        rc5, cmd = run_cmd(
            f"tmux display-message -t {pane_id} -p '#{{pane_current_command}}' 2>/dev/null"
        )
        if rc5 == 0 and "claude" in cmd.lower():
            return pane_pid  # Return pane_pid as a stand-in PID

    return None


def capture_pane(session, lines=300):
    """Capture the last N lines from the tmux pane."""
    rc, out = run_cmd(
        f"tmux capture-pane -t {session} -p -S -{lines} 2>/dev/null"
    )
    return out if rc == 0 else ""


def detect_token_exhaustion(pane_content):
    """Check if the pane shows signs of token/context exhaustion."""
    indicators = [
        "context window",
        "token limit",
        "maximum context",
        "conversation is too long",
        "exceeded the maximum",
        "ran out of tokens",
        "context length exceeded",
    ]
    lower = pane_content.lower()
    return any(ind in lower for ind in indicators)


def detect_crash(pane_content):
    """Check if the pane shows signs of a claude crash."""
    indicators = [
        "error: unexpected",
        "fatal error",
        "segmentation fault",
        "panic:",
        "unhandled exception",
        "claude exited",
    ]
    lower = pane_content.lower()
    return any(ind in lower for ind in indicators)


def save_snapshot(name, pane_content, reason):
    """Save a snapshot of the pane content for post-mortem analysis."""
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"claw-{name}-{ts}.md"
    filepath = SNAPSHOT_DIR / filename

    header = f"# Snapshot: {name}\n"
    header += f"- **Timestamp:** {now_iso()}\n"
    header += f"- **Reason:** {reason}\n"
    header += f"---\n\n"

    filepath.write_text(header + pane_content)
    log.info(f"[{name}] snapshot saved → {filepath}")
    return str(filepath)


def log_health_event(name, event_type, details=None):
    """Append a health event to the JSONL log."""
    entry = {
        "timestamp": now_iso(),
        "claw": name,
        "event": event_type,
    }
    if details:
        entry["details"] = details

    with open(HEALTH_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def kill_claude_in_session(session):
    """Send Ctrl-C then wait, as a graceful stop for claude in tmux."""
    run_cmd(f"tmux send-keys -t {session} C-c 2>/dev/null")
    time.sleep(2)
    # If still running, force kill the process
    pane_pid = get_pane_pid(session)
    claude_pid = find_claude_pid(pane_pid)
    if claude_pid:
        run_cmd(f"kill -9 {claude_pid} 2>/dev/null")
        time.sleep(1)


def restart_claude(session, name, resume_flag=""):
    """Launch claude in the tmux session, optionally with a resume hint."""
    cmd = "claude"
    if resume_flag:
        cmd += f" --resume"
    tmux_cmd = f'tmux send-keys -t {session} "{cmd}" Enter'
    run_cmd(tmux_cmd)
    log.info(f"[{name}] claude restarted in session '{session}'")


def create_tmux_session(session, workdir):
    """Create a new tmux session."""
    run_cmd(f"tmux new-session -d -s {session} -c {workdir} -x 200 -y 50")


# ---------------------------------------------------------------------------
# Scratch session discovery
# ---------------------------------------------------------------------------


def discover_scratch_sessions():
    """Find dynamically created claw-scratch-* tmux sessions."""
    rc, out = run_cmd("tmux list-sessions -F '#{session_name}' 2>/dev/null")
    if rc != 0 or not out:
        return {}

    scratch = {}
    for line in out.split("\n"):
        session = line.strip()
        if session.startswith("claw-scratch-"):
            # Try to get the workdir from the pane's current path
            rc2, wd = run_cmd(
                f"tmux display-message -t {session} -p '#{{pane_current_path}}' 2>/dev/null"
            )
            workdir = wd if rc2 == 0 and wd else str(HOME)
            scratch[session] = workdir
    return scratch


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def ensure_state_entry(state, name, session, workdir):
    """Ensure a state entry exists for the given claw."""
    if name not in state:
        state[name] = {
            "session": session,
            "workdir": workdir,
            "status": "unknown",
            "pid": None,
            "started": None,
            "tokenUsage": None,
            "lastOutput": None,
            "reboots": 0,
            "lastRebootReason": None,
        }
    return state[name]


# ---------------------------------------------------------------------------
# Main monitor loop
# ---------------------------------------------------------------------------


def monitor_claw(name, session, workdir, state):
    """Check and manage a single claw instance. Returns updated state entry."""
    entry = ensure_state_entry(state, name, session, workdir)
    entry["session"] = session
    entry["workdir"] = workdir

    # ── Check 1: Does the workdir exist? ──
    if not os.path.isdir(workdir):
        entry["status"] = "no_workdir"
        return entry

    # ── Check 2: Does the tmux session exist? ──
    if not tmux_session_exists(session):
        log.warning(f"[{name}] tmux session '{session}' is dead — recreating")
        log_health_event(name, "tmux_died")
        create_tmux_session(session, workdir)
        time.sleep(1)
        restart_claude(session, name)
        entry["status"] = "restarting"
        entry["pid"] = None
        entry["started"] = now_iso()
        entry["reboots"] = entry.get("reboots", 0) + 1
        entry["lastRebootReason"] = "tmux_died"
        return entry

    # ── Check 3: Is claude running? ──
    pane_pid = get_pane_pid(session)
    claude_pid = find_claude_pid(pane_pid)

    if not claude_pid:
        # Claude is not running — check why
        pane_content = capture_pane(session, 300)

        if detect_token_exhaustion(pane_content):
            reason = "token_exhaustion"
            log.info(f"[{name}] token exhaustion detected — saving snapshot & restarting")
            save_snapshot(name, pane_content, reason)
            log_health_event(name, reason)
            restart_claude(session, name, resume_flag="--resume")
            entry["reboots"] = entry.get("reboots", 0) + 1
            entry["lastRebootReason"] = reason

        elif detect_crash(pane_content):
            reason = "crash"
            log.warning(f"[{name}] crash detected — saving snapshot & restarting")
            save_snapshot(name, pane_content, reason)
            log_health_event(name, reason)
            restart_claude(session, name)
            entry["reboots"] = entry.get("reboots", 0) + 1
            entry["lastRebootReason"] = reason

        else:
            reason = "process_exited"
            log.info(f"[{name}] claude not running — restarting")
            log_health_event(name, reason)
            restart_claude(session, name)
            entry["reboots"] = entry.get("reboots", 0) + 1
            entry["lastRebootReason"] = reason

        entry["status"] = "restarting"
        entry["pid"] = None
        entry["started"] = now_iso()
        return entry

    # Claude IS running
    entry["status"] = "running"
    entry["pid"] = int(claude_pid)

    # ── Check 4: Stall detection ──
    # Capture last line as a proxy for activity
    last_line = capture_pane(session, 1).strip()
    now_ts = time.time()

    # Track last-seen output change
    if last_line != entry.get("lastOutput"):
        entry["lastOutput"] = last_line
        entry["_lastOutputChange"] = now_ts
    else:
        last_change = entry.get("_lastOutputChange", now_ts)
        stall_duration = now_ts - last_change

        if stall_duration > STALL_TIMEOUT:
            probe_sent = entry.get("_probeSent", 0)

            if now_ts - probe_sent > STALL_PROBE_WAIT and probe_sent > 0:
                # Already probed and still stalled — kill and restart
                log.warning(
                    f"[{name}] stalled for {stall_duration:.0f}s "
                    f"(probe sent {now_ts - probe_sent:.0f}s ago) — killing"
                )
                pane_content = capture_pane(session, 300)
                save_snapshot(name, pane_content, "stall")
                log_health_event(name, "stall_restart", {
                    "stallDuration": round(stall_duration),
                })
                kill_claude_in_session(session)
                time.sleep(2)
                restart_claude(session, name, resume_flag="--resume")
                entry["status"] = "restarting"
                entry["pid"] = None
                entry["started"] = now_iso()
                entry["reboots"] = entry.get("reboots", 0) + 1
                entry["lastRebootReason"] = "stall"
                entry["_probeSent"] = 0
                entry["_lastOutputChange"] = now_ts

            elif probe_sent == 0 or (now_ts - probe_sent > STALL_PROBE_WAIT):
                # Send a probe (newline) to see if it's actually stuck
                log.info(
                    f"[{name}] no output for {stall_duration:.0f}s — sending probe"
                )
                run_cmd(f"tmux send-keys -t {session} '' Enter 2>/dev/null")
                entry["_probeSent"] = now_ts
                log_health_event(name, "stall_probe", {
                    "stallDuration": round(stall_duration),
                })

    return entry


def main_loop():
    """Main monitoring loop."""
    log.info("Session manager started")

    # In-memory state that persists internal tracking keys (_lastOutputChange,
    # _probeSent) across poll cycles.  Disk state is loaded once at startup;
    # after that we only *write* to disk — never clobber in-memory keys.
    mem_state = load_state()

    while running:
        # Merge any disk-side changes (e.g. bootstrap wrote new entries)
        disk_state = load_state()
        for k, v in disk_state.items():
            if k not in mem_state:
                mem_state[k] = v
            else:
                # Keep internal keys from mem_state, update public keys from disk
                for dk, dv in v.items():
                    if not dk.startswith("_"):
                        mem_state[k][dk] = dv

        # Monitor hardcoded claws
        for session, workdir in CLAWS.items():
            name = SESSION_TO_NAME.get(session, session)
            mem_state[name] = monitor_claw(name, session, workdir, mem_state)

        # Discover and monitor scratch sessions
        scratch_sessions = discover_scratch_sessions()
        for session, workdir in scratch_sessions.items():
            name = session  # Use session name as the key for scratch
            mem_state[name] = monitor_claw(name, session, workdir, mem_state)

        # Write clean state to disk (strip internal tracking keys)
        clean_state = {}
        for k, v in mem_state.items():
            clean_entry = {
                dk: dv for dk, dv in v.items() if not dk.startswith("_")
            }
            clean_state[k] = clean_entry

        save_state(clean_state)

        # Sleep in small increments so we can respond to signals quickly
        for _ in range(POLL_INTERVAL * 2):
            if not running:
                break
            time.sleep(0.5)

    log.info("Session manager stopped")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    # Write PID file
    PID_FILE.write_text(str(os.getpid()))
    log.info(f"PID {os.getpid()} written to {PID_FILE}")

    try:
        main_loop()
    finally:
        # Clean up PID file on exit
        if PID_FILE.exists():
            try:
                stored_pid = int(PID_FILE.read_text().strip())
                if stored_pid == os.getpid():
                    PID_FILE.unlink()
                    log.info("PID file removed")
            except (ValueError, OSError):
                pass
