# Terminal Watch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Terminal Watch subsystem to the Gonzoclaw dashboard — a relay script captures tmux output and detects events, new server.py endpoints expose event data and SSE streaming, and a new frontend panel provides session controls, live event feed, and clipboard-first packet export for ChatGPT/Claude.

**Architecture:** Three components extending the existing Gonzoclaw stack: (1) standalone relay script (`scripts/terminal-relay.py`) polls tmux every 2s, strips ANSI, redacts secrets, detects events, writes to `logs/terminal-watch.jsonl`; (2) 8 new FastAPI endpoints in `dashboard/server.py` for relay management, event access, SSE streaming, and packet building; (3) new "Terminal Watch" panel in `dashboard/index.html` matching existing dark terminal aesthetic with session controls, live event feed, and clipboard copy.

**Tech Stack:** Python stdlib only (relay), FastAPI + existing JWT auth (server), vanilla JS (frontend)

**Line Budget:** relay ≤300, server endpoints ≤200, frontend panel ≤400, total <900 new lines

**Branch:** `feat/terminal-watch` (per CONSTRAINTS.md)

**Key files to reference (read-only):**
- `~/openclaw/dashboard/server.py` — existing FastAPI patterns (SSE at lines 256-298, auth at 62-88, config constants at 18-55, subprocess at 316-366, SQLite at 904-910)
- `~/openclaw/dashboard/index.html` — existing panel patterns (CSS vars at lines 12-31, panel structure at 236-253, SSE JS at 2305-2338, trading SSE at 4011-4025, button styles at 97-108/522-533/692-705)
- `~/openclaw/scripts/mirofish/polymarket_feed.py:13` — gamma API URL
- `~/openclaw/scripts/mirofish/trading_brain.py:63-76` — Kelly criterion reference
- `~/openclaw/scripts/mirofish/paper_wallet.py:19-23` — fee/execution sim reference

---

## File Structure

| Action | File | Responsibility | Lines |
|--------|------|----------------|-------|
| Create | `scripts/terminal-relay.py` | Standalone tmux poller + event detector + JSONL logger | ≤300 |
| Create | `scripts/tests/test_terminal_relay.py` | Unit tests for relay pure functions | ~120 |
| Modify | `dashboard/server.py` | Add 8 `/api/terminal/*` endpoints + 3 config constants | ≤200 added |
| Modify | `dashboard/index.html` | Add Terminal Watch panel (CSS + HTML + JS) | ≤400 added |

---

## Task 1: Project Setup

**Files:**
- Create branch: `feat/terminal-watch`
- Create: `scripts/tests/__init__.py`
- Create: `scripts/tests/test_terminal_relay.py`

- [ ] **Step 1: Create feature branch**

```bash
cd ~/openclaw && git checkout -b feat/terminal-watch
```

- [ ] **Step 2: Create test directory and skeleton**

```bash
mkdir -p ~/openclaw/scripts/tests
touch ~/openclaw/scripts/tests/__init__.py
```

- [ ] **Step 3: Write test skeleton**

Create `scripts/tests/test_terminal_relay.py`:

```python
"""Tests for terminal-relay.py pure functions."""
import sys
from pathlib import Path

# Add scripts dir to path so we can import terminal-relay as a module
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestStripAnsi:
    """ANSI escape sequence removal."""
    pass


class TestRedactSecrets:
    """Secret/credential redaction."""
    pass


class TestDetectEventType:
    """Terminal output event classification."""
    pass


class TestExtractSummary:
    """One-line summary extraction from output."""
    pass
```

- [ ] **Step 4: Verify test infra works**

Run: `cd ~/openclaw && python -m pytest scripts/tests/test_terminal_relay.py -v`
Expected: 0 tests collected, no errors (just "no tests ran")

- [ ] **Step 5: Commit**

```bash
cd ~/openclaw
git add scripts/tests/
git commit -m "feat(terminal-watch): add test infrastructure"
```

---

## Task 2: Relay Script — ANSI Stripping + Secret Redaction

**Files:**
- Create: `scripts/terminal-relay.py` (initial skeleton with utility functions)
- Modify: `scripts/tests/test_terminal_relay.py` (add tests)

- [ ] **Step 1: Write failing tests for strip_ansi**

Add to `TestStripAnsi` in test file:

```python
class TestStripAnsi:
    def test_removes_color_codes(self):
        from terminal_relay import strip_ansi
        assert strip_ansi("\x1b[31mERROR\x1b[0m") == "ERROR"

    def test_removes_cursor_movement(self):
        from terminal_relay import strip_ansi
        assert strip_ansi("\x1b[2J\x1b[Hhello") == "hello"

    def test_removes_osc_sequences(self):
        from terminal_relay import strip_ansi
        assert strip_ansi("\x1b]0;title\x07text") == "text"

    def test_preserves_plain_text(self):
        from terminal_relay import strip_ansi
        assert strip_ansi("normal output here") == "normal output here"

    def test_handles_nested_sequences(self):
        from terminal_relay import strip_ansi
        raw = "\x1b[1m\x1b[31mBOLD RED\x1b[0m normal"
        assert strip_ansi(raw) == "BOLD RED normal"

    def test_handles_256_color(self):
        from terminal_relay import strip_ansi
        assert strip_ansi("\x1b[38;5;196mred\x1b[0m") == "red"
```

- [ ] **Step 2: Write failing tests for redact_secrets**

Add to `TestRedactSecrets` in test file:

```python
class TestRedactSecrets:
    def test_redacts_openai_key(self):
        from terminal_relay import redact_secrets
        assert "[REDACTED]" in redact_secrets("key is sk-abc123def456ghi789jkl012")

    def test_redacts_aws_key(self):
        from terminal_relay import redact_secrets
        assert "[REDACTED]" in redact_secrets("AKIAIOSFODNN7EXAMPLE")

    def test_redacts_bearer_token(self):
        from terminal_relay import redact_secrets
        assert "[REDACTED]" in redact_secrets("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.test")

    def test_redacts_jwt(self):
        from terminal_relay import redact_secrets
        assert "[REDACTED]" in redact_secrets("token=eyJhbGciOiJIUzI1NiJ9.payload.sig")

    def test_redacts_env_values(self):
        from terminal_relay import redact_secrets
        result = redact_secrets("using key my-super-secret-value-123", env_values=["my-super-secret-value-123"])
        assert "my-super-secret-value-123" not in result
        assert "[REDACTED]" in result

    def test_redacts_key_value_patterns(self):
        from terminal_relay import redact_secrets
        result = redact_secrets("GITHUB_SECRET_KEY=ghp_abc123xyz")
        assert "ghp_abc123xyz" not in result

    def test_preserves_normal_text(self):
        from terminal_relay import redact_secrets
        assert redact_secrets("normal log output") == "normal log output"

    def test_redacts_ssh_key_header(self):
        from terminal_relay import redact_secrets
        assert "[REDACTED]" in redact_secrets("-----BEGIN RSA PRIVATE KEY-----")

    def test_skips_short_env_values(self):
        from terminal_relay import redact_secrets
        # Values < 8 chars should NOT be loaded for redaction (too many false positives)
        result = redact_secrets("value is abc", env_values=["abc"])
        assert result == "value is abc"
```

- [ ] **Step 3: Run tests, verify they fail**

Run: `cd ~/openclaw && python -m pytest scripts/tests/test_terminal_relay.py -v`
Expected: All tests FAIL with ImportError (module doesn't exist yet)

- [ ] **Step 4: Create terminal-relay.py with utility functions**

Create `scripts/terminal-relay.py`:

```python
#!/usr/bin/env python3
"""Terminal Watch relay — captures tmux output, detects events, logs to JSONL."""

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

def load_env_values() -> list[str]:
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

def redact_secrets(text: str, env_values: list[str] | None = None) -> str:
    for pat in _SECRET_PATTERNS:
        text = pat.sub("[REDACTED]", text)
    text = _KEY_VALUE_RE.sub(r"\1=[REDACTED]", text)
    if env_values:
        for val in env_values:
            if len(val) >= 8 and val in text:
                text = text.replace(val, "[REDACTED]")
    return text
```

Note: the file needs to be importable as `terminal_relay`. Create a symlink or add `sys.path` in tests. Since the filename has a hyphen, the test file already handles this with `sys.path.insert`. We need to make the import work — rename the import in tests:

Update test file imports to use importlib:

```python
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Import module with hyphen in name
_mod = importlib.import_module("terminal-relay")
strip_ansi = _mod.strip_ansi
redact_secrets = _mod.redact_secrets
```

Then update each test class to use the module-level imports instead of `from terminal_relay import ...`.

- [ ] **Step 5: Run tests, verify they pass**

Run: `cd ~/openclaw && python -m pytest scripts/tests/test_terminal_relay.py -v`
Expected: All strip_ansi and redact_secrets tests PASS

- [ ] **Step 6: Commit**

```bash
cd ~/openclaw
git add scripts/terminal-relay.py scripts/tests/test_terminal_relay.py
git commit -m "feat(terminal-watch): ANSI stripping + secret redaction with tests"
```

---

## Task 3: Relay Script — Event Detection

**Files:**
- Modify: `scripts/terminal-relay.py` (add detection + summary functions)
- Modify: `scripts/tests/test_terminal_relay.py` (add tests)

- [ ] **Step 1: Write failing tests for detect_event_type**

```python
class TestDetectEventType:
    def test_detects_traceback(self):
        output = "Traceback (most recent call last):\n  File 'x.py'\nValueError: bad"
        assert detect_event_type(output) == "error"

    def test_detects_error_prefix(self):
        assert detect_event_type("Error: connection refused") == "error"

    def test_detects_build_failure_syntax(self):
        assert detect_event_type("SyntaxError: invalid syntax") == "build_failure"

    def test_detects_build_failure_import(self):
        assert detect_event_type("ModuleNotFoundError: No module named 'foo'") == "build_failure"

    def test_detects_test_failure_pytest(self):
        output = "FAILED tests/test_foo.py::test_bar - AssertionError"
        assert detect_event_type(output) == "test_failure"

    def test_detects_test_failure_jest(self):
        assert detect_event_type("Tests:  2 failed, 3 passed") == "test_failure"

    def test_returns_none_for_clean_output(self):
        assert detect_event_type("Successfully installed package-1.0") is None

    def test_build_failure_takes_priority_over_error(self):
        output = "Error: SyntaxError: unexpected EOF"
        assert detect_event_type(output) == "build_failure"

    def test_test_failure_takes_priority_over_error(self):
        output = "FAILED test_x.py\nAssertionError: 1 != 2"
        assert detect_event_type(output) == "test_failure"
```

- [ ] **Step 2: Write failing tests for extract_summary**

```python
class TestExtractSummary:
    def test_extracts_error_line(self):
        output = "running stuff\nmore stuff\nValueError: bad input"
        result = extract_summary(output, "error")
        assert "ValueError" in result

    def test_extracts_test_failure_line(self):
        output = "collecting...\nFAILED test_foo.py::test_bar"
        result = extract_summary(output, "test_failure")
        assert "FAILED" in result

    def test_truncates_long_summaries(self):
        output = "Error: " + "x" * 300
        result = extract_summary(output, "error")
        assert len(result) <= 200

    def test_handles_empty_output(self):
        assert extract_summary("", "error") == ""
```

- [ ] **Step 3: Run tests, verify they fail**

Run: `cd ~/openclaw && python -m pytest scripts/tests/test_terminal_relay.py::TestDetectEventType scripts/tests/test_terminal_relay.py::TestExtractSummary -v`
Expected: FAIL (functions not defined)

- [ ] **Step 4: Implement detect_event_type and extract_summary**

Add to `scripts/terminal-relay.py`:

```python
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
```

- [ ] **Step 5: Run tests, verify they pass**

Run: `cd ~/openclaw && python -m pytest scripts/tests/test_terminal_relay.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
cd ~/openclaw
git add scripts/terminal-relay.py scripts/tests/test_terminal_relay.py
git commit -m "feat(terminal-watch): event detection + summary extraction with tests"
```

---

## Task 4: Relay Script — tmux Integration, Main Loop, CLI

**Files:**
- Modify: `scripts/terminal-relay.py` (add tmux helpers, TerminalRelay class, CLI)

This task completes the relay script. tmux functions require a running tmux session, so testing is manual.

- [ ] **Step 1: Add git helper functions**

```python
# ── Git helpers ──────────────────────────────────────────────────────────────
def get_git_branch(cwd: str) -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, cwd=cwd, timeout=3,
        )
        return r.stdout.strip() if r.returncode == 0 else "unknown"
    except Exception:
        return "unknown"

def get_git_diff_stat(cwd: str) -> str:
    try:
        r = subprocess.run(
            ["git", "diff", "--stat"],
            capture_output=True, text=True, cwd=cwd, timeout=5,
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""

def get_changed_files(cwd: str) -> list[str]:
    try:
        r = subprocess.run(
            ["git", "diff", "--name-only"],
            capture_output=True, text=True, cwd=cwd, timeout=5,
        )
        return [f for f in r.stdout.strip().splitlines() if f] if r.returncode == 0 else []
    except Exception:
        return []
```

- [ ] **Step 2: Add tmux helper functions**

```python
# ── tmux helpers ─────────────────────────────────────────────────────────────
def list_tmux_sessions() -> list[dict]:
    try:
        r = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}:#{session_windows}"],
            capture_output=True, text=True, timeout=3,
        )
        if r.returncode != 0:
            return []
        sessions = []
        for line in r.stdout.strip().splitlines():
            if ":" in line:
                name, windows = line.rsplit(":", 1)
                sessions.append({"name": name, "windows": int(windows)})
        return sessions
    except Exception:
        return []

def list_panes(session: str) -> list[dict]:
    try:
        fmt = "#{pane_index}:#{pane_id}:#{pane_current_command}:#{pane_current_path}"
        r = subprocess.run(
            ["tmux", "list-panes", "-t", session, "-F", fmt],
            capture_output=True, text=True, timeout=3,
        )
        if r.returncode != 0:
            return []
        panes = []
        for line in r.stdout.strip().splitlines():
            parts = line.split(":", 3)
            if len(parts) >= 4:
                panes.append({
                    "index": int(parts[0]),
                    "id": parts[1],
                    "command": parts[2],
                    "cwd": parts[3],
                })
        return panes
    except Exception:
        return []

def capture_pane(session: str, pane: str | None = None) -> str:
    target = f"{session}.{pane}" if pane is not None else session
    try:
        r = subprocess.run(
            ["tmux", "capture-pane", "-p", "-t", target],
            capture_output=True, text=True, timeout=5,
        )
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""
```

- [ ] **Step 3: Add TerminalRelay class**

```python
# ── Core relay ───────────────────────────────────────────────────────────────
class TerminalRelay:
    def __init__(self, session: str, pane: str | None = None):
        self.session = session
        self.pane = pane
        self.previous_capture = ""
        self.buffer: list[str] = []
        self.env_values = load_env_values()
        self.running = True
        self.last_change_time = time.time()
        self.event_count = 0

    def capture(self) -> str:
        return strip_ansi(capture_pane(self.session, self.pane))

    def diff(self, current: str) -> str | None:
        if current == self.previous_capture:
            return None
        prev_lines = self.previous_capture.splitlines()
        curr_lines = current.splitlines()
        if len(curr_lines) > len(prev_lines):
            return "\n".join(curr_lines[len(prev_lines):])
        if curr_lines != prev_lines:
            return current
        return None

    def update_buffer(self, text: str):
        self.buffer.extend(text.splitlines())
        if len(self.buffer) > BUFFER_SIZE:
            self.buffer = self.buffer[-BUFFER_SIZE:]

    def get_pane_cwd(self) -> str:
        panes = list_panes(self.session)
        target = str(self.pane or "0")
        for p in panes:
            if str(p["index"]) == target:
                return p["cwd"]
        return str(OPENCLAW_ROOT)

    def build_event(self, event_type: str, output: str) -> dict:
        cwd = self.get_pane_cwd()
        tail = output.splitlines()[-TAIL_SIZE:]
        return {
            "timestamp": datetime.now().isoformat(),
            "session": self.session,
            "pane": self.pane or "0",
            "event_type": event_type,
            "command": "",
            "exit_code": None,
            "duration_ms": None,
            "cwd": cwd,
            "branch": get_git_branch(cwd),
            "output_tail": [redact_secrets(l, self.env_values) for l in tail],
            "summary": redact_secrets(extract_summary(output, event_type), self.env_values),
        }

    def write_event(self, event: dict):
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(event) + "\n")
        self.event_count += 1

    def snapshot(self) -> dict:
        output = "\n".join(self.buffer[-100:])
        event = self.build_event("user_snapshot", output)
        event["output_tail"] = [redact_secrets(l, self.env_values) for l in self.buffer[-100:]]
        self.write_event(event)
        return event

    def write_pid(self):
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text(str(os.getpid()))

    def cleanup_pid(self):
        if PID_FILE.exists():
            try:
                if int(PID_FILE.read_text().strip()) == os.getpid():
                    PID_FILE.unlink()
            except Exception:
                pass

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
```

- [ ] **Step 4: Add CLI and stop function**

```python
# ── CLI ──────────────────────────────────────────────────────────────────────
def stop_relay():
    if not PID_FILE.exists():
        print("[terminal-relay] No PID file — not running?")
        return
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        print(f"[terminal-relay] Sent SIGTERM to PID {pid}")
        PID_FILE.unlink(missing_ok=True)
    except ProcessLookupError:
        print(f"[terminal-relay] Stale PID file — cleaning up")
        PID_FILE.unlink(missing_ok=True)
    except Exception as e:
        print(f"[terminal-relay] Error stopping: {e}")


def main():
    parser = argparse.ArgumentParser(description="Terminal Watch relay")
    parser.add_argument("--session", help="tmux session name to watch")
    parser.add_argument("--pane", help="pane index (default: active pane)")
    parser.add_argument("--list", action="store_true", help="list tmux sessions")
    parser.add_argument("--stop", action="store_true", help="stop running relay")
    args = parser.parse_args()

    if args.list:
        sessions = list_tmux_sessions()
        if not sessions:
            print("No tmux sessions found.")
            return
        for s in sessions:
            print(f"  {s['name']} ({s['windows']} windows)")
            for p in list_panes(s["name"]):
                print(f"    pane {p['index']} ({p['id']}): {p['command']} @ {p['cwd']}")
        return

    if args.stop:
        stop_relay()
        return

    if not args.session:
        parser.print_help()
        sys.exit(1)

    TerminalRelay(args.session, args.pane).run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Manual test — list sessions**

Run: `cd ~/openclaw && python scripts/terminal-relay.py --list`
Expected: Lists any running tmux sessions (or "No tmux sessions found")

- [ ] **Step 6: Manual test — attach to session (if tmux available)**

```bash
# In one terminal:
tmux new-session -d -s test-relay 'echo "hello world"; sleep 120'
# In another:
cd ~/openclaw && timeout 10 python scripts/terminal-relay.py --session test-relay || true
# Cleanup:
tmux kill-session -t test-relay 2>/dev/null
```

Expected: Relay starts, prints PID, captures output

- [ ] **Step 7: Verify line count**

Run: `wc -l ~/openclaw/scripts/terminal-relay.py`
Expected: ≤300 lines

- [ ] **Step 8: Run all tests**

Run: `cd ~/openclaw && python -m pytest scripts/tests/test_terminal_relay.py -v`
Expected: All tests PASS

- [ ] **Step 9: Commit**

```bash
cd ~/openclaw
git add scripts/terminal-relay.py scripts/tests/test_terminal_relay.py
git commit -m "feat(terminal-watch): complete relay script with tmux integration + CLI"
```

---

## Task 5: Backend — Config Constants + Relay Management Endpoints

**Files:**
- Modify: `~/openclaw/dashboard/server.py` (add config constants + 4 endpoints)

Add all new code in a single block after the trading dashboard section (after line ~1100, before the SPA catch-all at ~1103).

- [ ] **Step 1: Add missing imports and config constants**

Add `signal` and `sys` to the imports at line 1 of server.py (they're needed for relay process management):

```python
import os, json, asyncio, secrets, time, hashlib, subprocess, re, uuid, base64, signal, sys
```

Then add after existing config constants (around line 55 in server.py):

```python
# ── Terminal Watch ────────────────────────────────────────────────────────────
TERMINAL_RELAY = OPENCLAW_ROOT / "scripts" / "terminal-relay.py"
TERMINAL_LOG   = LOGS_DIR / "terminal-watch.jsonl"
TERMINAL_PID   = LOGS_DIR / "terminal-relay.pid"
```

- [ ] **Step 2: Add relay management endpoints**

Add before the SPA catch-all route (before `@app.get("/{path:path}")`):

```python
# ── Terminal Watch endpoints ──────────────────────────────────────────────────

@app.get("/api/terminal/sessions")
async def terminal_sessions(user: str = Depends(get_current_user)):
    """List available tmux sessions and panes."""
    try:
        r = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}:#{session_windows}"],
            capture_output=True, text=True, timeout=3,
        )
        if r.returncode != 0:
            return {"sessions": []}
        sessions = []
        for line in r.stdout.strip().splitlines():
            if ":" not in line:
                continue
            name, windows = line.rsplit(":", 1)
            # Get panes for this session
            pr = subprocess.run(
                ["tmux", "list-panes", "-t", name, "-F",
                 "#{pane_index}:#{pane_id}:#{pane_current_command}:#{pane_current_path}"],
                capture_output=True, text=True, timeout=3,
            )
            panes = []
            if pr.returncode == 0:
                for pl in pr.stdout.strip().splitlines():
                    parts = pl.split(":", 3)
                    if len(parts) >= 4:
                        panes.append({"index": int(parts[0]), "id": parts[1],
                                      "command": parts[2], "cwd": parts[3]})
            sessions.append({"name": name, "windows": int(windows), "panes": panes})
        return {"sessions": sessions}
    except Exception:
        return {"sessions": []}


@app.post("/api/terminal/start")
async def terminal_start(request: Request, user: str = Depends(get_current_user)):
    """Start the relay on a specified tmux session/pane."""
    data = await request.json()
    session = data.get("session")
    if not session:
        raise HTTPException(400, "Missing 'session'")
    pane = data.get("pane")
    # Check if already running
    if TERMINAL_PID.exists():
        try:
            pid = int(TERMINAL_PID.read_text().strip())
            os.kill(pid, 0)  # Check if process exists
            return {"status": "already_running", "pid": pid}
        except (ProcessLookupError, ValueError):
            TERMINAL_PID.unlink(missing_ok=True)
    # Start relay
    cmd = [sys.executable, str(TERMINAL_RELAY), "--session", session]
    if pane is not None:
        cmd.extend(["--pane", str(pane)])
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Wait briefly for PID file
    for _ in range(10):
        time.sleep(0.2)
        if TERMINAL_PID.exists():
            pid = int(TERMINAL_PID.read_text().strip())
            return {"status": "started", "pid": pid, "session": session, "pane": pane}
    return {"status": "started", "session": session, "pane": pane}


@app.post("/api/terminal/stop")
async def terminal_stop(user: str = Depends(get_current_user)):
    """Stop the running relay."""
    if not TERMINAL_PID.exists():
        return {"status": "not_running"}
    try:
        pid = int(TERMINAL_PID.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        TERMINAL_PID.unlink(missing_ok=True)
        return {"status": "stopped", "pid": pid}
    except ProcessLookupError:
        TERMINAL_PID.unlink(missing_ok=True)
        return {"status": "not_running", "note": "stale PID cleaned"}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/terminal/status")
async def terminal_status(user: str = Depends(get_current_user)):
    """Check relay status."""
    running = False
    pid = None
    if TERMINAL_PID.exists():
        try:
            pid = int(TERMINAL_PID.read_text().strip())
            os.kill(pid, 0)
            running = True
        except (ProcessLookupError, ValueError):
            TERMINAL_PID.unlink(missing_ok=True)
            pid = None
    event_count = 0
    if TERMINAL_LOG.exists():
        event_count = sum(1 for _ in open(TERMINAL_LOG))
    return {"running": running, "pid": pid, "event_count": event_count,
            "log_file": str(TERMINAL_LOG)}
```

- [ ] **Step 3: Manual test — verify endpoints respond**

```bash
cd ~/openclaw/dashboard && python -c "
import uvicorn
# Just check import works and endpoints are registered
" && curl -s http://localhost:7080/api/terminal/status | python -m json.tool
```

Expected: Returns `{"running": false, "pid": null, "event_count": 0, ...}`

- [ ] **Step 4: Commit**

```bash
cd ~/openclaw
git add dashboard/server.py
git commit -m "feat(terminal-watch): add relay management endpoints to server.py"
```

---

## Task 6: Backend — Events + SSE Stream Endpoints

**Files:**
- Modify: `~/openclaw/dashboard/server.py` (add 2 more endpoints)

- [ ] **Step 1: Add events endpoint**

Add after the relay management endpoints:

```python
@app.get("/api/terminal/events")
async def terminal_events(
    n: int = 20,
    errors_only: bool = False,
    user: str = Depends(get_current_user),
):
    """Return last N events from the JSONL log."""
    if not TERMINAL_LOG.exists():
        return {"events": []}
    lines = TERMINAL_LOG.read_text().strip().splitlines()
    events = []
    for line in reversed(lines):
        try:
            ev = json.loads(line)
            if errors_only and ev.get("event_type") not in ("error", "build_failure", "test_failure"):
                continue
            events.append(ev)
            if len(events) >= n:
                break
        except Exception:
            pass
    return {"events": events}
```

- [ ] **Step 2: Add SSE stream endpoint**

Follow the existing trading SSE pattern from server.py lines 874-887:

```python
@app.get("/api/terminal/stream")
async def terminal_stream(request: Request):
    """SSE stream of new terminal events."""
    token = request.cookies.get("oc_token") or request.query_params.get("token")
    if not token or not verify_token(token):
        if not is_localhost(request):
            raise HTTPException(401, "Not authenticated")

    async def event_gen():
        last_count = 0
        if TERMINAL_LOG.exists():
            last_count = sum(1 for _ in open(TERMINAL_LOG))
        while True:
            if await request.is_disconnected():
                break
            try:
                if TERMINAL_LOG.exists():
                    lines = TERMINAL_LOG.read_text().strip().splitlines()
                    current_count = len(lines)
                    if current_count > last_count:
                        new_events = []
                        for line in lines[last_count:]:
                            try:
                                new_events.append(json.loads(line))
                            except Exception:
                                pass
                        if new_events:
                            yield f"data: {json.dumps({'events': new_events})}\n\n"
                        last_count = current_count
                    else:
                        yield ": heartbeat\n\n"
                else:
                    yield ": heartbeat\n\n"
            except Exception:
                yield ": heartbeat\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(
        event_gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

- [ ] **Step 3: Manual test — events endpoint**

```bash
curl -s http://localhost:7080/api/terminal/events | python -m json.tool
```

Expected: `{"events": []}` (no events yet)

- [ ] **Step 4: Commit**

```bash
cd ~/openclaw
git add dashboard/server.py
git commit -m "feat(terminal-watch): add events + SSE stream endpoints"
```

---

## Task 7: Backend — Packet Building Endpoints

**Files:**
- Modify: `~/openclaw/dashboard/server.py` (add 3 more endpoints)

- [ ] **Step 1: Add snapshot endpoint**

```python
@app.post("/api/terminal/snapshot")
async def terminal_snapshot(user: str = Depends(get_current_user)):
    """Trigger a manual snapshot via the relay's buffer (writes to JSONL)."""
    if not TERMINAL_PID.exists():
        raise HTTPException(400, "Relay not running")
    try:
        pid = int(TERMINAL_PID.read_text().strip())
        os.kill(pid, 0)
    except (ProcessLookupError, ValueError):
        raise HTTPException(400, "Relay not running")
    # Signal the relay to take a snapshot by writing a trigger file
    trigger = LOGS_DIR / "terminal-snapshot-trigger"
    trigger.write_text(datetime.now().isoformat())
    # Wait for new event to appear
    pre_count = sum(1 for _ in open(TERMINAL_LOG)) if TERMINAL_LOG.exists() else 0
    for _ in range(15):
        time.sleep(0.2)
        if TERMINAL_LOG.exists():
            count = sum(1 for _ in open(TERMINAL_LOG))
            if count > pre_count:
                lines = TERMINAL_LOG.read_text().strip().splitlines()
                return json.loads(lines[-1])
    return {"status": "snapshot_requested", "note": "check events shortly"}
```

Note: The snapshot trigger mechanism uses a trigger file. The relay checks for this file each poll cycle (already implemented in Task 4 Step 3).

- [ ] **Step 2: Add packet building endpoint**

```python
def _build_packet(event: dict | None = None) -> dict:
    """Build an analysis packet from an event + git context."""
    cwd = event.get("cwd", str(OPENCLAW_ROOT)) if event else str(OPENCLAW_ROOT)
    # Recent commands from JSONL
    recent = []
    if TERMINAL_LOG.exists():
        for line in reversed(TERMINAL_LOG.read_text().strip().splitlines()[-20:]):
            try:
                ev = json.loads(line)
                if ev.get("command"):
                    recent.append(ev["command"])
                if len(recent) >= 5:
                    break
            except Exception:
                pass
    # Git context
    try:
        branch_r = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, cwd=cwd, timeout=3,
        )
        branch = branch_r.stdout.strip() if branch_r.returncode == 0 else "unknown"
    except Exception:
        branch = "unknown"
    try:
        diff_r = subprocess.run(
            ["git", "diff", "--stat"], capture_output=True, text=True, cwd=cwd, timeout=5,
        )
        diff_stat = diff_r.stdout.strip() if diff_r.returncode == 0 else ""
    except Exception:
        diff_stat = ""
    try:
        files_r = subprocess.run(
            ["git", "diff", "--name-only"], capture_output=True, text=True, cwd=cwd, timeout=5,
        )
        changed = [f for f in files_r.stdout.strip().splitlines() if f] if files_r.returncode == 0 else []
    except Exception:
        changed = []

    packet = {
        "context": {
            "repo": Path(cwd).name,
            "branch": branch,
            "cwd": cwd,
            "session": event.get("session", "") if event else "",
            "recent_commands": recent,
            "git_diff_stat": diff_stat,
            "changed_files": changed,
        },
        "event": {
            "type": event.get("event_type", "") if event else "",
            "command": event.get("command", "") if event else "",
            "exit_code": event.get("exit_code") if event else None,
            "output_tail": event.get("output_tail", []) if event else [],
            "duration_ms": event.get("duration_ms") if event else None,
        },
        "question": "Explain what failed and suggest a fix.",
    }
    return packet


@app.post("/api/terminal/packet")
async def terminal_packet(request: Request, user: str = Depends(get_current_user)):
    """Build an analysis packet from the last event or a specified event."""
    data = await request.json() if request.headers.get("content-type") == "application/json" else {}
    event_id = data.get("event_id")
    event = None
    if TERMINAL_LOG.exists():
        lines = TERMINAL_LOG.read_text().strip().splitlines()
        if event_id:
            for line in reversed(lines):
                try:
                    ev = json.loads(line)
                    if ev.get("timestamp") == event_id:
                        event = ev
                        break
                except Exception:
                    pass
        elif lines:
            try:
                event = json.loads(lines[-1])
            except Exception:
                pass
    if not event:
        raise HTTPException(404, "No events found")
    return _build_packet(event)


@app.get("/api/terminal/packet/preview")
async def terminal_packet_preview(user: str = Depends(get_current_user)):
    """Preview the packet that would be built from the most recent event."""
    event = None
    if TERMINAL_LOG.exists():
        lines = TERMINAL_LOG.read_text().strip().splitlines()
        if lines:
            try:
                event = json.loads(lines[-1])
            except Exception:
                pass
    if not event:
        return {"packet": None, "note": "No events available"}
    return {"packet": _build_packet(event)}
```

- [ ] **Step 3: Verify endpoint count and line budget**

Count the new lines added to server.py. Target: ≤200 lines added.

```bash
# Compare line counts
wc -l ~/openclaw/dashboard/server.py
# Should be original (~1118) + ≤200 new = ≤1318
```

- [ ] **Step 4: Manual test — packet preview**

```bash
curl -s http://localhost:7080/api/terminal/packet/preview | python -m json.tool
```

Expected: `{"packet": null, "note": "No events available"}` (no events yet)

- [ ] **Step 5: Commit**

```bash
cd ~/openclaw
git add dashboard/server.py
git commit -m "feat(terminal-watch): add packet building + snapshot endpoints"
```

---

## Task 8: Frontend — CSS for Terminal Watch Panel

**Files:**
- Modify: `~/openclaw/dashboard/index.html` (add CSS)

Insert new CSS before the nav tabs section (before `/* ── Nav tabs */` comment, around line 518).

- [ ] **Step 1: Add Terminal Watch CSS**

```css
/* ── Terminal Watch ──────────────────────────────────────────────────────── */
.tw-status { display: flex; align-items: center; gap: 10px; padding: 11px 18px; border-bottom: 1px solid var(--grey3); }
.tw-status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--grey2); flex-shrink: 0; }
.tw-status-dot.watching { background: var(--neon-green); box-shadow: 0 0 8px rgba(0,255,136,0.5); animation: tw-pulse 2s ease-in-out infinite; }
.tw-status-dot.error { background: var(--neon-red); box-shadow: 0 0 8px rgba(255,0,46,0.5); }
@keyframes tw-pulse { 50% { box-shadow: 0 0 14px rgba(0,255,136,0.7); } }
.tw-session { font-size: 0.60rem; color: var(--offwhite); letter-spacing: 1px; }
.tw-uptime { font-size: 0.50rem; color: var(--grey2); margin-left: auto; }
.tw-controls { display: flex; gap: 6px; padding: 8px 18px; border-bottom: 1px solid var(--grey3); flex-wrap: wrap; }
.tw-btn { font-size: 0.50rem; letter-spacing: 2px; padding: 4px 12px; border: 1px solid var(--border-mid); border-radius: 1px; background: transparent; color: var(--orange); cursor: pointer; font-family: inherit; transition: all 0.2s; }
.tw-btn:hover { background: var(--orange-dim); border-color: var(--orange); box-shadow: 0 0 8px rgba(232,104,0,0.3); }
.tw-btn.primary { border-color: var(--orange); }
.tw-btn.primary:hover { background: var(--orange); color: #000; }
.tw-btn.danger { border-color: rgba(255,0,46,0.3); color: var(--neon-red); }
.tw-btn.danger:hover { background: rgba(255,0,46,0.1); }
.tw-select { font-size: 0.56rem; padding: 4px 8px; background: var(--bg); border: 1px solid var(--grey3); color: var(--offwhite); font-family: inherit; border-radius: 1px; }
.tw-select:focus { outline: none; border-color: var(--orange); }
.tw-events { max-height: 400px; overflow-y: auto; }
.tw-events::-webkit-scrollbar { width: 5px; }
.tw-events::-webkit-scrollbar-track { background: rgba(255,255,255,0.02); }
.tw-events::-webkit-scrollbar-thumb { background: rgba(232,104,0,0.25); border-radius: 2px; }
.tw-event { padding: 10px 18px; border-bottom: 1px solid rgba(255,255,255,0.04); cursor: pointer; position: relative; animation: entry-slide 0.45s ease-out; }
.tw-event:hover { background: rgba(232,104,0,0.04); }
.tw-event::after { content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 2px; }
.tw-event.ev-error::after { background: var(--neon-red); box-shadow: 0 0 6px rgba(255,0,46,0.4); }
.tw-event.ev-build_failure::after { background: var(--neon-red); }
.tw-event.ev-test_failure::after { background: var(--orange); box-shadow: 0 0 6px rgba(232,104,0,0.4); }
.tw-event.ev-command_finished::after { background: var(--offwhite); }
.tw-event.ev-stalled::after { background: var(--grey2); }
.tw-event.ev-user_snapshot::after { background: var(--neon-cyan); }
.tw-event-hdr { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.tw-event-type { font-size: 0.50rem; letter-spacing: 1.5px; padding: 2px 8px; border: 1px solid; border-radius: 1px; }
.tw-event-type.error, .tw-event-type.build_failure { border-color: rgba(255,0,46,0.4); color: var(--neon-red); }
.tw-event-type.test_failure { border-color: rgba(232,104,0,0.4); color: var(--orange); }
.tw-event-type.command_finished { border-color: rgba(240,236,228,0.2); color: var(--grey1); }
.tw-event-type.stalled { border-color: rgba(102,99,96,0.4); color: var(--grey2); }
.tw-event-type.user_snapshot { border-color: rgba(0,212,255,0.4); color: var(--neon-cyan); }
.tw-event-ts { font-size: 0.50rem; color: var(--grey2); }
.tw-event-summary { font-size: 0.60rem; color: var(--offwhite); margin-top: 4px; }
.tw-event-cmd { font-size: 0.54rem; color: var(--grey1); margin-top: 2px; }
.tw-event-tail { display: none; margin-top: 8px; padding: 8px; background: var(--bg); border: 1px solid var(--grey3); font-size: 0.54rem; color: var(--grey1); white-space: pre-wrap; word-break: break-all; max-height: 200px; overflow-y: auto; }
.tw-event.expanded .tw-event-tail { display: block; }
.tw-packet { padding: 12px 18px; border-top: 1px solid var(--grey3); }
.tw-packet-btns { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
.tw-packet-input { width: 100%; padding: 6px 10px; background: var(--bg); border: 1px solid var(--grey3); color: var(--offwhite); font-family: inherit; font-size: 0.56rem; border-radius: 1px; margin-top: 8px; }
.tw-packet-input:focus { outline: none; border-color: var(--orange); }
.tw-packet-preview { margin-top: 8px; padding: 8px; background: var(--bg); border: 1px solid var(--grey3); font-size: 0.50rem; color: var(--grey1); white-space: pre-wrap; max-height: 250px; overflow-y: auto; display: none; }
.tw-toggles { display: flex; gap: 14px; padding: 8px 18px; border-top: 1px solid var(--grey3); flex-wrap: wrap; }
.tw-toggle { display: flex; align-items: center; gap: 4px; font-size: 0.50rem; color: var(--grey2); cursor: pointer; }
.tw-toggle input { accent-color: var(--orange); }
.tw-explain { padding: 12px 18px; border-top: 1px solid var(--grey3); text-align: center; }
.tw-explain-btn { font-size: 0.56rem; letter-spacing: 2px; padding: 8px 24px; border: 1px solid var(--orange); border-radius: 1px; background: var(--orange-dim); color: var(--orange-hi); cursor: pointer; font-family: inherit; transition: all 0.2s; }
.tw-explain-btn:hover { background: var(--orange); color: #000; box-shadow: 0 0 18px rgba(232,104,0,0.5); }
```

- [ ] **Step 2: Commit CSS**

```bash
cd ~/openclaw
git add dashboard/index.html
git commit -m "feat(terminal-watch): add Terminal Watch panel CSS"
```

---

## Task 9: Frontend — HTML Panel Structure

**Files:**
- Modify: `~/openclaw/dashboard/index.html` (add nav tab + page container + panel HTML)

- [ ] **Step 1: Add nav tab**

Find the nav-tabs div (around line 1282-1289) and add a new tab:

```html
<button class="nav-tab" id="tabTerminal" onclick="showPage('terminal')">⊡ TERMINAL</button>
```

Add it after the TRADING tab.

- [ ] **Step 2: Add page container**

Add a new page container after the trading page (before the modals section). Find `pageTrading` div's closing `</div>` and add after it:

```html
<!-- ── Terminal Watch ──────────────────────────────────────────────────── -->
<div class="page" id="pageTerminal">
  <div class="panel" style="max-width:900px;margin:0 auto;">
    <div class="tw-status" id="twStatus">
      <span class="tw-status-dot" id="twDot"></span>
      <span class="tw-session" id="twSession">OFF</span>
      <span class="tw-uptime" id="twUptime"></span>
    </div>
    <div class="tw-controls">
      <select class="tw-select" id="twSessionPicker"><option value="">— select session —</option></select>
      <button class="tw-btn primary" id="twBtnAttach" onclick="twAttach()">ATTACH</button>
      <button class="tw-btn" onclick="twStart()">START</button>
      <button class="tw-btn danger" onclick="twStop()">STOP</button>
      <button class="tw-btn" onclick="twSnapshot()">SNAPSHOT</button>
    </div>
    <div class="panel-hdr">
      <span class="panel-hdr-title">Event Feed</span>
      <span class="panel-hdr-count" id="twEventCount">0</span>
    </div>
    <div class="tw-events" id="twEvents">
      <div class="empty"><span class="empty-char">📡</span>no events yet — attach to a tmux session</div>
    </div>
    <div class="tw-packet">
      <div class="tw-packet-btns">
        <button class="tw-btn" onclick="twPreviewPacket()">PREVIEW PACKET</button>
        <button class="tw-btn" onclick="twCopyPacket('chatgpt')">COPY FOR CHATGPT</button>
        <button class="tw-btn" onclick="twCopyPacket('claude')">COPY FOR CLAUDE</button>
        <button class="tw-btn" onclick="twCopyPacket('both')">COPY FOR BOTH</button>
      </div>
      <input class="tw-packet-input" id="twQuestion" placeholder="Add your question (optional)..." />
      <div class="tw-packet-preview" id="twPacketPreview"></div>
    </div>
    <div class="tw-toggles">
      <label class="tw-toggle"><input type="checkbox" id="twAutoSnap" /> Auto-snapshot on error</label>
      <label class="tw-toggle"><input type="checkbox" id="twIncludeDiff" checked /> Include git diff</label>
      <label class="tw-toggle"><input type="checkbox" id="twIncludeHistory" checked /> Include command history</label>
      <label class="tw-toggle"><input type="checkbox" id="twErrorsOnly" /> Errors only</label>
    </div>
    <div class="tw-explain">
      <button class="tw-explain-btn" onclick="twExplain()">⚡ EXPLAIN WHAT JUST HAPPENED</button>
    </div>
  </div>
</div>
```

- [ ] **Step 3: Add page switch case**

In the `showPage()` function, add a case for the terminal page:

```javascript
else if (page === 'terminal') {
    document.getElementById('pageTerminal').classList.add('active')
    document.getElementById('tabTerminal').classList.add('active')
    twLoadSessions()
    twLoadEvents()
    twLoadStatus().then(() => { if (twState.running) twConnectSSE() })
}
```

Note: This is the complete `showPage` case — it includes status loading and SSE auto-connect. No further edits to `showPage()` are needed in later tasks.

- [ ] **Step 4: Commit HTML structure**

```bash
cd ~/openclaw
git add dashboard/index.html
git commit -m "feat(terminal-watch): add Terminal Watch panel HTML structure"
```

---

## Task 10: Frontend — JavaScript Logic

**Files:**
- Modify: `~/openclaw/dashboard/index.html` (add JS functions)

Add all Terminal Watch JS in a single block after the trading SSE section (around line 4025).

- [ ] **Step 1: Add state variables and data loaders**

```javascript
// ── Terminal Watch ─────────────────────────────────────────────────────────
const twState = {
  running: false,
  session: '',
  pane: '',
  startTime: null,
  events: [],
  uptimeInterval: null,
}

async function twLoadSessions() {
  try {
    const r = await fetch('/api/terminal/sessions')
    const d = await r.json()
    const sel = document.getElementById('twSessionPicker')
    sel.innerHTML = '<option value="">— select session —</option>'
    for (const s of d.sessions || []) {
      for (const p of s.panes || []) {
        const val = `${s.name}:${p.index}`
        const label = `${s.name}:${p.index} (${p.command} @ ${p.cwd.split('/').pop()})`
        sel.innerHTML += `<option value="${val}">${label}</option>`
      }
    }
  } catch(e) { console.error('[tw] failed to load sessions', e) }
}

async function twLoadEvents() {
  try {
    const errOnly = document.getElementById('twErrorsOnly')?.checked
    const url = `/api/terminal/events?n=20${errOnly ? '&errors_only=true' : ''}`
    const r = await fetch(url)
    const d = await r.json()
    twState.events = d.events || []
    twRenderEvents()
  } catch(e) { console.error('[tw] failed to load events', e) }
}

async function twLoadStatus() {
  try {
    const r = await fetch('/api/terminal/status')
    const d = await r.json()
    twState.running = d.running
    twUpdateStatusUI(d)
  } catch(e) {}
}
```

- [ ] **Step 2: Add control functions**

```javascript
async function twAttach() {
  const val = document.getElementById('twSessionPicker').value
  if (!val) return
  twLoadSessions()
}

async function twStart() {
  const val = document.getElementById('twSessionPicker').value
  if (!val) { toast('Select a session first'); return }
  const [session, pane] = val.split(':')
  try {
    const r = await fetch('/api/terminal/start', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ session, pane }),
    })
    const d = await r.json()
    if (d.status === 'started' || d.status === 'already_running') {
      twState.running = true
      twState.session = session
      twState.pane = pane
      twState.startTime = Date.now()
      twStartUptime()
      twConnectSSE()
      twUpdateStatusUI(d)
      toast('Relay started')
    }
  } catch(e) { toast('Failed to start relay') }
}

async function twStop() {
  try {
    await fetch('/api/terminal/stop', { method: 'POST' })
    twState.running = false
    twState.session = ''
    twState.startTime = null
    if (twState.uptimeInterval) clearInterval(twState.uptimeInterval)
    if (twState.sse) { twState.sse.close(); twState.sse = null }
    twUpdateStatusUI({ running: false })
    toast('Relay stopped')
  } catch(e) { toast('Failed to stop relay') }
}

async function twSnapshot() {
  try {
    const r = await fetch('/api/terminal/snapshot', { method: 'POST' })
    const d = await r.json()
    toast('Snapshot taken')
    twLoadEvents()
  } catch(e) { toast('Snapshot failed — is relay running?') }
}
```

- [ ] **Step 3: Add rendering functions**

```javascript
function twUpdateStatusUI(d) {
  const dot = document.getElementById('twDot')
  const label = document.getElementById('twSession')
  dot.className = 'tw-status-dot' + (d.running ? ' watching' : '')
  label.textContent = d.running
    ? `WATCHING ${twState.session}:${twState.pane}`
    : 'OFF'
}

function twRenderEvents() {
  const el = document.getElementById('twEvents')
  const count = document.getElementById('twEventCount')
  count.textContent = twState.events.length
  if (!twState.events.length) {
    el.innerHTML = '<div class="empty"><span class="empty-char">📡</span>no events yet — attach to a tmux session</div>'
    return
  }
  el.innerHTML = twState.events.map(ev => {
    const ts = new Date(ev.timestamp).toLocaleTimeString()
    const tail = (ev.output_tail || []).join('\n')
    return `<div class="tw-event ev-${ev.event_type}" onclick="this.classList.toggle('expanded')">
      <div class="tw-event-hdr">
        <span class="tw-event-type ${ev.event_type}">${(ev.event_type||'').toUpperCase()}</span>
        <span class="tw-event-ts">${ts}</span>
      </div>
      ${ev.summary ? `<div class="tw-event-summary">${esc(ev.summary)}</div>` : ''}
      ${ev.command ? `<div class="tw-event-cmd">$ ${esc(ev.command)}</div>` : ''}
      ${tail ? `<div class="tw-event-tail">${esc(tail)}</div>` : ''}
    </div>`
  }).join('')
}

function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML }
```

Note: An `esc()` helper already exists at line ~3495 in index.html. Do NOT add a duplicate — reuse the existing one. Only add the `esc()` definition if you confirm it doesn't already exist.

- [ ] **Step 4: Add SSE connection**

```javascript
twState.sse = null

function twConnectSSE() {
  if (twState.sse) twState.sse.close()
  const tkn = getCookie('oc_token')
  twState.sse = new EventSource(`/api/terminal/stream?token=${tkn}`)
  twState.sse.onmessage = (e) => {
    try {
      const d = JSON.parse(e.data)
      if (d.events) {
        for (const ev of d.events) {
          twState.events.unshift(ev)
          // Auto-snapshot on error
          if (document.getElementById('twAutoSnap')?.checked &&
              ['error','build_failure','test_failure'].includes(ev.event_type)) {
            twSnapshot()
          }
        }
        twState.events = twState.events.slice(0, 50)
        twRenderEvents()
      }
    } catch(_) {}
  }
  twState.sse.onerror = () => {
    twState.sse.close()
    setTimeout(twConnectSSE, 5000)
  }
}
```

- [ ] **Step 5: Add packet and clipboard functions**

```javascript
async function twPreviewPacket() {
  try {
    const r = await fetch('/api/terminal/packet/preview')
    const d = await r.json()
    const el = document.getElementById('twPacketPreview')
    if (d.packet) {
      el.textContent = JSON.stringify(d.packet, null, 2)
      el.style.display = 'block'
    } else {
      el.textContent = 'No events available'
      el.style.display = 'block'
    }
  } catch(e) { toast('Failed to load packet preview') }
}

async function twCopyPacket(target) {
  try {
    const r = await fetch('/api/terminal/packet', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({}),
    })
    const packet = await r.json()
    const q = document.getElementById('twQuestion').value.trim()
    if (q) packet.question = q
    let text = ''
    if (target === 'chatgpt') {
      text = 'Analyze this terminal output:\n\n' + JSON.stringify(packet, null, 2)
    } else if (target === 'claude') {
      text = 'Here is terminal context from my development session. Analyze the output and suggest next steps:\n\n' + JSON.stringify(packet, null, 2)
    } else {
      text = 'Terminal analysis packet — paste into ChatGPT or Claude:\n\n' + JSON.stringify(packet, null, 2)
    }
    await navigator.clipboard.writeText(text)
    toast('Copied to clipboard')
  } catch(e) { toast('Copy failed — try again') }
}

async function twExplain() {
  try {
    const r = await fetch('/api/terminal/packet', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({}),
    })
    const packet = await r.json()
    packet.question = 'Explain what just happened in this terminal session. What failed, why, and what should I do next?'
    const text = JSON.stringify(packet, null, 2)
    await navigator.clipboard.writeText(text)
    toast('Explanation packet copied — paste into ChatGPT or Claude')
  } catch(e) { toast('No events to explain') }
}

function twStartUptime() {
  if (twState.uptimeInterval) clearInterval(twState.uptimeInterval)
  twState.uptimeInterval = setInterval(() => {
    if (!twState.startTime) return
    const secs = Math.floor((Date.now() - twState.startTime) / 1000)
    const m = Math.floor(secs / 60)
    const s = secs % 60
    document.getElementById('twUptime').textContent = `${m}m ${s}s`
  }, 1000)
}
```

- [ ] **Step 6: Verify line count**

```bash
# Count new lines added to index.html
wc -l ~/openclaw/dashboard/index.html
# Should be original (~4031) + ≤400 new = ≤4431
```

- [ ] **Step 8: Commit**

```bash
cd ~/openclaw
git add dashboard/index.html
git commit -m "feat(terminal-watch): add Terminal Watch JS logic (SSE, packets, clipboard)"
```

---

## Task 11: Watchdog Integration

**Files:**
- Modify: `scripts/cron-tunnel-watchdog.sh` (add relay PID cleanup)

Note: The snapshot trigger file check was already added to the relay's `run()` method in Task 4 Step 3.

- [ ] **Step 1: Add relay PID check to watchdog**

Add to `cron-tunnel-watchdog.sh` (after existing process checks):

```bash
# Terminal relay cleanup
RELAY_PID="$HOME/openclaw/logs/terminal-relay.pid"
if [ -f "$RELAY_PID" ]; then
    PID=$(cat "$RELAY_PID")
    if ! kill -0 "$PID" 2>/dev/null; then
        echo "$(date): terminal-relay PID $PID dead — cleaning up" >> "$HOME/openclaw/logs/watchdog.log"
        rm -f "$RELAY_PID"
    fi
fi
```

- [ ] **Step 3: Verify relay line count**

```bash
wc -l ~/openclaw/scripts/terminal-relay.py
# Must be ≤300
```

- [ ] **Step 4: Commit**

```bash
cd ~/openclaw
git add scripts/cron-tunnel-watchdog.sh
git commit -m "feat(terminal-watch): add watchdog integration"
```

---

## Task 12: End-to-End Testing

**Files:** None modified — verification only.

- [ ] **Step 1: Start the dashboard**

```bash
cd ~/openclaw/dashboard && python server.py &
```

- [ ] **Step 2: Verify Terminal Watch panel renders**

Open `http://localhost:7080` in browser, click the TERMINAL tab. Verify:
- Status bar shows "OFF" with gray dot
- Session picker dropdown is present
- All buttons render (ATTACH, START, STOP, SNAPSHOT)
- Event feed shows empty state ("no events yet")
- Packet section buttons render
- Toggle checkboxes render
- "EXPLAIN WHAT JUST HAPPENED" button renders with orange glow

- [ ] **Step 3: Test relay attachment**

```bash
# Create a test tmux session
tmux new-session -d -s test-tw 'bash'
```

In the dashboard, select `test-tw:0` from dropdown and click START. Verify:
- Status changes to WATCHING (green pulse)
- Uptime counter starts

- [ ] **Step 4: Trigger events**

In the test tmux session:
```bash
tmux send-keys -t test-tw 'python -c "raise ValueError(\"test error\")"' Enter
```

Verify: Error event appears in the dashboard event feed within ~4 seconds.

- [ ] **Step 5: Test packet copy**

Click "COPY FOR CHATGPT" button. Paste into a text editor. Verify:
- Packet contains event type, output_tail, git context
- No secrets/API keys appear in output
- Question field is present

- [ ] **Step 6: Test clipboard on mobile Safari**

If testing on mobile: verify clipboard.writeText works (may need HTTPS via Cloudflare tunnel).

- [ ] **Step 7: Test SSE reconnection**

Stop and restart the dashboard server. Verify the terminal panel reconnects SSE within ~5 seconds.

- [ ] **Step 8: Verify total line budget**

```bash
echo "=== Line Counts ==="
wc -l ~/openclaw/scripts/terminal-relay.py
echo "Target: ≤300"
# For server.py, count only new lines:
echo "server.py total:"
wc -l ~/openclaw/dashboard/server.py
echo "Target: original (~1118) + ≤200 new"
echo "index.html total:"
wc -l ~/openclaw/dashboard/index.html
echo "Target: original (~4031) + ≤400 new"
```

- [ ] **Step 9: Cleanup test session**

```bash
tmux kill-session -t test-tw 2>/dev/null
python ~/openclaw/scripts/terminal-relay.py --stop
```

- [ ] **Step 10: Final commit if any fixes were needed**

```bash
cd ~/openclaw
git status
# If changes: git add + commit with "fix(terminal-watch): ..."
```

---

## Summary

| Task | What | Files | Commit |
|------|------|-------|--------|
| 1 | Setup + branch | tests/ skeleton | `feat(terminal-watch): add test infrastructure` |
| 2 | ANSI strip + redact | terminal-relay.py + tests | `feat(terminal-watch): ANSI stripping + secret redaction with tests` |
| 3 | Event detection | terminal-relay.py + tests | `feat(terminal-watch): event detection + summary extraction with tests` |
| 4 | tmux + main loop + CLI | terminal-relay.py | `feat(terminal-watch): complete relay script with tmux integration + CLI` |
| 5 | Server: relay mgmt endpoints | server.py | `feat(terminal-watch): add relay management endpoints` |
| 6 | Server: events + SSE | server.py | `feat(terminal-watch): add events + SSE stream endpoints` |
| 7 | Server: packet endpoints | server.py | `feat(terminal-watch): add packet building + snapshot endpoints` |
| 8 | Frontend: CSS | index.html | `feat(terminal-watch): add Terminal Watch panel CSS` |
| 9 | Frontend: HTML structure | index.html | `feat(terminal-watch): add Terminal Watch panel HTML structure` |
| 10 | Frontend: JS logic | index.html | `feat(terminal-watch): add Terminal Watch JS logic` |
| 11 | Watchdog integration | watchdog.sh | `feat(terminal-watch): add watchdog integration` |
| 12 | End-to-end testing | (none) | Fix commits if needed |
