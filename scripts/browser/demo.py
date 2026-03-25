#!/usr/bin/env python3
"""Live demo of Browser Eyes & Hands v2 — persistent session + multi-tab."""

import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from browser.pool import BrowserPool
from browser.tab_manager import TabManager
from browser.eyes import Eyes
from browser.hands import Hands

def main():
    print("\n🦞 Browser Eyes & Hands v2 — Persistent + Multi-Tab Demo\n")

    pool = BrowserPool(headless=False)
    engine = pool.get()
    tabs = TabManager(engine)

    try:
        # --- Tab 1: Hacker News ---
        print("📍 Opening Tab 1: Hacker News...")
        news_page = tabs.create("news")
        news_page.goto("https://news.ycombinator.com", wait_until="domcontentloaded")
        news_eyes = Eyes(engine, page=news_page)
        print(f"   Title: {news_eyes.title()}")
        time.sleep(1)

        # --- Tab 2: Example.com ---
        print("\n📍 Opening Tab 2: Example.com...")
        example_page = tabs.create("example")
        example_page.goto("https://example.com", wait_until="domcontentloaded")
        example_eyes = Eyes(engine, page=example_page)
        print(f"   Title: {example_eyes.title()}")
        time.sleep(1)

        # --- Read from both tabs without switching ---
        print(f"\n👁️  Tab count: {tabs.count()}")
        print(f"   Tabs open: {tabs.list_tabs()}")
        print(f"\n👁️  News tab title: {news_eyes.title()}")
        print(f"   Example tab title: {example_eyes.title()}")

        # --- Switch and interact ---
        print("\n🤚 Switching to news tab and scrolling...")
        tabs.switch("news")
        news_hands = Hands(engine, page=news_page)
        news_hands.scroll(x=0, y=600)
        time.sleep(1)

        # --- Links from news tab ---
        print("\n👁️  Top 5 HN links:")
        links = news_eyes.links()[:10]
        count = 0
        for link in links:
            text = link.get("text", "").strip()[:60]
            if text and count < 5:
                print(f"   • {text}")
                count += 1

        # --- Screenshot both tabs ---
        out_dir = Path(__file__).parent / "demo_output"
        out_dir.mkdir(exist_ok=True)

        print("\n📸 Screenshotting both tabs...")
        news_shot = out_dir / "demo-news.png"
        news_eyes.screenshot(save_path=news_shot)
        print(f"   News → {news_shot}")

        example_shot = out_dir / "demo-example.png"
        example_eyes.screenshot(save_path=example_shot)
        print(f"   Example → {example_shot}")

        # --- Demonstrate pool persistence ---
        print("\n♻️  Browser is still alive (persistent pool)...")
        print(f"   Pool alive: {pool.is_alive()}")

        # --- Close one tab ---
        print("\n🗑️  Closing example tab...")
        tabs.close("example")
        print(f"   Remaining tabs: {tabs.list_tabs()}")

        time.sleep(2)
        print("\n✅ Demo complete. Shutting down pool.\n")

    finally:
        pool.shutdown()


if __name__ == "__main__":
    main()
