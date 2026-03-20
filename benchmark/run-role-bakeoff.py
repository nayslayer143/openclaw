#!/usr/bin/env python3
"""
OpenClaw v4.2 — Role-Specialist Bakeoff
Tests models against 6 agent roles using real Omega MegaCorp business context.
Usage: python3 benchmark/run-role-bakeoff.py
Results saved to: benchmark/bakeoff-role-specialist-YYYY-MM-DD.md
Est. runtime: 2-3 hours
"""

import json
import sys
import time
import urllib.request
from datetime import datetime

OLLAMA_URL = "http://localhost:11434/api/chat"
DATE = datetime.now().strftime("%Y-%m-%d")
OUTPUT = f"benchmark/bakeoff-role-specialist-{DATE}.md"
TIMEOUT = 300  # 5 min per task

ROLE_MODELS = {
    "coding":    ["qwen3:32b", "qwen3-coder-next", "devstral-small-2"],
    "research":  ["qwen3:32b", "qwen3:30b"],
    "ops":       ["qwen3:32b", "qwen2.5:7b"],
    "business":  ["qwen3:32b", "qwen3:30b"],
    "memory":    ["qwen3:32b", "llama3.3:70b"],
}

TOOLS = [
    {"type": "function", "function": {"name": "read_file", "description": "Read a file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "write_file", "description": "Write content to a file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}},
    {"type": "function", "function": {"name": "run_bash", "description": "Run a shell command", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "create_branch", "description": "Create a git branch", "parameters": {"type": "object", "properties": {"repo_path": {"type": "string"}, "branch_name": {"type": "string"}}, "required": ["repo_path", "branch_name"]}}},
    {"type": "function", "function": {"name": "send_telegram", "description": "Send Telegram message to Jordan", "parameters": {"type": "object", "properties": {"message": {"type": "string"}, "tier": {"type": "string", "enum": ["1", "2", "3"]}}, "required": ["message", "tier"]}}},
]


def chat(model, messages, tools=None, timeout=TIMEOUT):
    payload = {"model": model, "messages": messages, "stream": False, "think": False}
    if tools:
        payload["tools"] = tools
    data = json.dumps(payload).encode()
    req = urllib.request.Request(OLLAMA_URL, data=data, headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read()), round(time.time() - t0, 1)
    except Exception as e:
        return {"error": str(e)}, round(time.time() - t0, 1)


def check_tool_call(resp):
    msg = resp.get("message", {})
    calls = msg.get("tool_calls", [])
    if not calls:
        return False, "no tool_calls field"
    for call in calls:
        fn = call.get("function", {})
        if not fn.get("name"):
            return False, "missing function name"
        args = fn.get("arguments", {})
        if isinstance(args, str):
            try:
                json.loads(args)
            except Exception as e:
                return False, f"invalid JSON args: {e}"
    return True, "ok"


def check_text(resp, min_len=50):
    if "error" in resp:
        return False, resp["error"]
    content = resp.get("message", {}).get("content", "")
    if len(content) < min_len:
        return False, f"too short ({len(content)} chars)"
    return True, content[:100].replace("\n", " ")


def score(model, tasks, use_tools=False, role_label=""):
    results = []
    for i, (task_desc, prompt) in enumerate(tasks, 1):
        print(f"    [{i}/{len(tasks)}] {task_desc[:55]}...", end=" ", flush=True)
        messages = [{"role": "user", "content": prompt}]
        resp, latency = chat(model, messages, tools=TOOLS if use_tools else None)
        if use_tools:
            passed, detail = check_tool_call(resp)
        else:
            passed, detail = check_text(resp)
        status = "PASS" if passed else "FAIL"
        if "error" in resp and "timed out" in str(resp.get("error", "")):
            status = "TIMEOUT"
        print(f"{status} ({latency}s)")
        results.append({"task": task_desc, "status": status, "passed": passed, "latency": latency, "detail": detail[:120]})
    return results


# ---------------------------------------------------------------------------
# ROLE 1 — CODING / BUILD AGENT
# ---------------------------------------------------------------------------
CODING_TASKS = [
    ("C1a: tool chain - read file", "Use the read_file tool to read ~/openclaw/CLAUDE.md"),
    ("C1b: tool chain - create branch", "Use the create_branch tool to create branch 'fix/nfc-write-error' in ~/projects/pfpcards"),
    ("C1c: tool chain - run bash", "Use the run_bash tool to run: cd ~/projects/pfpcards && npm test"),
    ("C1d: tool chain - write result", "Use the write_file tool to write 'Build result: tests passed' to ~/openclaw/build-results/result-pfpcards-test.md"),
    ("C1e: tool chain - telegram", "Use the send_telegram tool to send a Tier-1 message: 'pfpcards test suite passed, ready for review'"),
    ("C1f: chained - read then branch", "First use read_file to read ~/projects/pfpcards/package.json, then use create_branch to create branch 'feature/batch-nfc-encoding' in ~/projects/pfpcards"),
    ("C1g: chained - test then notify", "Use run_bash to run the test suite at ~/projects/pfpcards, then use send_telegram with a Tier-2 message summarizing the result"),
    ("C1h: chained - branch and test", "Use create_branch to create 'feature/holographic-drop-scheduler' in ~/projects/omega-fashion, then use run_bash to run tests"),
    ("C1i: chained - read and write", "Use read_file to read ~/openclaw/agents/configs/orchestrator.md, then use write_file to save a one-sentence summary to ~/openclaw/build-results/orchestrator-summary.md"),
    ("C1j: chained - full loop", "Use read_file on ~/projects/pfpcards/src/nfc.js, then create_branch 'fix/nfc-encoding-utf8' in ~/projects/pfpcards, then send_telegram Tier-2: 'NFC fix branch ready for build'"),
]

# C2: Multi-file bug report
BUG_REPORT = """
Bug report — pfpcards NFC write failure

Repo: ~/projects/pfpcards
Files involved:
  - src/nfc.js (NFC write handler)
  - src/api/cards.js (API endpoint)
  - tests/nfc.test.js (failing test)

Issue: When a card URL exceeds 137 bytes, the NFC write silently fails. No error is thrown.
The NDEF record is created but the write command returns success even when the chip rejects it.

Expected: throw NFC_WRITE_ERROR with byte count and limit in message
Actual: write returns { success: true } even on rejection

Test currently failing: 'should throw on oversized NDEF record'
"""

# C3: New API endpoint spec
API_SPEC = """
Repo: ~/projects/pfpcards
Add a new endpoint: POST /api/cards/batch

Spec:
- Accepts array of up to 50 card objects: { owner_name, url, nfc_uid }
- Validates each card: url must be valid, nfc_uid must be 14 hex chars
- Returns: { created: N, failed: [{ index, reason }] }
- Auth: Bearer token required (existing auth middleware)
- Rate limit: 10 requests/minute per API key
- Error codes: 400 (validation), 401 (unauth), 429 (rate limit)

Implement in a feature branch with tests covering: happy path, partial failure, auth failure, rate limit.
"""

CODING_LONG_TASKS = [
    ("C2: bug fix - NFC write failure", f"You are a senior engineer. A bug has been filed. Follow the Explore→Plan→Code→Review sequence. Write a plan.md first, then describe the fix.\n\n{BUG_REPORT}"),
    ("C3: new endpoint - batch cards", f"You are a senior engineer. Implement this feature. Write a plan.md covering: files to create/modify, risks, rollback, test plan.\n\n{API_SPEC}"),
]

# ---------------------------------------------------------------------------
# ROLE 2 — RESEARCH / PLANNING
# ---------------------------------------------------------------------------
RESEARCH_TASKS = [
    ("R1: repo scout - EmergentWebActions", """You are a Research Agent. Scout this GitHub repo and return a structured verdict.

Repo: https://github.com/nayslayer143/EmergentWebActions

Return exactly:
- Relevance score: X/10
- Evidence: (2-3 specific observations from the repo)
- Install complexity: low/medium/high
- Integration risk: low/medium/high
- Verdict: integrate / watch / skip
- Reason: (one sentence)

Do not hallucinate features or star counts. Only report what you can directly observe."""),

    ("R2: competitor gap analysis", """You are a Research Agent. Analyze these 3 competitors to Omega's lenticular fashion platform and identify specific gaps.

Competitor 1: Iridescent Inc — sells holographic foil-printed apparel via their own DTC site. Static prints, no movement effect. Price: $80-150.
Competitor 2: SpaceCloth — festival fashion brand using reflective materials. Active on TikTok. No in-house manufacturing. Price: $60-200.
Competitor 3: MorphTex — sells lenticular fabric by the yard to designers. B2B only, no DTC presence.

For each competitor provide: one-line accurate characterization, top gap vs Omega, specific opportunity.
Final line: which gap represents the biggest near-term revenue opportunity for Omega and why."""),

    ("R3: 30-day launch plan", """You are a Research Agent and Planner. Jordan needs to launch the lenticular fashion DTC drop business in 30 days and hit $10,000 in revenue.

Assets available:
- 3,000 sq ft SF fabrication lab with full equipment
- Lenticular textile samples ready
- TikTok account not yet started
- $0 marketing budget (organic only)
- OpenClaw AI system for content and ops

Produce a phased 30-day plan:
- Week 1 tasks (concrete, assignable)
- Week 2 tasks
- Week 3 tasks
- Week 4 tasks
- Top 3 risks with mitigations
- Single most important action on Day 1"""),
]

# ---------------------------------------------------------------------------
# ROLE 3 — OPS / TRIAGE
# ---------------------------------------------------------------------------
OPS_TIER_ITEMS = """
Classify each of the following 10 actions as Tier 1 (auto-execute), Tier 2 (hold for Jordan approval), or Tier 3 (exact confirmation string required). Give one-sentence reasoning per item.

1. Run ollama list to check which models are loaded
2. Deploy a new product page for pfpcards.com to production
3. Read ~/openclaw/MEMORY.md to extract yesterday's patterns
4. Send a TikTok post announcing the lenticular jacket drop
5. Write a draft email to a potential investor (not send)
6. Charge a customer's card for a $260 jacket order
7. Create a git branch called 'feature/drop-scheduler'
8. Restart the Ollama service after a crash
9. Send a Tier-2 Telegram to Jordan: 'Build complete, ready for staging deploy review'
10. Delete the ~/openclaw/logs/ directory to free disk space

Format: Item N: Tier X — [reasoning]"""

OPS_LOG = """
Triage these log excerpts. For each file: identify which FATALs require a Tier-2 Telegram alert, which WARNINGs can be ignored, and give probable root cause.

--- ops-agent-2026-03-19.jsonl ---
INFO  09:00 Health check started
INFO  09:00 Ollama: responding
WARNING 09:01 Disk usage: 78% (threshold: 80%)
INFO  09:01 Queue depth: 3
FATAL 09:02 Neo4j: connection refused (bolt://localhost:7687)
INFO  09:03 Health check complete

--- build-agent-2026-03-19.jsonl ---
INFO  11:30 Task build-1742300001 started
INFO  11:31 Branch feature/nfc-batch created
WARNING 11:45 Test run: 2 tests skipped (no NFC hardware)
FATAL 11:52 Tests failed: nfc.test.js assertion error — expected 137 got 142
INFO  11:52 Task marked blocked, output contract written

--- research-agent-2026-03-19.jsonl ---
INFO  14:00 Intel scan started
INFO  14:01 No unprocessed scout reports found
INFO  14:01 Intel scan complete — nothing to process"""

OPS_TASK_PACKET = """Convert this plain-text task into a valid JSON task packet matching this schema exactly:
{
  "task_id": "build-[timestamp]",
  "repo_path": "string",
  "goal": "string (one sentence)",
  "acceptance_criteria": ["string"],
  "forbidden_operations": ["string"],
  "time_budget_minutes": number,
  "risk_level": "low | medium | high",
  "output_location": "string"
}

Task description:
Fix the NFC write bug in the pfpcards repo. When a card URL exceeds 137 bytes the write silently fails instead of throwing. The fix should throw NFC_WRITE_ERROR with the byte count. Tests must pass. Do not touch the payment or auth code. Should take under 30 minutes. Medium risk."""

OPS_TASKS = [
    ("O1: tier classification - 10 items", OPS_TIER_ITEMS),
    ("O2: log triage", OPS_LOG),
    ("O3: task packet formatting", OPS_TASK_PACKET),
]

# ---------------------------------------------------------------------------
# ROLE 4 — BUSINESS / DOCUMENT
# ---------------------------------------------------------------------------
MARKET_BRIEF = """Topic: North American holographic lenticular fashion market, 2026.

Context: Omega MegaCorp is launching a DTC + B2B platform for holographic lenticular textile.
Physics-based fabric that changes as the wearer moves. No equivalent product currently sold DTC at scale in North America.
TikTok is the primary distribution channel. Festival fashion, streetwear, and premium outerwear are the initial segments.
Year 1 revenue target: $3.2M base case."""

PRODUCT_BRIEF_INFOCUBE = """Product: The Information Cube
An improbable sphere covered in kinetic keyboard keys with a central display. It functions as a mixed media creativity controller, gaming input device, and digital audio/video controller. It makes the invisible (cognition, creativity, thought) physically observable and interactable. Price point: $150-300. Target customer: creators, gamers, musicians, and anyone who thinks with their hands."""

PRODUCT_BRIEF_PFPCARDS = """Product: pfpcards (xyz.cards)
Custom-printed, laser-etched brass business cards with an embedded NFC chip. Tap the card to any smartphone and instantly transfer contact info, links, or a portfolio. Produced in-house at Omega's SF fabrication lab. Positioned as a premium networking tool for founders, creatives, and professionals. Price: $40-80 per card. Live at www.pfpcards.com."""

SUPPORT_COMPLAINT_1 = """Customer message: 'I ordered 10 pfpcards 2 weeks ago and I still haven't received a shipping confirmation. I have a conference next Thursday and I specifically need these cards for it. This is really frustrating — I paid $450 and heard nothing. Please help.'"""

SUPPORT_COMPLAINT_2 = """Customer message: 'I tapped my new pfpcard on my friend's Android phone and nothing happened. It worked fine on my iPhone. Is there a compatibility issue? Did I get a defective card?'"""

SUPPORT_COMPLAINT_3 = """Customer message: 'I saw the holographic jacket on TikTok and I NEED it. How do I buy one? I can't find a store link anywhere. Also do you ship to Canada?'"""

BUSINESS_TASKS = [
    ("B1: market intel report - lenticular fashion", f"""You are a Business Agent. Write a client-ready market intelligence report from this brief. Format: Executive Summary (2 sentences), 3 Key Findings (with specific supporting points), Market Implications, and 3 Actionable Recommendations for Omega. No hallucinated data.\n\n{MARKET_BRIEF}"""),
    ("B2a: product copy - InformationCube", f"""You are a Business Agent. Write product page copy from this brief. Deliver: Headline (under 10 words, specific not generic), Subheadline (one sentence), 3 Value Props (concrete, not fluffy), CTA (under 5 words), SEO meta description (under 160 characters).\n\n{PRODUCT_BRIEF_INFOCUBE}"""),
    ("B2b: product copy - pfpcards", f"""You are a Business Agent. Write product page copy from this brief. Deliver: Headline (under 10 words), Subheadline (one sentence), 3 Value Props (concrete), CTA (under 5 words), SEO meta description (under 160 characters).\n\n{PRODUCT_BRIEF_PFPCARDS}"""),
    ("B4a: support draft - shipping delay", f"""You are a Support Agent. Write a Tier-1 draft customer response. Under 150 words. Acknowledge the specific complaint, give a clear next step, appropriate tone. FAQ context: standard processing 5-7 business days, shipping 3-5 business days, expedite requests handled case by case.\n\n{SUPPORT_COMPLAINT_1}"""),
    ("B4b: support draft - NFC compatibility", f"""You are a Support Agent. Write a Tier-1 draft response. Under 150 words. FAQ context: NFC works on all NFC-enabled Android (4.4+) and iPhone (XR+). If Android fails, try: Settings → NFC → ensure enabled, hold card to back of phone for 2-3 seconds near camera. Most cases resolve with these steps.\n\n{SUPPORT_COMPLAINT_2}"""),
    ("B4c: support draft - purchase inquiry", f"""You are a Support Agent. Write a Tier-1 draft response. Under 150 words. Context: holographic jackets not yet available for purchase — launch drop coming soon. Canada shipping: not yet available but planned. Capture email for drop notification.\n\n{SUPPORT_COMPLAINT_3}"""),
]

# ---------------------------------------------------------------------------
# ROLE 5 — MEMORY / SYNTHESIS
# ---------------------------------------------------------------------------
SYNTHETIC_LOGS = """
=== ops-agent-2026-03-19.jsonl ===
{"ts":"09:00","level":"INFO","msg":"Health check started"}
{"ts":"09:00","level":"INFO","msg":"Ollama: responding","models":["qwen3:32b","nomic-embed-text"]}
{"ts":"09:01","level":"WARNING","msg":"Disk usage 78%","threshold":80}
{"ts":"09:02","level":"FATAL","msg":"Neo4j connection refused","uri":"bolt://localhost:7687"}
{"ts":"09:03","level":"INFO","msg":"Tier-2 alert sent: Neo4j down"}
{"ts":"13:00","level":"INFO","msg":"Health check started"}
{"ts":"13:00","level":"INFO","msg":"Ollama: responding"}
{"ts":"13:01","level":"INFO","msg":"Disk usage 79%"}
{"ts":"13:02","level":"FATAL","msg":"Neo4j connection refused","uri":"bolt://localhost:7687"}
{"ts":"13:02","level":"INFO","msg":"Tier-2 alert sent: Neo4j down (repeat)"}

=== build-agent-2026-03-19.jsonl ===
{"ts":"11:30","level":"INFO","msg":"Task build-1742300001 started","goal":"Fix NFC write silent failure"}
{"ts":"11:31","level":"INFO","msg":"Branch created","branch":"fix/nfc-write-error"}
{"ts":"11:35","level":"INFO","msg":"EXPLORE complete","files_mapped":3}
{"ts":"11:40","level":"INFO","msg":"PLAN written","plan":"plan-nfc-fix.md"}
{"ts":"11:45","level":"WARNING","msg":"2 tests skipped: no NFC hardware in env"}
{"ts":"11:52","level":"FATAL","msg":"Tests failed","test":"nfc.test.js","expected":137,"got":142}
{"ts":"11:52","level":"INFO","msg":"Task blocked","reason":"byte limit off by 5, needs investigation"}
{"ts":"14:00","level":"INFO","msg":"Task build-1742300002 started","goal":"Add batch endpoint POST /api/cards/batch"}
{"ts":"14:05","level":"INFO","msg":"Branch created","branch":"feature/batch-nfc-encoding"}
{"ts":"14:45","level":"INFO","msg":"Tests passed","passed":12,"failed":0}
{"ts":"14:46","level":"INFO","msg":"Output contract written","status":"success"}

=== research-agent-2026-03-19.jsonl ===
{"ts":"08:00","level":"INFO","msg":"Intel scan started"}
{"ts":"08:01","level":"INFO","msg":"No unprocessed scout reports"}
{"ts":"12:00","level":"INFO","msg":"Intel scan started"}
{"ts":"12:02","level":"INFO","msg":"Scout report found","file":"github-scout-2026-03-19.md"}
{"ts":"12:05","level":"INFO","msg":"Repo scored 7/10","repo":"EmergentWebActions","verdict":"watch"}
{"ts":"12:05","level":"INFO","msg":"Appended to repo-queue/pending.md"}
"""

MEMORY_TASKS = [
    ("M1: log synthesis - structured MEMORY.md append", f"""You are a Memory Librarian. Synthesize today's agent logs into a structured MEMORY.md append entry.

Format:
## {DATE}
**Completed:** [list]
**Blocked:** [list with reasons]
**Patterns:** [recurring observations, not just event list]
**Errors:** [FATALs with probable cause]
**Stats:** tasks completed N, blocked N, avg build time X min

Rules: no raw log lines, under 400 words, extract patterns not just events.

Logs:
{SYNTHETIC_LOGS}"""),

    ("M2: failure pattern extraction", f"""You are a Memory Librarian. Analyze these logs and identify recurring failure patterns.

For each pattern:
- Pattern name (3-5 words)
- Evidence (which log entries, how many times)
- Proposed CONSTRAINTS.md rule to prevent recurrence

Logs:
{SYNTHETIC_LOGS}"""),
]

# ---------------------------------------------------------------------------
# RUNNER
# ---------------------------------------------------------------------------
all_results = {}

def run_role(role_name, models, tasks, use_tools=False):
    print(f"\n{'='*65}")
    print(f"  ROLE: {role_name.upper()}")
    print(f"{'='*65}")
    role_results = {}
    for model in models:
        print(f"\n  Model: {model}")
        role_results[model] = score(model, tasks, use_tools=use_tools, role_label=role_name)
    all_results[role_name] = role_results
    return role_results


def tally(results):
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    latencies = [r["latency"] for r in results]
    avg_lat = sum(latencies) / len(latencies) if latencies else 0
    return passed, total, round(avg_lat, 1)


def write_report():
    lines = [
        f"# Role-Specialist Bakeoff — {DATE}",
        f"",
        f"**Models tested:** {', '.join(set(m for role in all_results.values() for m in role))}",
        f"**Run completed:** {datetime.now().strftime('%H:%M')}",
        "",
    ]

    # Master decision sheet
    lines += ["## Master Decision Sheet", ""]
    lines += ["| Role | Model | Tasks Passed | Avg Latency | Format Errors |",
              "|------|-------|-------------|-------------|---------------|"]
    for role, models in all_results.items():
        for model, results in models.items():
            p, t, avg = tally(results)
            fmt_errors = sum(1 for r in results if "tool_calls" in r.get("detail", "") or r["status"] == "FAIL")
            lines.append(f"| {role} | {model} | {p}/{t} | {avg}s | {fmt_errors} |")

    lines.append("")

    # Per-role detail
    for role, models in all_results.items():
        lines += [f"## Role: {role.title()}", ""]
        for model, results in models.items():
            p, t, avg = tally(results)
            lines += [f"### {model} — {p}/{t} passed, avg {avg}s", ""]
            lines += ["| Task | Status | Latency | Detail |",
                      "|------|--------|---------|--------|"]
            for r in results:
                lines.append(f"| {r['task']} | {r['status']} | {r['latency']}s | {r['detail'][:60]} |")
            lines.append("")

    lines += ["", f"*Generated by run-role-bakeoff.py — OpenClaw v4.2*"]

    with open(OUTPUT, "w") as f:
        f.write("\n".join(lines))
    print(f"\n  Report saved to: {OUTPUT}")


def main():
    print(f"\nOpenClaw Role-Specialist Bakeoff — {DATE}")
    print(f"Est. runtime: 2-3 hours. Output: {OUTPUT}\n")

    run_role("coding",   ROLE_MODELS["coding"],   CODING_TASKS,   use_tools=True)
    run_role("research", ROLE_MODELS["research"],  RESEARCH_TASKS, use_tools=False)
    run_role("ops",      ROLE_MODELS["ops"],       OPS_TASKS,      use_tools=False)
    run_role("business", ROLE_MODELS["business"],  BUSINESS_TASKS, use_tools=False)
    run_role("memory",   ROLE_MODELS["memory"],    MEMORY_TASKS,   use_tools=False)

    write_report()

    print("\n" + "="*65)
    print("  BAKEOFF COMPLETE")
    print("="*65)
    for role, models in all_results.items():
        print(f"\n  {role.upper()}:")
        for model, results in models.items():
            p, t, avg = tally(results)
            print(f"    {model}: {p}/{t} ({avg}s avg)")


if __name__ == "__main__":
    main()
