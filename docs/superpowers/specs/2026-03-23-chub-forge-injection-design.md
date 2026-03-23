# chub FORGE Injection — Design Spec
**Date:** 2026-03-23
**Status:** Approved
**Phase:** 4 (active)

---

## Overview

When ClawTeam dispatches a FORGE agent task, the agent's prompt often references third-party libraries by name. Without current API docs, FORGE relies on training-time knowledge that may be stale or incomplete. This spec defines a lightweight `chub.py` module that detects library references in FORGE prompts, fetches verified API docs from the local `chub` CLI, and prepends the docs to the prompt before the Ollama call.

The integration is FORGE-only and fully graceful — any failure silently returns an empty string so FORGE is never blocked.

---

## Architecture

### File Layout

```
scripts/clawteam/
├── chub.py          ← new module (fetch_chub_context)
├── runner.py        ← modified: inject chub_ctx for FORGE codename
└── tests/
    └── test_chub.py ← new test file
```

### Data Flow

```
runner.run_agent(codename="FORGE", prompt=...)
  → chub.fetch_chub_context(prompt)
    → _extract_candidates(prompt)   → ["requests", "boto3", ...]  (max 3)
    → chub search <candidate> --json  (subprocess, 3s timeout) per candidate
    → first accepted match → chub get <id> --lang py  (subprocess, 5s timeout)
    → cap at 3000 chars, prepend "[API DOCS: {id}]\n"
    → return doc string  (or "" on any failure)
  → user_content = f"{chub_ctx}\n\n{prompt}" if chub_ctx else prompt
  → messages = [system, {"role": "user", "content": user_content}]
  → POST to Ollama /api/chat
```

---

## Module: `chub.py`

### Public API

```python
def fetch_chub_context(prompt: str) -> str:
    """
    Detect library references in prompt, fetch docs via chub CLI.
    Returns "[API DOCS: {id}]\n{docs}" on success, "" on any failure.
    Never raises.
    """
```

### Library Detection — `_extract_candidates(prompt: str) -> list[str]`

Scans prompt with regex patterns in priority order:

| Pattern | Example match | Extracted |
|---|---|---|
| Backtick-wrapped | `` `requests` `` | `requests` |
| Import statement | `import boto3` | `boto3` |
| From-import | `from PIL import Image` | `PIL` |
| "using X" | `using requests` | `requests` |
| "with X API" | `with the stripe API` | `stripe` |
| "call X" / "use X" | `call openai` | `openai` |

Candidates are:
- Deduplicated (preserve first-seen order)
- Filtered against blocklist: `python`, `code`, `function`, `data`, `file`, `string`, `list`, `dict`, `api`, `json`, `http`
- Capped at 3 candidates (to bound worst-case latency: 3 × 3s = 9s)

### Lookup — `_lookup_chub(candidate: str) -> str`

1. Run `chub search <candidate> --json` (subprocess, `timeout=3`, `capture_output=True`)
2. Parse JSON response. Accept top result if `result["name"].lower()` equals or starts with `candidate.lower()`
3. If accepted: run `chub get <result_id> --lang py` (subprocess, `timeout=5`, `capture_output=True`)
4. Return stdout string, capped at 3000 chars with `[API DOCS: {result_id}]\n` prepended
5. Return `""` if: chub not on PATH (`FileNotFoundError`), empty results array, name mismatch, timeout, JSON parse error, non-zero exit code

### Integration in `runner.py`

```python
from clawteam.chub import fetch_chub_context

def run_agent(codename: str, model: str, prompt: str) -> str:
    system = _SYSTEM_PROMPTS.get(codename.upper(), _DEFAULT_SYSTEM)
    chub_ctx = fetch_chub_context(prompt) if codename.upper() == "FORGE" else ""
    user_content = f"{chub_ctx}\n\n{prompt}" if chub_ctx else prompt
    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": user_content},
    ]
    # ... existing Ollama POST logic unchanged
```

---

## Error Handling

All subprocess calls are wrapped in a top-level `try/except Exception`. Specific silenced cases:

| Failure mode | Cause | Result |
|---|---|---|
| `FileNotFoundError` | chub not on PATH | `""` |
| `subprocess.TimeoutExpired` | search or get exceeded timeout | `""` |
| `json.JSONDecodeError` | malformed chub search output | `""` |
| Empty results array | no match in chub registry | `""` |
| Name mismatch | top result unrelated to candidate | `""` |
| Non-zero exit code | chub CLI error | `""` |
| Any other exception | unexpected failure | `""` |

FORGE is never blocked. The Ollama call always proceeds.

---

## Tests — `test_chub.py`

| Test | Covers |
|---|---|
| `test_detect_backtick` | `` `requests` `` in prompt → `requests` in candidates |
| `test_detect_import` | `import boto3` → `boto3` in candidates |
| `test_lookup_success` | mock `chub search` returns match, mock `chub get` returns docs → `fetch_chub_context` returns `"[API DOCS: requests]\n..."`, content capped at 3000 chars |
| `test_graceful_chub_not_found` | `subprocess.run` raises `FileNotFoundError` → returns `""` |
| `test_graceful_no_match` | `chub search` returns `[]` → returns `""` |

All tests mock `subprocess.run` — no real chub calls in the test suite.

One additional case added to `test_runner.py`:
- FORGE codename + mocked non-empty `fetch_chub_context` → user content has prepended docs
- Non-FORGE codename → `fetch_chub_context` never called

---

## Constraints

- chub calls via subprocess only (no shell=True, no PATH injection)
- Max 3 candidates per prompt (9s worst-case subprocess overhead)
- Doc output capped at 3000 chars (prevents oversized Ollama context)
- FORGE-only: no other agent codename triggers chub lookup
- All failures silent: never raises, never blocks runner
- No network calls: chub reads its local registry (`~/.chub/` or equivalent)
- No new dependencies: `subprocess`, `json`, `re` — all stdlib
