#!/usr/bin/env python3
"""
design-inject.py — Design KB Brief Injector
Omega MegaCorp / OpenClaw

Usage:
  python design-inject.py "brutalist typographic neon"          # tag query
  python design-inject.py --top 3                               # top by intensity
  python design-inject.py --for landing                         # filter by applicable_to
  python design-inject.py --random                              # random high-intensity pick
  python design-inject.py --brief-only                          # just brief_injection lines
  python design-inject.py --stats                               # KB summary stats

Called automatically by cinematic-web / aesthetic-pulse skills.
Claude Code can also call it directly: python agents/tools/design-inject.py "[tags]"

Returns: formatted text block ready for brief injection.
"""

import json
import sys
import random
import argparse
from pathlib import Path
from datetime import datetime, timedelta

KB_PATH = Path(__file__).parent.parent.parent / "autoresearch/outputs/datasets/design-kb-current.json"


def load_kb():
    if not KB_PATH.exists():
        return []
    with open(KB_PATH) as f:
        data = json.load(f)
    return data.get("entries", [])


def score_entry(entry, query_tags):
    """Score an entry against query tags. Returns 0–100."""
    if not query_tags:
        return entry.get("intensity", 5) * 10

    entry_tags = set(
        t.lower() for t in
        entry.get("aesthetic_tags", []) + entry.get("techniques", []) + entry.get("applicable_to", [])
    )
    query_set = set(t.lower() for t in query_tags)

    overlap = len(query_set & entry_tags)
    tag_score = (overlap / max(len(query_set), 1)) * 60
    intensity_score = entry.get("intensity", 5) * 4  # max 40

    return tag_score + intensity_score


def format_entry(entry, index, brief_only=False):
    """Format a single KB entry for brief injection."""
    if brief_only:
        return f'  • "{entry["brief_injection"]}" — {entry["name"]}'

    lines = [
        f"[REF {index}] {entry['name']}",
        f"  URL: {entry['url']}",
        f"  What works: {entry['what_makes_it_special']}",
        f"  The unexpected: {entry['the_unexpected']}",
        f"  Techniques: {', '.join(entry.get('techniques', [])[:5])}",
        f"  Tags: {', '.join(entry.get('aesthetic_tags', [])[:4])}  |  Intensity: {entry.get('intensity', '?')}/10",
        f"  → BRIEF INJECTION: \"{entry['brief_injection']}\"",
    ]
    return "\n".join(lines)


def print_header(query_tags, n, mode):
    print("=" * 60)
    print("DESIGN KB — BRIEF INJECTION")
    print(f"Query: {' '.join(query_tags) if query_tags else mode}")
    print(f"Returning: top {n} matches")
    print(f"KB: {KB_PATH}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Design KB brief injector")
    parser.add_argument("query", nargs="*", help="Aesthetic/technique tags to match")
    parser.add_argument("--top", type=int, default=3, help="Number of entries to return (default 3)")
    parser.add_argument("--for", dest="applicable_to", help="Filter by applicable_to type")
    parser.add_argument("--random", action="store_true", help="Return random high-intensity pick")
    parser.add_argument("--brief-only", action="store_true", help="Return only brief_injection lines")
    parser.add_argument("--stats", action="store_true", help="Show KB summary stats")
    parser.add_argument("--json", action="store_true", help="Output raw JSON entries")

    args = parser.parse_args()
    entries = load_kb()

    if not entries:
        print("Design KB is empty. Run design-intel-scout.lobster to populate it.")
        sys.exit(0)

    # Stats mode
    if args.stats:
        all_tags = [t for e in entries for t in e.get("aesthetic_tags", [])]
        all_techniques = [t for e in entries for t in e.get("techniques", [])]
        tag_counts = {}
        for t in all_tags:
            tag_counts[t] = tag_counts.get(t, 0) + 1
        top_tags = sorted(tag_counts.items(), key=lambda x: -x[1])[:10]

        print(f"\nDESIGN KB STATS")
        print(f"  Total entries: {len(entries)}")
        print(f"  Intensity avg: {sum(e.get('intensity',5) for e in entries)/len(entries):.1f}/10")
        print(f"  Date range: {min(e['discovered'] for e in entries)} → {max(e['discovered'] for e in entries)}")
        print(f"  Sources: {', '.join(set(e.get('source','?') for e in entries))}")
        print(f"\n  Top aesthetic tags:")
        for tag, count in top_tags:
            print(f"    {tag}: {count}")
        print(f"\n  Unique techniques: {len(set(all_techniques))}")
        return

    # Filter by applicable_to
    if args.applicable_to:
        entries = [e for e in entries if args.applicable_to.lower() in [t.lower() for t in e.get("applicable_to", [])]]

    # Random mode
    if args.random:
        high_intensity = [e for e in entries if e.get("intensity", 0) >= 7]
        pool = high_intensity if high_intensity else entries
        selected = [random.choice(pool)]
        print_header([], 1, "random")
        print(format_entry(selected[0], 1, args.brief_only))
        return

    # Score and rank
    query_tags = args.query if args.query else []
    scored = sorted(entries, key=lambda e: score_entry(e, query_tags), reverse=True)
    top = scored[:args.top]

    if not args.brief_only and not args.json:
        print_header(query_tags, len(top), "tag match")
        print()

    if args.json:
        print(json.dumps(top, indent=2))
        return

    if args.brief_only:
        print("\nBRIEF INJECTIONS from Design KB:")
        for i, entry in enumerate(top, 1):
            print(format_entry(entry, i, brief_only=True))
        print()
        return

    for i, entry in enumerate(top, 1):
        print(format_entry(entry, i))
        if i < len(top):
            print()

    print()
    print(f"Tip: Drop the → BRIEF INJECTION lines directly into your design brief.")
    print(f"     Run with --stats to see full KB breakdown.")


if __name__ == "__main__":
    main()
