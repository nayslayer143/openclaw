#!/usr/bin/env python3
"""
mirofish-simulate.py — Lean market simulation engine.
Takes a question, runs structured multi-perspective analysis via Ollama, outputs scored report.

Usage:
  python3 mirofish-simulate.py "Should we enter the Open WebUI consulting market?"
  python3 mirofish-simulate.py --topic "NFC card pricing strategy" --notify

Outputs: ~/openclaw/mirofish/reports/sim-[slug]-[date].md
"""

import os
import sys
import json
import re
import hashlib
import datetime
import argparse
import urllib.request
from pathlib import Path

OPENCLAW = Path.home() / "openclaw"
REPORTS_DIR = OPENCLAW / "mirofish" / "reports"
OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
MODEL = os.environ.get("MIROFISH_MODEL", "gemma4:26b")


def llm(prompt, system="", timeout=300):
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    data = json.dumps({"model": MODEL, "messages": messages, "stream": False}).encode()
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=data,
        headers={"Content-Type": "application/json"}
    )
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        result = json.loads(resp.read())
        content = result.get("message", {}).get("content", "").strip()
        # Strip <think> tags from qwen3
        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
        return content
    except Exception as e:
        return f"[LLM error: {e}]"


def notify_telegram(msg):
    try:
        env = {}
        env_file = OPENCLAW / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.strip() and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
        token = env.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = env.get("TELEGRAM_ALLOWED_USERS", "").strip().strip('"[]').split(",")[0].strip()
        if token and chat_id:
            data = json.dumps({"chat_id": chat_id, "text": msg[:4000]}).encode()
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data=data,
                headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


SYSTEM_PROMPT = """You are MiroFish, a market simulation engine. You analyze business questions
by modeling multiple competing perspectives, then synthesizing a strategic recommendation.

Your process:
1. FRAME — Define the question, timeframe, and key variables
2. ACTORS — Identify 4-6 market actors (competitors, customers, regulators, etc.)
3. FORCES — Map the forces acting on each actor (economic, technological, regulatory, social)
4. SCENARIOS — Run 3 scenarios: optimistic, base case, pessimistic
5. SYNTHESIS — What the scenarios converge on, where they diverge, and what that means
6. RECOMMENDATION — Clear, specific, actionable next steps with confidence level

Be specific. Name real companies, cite real pricing, reference real trends.
No generic advice. Think like a strategist with access to market data."""


def simulate(topic):
    print(f"[mirofish] Simulating: {topic[:80]}")

    # Phase 1: Frame + Actors + Forces
    print("[mirofish] Phase 1: Framing...")
    frame = llm(f"""SIMULATION REQUEST: {topic}

Run phases 1-3 of your simulation process:

1. FRAME: Define the exact question, timeframe (default 6-12 months), and 4-6 key variables that will determine the outcome.

2. ACTORS: Identify 4-6 specific market actors relevant to this question. For each: name, current position, resources, likely moves.

3. FORCES: For each actor, what forces push them toward or away from different outcomes? Map at least 2 forces per actor.

Be extremely specific. Name real companies, real products, real price points.""",
        system=SYSTEM_PROMPT)

    # Phase 2: Scenarios + Synthesis
    print("[mirofish] Phase 2: Scenarios...")
    scenarios = llm(f"""Continue the simulation for: {topic}

Context from Phase 1:
{frame[:3000]}

Now run phases 4-6:

4. SCENARIOS: Model 3 distinct scenarios:
   - BULL CASE: What happens if conditions favor us? Probability estimate.
   - BASE CASE: Most likely outcome given current trajectories. Probability estimate.
   - BEAR CASE: What happens if conditions work against us? Probability estimate.

   For each scenario: specific outcomes, timeline, revenue impact, key triggers.

5. SYNTHESIS:
   - What do all 3 scenarios agree on? (These are high-confidence bets)
   - Where do they diverge? (These are the risks to monitor)
   - What's the expected value across scenarios?

6. RECOMMENDATION:
   - GO / NO-GO / CONDITIONAL — with clear conditions
   - Specific first 3 actions to take this week
   - What to monitor monthly to validate/invalidate the thesis
   - Confidence level (1-10) with justification""",
        system=SYSTEM_PROMPT)

    # Phase 3: Self-score
    print("[mirofish] Phase 3: Scoring...")
    score = llm(f"""Score this simulation report on 5 dimensions (1-5 each):

Topic: {topic}

Report:
{frame[:1500]}
{scenarios[:1500]}

Score each dimension:
1. ACCURACY — Are claims verifiable? Are named companies/prices correct?
2. SPECIFICITY — Are recommendations concrete with numbers, dates, actions?
3. FORMAT — Is it clean, structured, ready to share?
4. CONFIDENCE CALIBRATION — Does stated confidence match evidence quality?
5. ACTIONABILITY — Can the reader take clear next steps today?

Return ONLY a JSON object: {{"accuracy": N, "specificity": N, "format": N, "confidence": N, "actionability": N, "average": N, "summary": "one sentence"}}""",
        system="You are a report quality scorer. Return only valid JSON.")

    # Parse score
    try:
        score_match = re.search(r'\{[^}]+\}', score)
        score_data = json.loads(score_match.group()) if score_match else {}
    except Exception:
        score_data = {"average": "?", "summary": "Score parse failed"}

    return frame, scenarios, score_data


def run(topic, notify=False):
    today = datetime.date.today().isoformat()
    now = datetime.datetime.now().strftime("%H:%M")
    slug = re.sub(r'[^a-z0-9]+', '-', topic.lower())[:40].strip('-')

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    frame, scenarios, score = simulate(topic)

    avg = score.get("average", "?")
    report_path = REPORTS_DIR / f"sim-{slug}-{today}.md"

    report = f"""# MiroFish Simulation: {topic}
> Generated {today} at {now} | Model: {MODEL} | Engine: MiroFish v2 (lean)

---

## Quality Score: {avg}/5
| Dimension | Score |
|-----------|-------|
| Accuracy | {score.get('accuracy', '?')}/5 |
| Specificity | {score.get('specificity', '?')}/5 |
| Format | {score.get('format', '?')}/5 |
| Confidence | {score.get('confidence', '?')}/5 |
| Actionability | {score.get('actionability', '?')}/5 |

> {score.get('summary', '')}

---

## Analysis

{frame}

---

## Scenarios & Recommendation

{scenarios}

---

*Simulated by MiroFish v2. Use this to decide whether to commit resources, not as a substitute for market validation.*
"""

    report_path.write_text(report)
    print(f"[mirofish] Report written: {report_path}")
    print(f"[mirofish] Score: {avg}/5")

    if notify:
        preview = f"MiroFish simulation complete: {topic[:60]}\nScore: {avg}/5\nReport: mirofish/reports/sim-{slug}-{today}.md"
        notify_telegram(preview)

    return report_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MiroFish market simulation")
    parser.add_argument("topic", nargs="?", help="Simulation topic/question")
    parser.add_argument("--topic", "-t", dest="topic_flag", help="Topic (alternative flag)")
    parser.add_argument("--notify", "-n", action="store_true", help="Send Telegram notification")
    args = parser.parse_args()

    topic = args.topic or args.topic_flag
    if not topic:
        print("Usage: python3 mirofish-simulate.py 'Should we enter the X market?'")
        sys.exit(1)

    run(topic, notify=args.notify)
