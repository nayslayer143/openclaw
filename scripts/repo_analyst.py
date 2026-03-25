#!/usr/bin/env python3
from __future__ import annotations
"""
GitHub Repo Analyst — Ollama-powered intelligence scoring
Reads crawler output, sends top repos to local LLM, writes recommendations.

Usage:
    python repo_analyst.py                          # analyze latest crawl
    python repo_analyst.py --crawl-file path.json   # analyze specific crawl
    python repo_analyst.py --top 20                 # only top N repos (default 40)
    python repo_analyst.py --model qwen3:30b        # specify model (default qwen3:30b)

Dependencies: NONE beyond stdlib. Ollama called via urllib (localhost:11434).
"""
import json
import os
import sys
import time
import uuid
import argparse
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

# ─── CONFIG ────────────────────────────────────────────────────────────────────

OPENCLAW_ROOT = Path.home() / "openclaw"
DATASET_DIR = OPENCLAW_ROOT / "autoresearch" / "outputs" / "datasets"
INTEL_DIR = OPENCLAW_ROOT / "autoresearch" / "github-intel"
RECS_FILE = INTEL_DIR / "recommendations.json"
OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen3:30b"
DEFAULT_TOP_N = 40
MAX_RETRIES = 1
REQUEST_DELAY = 1.0  # seconds between Ollama calls

# ─── OLLAMA INTERFACE ──────────────────────────────────────────────────────────

def ollama_available() -> bool:
    """Check if Ollama is running."""
    try:
        req = urllib.request.Request("http://localhost:11434/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


def call_ollama(prompt: str, model: str) -> str:
    """Send prompt to Ollama, return raw response text.
    Handles qwen3 thinking mode: if response is empty, falls back to thinking field."""
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 4096},
    }).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        response = body.get("response", "")
        # qwen3 thinking mode: actual output may be in response, thinking in thinking field
        # If response is empty, try to extract JSON from thinking field
        if not response.strip() and body.get("thinking", ""):
            response = body["thinking"]
        return response


def parse_llm_json(raw: str) -> dict | None:
    """Extract JSON from LLM response, handling markdown fences."""
    text = raw.strip()
    # Strip markdown code fences
    if "```" in text:
        lines = text.split("\n")
        inside = False
        json_lines = []
        for line in lines:
            if line.strip().startswith("```"):
                inside = not inside
                continue
            if inside:
                json_lines.append(line)
        text = "\n".join(json_lines).strip()
    # Strip /no_think tags from qwen3 models
    if "<think>" in text:
        import re
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try to find JSON object in text
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass
    return None


# ─── PROMPT ────────────────────────────────────────────────────────────────────

def build_prompt(repo: dict) -> str:
    return f"""You are a trading systems architect reviewing open-source repos for potential integration into a prediction market trading bot stack.

The stack has 3 bots:
- Clawmpson: main trading system with 4 strategies (arb, price-lag, momentum, LLM), 5 feeds, graduation engine (Python, 10+ modules, SQLite)
- ArbClaw: lean single-strategy arb detector, 5-min cycle (Python, 3 files, not yet built)
- RivalClaw: Chad's rival instance at ~/rivalclaw/ — 8-strategy quant engine + hedge engine, Polymarket + Kalshi + CoinGecko, self-tuner, own SQLite DB

Repo: {repo.get('name', 'unknown')}
URL: {repo.get('url', '')}
Stars: {repo.get('stars', 0)} | Forks: {repo.get('forks', 0)} | Language: {repo.get('language', 'Unknown')}
Last updated: {repo.get('last_updated', 'unknown')}
Description: {repo.get('description', 'No description')}
Topics: {', '.join(repo.get('topics', []))}
README snippet: {repo.get('readme_snippet', 'N/A')[:500]}

Score this repo:
1. integration_value (1-10): how useful would integrating patterns/code from this repo be?
2. complexity (1-10): how hard is the integration? (1=drop-in, 10=massive refactor)
3. clawmpson_relevance (1-10): relevance to Clawmpson (main multi-strategy system)
4. arbclaw_relevance (1-10): relevance to ArbClaw (lean arb detector)
5. rivalclaw_relevance (1-10): relevance to RivalClaw (rival strategy comparison)
6. what_to_take: 1-2 sentence description of what specifically to extract/integrate
7. risk: any risks or concerns (license, maintenance, complexity)
8. verdict: INTEGRATE / STUDY / SKIP

Respond in JSON only, no markdown. Do not wrap in code fences. /no_think"""


# ─── ANALYSIS ──────────────────────────────────────────────────────────────────

def analyze_repo(repo: dict, model: str) -> dict | None:
    """Analyze a single repo via Ollama. Returns parsed scores or None."""
    prompt = build_prompt(repo)
    for attempt in range(MAX_RETRIES + 1):
        try:
            raw = call_ollama(prompt, model)
            parsed = parse_llm_json(raw)
            if parsed and "integration_value" in parsed:
                return parsed
            if attempt < MAX_RETRIES:
                print(f"    Retry {attempt + 1}: malformed response, retrying...")
                time.sleep(REQUEST_DELAY)
        except urllib.error.URLError as e:
            print(f"    Ollama error: {e}")
            return None
        except Exception as e:
            print(f"    Error: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(REQUEST_DELAY)
    return None


def load_crawl(filepath: Path) -> list[dict]:
    """Load crawler JSON output."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def find_latest_crawl() -> Path | None:
    """Find most recent crawl JSON in dataset dir."""
    if not DATASET_DIR.exists():
        return None
    jsons = sorted(DATASET_DIR.glob("crawl_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    # Also check files matching github_scan_*.json or crawl*.json
    if not jsons:
        jsons = sorted(DATASET_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return jsons[0] if jsons else None


def load_existing_recs() -> dict:
    """Load existing recommendations file, or return empty structure."""
    if RECS_FILE.exists():
        try:
            return json.loads(RECS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"crawl_date": "", "analyzed_at": "", "model": "", "total_analyzed": 0, "recommendations": []}


def run_analysis(crawl_file: Path, top_n: int = DEFAULT_TOP_N, model: str = DEFAULT_MODEL):
    """Main analysis pipeline."""
    print(f"\n{'='*60}")
    print(f"  GITHUB INTELLIGENCE ANALYST")
    print(f"  Model: {model} | Top: {top_n}")
    print(f"  Crawl: {crawl_file.name}")
    print(f"{'='*60}\n")

    # Check Ollama
    if not ollama_available():
        print("ERROR: Ollama is not running at localhost:11434")
        print("  Start with: ollama serve")
        print("  Skipping analysis gracefully.")
        return

    # Load crawl data
    repos = load_crawl(crawl_file)
    if not repos:
        print("No repos found in crawl file.")
        return

    # Sort by signal_score, take top N
    repos.sort(key=lambda r: r.get("signal_score", 0), reverse=True)
    repos = repos[:top_n]
    print(f"Analyzing {len(repos)} repos...\n")

    # Load existing recs to preserve status of already-reviewed items
    # CRITICAL: repos are NEVER deleted. We accumulate across crawls.
    existing = load_existing_recs()
    existing_by_url = {r["repo_url"]: r for r in existing.get("recommendations", [])}

    # Start with all existing recs that won't be re-analyzed (preserves old discoveries)
    new_urls_this_crawl = {repo.get("url", "") for repo in repos}
    preserved_recs = [r for r in existing.get("recommendations", []) if r["repo_url"] not in new_urls_this_crawl]

    recommendations = []
    for i, repo in enumerate(repos, 1):
        name = repo.get("full_name") or repo.get("name", "unknown")
        url = repo.get("url", "")
        print(f"  [{i}/{len(repos)}] {name} (*{repo.get('stars', 0):,})")

        scores = analyze_repo(repo, model)
        time.sleep(REQUEST_DELAY)

        if scores is None:
            print(f"    -> analysis_failed")
            rec = {
                "id": str(uuid.uuid4()),
                "repo_name": name,
                "repo_url": url,
                "stars": repo.get("stars", 0),
                "language": repo.get("language", "Unknown"),
                "signal_score": repo.get("signal_score", 0),
                "integration_value": 0,
                "complexity": 0,
                "clawmpson_relevance": 0,
                "arbclaw_relevance": 0,
                "rivalclaw_relevance": 0,
                "what_to_take": "",
                "risk": "analysis_failed",
                "verdict": "SKIP",
                "status": "analysis_failed",
                "approved_for": [],
                "approved_at": None,
                "task_id": None,
            }
        else:
            # Clamp scores to 1-10
            def clamp(v, lo=1, hi=10):
                try:
                    return max(lo, min(hi, int(v)))
                except (TypeError, ValueError):
                    return 5

            # Preserve status if repo was already reviewed
            prev = existing_by_url.get(url, {})
            status = prev.get("status", "pending")
            if status in ("approved", "rejected", "bookmarked"):
                # Keep existing review status
                pass
            else:
                status = "pending"

            rec = {
                "id": prev.get("id", str(uuid.uuid4())),
                "repo_name": name,
                "repo_url": url,
                "stars": repo.get("stars", 0),
                "language": repo.get("language", "Unknown"),
                "signal_score": repo.get("signal_score", 0),
                "integration_value": clamp(scores.get("integration_value", 5)),
                "complexity": clamp(scores.get("complexity", 5)),
                "clawmpson_relevance": clamp(scores.get("clawmpson_relevance", 5)),
                "arbclaw_relevance": clamp(scores.get("arbclaw_relevance", 5)),
                "rivalclaw_relevance": clamp(scores.get("rivalclaw_relevance", 5)),
                "what_to_take": str(scores.get("what_to_take", ""))[:300],
                "risk": str(scores.get("risk", ""))[:300],
                "verdict": scores.get("verdict", "STUDY").upper(),
                "status": status,
                "approved_for": prev.get("approved_for", []),
                "approved_at": prev.get("approved_at"),
                "task_id": prev.get("task_id"),
            }
            # Normalize verdict
            if rec["verdict"] not in ("INTEGRATE", "STUDY", "SKIP"):
                rec["verdict"] = "STUDY"

            print(f"    -> {rec['verdict']} (val={rec['integration_value']}, cx={rec['complexity']})")

        recommendations.append(rec)

    # Merge: new/updated recs + preserved old recs (NEVER delete)
    all_recs = recommendations + preserved_recs

    # Sort by integration_value descending
    all_recs.sort(key=lambda r: r.get("integration_value", 0), reverse=True)

    # Write output — accumulates across crawls, nothing is ever lost
    INTEL_DIR.mkdir(parents=True, exist_ok=True)
    output = {
        "crawl_date": datetime.now().strftime("%Y-%m-%d"),
        "analyzed_at": datetime.now().isoformat(),
        "model": model,
        "total_analyzed": len(recommendations),  # new this run
        "total_library": len(all_recs),           # total accumulated
        "recommendations": all_recs,
    }
    RECS_FILE.write_text(json.dumps(output, indent=2), encoding="utf-8")

    # Also snapshot to dated archive (belt-and-suspenders: repos are NEVER lost)
    archive_file = INTEL_DIR / f"recommendations_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    archive_file.write_text(json.dumps(output, indent=2), encoding="utf-8")

    # Summary
    verdicts = {}
    for r in recommendations:
        v = r.get("verdict", "SKIP")
        verdicts[v] = verdicts.get(v, 0) + 1

    print(f"\n{'='*60}")
    print(f"  ANALYSIS COMPLETE")
    print(f"  New repos analyzed: {len(recommendations)}")
    print(f"  Total library size: {len(all_recs)}")
    for v, c in sorted(verdicts.items()):
        print(f"    {v}: {c}")
    print(f"  Preserved from previous crawls: {len(preserved_recs)}")
    print(f"  Output: {RECS_FILE}")
    print(f"  Snapshot: {archive_file.name}")
    print(f"{'='*60}\n")


# ─── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GitHub Repo Analyst — Ollama LLM scoring")
    parser.add_argument("--crawl-file", type=str, help="Path to crawl JSON file")
    parser.add_argument("--top", type=int, default=DEFAULT_TOP_N, help="Analyze top N repos (default 40)")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL, help="Ollama model (default qwen3:30b)")
    args = parser.parse_args()

    if args.crawl_file:
        crawl_path = Path(args.crawl_file)
    else:
        crawl_path = find_latest_crawl()

    if not crawl_path or not crawl_path.exists():
        print("ERROR: No crawl file found.")
        print(f"  Looked in: {DATASET_DIR}")
        print("  Provide --crawl-file or run github_crawler.py first.")
        sys.exit(1)

    run_analysis(crawl_path, top_n=args.top, model=args.model)
