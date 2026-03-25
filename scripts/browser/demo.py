#!/usr/bin/env python3
"""Live demo of Browser Eyes & Hands — run with HEADED=1 to watch."""

import sys, time
from pathlib import Path

# Add scripts/ to path so `browser.x` imports work
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from browser.browser_engine import BrowserEngine
from browser.eyes import Eyes
from browser.hands import Hands

DEMO_URL = "https://news.ycombinator.com"

def main():
    print("\n🦞 Browser Eyes & Hands — Live Demo\n")

    with BrowserEngine(headless=False, rate_limit_seconds=(0.5, 1.0)) as engine:
        eyes = Eyes(engine)
        hands = Hands(engine)

        # --- Navigate ---
        print(f"📍 Navigating to {DEMO_URL}...")
        title = engine.navigate(DEMO_URL)
        print(f"   Title: {title}")
        time.sleep(1)

        # --- Eyes: read the page ---
        print("\n👁️  Reading page title...")
        print(f"   Title via eyes: {eyes.title()}")

        print("\n👁️  Extracting top links...")
        links = eyes.links()[:10]
        for i, link in enumerate(links, 1):
            text = link.get("text", "").strip()[:60]
            href = link.get("href", "")[:80]
            if text:
                print(f"   {i}. {text}")
                print(f"      → {href}")

        # --- Eyes: DOM text ---
        print("\n👁️  Extracting DOM text (first 500 chars)...")
        text = eyes.dom_text()
        print(f"   {text[:500]}...")

        time.sleep(1)

        # --- Hands: scroll down ---
        print("\n🤚 Scrolling down the page...")
        hands.scroll(x=0, y=800)
        time.sleep(1)

        # --- Hands: scroll back up ---
        print("\n🤚 Scrolling back up...")
        hands.scroll(x=0, y=-800)
        time.sleep(1)

        # --- Eyes: screenshot ---
        out_dir = Path(__file__).parent / "demo_output"
        out_dir.mkdir(exist_ok=True)
        print(f"\n📸 Taking screenshot...")
        path = eyes.screenshot_timestamped(out_dir=str(out_dir))
        print(f"   Saved to: {path}")

        # --- Eyes: hybrid extract ---
        print("\n🔍 Running hybrid extract (auto mode)...")
        result = eyes.extract(mode="auto")
        print(f"   Mode used: {'DOM text' if isinstance(result, str) else 'screenshot'}")
        if isinstance(result, str):
            print(f"   Content preview: {result[:300]}...")

        time.sleep(2)
        print("\n✅ Demo complete. Browser closing.\n")


if __name__ == "__main__":
    main()
