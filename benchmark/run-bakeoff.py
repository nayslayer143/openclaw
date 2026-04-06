#!/usr/bin/env python3
"""
OpenClaw v4.1 — Model Bakeoff
Tests a model against the Phase 0 exit criteria:
  - 10/10 chained tool-call tasks (zero format errors required)
  - 10 code-analysis tasks
  - 5 long-context summarizations
Usage: python3 benchmark/run-bakeoff.py [model] [output_file]
Default: qwen3:32b, benchmark/bakeoff-YYYY-MM-DD.md
"""

import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = sys.argv[1] if len(sys.argv) > 1 else "qwen3:32b"
DATE = datetime.now().strftime("%Y-%m-%d")
OUTPUT = sys.argv[2] if len(sys.argv) > 2 else f"benchmark/bakeoff-{DATE}.md"


def chat(messages, tools=None, timeout=180):
    import os as _os  # benchmark script — local alias avoids top-level import
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "think": False,
        "options": {"num_ctx": int(_os.environ.get("OPENCLAW_NUM_CTX", "16384"))},
    }
    if tools:
        payload["tools"] = tools
    data = json.dumps(payload).encode()
    req = urllib.request.Request(OLLAMA_URL, data=data,
                                  headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            latency = time.time() - t0
            result = json.loads(resp.read())
            return result, latency
    except Exception as e:
        return {"error": str(e)}, time.time() - t0


def check_tool_call(response):
    """Returns True if response contains a valid tool_calls structure."""
    msg = response.get("message", {})
    calls = msg.get("tool_calls", [])
    if not calls:
        return False, "no tool_calls field"
    for call in calls:
        if "function" not in call:
            return False, f"missing 'function' key in call: {call}"
        fn = call["function"]
        if "name" not in fn:
            return False, f"missing 'name' in function: {fn}"
        if "arguments" not in fn:
            return False, f"missing 'arguments' in function: {fn}"
        args = fn["arguments"]
        if isinstance(args, str):
            try:
                json.loads(args)
            except json.JSONDecodeError as e:
                return False, f"arguments not valid JSON: {e}"
    return True, "ok"


# ---------------------------------------------------------------------------
# Tool definitions for tool-call tests
# ---------------------------------------------------------------------------
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "File path"}},
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_tests",
            "description": "Run the test suite for a repo",
            "parameters": {
                "type": "object",
                "properties": {"repo_path": {"type": "string"}},
                "required": ["repo_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_branch",
            "description": "Create a git branch",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string"},
                    "branch_name": {"type": "string"}
                },
                "required": ["repo_path", "branch_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_telegram",
            "description": "Send a message to Jordan via Telegram",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "tier": {"type": "string", "enum": ["1", "2", "3"]}
                },
                "required": ["message", "tier"]
            }
        }
    }
]

TOOL_CALL_TASKS = [
    "Read the file at ~/openclaw/CLAUDE.md",
    "Create a git branch named 'fix/auth-bug' in the repo at ~/projects/myapp",
    "Run the test suite for the repo at ~/projects/myapp",
    "Write 'hello world' to the file /tmp/test.txt",
    "Send a Tier-1 Telegram message: 'Health check complete, all systems nominal'",
    "Read ~/openclaw/agents/configs/orchestrator.md then create a branch named 'update/orchestrator' in ~/openclaw",
    "Run tests for ~/projects/api, then send a Tier-2 Telegram message with the result",
    "Use the write_file tool to write the following content to ~/openclaw/build-results/result-test.md: 'Build result summary: task completed successfully.'",
    "Create a branch named 'feature/nfc-card-api' and then run tests in ~/projects/xyz-cards",
    "Read ~/openclaw/CONSTRAINTS.md and send a Tier-1 Telegram: 'Constraints loaded successfully'",
]

CODE_ANALYSIS_TASKS = [
    "What are the security risks in this code: `eval(user_input)`? Name the vulnerability.",
    "A function returns None instead of [] for an empty list. Is this a bug? Why?",
    "What does `git reset --hard HEAD~1` do? Is it reversible?",
    "Explain what a SQL injection attack is in one sentence.",
    "What is the difference between authentication and authorization?",
    "A webhook receives POST requests with no signature verification. What is the risk?",
    "Why should secrets never be committed to git, even if later deleted?",
    "What does an HTTP 429 status code mean and how should a client handle it?",
    "What is the purpose of a database index? When would you not use one?",
    "Explain the difference between a process and a thread in two sentences.",
]

LONG_CONTEXT_TEXT = """
OpenClaw is a web business operating system running on an M2 Max with 96GB RAM.
It uses Claude Code as the build plane, Ollama for local inference at zero API cost,
Lobster for deterministic workflows, and a multi-agent architecture for research,
build, and ops tasks. The system is organized into phases: Phase 0 hardens the
infrastructure and runs model bakeoffs. Phase 1 activates four core agents. Phase 2
adds MiroFish simulation and market intelligence. Phase 3 adds marketing and support
agents. Phase 4 adds the Memory Librarian and AutoResearch loop.

The Jake Layer provides a 3-layer context routing standard: CLAUDE.md as the map,
root CONTEXT.md as the router, and workspace CONTEXT.md files as local execution
contexts. This prevents agents from over-loading context by making routing explicit.

Security is enforced through a tiered approval system: Tier 1 is auto-execute for
reversible internal actions, Tier 2 requires explicit Jordan approval for external
side effects, and Tier 3 requires an exact confirmation string for financial or
production actions. No timeouts exist on Tier 2 or 3 — the queue holds indefinitely.

Model assignments: qwen3:32b for orchestration and reasoning, qwen2.5:7b for fast
triage and ops, nomic-embed-text for embeddings. The daily budget hard cap is $10.
The gateway is locked to 127.0.0.1. Telegram DM is the only approved communication
channel. Jordan approves all Tier-2+ actions.

Revenue target: $10k/month minimum. Active products are The InformationCube (spherical
digital controller for mixed media and gaming) and xyz.cards (brass NFC business cards).
Both products are nearly ready to ship. The system's primary job is to keep development
moving and get products in front of paying customers as fast as possible.
""".strip()

SUMMARIZATION_TASKS = [
    f"Summarize this in exactly 3 bullet points:\n\n{LONG_CONTEXT_TEXT}",
    f"What are the top 3 security constraints described here:\n\n{LONG_CONTEXT_TEXT}",
    f"List the active products and their one-line descriptions from this text:\n\n{LONG_CONTEXT_TEXT}",
    f"What is the approval tier system? Describe each tier in one sentence:\n\n{LONG_CONTEXT_TEXT}",
    f"What is the revenue target and what products are closest to generating it:\n\n{LONG_CONTEXT_TEXT}",
]


def run_section(title, tasks, use_tools=False):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")
    results = []
    for i, task in enumerate(tasks, 1):
        print(f"  [{i}/{len(tasks)}] ", end="", flush=True)
        messages = [{"role": "user", "content": task}]
        resp, latency = chat(messages, tools=TOOLS if use_tools else None)

        if "error" in resp:
            status = "ERROR"
            detail = resp["error"]
            passed = False
        elif use_tools:
            passed, detail = check_tool_call(resp)
            status = "PASS" if passed else "FAIL"
        else:
            content = resp.get("message", {}).get("content", "")
            passed = len(content) > 20
            status = "PASS" if passed else "FAIL"
            detail = content[:80].replace("\n", " ") + "..." if len(content) > 80 else content

        latency_str = f"{latency:.1f}s"
        print(f"{status} ({latency_str}) — {detail[:60]}")
        results.append({
            "task": task[:60],
            "status": status,
            "passed": passed,
            "latency": round(latency, 1),
            "detail": detail[:120]
        })
    return results


def main():
    print(f"\nOpenClaw Bakeoff — {MODEL} — {DATE}")
    print(f"Ollama: {OLLAMA_URL}")

    # Warm-up ping
    print("\nWarm-up ping...", end="", flush=True)
    resp, lat = chat([{"role": "user", "content": "Reply with the single word: ready"}])
    content = resp.get("message", {}).get("content", "")
    print(f" {lat:.1f}s — {content[:40]}")

    tool_results = run_section("TOOL-CALL TASKS (10/10 required to pass Phase 0)", TOOL_CALL_TASKS, use_tools=True)
    code_results = run_section("CODE ANALYSIS TASKS", CODE_ANALYSIS_TASKS, use_tools=False)
    summ_results = run_section("LONG-CONTEXT SUMMARIZATION TASKS", SUMMARIZATION_TASKS, use_tools=False)

    # Tally
    tool_pass = sum(1 for r in tool_results if r["passed"])
    code_pass = sum(1 for r in code_results if r["passed"])
    summ_pass = sum(1 for r in summ_results if r["passed"])
    tool_latencies = [r["latency"] for r in tool_results]
    avg_lat = sum(tool_latencies) / len(tool_latencies)

    phase0_exit = tool_pass == 10

    print(f"\n{'='*60}")
    print(f"  RESULTS SUMMARY")
    print(f"{'='*60}")
    print(f"  Tool-call tasks:       {tool_pass}/10 {'<-- PASS (Phase 0 exit met)' if phase0_exit else '<-- FAIL (Phase 0 blocked)'}")
    print(f"  Code analysis tasks:   {code_pass}/10")
    print(f"  Summarization tasks:   {summ_pass}/5")
    print(f"  Avg tool-call latency: {avg_lat:.1f}s")
    print(f"  Phase 0 exit:          {'YES' if phase0_exit else 'NO — fix format errors before proceeding'}")

    # Write markdown report
    lines = [
        f"# Bakeoff — {MODEL} — {DATE}",
        "",
        f"**Phase 0 exit criteria met:** {'YES' if phase0_exit else 'NO'}",
        f"**Tool-call tasks:** {tool_pass}/10",
        f"**Code analysis tasks:** {code_pass}/10",
        f"**Summarization tasks:** {summ_pass}/5",
        f"**Avg tool-call latency:** {avg_lat:.1f}s",
        "",
        "## Tool-Call Tasks",
        "| # | Task | Status | Latency | Detail |",
        "|---|------|--------|---------|--------|",
    ]
    for i, r in enumerate(tool_results, 1):
        lines.append(f"| {i} | {r['task']} | {r['status']} | {r['latency']}s | {r['detail']} |")

    lines += ["", "## Code Analysis Tasks",
              "| # | Task | Status | Latency |",
              "|---|------|--------|---------|"]
    for i, r in enumerate(code_results, 1):
        lines.append(f"| {i} | {r['task']} | {r['status']} | {r['latency']}s |")

    lines += ["", "## Summarization Tasks",
              "| # | Task | Status | Latency |",
              "|---|------|--------|---------|"]
    for i, r in enumerate(summ_results, 1):
        lines.append(f"| {i} | {r['task']} | {r['status']} | {r['latency']}s |")

    lines += ["", f"*Generated by run-bakeoff.py — OpenClaw v4.1*"]

    with open(OUTPUT, "w") as f:
        f.write("\n".join(lines))

    print(f"\n  Report saved to: {OUTPUT}")
    return 0 if phase0_exit else 1


if __name__ == "__main__":
    sys.exit(main())
