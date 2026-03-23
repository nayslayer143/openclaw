#!/usr/bin/env python3
from __future__ import annotations
"""
Clawmson Scout — Telegram UX layer for the Twitter Scout pipeline.
Handles link processing, digest generation, and report formatting.
clawmson_scout never imports telegram-dispatcher; send_fn is injected.
"""

import re
import clawmson_db as db
import clawmson_twitter as tw

_TWITTER_RE = re.compile(r'https?://(x\.com|twitter\.com)/\w+/status/\d+')

_EMOJI = {
    "tool":                 "🔧",
    "technique":            "💡",
    "business_intel":       "📈",
    "code_pattern":         "🧩",
    "market_intel":         "📊",
    "irrelevant":           "🗑",
    "extraction_failed":    "❌",
    "categorization_failed":"⚠️",
}


def format_scout_report(results: list) -> str:
    """Compact summary sent immediately after batch processing completes."""
    total = len(results)
    link_word = "link" if total == 1 else "links"

    # Count by category
    counts: dict = {}
    for r in results:
        cat = r["categorization"].get("category", "unknown")
        counts[cat] = counts.get(cat, 0) + 1

    # Category summary line — priority categories first, failures last
    cat_parts = []
    priority_cats = ["tool", "technique", "business_intel", "code_pattern", "market_intel"]
    other_cats    = ["irrelevant", "extraction_failed", "categorization_failed"]
    for cat in priority_cats:
        if cat in counts:
            emoji = _EMOJI.get(cat, "•")
            n = counts[cat]
            label = cat.replace("_", " ")
            cat_parts.append(f"{emoji} {n} {label}")
    for cat in other_cats:
        if cat in counts:
            emoji = _EMOJI.get(cat, "•")
            n = counts[cat]
            label = cat.replace("_", " ")
            cat_parts.append(f"{emoji} {n} {label}")

    # Top find: highest relevance_score
    scored = sorted(
        results,
        key=lambda r: r["categorization"].get("relevance_score", 0),
        reverse=True
    )
    top = scored[0]["categorization"] if scored else {}
    top_score   = top.get("relevance_score", 0)
    top_summary = top.get("summary", "")

    lines = [f"📊 Scout Report ({total} {link_word})"]
    if cat_parts:
        lines.append(" · ".join(cat_parts))
    if top_score and top_summary:
        lines.append(f"\nTop find ({top_score}/10): {top_summary}")
    lines.append("\nSend /scout for full digest.")
    return "\n".join(lines)


def generate_digest(chat_id: str, since_hours: int = 24) -> str:
    """Full categorized digest for /scout command."""
    digest = db.get_scout_digest(chat_id, since_hours=since_hours)
    counts    = digest.get("counts", {})
    top_items = digest.get("top_items", [])

    if not counts:
        return f"No scouted links in the last {since_hours}h. Paste some Twitter/X links to get started."

    lines = [f"📋 Scout Digest (last {since_hours}h)\n"]

    # Category breakdown sorted by count descending
    for cat, n in sorted(counts.items(), key=lambda x: -x[1]):
        emoji = _EMOJI.get(cat, "•")
        label = cat.replace("_", " ")
        lines.append(f"{emoji} {label}: {n}")

    # Top items
    if top_items:
        lines.append("\n🏆 Top finds:")
        for item in top_items:
            score   = item.get("relevance_score", 0)
            summary = item.get("summary") or "(no summary)"
            author  = item.get("author") or "unknown"
            cat     = item.get("category", "")
            emoji   = _EMOJI.get(cat, "•")
            url     = item.get("url", "")
            lines.append(f"{emoji} [{score}/10] @{author}: {summary}")
            lines.append(f"   {url}")

    return "\n".join(lines)


def handle_scout_links(chat_id: str, message_text: str, send_fn) -> None:
    """
    Main entry point, called from _scout_thread in telegram-dispatcher.
    send_fn is the dispatcher's send() — injected to avoid circular import.
    """
    full_urls = [m.group(0) for m in _TWITTER_RE.finditer(message_text)]

    n = len(full_urls)
    link_word = "link" if n == 1 else "links"
    send_fn(chat_id, f"🔍 Scouting {n} {link_word}...")

    batch = tw.process_batch(full_urls)

    for record in batch["results"]:
        db.save_scout_link(
            chat_id,
            record["url"],
            record["extraction"],
            record["categorization"],
        )

    send_fn(chat_id, format_scout_report(batch["results"]))
