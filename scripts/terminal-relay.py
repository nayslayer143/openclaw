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

_ANSI_RE = re.compile(
    r"\x1b\[[0-9;]*[a-zA-Z]"       # CSI sequences (colors, cursor)
    r"|\x1b\].*?\x07"              # OSC sequences (title sets)
    r"|\x1b[()][AB012]"            # Character set selection
    r"|\x1b\[\??[0-9;]*[hl]"      # Mode set/reset
)

def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)

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

def _git(args, cwd, timeout=3, default=""):
    try:
        r = subprocess.run(["git"] + args, capture_output=True, text=True, cwd=cwd, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else default
    except Exception:
        return default

def get_git_branch(cwd): return _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd) or "unknown"
def get_git_diff_stat(cwd): return _git(["diff", "--stat"], cwd, timeout=5)
def get_changed_files(cwd):
    out = _git(["diff", "--name-only"], cwd, timeout=5)
    return [f for f in out.splitlines() if f] if out else []

def _tmux(args, timeout=3):
    try:
        r = subprocess.run(["tmux"] + args, capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else None
    except Exception:
        return None

def list_tmux_sessions():
    out = _tmux(["list-sessions", "-F", "#{session_name}:#{session_windows}"])
    if not out: return []
    sessions = []
    for line in out.strip().splitlines():
        if ":" in line:
            name, windows = line.rsplit(":", 1)
            sessions.append({"name": name, "windows": int(windows)})
    return sessions

def list_panes(session):
    fmt = "#{pane_index}:#{pane_id}:#{pane_current_command}:#{pane_current_path}"
    out = _tmux(["list-panes", "-t", session, "-F", fmt])
    if not out: return []
    panes = []
    for line in out.strip().splitlines():
        parts = line.split(":", 3)
        if len(parts) >= 4:
            panes.append({"index": int(parts[0]), "id": parts[1],
                          "command": parts[2], "cwd": parts[3]})
    return panes

def capture_pane(session, pane=None):
    target = f"{session}.{pane}" if pane is not None else session
    return _tmux(["capture-pane", "-p", "-t", target], timeout=5) or ""

class TerminalRelay:
    def __init__(self, session, pane=None):
        self.session, self.pane = session, pane
        self.previous_capture, self.buffer = "", []
        self.env_values = load_env_values()
        self.running, self.last_change_time, self.event_count = True, time.time(), 0

    def capture(self): return strip_ansi(capture_pane(self.session, self.pane))

    def diff(self, current):
        if current == self.previous_capture: return None
        prev, curr = self.previous_capture.splitlines(), current.splitlines()
        if len(curr) > len(prev): return "\n".join(curr[len(prev):])
        return current if curr != prev else None

    def update_buffer(self, text):
        self.buffer.extend(text.splitlines())
        if len(self.buffer) > BUFFER_SIZE: self.buffer = self.buffer[-BUFFER_SIZE:]

    def get_pane_cwd(self):
        target = str(self.pane or "0")
        for p in list_panes(self.session):
            if str(p["index"]) == target: return p["cwd"]
        return str(OPENCLAW_ROOT)

    def build_event(self, event_type, output):
        cwd = self.get_pane_cwd()
        tail = output.splitlines()[-TAIL_SIZE:]
        return {"timestamp": datetime.now().isoformat(), "session": self.session,
                "pane": self.pane or "0", "event_type": event_type, "command": "",
                "exit_code": None, "duration_ms": None, "cwd": cwd,
                "branch": get_git_branch(cwd),
                "output_tail": [redact_secrets(l, self.env_values) for l in tail],
                "summary": redact_secrets(extract_summary(output, event_type), self.env_values)}

    def write_event(self, event):
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a") as f: f.write(json.dumps(event) + "\n")
        self.event_count += 1

    def snapshot(self):
        output = "\n".join(self.buffer[-100:])
        event = self.build_event("user_snapshot", output)
        event["output_tail"] = [redact_secrets(l, self.env_values) for l in self.buffer[-100:]]
        self.write_event(event)
        return event

    def write_pid(self):
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text(str(os.getpid()))

    def cleanup_pid(self):
        try:
            if PID_FILE.exists() and int(PID_FILE.read_text().strip()) == os.getpid():
                PID_FILE.unlink()
        except Exception: pass

    def run(self):
        self.write_pid()
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, "running", False))
        signal.signal(signal.SIGINT, lambda *_: setattr(self, "running", False))

        label = f"{self.session}" + (f".{self.pane}" if self.pane else "")
        print(f"[terminal-relay] Watching {label} | PID {os.getpid()}")

        while self.running:
            try:
                current = self.capture()
                new_content = self.diff(current)

                if new_content:
                    self.last_change_time = time.time()
                    self.update_buffer(new_content)

                    event_type = detect_event_type(new_content)
                    if event_type:
                        event = self.build_event(event_type, new_content)
                        self.write_event(event)
                        print(f"[terminal-relay] {event_type}: {event['summary'][:80]}")

                    # Prompt reappeared → command finished
                    last_line = new_content.strip().splitlines()[-1] if new_content.strip() else ""
                    if last_line.rstrip().endswith(("$ ", "% ", "> ")):
                        event = self.build_event("command_finished", new_content)
                        self.write_event(event)
                else:
                    elapsed = time.time() - self.last_change_time
                    if elapsed > STALL_TIMEOUT:
                        event = self.build_event("stalled", "\n".join(self.buffer[-TAIL_SIZE:]))
                        self.write_event(event)
                        self.last_change_time = time.time()

                self.previous_capture = current
                time.sleep(POLL_INTERVAL)

                # Check for snapshot trigger from API
                trigger = LOGS_DIR / "terminal-snapshot-trigger"
                if trigger.exists():
                    try:
                        self.snapshot()
                        trigger.unlink(missing_ok=True)
                        print("[terminal-relay] Snapshot triggered via API")
                    except Exception as e:
                        print(f"[terminal-relay] Snapshot error: {e}", file=sys.stderr)
            except Exception as e:
                print(f"[terminal-relay] Error: {e}", file=sys.stderr)
                time.sleep(POLL_INTERVAL)

        self.cleanup_pid()
        print("[terminal-relay] Stopped.")
def stop_relay():
    if not PID_FILE.exists():
        print("[terminal-relay] No PID file — not running?"); return
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        print(f"[terminal-relay] Sent SIGTERM to PID {pid}")
        PID_FILE.unlink(missing_ok=True)
    except ProcessLookupError:
        print("[terminal-relay] Stale PID file — cleaning up")
        PID_FILE.unlink(missing_ok=True)
    except Exception as e:
        print(f"[terminal-relay] Error stopping: {e}")

def main():
    ap = argparse.ArgumentParser(description="Terminal Watch relay")
    ap.add_argument("--session", help="tmux session name")
    ap.add_argument("--pane", help="pane index")
    ap.add_argument("--list", action="store_true", help="list tmux sessions")
    ap.add_argument("--stop", action="store_true", help="stop running relay")
    args = ap.parse_args()
    if args.list:
        for s in (list_tmux_sessions() or [print("No tmux sessions found.")] and []):
            print(f"  {s['name']} ({s['windows']} windows)")
            for p in list_panes(s["name"]):
                print(f"    pane {p['index']} ({p['id']}): {p['command']} @ {p['cwd']}")
        return
    if args.stop: stop_relay(); return
    if not args.session: ap.print_help(); sys.exit(1)
    TerminalRelay(args.session, args.pane).run()

if __name__ == "__main__":
    main()
