# chub FORGE Injection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `chub.py` module that detects library names in FORGE agent prompts and prepends verified API docs before the Ollama call, with full graceful degradation.

**Architecture:** New `scripts/clawteam/chub.py` exposes `fetch_chub_context(prompt) -> str`; `runner.py` calls it for FORGE codename only and prepends the result to the user message. All subprocess calls use `check=False` and are wrapped in `try/except Exception` — any failure returns `""` silently.

**Tech Stack:** Python 3 stdlib only (`subprocess`, `json`, `re`); `chub` CLI (already installed at `/usr/local/bin/chub` or equivalent); `pytest` + `unittest.mock`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `scripts/clawteam/chub.py` | **Create** | `_extract_candidates`, `_lookup_chub`, `fetch_chub_context` |
| `scripts/clawteam/tests/test_chub.py` | **Create** | 12 unit tests for chub.py |
| `scripts/clawteam/runner.py` | **Modify** (lines 7–36) | Add import + 2-line FORGE injection |
| `scripts/clawteam/tests/test_runner.py` | **Modify** (append) | 2 new integration tests |

---

## Task 1: `_extract_candidates` — detection logic + tests

**Files:**
- Create: `scripts/clawteam/tests/test_chub.py`
- Create: `scripts/clawteam/chub.py` (partial — `_extract_candidates` only)

- [ ] **Step 1: Create `test_chub.py` with detection tests**

```python
# scripts/clawteam/tests/test_chub.py
"""Tests for chub.py — FORGE context injection."""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def test_detect_backtick():
    """Backtick-wrapped name is extracted as a candidate."""
    from clawteam.chub import _extract_candidates
    result = _extract_candidates("use `requests` to fetch data from an API")
    assert "requests" in result


def test_detect_import():
    """import statement extracts the module name."""
    from clawteam.chub import _extract_candidates
    result = _extract_candidates("import boto3\nupload the file to S3")
    assert "boto3" in result


def test_short_candidate_filtered():
    """Candidates shorter than 4 chars are dropped before subprocess."""
    from clawteam.chub import _extract_candidates
    # 'os' and 're' are 2 chars — must be filtered out
    result = _extract_candidates("import os\nuse re to match")
    assert "os" not in result
    assert "re" not in result


def test_candidate_with_spaces_filtered():
    """Backtick-wrapped multi-word name is rejected by shape filter."""
    from clawteam.chub import _extract_candidates
    # backtick pattern captures "some library" (contains a space)
    result = _extract_candidates("use `some library` to process data")
    # "some library" contains a space — shape filter `re.match(r'^[\w][\w.\-]*$', c)` drops it
    assert "some library" not in result
```

- [ ] **Step 2: Run detection tests — expect ImportError (module not yet created)**

```bash
cd /Users/nayslayer/openclaw/.claude/worktrees/hardcore-hertz
python3 -m pytest scripts/clawteam/tests/test_chub.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'clawteam.chub'`

- [ ] **Step 3: Create `scripts/clawteam/chub.py` with `_BLOCKLIST`, `_PATTERNS`, and `_extract_candidates`**

```python
#!/usr/bin/env python3
"""
chub.py — FORGE context injection via chub CLI.
Detects library references in prompts and prepends verified API docs.
Never raises. Returns "" on any failure.
"""
from __future__ import annotations
import json
import re
import subprocess

_BLOCKLIST = {
    "python", "code", "function", "data", "file", "string", "list", "dict",
    "api", "json", "http", "re", "os", "io", "sys", "time", "math", "csv",
    "abc", "ast", "uuid", "enum", "copy", "ssl", "xml", "url", "app", "sql",
    "log", "cli", "db",
}

_PATTERNS = [
    r'`([^`]+)`',                                        # `library`
    r'\bimport\s+(\w+)',                                 # import X
    r'\bfrom\s+(\w+)\s+import',                         # from X import
    r'\busing\s+(\w+)',                                  # using X
    r'\bwith\s+(?:the\s+)?(\w+)\s+[Aa][Pp][Ii]',       # with X API
    r'\b(?:call|use)\s+(\w+)',                           # call X / use X
]

_DOC_CAP = 3000


def _extract_candidates(prompt: str) -> list[str]:
    """
    Extract up to 3 valid library candidate names from prompt.
    Pipeline: deduplicate → filter (shape + length + blocklist) → cap at 3.
    """
    seen: list[str] = []
    seen_set: set[str] = set()
    for pattern in _PATTERNS:
        for match in re.finditer(pattern, prompt):
            name = match.group(1)
            if name not in seen_set:
                seen.append(name)
                seen_set.add(name)

    filtered = []
    for c in seen:
        if not re.match(r'^[\w][\w.\-]*$', c):   # shape: no spaces, valid chars
            continue
        if len(c) < 4:                             # min length: block os, re, io
            continue
        if c.lower() in _BLOCKLIST:               # blocklist: common false positives
            continue
        filtered.append(c)

    return filtered[:3]
```

Do NOT add `_lookup_chub` or `fetch_chub_context` yet — those come in Task 2.

- [ ] **Step 4: Run detection tests — expect pass**

```bash
python3 -m pytest scripts/clawteam/tests/test_chub.py::test_detect_backtick scripts/clawteam/tests/test_chub.py::test_detect_import scripts/clawteam/tests/test_chub.py::test_short_candidate_filtered scripts/clawteam/tests/test_chub.py::test_candidate_with_spaces_filtered -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/clawteam/chub.py scripts/clawteam/tests/test_chub.py
git commit -m "feat: chub _extract_candidates with detection tests"
```

---

## Task 2: `_lookup_chub` + `fetch_chub_context` — lookup, cap, graceful degradation

**Files:**
- Modify: `scripts/clawteam/chub.py` (append `_lookup_chub` and `fetch_chub_context`)
- Modify: `scripts/clawteam/tests/test_chub.py` (append 5 tests)

- [ ] **Step 1: Append 8 lookup/graceful tests to `test_chub.py`**

Add these after the existing 4 tests (do not replace anything):

```python
def _make_proc(stdout: bytes = b"", returncode: int = 0):
    """Build a mock CompletedProcess."""
    m = MagicMock()
    m.stdout = stdout
    m.returncode = returncode
    return m


def test_lookup_success():
    """Successful chub search+get returns formatted doc string."""
    import json as _json
    from clawteam.chub import fetch_chub_context
    search_out = _json.dumps([{"id": "requests", "name": "requests"}]).encode()
    doc_body = "Sample requests docs."
    search_proc = _make_proc(stdout=search_out)
    get_proc = _make_proc(stdout=doc_body.encode())
    with patch("clawteam.chub.subprocess.run", side_effect=[search_proc, get_proc]):
        result = fetch_chub_context("use `requests` to call an endpoint")
    assert result.startswith("[API DOCS: requests]\n")
    assert doc_body in result


def test_cap_boundary():
    """Doc body is sliced to exactly 3000 chars, not 3001."""
    import json as _json
    from clawteam.chub import fetch_chub_context
    search_out = _json.dumps([{"id": "requests", "name": "requests"}]).encode()
    doc_body = "X" * 3001
    search_proc = _make_proc(stdout=search_out)
    get_proc = _make_proc(stdout=doc_body.encode())
    with patch("clawteam.chub.subprocess.run", side_effect=[search_proc, get_proc]):
        result = fetch_chub_context("use `requests` to call an endpoint")
    label = "[API DOCS: requests]\n"
    body = result[len(label):]
    assert len(body) == 3000
    assert body == "X" * 3000


def test_graceful_chub_not_found():
    """FileNotFoundError (chub not on PATH) → returns empty string."""
    from clawteam.chub import fetch_chub_context
    with patch("clawteam.chub.subprocess.run", side_effect=FileNotFoundError):
        result = fetch_chub_context("use `requests` to fetch data")
    assert result == ""


def test_graceful_no_match():
    """Empty search results → returns empty string."""
    import json as _json
    from clawteam.chub import fetch_chub_context
    search_proc = _make_proc(stdout=_json.dumps([]).encode())
    with patch("clawteam.chub.subprocess.run", return_value=search_proc):
        result = fetch_chub_context("use `requests` to fetch data")
    assert result == ""


def test_graceful_non_list_json():
    """chub search returns valid JSON that is not a list → returns empty string."""
    import json as _json
    from clawteam.chub import fetch_chub_context
    search_proc = _make_proc(stdout=_json.dumps({"error": "rate limited"}).encode())
    with patch("clawteam.chub.subprocess.run", return_value=search_proc):
        result = fetch_chub_context("use `requests` to fetch data")
    assert result == ""


def test_graceful_timeout():
    """subprocess.TimeoutExpired → returns empty string."""
    import subprocess as _sp
    from clawteam.chub import fetch_chub_context
    with patch("clawteam.chub.subprocess.run", side_effect=_sp.TimeoutExpired("chub", 3)):
        result = fetch_chub_context("use `requests` to fetch data")
    assert result == ""


def test_graceful_name_mismatch():
    """chub search top result name does not match candidate → returns empty string."""
    import json as _json
    from clawteam.chub import fetch_chub_context
    # search for "boto3" but chub returns "django" as top result
    search_proc = _make_proc(
        stdout=_json.dumps([{"id": "django", "name": "django"}]).encode()
    )
    with patch("clawteam.chub.subprocess.run", return_value=search_proc):
        result = fetch_chub_context("use `boto3` to upload files")
    assert result == ""


def test_graceful_nonzero_exit_search():
    """Non-zero returncode from chub search → returns empty string."""
    from clawteam.chub import fetch_chub_context
    search_proc = _make_proc(stdout=b"", returncode=1)
    with patch("clawteam.chub.subprocess.run", return_value=search_proc):
        result = fetch_chub_context("use `requests` to fetch data")
    assert result == ""
```

- [ ] **Step 2: Run lookup tests — expect ImportError/AttributeError (functions not yet implemented)**

```bash
python3 -m pytest scripts/clawteam/tests/test_chub.py::test_lookup_success scripts/clawteam/tests/test_chub.py::test_cap_boundary scripts/clawteam/tests/test_chub.py::test_graceful_chub_not_found scripts/clawteam/tests/test_chub.py::test_graceful_no_match scripts/clawteam/tests/test_chub.py::test_graceful_non_list_json scripts/clawteam/tests/test_chub.py::test_graceful_timeout scripts/clawteam/tests/test_chub.py::test_graceful_name_mismatch scripts/clawteam/tests/test_chub.py::test_graceful_nonzero_exit_search -v 2>&1 | tail -10
```

Expected: errors referencing missing `fetch_chub_context`

- [ ] **Step 3: Append `_lookup_chub` and `fetch_chub_context` to `scripts/clawteam/chub.py`**

Add after the `_extract_candidates` function (after the `return filtered[:3]` line):

```python

def _lookup_chub(candidate: str) -> str:
    """
    Search chub registry for candidate. Returns formatted doc string or "".
    Uses check=False — non-zero exit codes are handled by inspecting returncode.
    """
    search = subprocess.run(
        ["chub", "search", candidate, "--json"],
        capture_output=True, timeout=3, check=False,
    )
    if search.returncode != 0:
        return ""
    try:
        data = json.loads(search.stdout)
    except json.JSONDecodeError:
        return ""
    if not isinstance(data, list) or not data:
        return ""
    top = data[0]
    name = top.get("name", "")
    if not (
        name.lower() == candidate.lower()
        or (name.lower().startswith(candidate.lower()) and len(candidate) >= 4)
    ):
        return ""
    result_id = top.get("id") or name or candidate
    doc = subprocess.run(
        ["chub", "get", result_id, "--lang", "py"],
        capture_output=True, timeout=5, check=False,
    )
    if doc.returncode != 0:
        return ""
    body = doc.stdout.decode("utf-8", errors="replace")[:_DOC_CAP]
    return f"[API DOCS: {result_id}]\n{body}"


def fetch_chub_context(prompt: str) -> str:
    """
    Detect library references in prompt, fetch docs via chub CLI.
    Returns "[API DOCS: {id}]\\n{docs}" on success, "" on any failure.
    Never raises.
    """
    try:
        candidates = _extract_candidates(prompt)
        for candidate in candidates:
            doc = _lookup_chub(candidate)
            if doc:
                return doc
        return ""
    except Exception:
        return ""
```

- [ ] **Step 4: Run all 12 chub tests — expect all pass**

```bash
python3 -m pytest scripts/clawteam/tests/test_chub.py -v
```

Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/clawteam/chub.py scripts/clawteam/tests/test_chub.py
git commit -m "feat: chub _lookup_chub + fetch_chub_context with graceful degradation"
```

---

## Task 3: `runner.py` FORGE injection + integration tests

**Files:**
- Modify: `scripts/clawteam/tests/test_runner.py` (append 2 tests)
- Modify: `scripts/clawteam/runner.py` (lines 7–36: add import + 2 lines)

- [ ] **Step 1: Append 2 integration tests to `scripts/clawteam/tests/test_runner.py`**

Add after the last test (`test_run_includes_system_prompt`):

```python
def test_forge_prepends_chub_context():
    """FORGE codename: chub context is prepended with double-newline separator."""
    from clawteam.runner import run_agent
    chub_ctx = "[API DOCS: requests]\nSample docs."
    prompt = "write a GET request"
    mock_resp = _mock_streaming_response("done")
    # Patch the name as bound in runner's namespace (from clawteam.chub import fetch_chub_context)
    with patch("clawteam.runner.requests.post", return_value=mock_resp) as mock_post, \
         patch("clawteam.runner.fetch_chub_context", return_value=chub_ctx):
        run_agent("FORGE", "qwen3-coder-next", prompt)
    payload = mock_post.call_args[1]["json"]
    user_content = payload["messages"][-1]["content"]
    assert user_content == f"{chub_ctx}\n\n{prompt}"


def test_non_forge_skips_chub():
    """Non-FORGE codenames never call fetch_chub_context."""
    from clawteam.runner import run_agent
    mock_resp = _mock_streaming_response("done")
    # Patch the name as bound in runner's namespace
    with patch("clawteam.runner.requests.post", return_value=mock_resp), \
         patch("clawteam.runner.fetch_chub_context") as mock_fetch:
        run_agent("SCOUT", "qwen3:30b", "do research")
    assert mock_fetch.call_count == 0
```

- [ ] **Step 2: Run the 2 new tests — expect failure (runner.py not yet modified)**

```bash
python3 -m pytest scripts/clawteam/tests/test_runner.py::test_forge_prepends_chub_context scripts/clawteam/tests/test_runner.py::test_non_forge_skips_chub -v 2>&1 | tail -15
```

Expected: FAILED — `test_forge_prepends_chub_context` fails because `user_content` is just `prompt` (no chub prepend yet); `test_non_forge_skips_chub` may pass vacuously — either way confirms wiring is missing.

- [ ] **Step 3: Modify `scripts/clawteam/runner.py`**

Add the import after the existing imports at line 10 (after `import requests`):

```python
from clawteam.chub import fetch_chub_context
```

Then replace the `run_agent` function body between the `system = ...` line and `messages = [` to inject `chub_ctx`. The existing lines 32–36 currently read:

```python
    system = _SYSTEM_PROMPTS.get(codename.upper(), _DEFAULT_SYSTEM)
    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": prompt},
    ]
```

Replace with:

```python
    system = _SYSTEM_PROMPTS.get(codename.upper(), _DEFAULT_SYSTEM)
    chub_ctx = fetch_chub_context(prompt) if codename.upper() == "FORGE" else ""
    user_content = f"{chub_ctx}\n\n{prompt}" if chub_ctx else prompt
    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": user_content},
    ]
```

No other changes to `runner.py`.

- [ ] **Step 4: Run the 2 new runner tests — expect pass**

```bash
python3 -m pytest scripts/clawteam/tests/test_runner.py::test_forge_prepends_chub_context scripts/clawteam/tests/test_runner.py::test_non_forge_skips_chub -v
```

Expected: 2 passed

- [ ] **Step 5: Run the full test suite to confirm no regressions**

```bash
python3 -m pytest scripts/clawteam/tests/ -v --ignore=scripts/clawteam/tests/test_patterns.py 2>&1 | tail -20
```

Note: `test_patterns.py` has a known segfault issue on Python 3.9.6 + macOS in pytest context (ThreadPoolExecutor). Run it separately if needed:

```bash
python3 -m pytest scripts/clawteam/tests/test_patterns.py -v 2>&1 | tail -10
```

Expected: all other tests pass; patterns tests pass when run in isolation.

- [ ] **Step 6: Commit**

```bash
git add scripts/clawteam/runner.py scripts/clawteam/tests/test_runner.py
git commit -m "feat: inject chub API docs into FORGE agent prompts"
```
