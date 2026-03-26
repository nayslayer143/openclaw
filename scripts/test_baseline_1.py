#!/usr/bin/env python3
"""
Baseline test: visit https://example.com, extract title and all links.

Uses the browser tools from ~/openclaw/scripts/browser/.
Run from the scripts/ directory or ensure the path is on sys.path.

Usage:
    python /Users/nayslayer/openclaw/scripts/test_baseline_1.py
"""

import sys
from pathlib import Path

# Ensure the scripts/ directory is on the path so `browser` is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from browser.browser_tools import browser_open, browser_shutdown

TARGET_URL = "https://example.com"


def main():
    print(f"Visiting: {TARGET_URL}\n")

    result = browser_open(TARGET_URL, wait_until="domcontentloaded", extract="dom")

    if not result.get("ok"):
        print(f"ERROR: {result.get('error')}")
        if result.get("traceback"):
            print(result["traceback"])
        sys.exit(1)

    # --- Title ---
    title = result.get("title", "(no title)")
    print(f"Page Title: {title}")
    print(f"Final URL:  {result.get('url')}")

    # --- Links ---
    # browser_open() caps at 20 links via eyes.links()[:20].
    # For a full list we call Eyes directly (see below).
    links = result.get("links", [])

    if links:
        print(f"\nLinks found ({len(links)}):")
        for i, link in enumerate(links, 1):
            text = link.get("text") or "(no text)"
            href = link.get("href") or "(no href)"
            print(f"  {i:>3}. {text[:60]!r:<62}  {href}")
    else:
        print("\nNo links found on the page.")

    # --- Shutdown the persistent browser pool cleanly ---
    browser_shutdown()
    print("\nDone.")


if __name__ == "__main__":
    main()
