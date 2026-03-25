#!/usr/bin/env python3
"""
Feed quality comparison: PRAW (free) vs ScrapeCreators (paid).

Runs both Reddit backends on the same topic and prints a side-by-side
quality report so you can decide which is worth keeping.

Usage:
    python3 compare_feeds.py "Polymarket prediction market"
    python3 compare_feeds.py "Kalshi AI betting" --time-filter week
    python3 compare_feeds.py --topics all   # runs default trading topics
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

_SCRIPTS = Path(__file__).parent
sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(_SCRIPTS.parent))  # openclaw/scripts

_LAST30DAYS_PY = Path.home() / ".claude" / "skills" / "last30days" / "scripts" / "last30days.py"

DEFAULT_TOPICS = [
    "Polymarket prediction market",
    "Kalshi prediction market",
    "Trump Polymarket odds",
]

# ── Colour helpers ─────────────────────────────────────────────────────────────

_GREEN  = "\033[92m"
_YELLOW = "\033[93m"
_RED    = "\033[91m"
_CYAN   = "\033[96m"
_BOLD   = "\033[1m"
_RESET  = "\033[0m"

def _c(text, colour):
    return f"{colour}{text}{_RESET}"

# ── ScrapeCreators runner (via last30days --emit=json) ─────────────────────────

def run_scrapecreators(topic: str, timeout: int = 120) -> dict:
    """Run last30days with ScrapeCreators key and return parsed JSON."""
    if not os.environ.get("SCRAPECREATORS_API_KEY"):
        return {"error": "SCRAPECREATORS_API_KEY not set", "items": []}

    try:
        t0 = time.time()
        result = subprocess.run(
            [sys.executable, str(_LAST30DAYS_PY), topic,
             "--emit=json", "--quick", "--search=reddit"],
            capture_output=True, text=True, timeout=timeout,
            cwd=str(_LAST30DAYS_PY.parent),
            env={**os.environ},
        )
        elapsed = time.time() - t0
        if result.returncode != 0:
            return {"error": result.stderr[:300], "items": [], "elapsed": elapsed}
        data = json.loads(result.stdout)
        items = data if isinstance(data, list) else data.get("items", [])
        return {"items": items, "elapsed": elapsed, "source": "scrapecreators"}
    except subprocess.TimeoutExpired:
        return {"error": "timeout", "items": []}
    except Exception as e:
        return {"error": str(e), "items": []}


# ── PRAW runner ────────────────────────────────────────────────────────────────

def run_praw(topic: str) -> dict:
    """Run PRAW Reddit search and return posts in comparable format."""
    try:
        from autoresearch.reddit_praw_feed import search_reddit, is_configured
    except ImportError:
        from reddit_praw_feed import search_reddit, is_configured

    if not is_configured():
        return {"error": "REDDIT_CLIENT_ID/SECRET not set — see setup in reddit_praw_feed.py", "items": []}

    t0 = time.time()
    posts = search_reddit(topic, limit=25, time_filter="month")
    elapsed = time.time() - t0

    # Normalize to same shape as last30days items
    items = [{
        "id":        p["id"],
        "title":     p["title"],
        "url":       p["url"],
        "text":      p["selftext"],
        "date":      p["date"],
        "relevance": p["relevance"],
        "direction": p["direction"],
        "engagement": {"score": p["score"], "num_comments": p["num_comments"]},
        "source":    "praw",
    } for p in posts]

    return {"items": items, "elapsed": elapsed, "source": "praw"}


# ── Comparison report ──────────────────────────────────────────────────────────

def _score_result(item: dict) -> float:
    """Rough quality score: relevance × log(engagement+1)."""
    import math
    rel = float(item.get("relevance") or 0.5)
    eng = item.get("engagement") or {}
    score = eng.get("score") or eng.get("ups") or 0
    comments = eng.get("num_comments") or eng.get("num_comments") or 0
    return rel * math.log1p(score + comments * 2)


def compare(topic: str, verbose: bool = False):
    print(f"\n{_c('═' * 60, _BOLD)}")
    print(f"{_c('TOPIC:', _BOLD)} {topic}")
    print(_c('═' * 60, _BOLD))

    print(f"\n{_c('[1/2] ScrapeCreators...', _CYAN)}")
    sc = run_scrapecreators(topic)

    print(f"{_c('[2/2] PRAW (free)...', _CYAN)}")
    pr = run_praw(topic)

    # ── Stats ──
    sc_items = sc.get("items", [])
    pr_items = pr.get("items", [])

    sc_elapsed = sc.get("elapsed", 0)
    pr_elapsed = pr.get("elapsed", 0)

    sc_scores  = [_score_result(i) for i in sc_items]
    pr_scores  = [_score_result(i) for i in pr_items]

    sc_avg  = sum(sc_scores) / len(sc_scores) if sc_scores else 0
    pr_avg  = sum(pr_scores) / len(pr_scores) if pr_scores else 0
    sc_top3 = sorted(sc_scores, reverse=True)[:3]
    pr_top3 = sorted(pr_scores, reverse=True)[:3]

    def _winner(a, b):
        if a > b * 1.1:  return _c("SC wins", _GREEN)
        if b > a * 1.1:  return _c("PRAW wins", _GREEN)
        return _c("tie", _YELLOW)

    print(f"\n{'Metric':<28} {'ScrapeCreators':>16} {'PRAW (free)':>16}")
    print("-" * 62)
    sc_err = f"  {_c('ERROR', _RED)}" if sc.get("error") else ""
    pr_err = f"  {_c('ERROR', _RED)}" if pr.get("error") else ""
    print(f"{'Posts returned':<28} {len(sc_items):>16}{sc_err} {len(pr_items):>16}{pr_err}")
    print(f"{'Avg quality score':<28} {sc_avg:>16.2f} {pr_avg:>16.2f}  ← {_winner(sc_avg, pr_avg)}")
    print(f"{'Top-3 avg score':<28} {sum(sc_top3)/len(sc_top3) if sc_top3 else 0:>16.2f} {sum(pr_top3)/len(pr_top3) if pr_top3 else 0:>16.2f}")
    print(f"{'Elapsed (s)':<28} {sc_elapsed:>16.1f} {pr_elapsed:>16.1f}")
    print(f"{'Cost':<28} {'~1 credit':>16} {'$0':>16}")

    if sc.get("error"):
        print(f"\n{_c('SC error:', _RED)} {sc['error']}")
    if pr.get("error"):
        print(f"\n{_c('PRAW error:', _RED)} {pr['error']}")

    if verbose and sc_items:
        print(f"\n{_c('Top 3 ScrapeCreators posts:', _CYAN)}")
        for i, item in enumerate(sorted(sc_items, key=_score_result, reverse=True)[:3], 1):
            title = item.get("title") or item.get("text", "")[:80]
            print(f"  {i}. [{item.get('date','?')}] {title[:80]}")
            print(f"     {item.get('url','')}")

    if verbose and pr_items:
        print(f"\n{_c('Top 3 PRAW posts:', _CYAN)}")
        for i, item in enumerate(sorted(pr_items, key=_score_result, reverse=True)[:3], 1):
            print(f"  {i}. [{item.get('date','?')}] {item.get('title','')[:80]}")
            print(f"     {item.get('url','')}")

    return {"topic": topic, "sc_count": len(sc_items), "praw_count": len(pr_items),
            "sc_avg": sc_avg, "praw_avg": pr_avg, "sc_elapsed": sc_elapsed, "praw_elapsed": pr_elapsed}


def main():
    parser = argparse.ArgumentParser(description="Compare ScrapeCreators vs PRAW Reddit quality")
    parser.add_argument("topic", nargs="?", help="Topic to research")
    parser.add_argument("--topics", choices=["all"], help="Run all default trading topics")
    parser.add_argument("--time-filter", default="month")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show top posts")
    parser.add_argument("--json-out", help="Save full results to JSON file")
    args = parser.parse_args()

    topics = DEFAULT_TOPICS if args.topics == "all" else [args.topic or DEFAULT_TOPICS[0]]
    all_results = []

    for topic in topics:
        r = compare(topic, verbose=args.verbose)
        all_results.append(r)

    # ── Summary ──
    if len(all_results) > 1:
        print(f"\n{_c('═' * 60, _BOLD)}")
        print(_c("SUMMARY", _BOLD))
        print(_c('═' * 60, _BOLD))
        sc_wins  = sum(1 for r in all_results if r["sc_avg"]   > r["praw_avg"] * 1.1)
        pr_wins  = sum(1 for r in all_results if r["praw_avg"] > r["sc_avg"]   * 1.1)
        ties     = len(all_results) - sc_wins - pr_wins
        print(f"ScrapeCreators wins: {sc_wins}  |  PRAW wins: {pr_wins}  |  Ties: {ties}")
        total_sc_cost = sum(1 for _ in all_results)
        print(f"Credits used this run: ~{total_sc_cost}  (out of 100 trial)")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(all_results, indent=2))
        print(f"\nResults saved to {args.json_out}")


if __name__ == "__main__":
    main()
