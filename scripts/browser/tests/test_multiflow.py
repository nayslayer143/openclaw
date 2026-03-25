#!/usr/bin/env python3
"""
Multi-step end-to-end browser workflow tests.
Tests realistic sequences: navigate → interact → extract → verify.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from browser import BrowserEngine, Eyes, Hands, browser_open


def test_navigate_extract_links():
    """Navigate, extract text, get links — full perception pipeline."""
    with BrowserEngine() as engine:
        engine.navigate("https://example.com")
        eyes = Eyes(engine)
        text = eyes.dom_text()
        links = eyes.links()
        title = eyes.title()

        assert "Example Domain" in text
        assert title == "Example Domain"
        assert len(links) > 0
        assert any("iana" in (l.get("href") or "").lower() for l in links)


def test_multi_page_navigation():
    """Navigate to multiple pages in sequence."""
    with BrowserEngine(rate_limit_seconds=(0.1, 0.2)) as engine:
        urls = [
            "https://example.com",
            "https://example.org",
        ]
        results = []
        for url in urls:
            engine.navigate(url)
            eyes = Eyes(engine)
            results.append({"url": engine.current_url(), "title": eyes.title()})

        assert len(results) == 2
        assert all(r["title"] for r in results)


def test_browser_open_tool_end_to_end():
    """browser_open tool — complete round trip via high-level API."""
    result = browser_open("https://example.com", extract="dom")
    assert result["ok"] is True
    assert result["title"] == "Example Domain"
    assert "Example Domain" in result["content"]
    assert len(result["links"]) > 0


def test_screenshot_then_text():
    """Take screenshot and extract text from same page."""
    with BrowserEngine() as engine:
        engine.navigate("https://example.com")
        eyes = Eyes(engine)

        data = eyes.screenshot(full_page=True)
        assert data[:4] == b'\x89PNG'

        text = eyes.dom_text()
        assert len(text) > 0


def test_form_fill_and_read_back():
    """Fill a multi-field form, read back values — no network needed."""
    with BrowserEngine() as engine:
        engine.page.set_content("""
            <html><body>
              <form id="test-form">
                <input id="first" type="text"/>
                <input id="last" type="text"/>
                <input id="age" type="number"/>
                <button type="submit">Submit</button>
              </form>
            </body></html>
        """)
        hands = Hands(engine)
        hands.fill_form({
            "#first": "Jordan",
            "#last": "Claw",
            "#age": "30",
        })
        assert engine.page.locator("#first").input_value() == "Jordan"
        assert engine.page.locator("#last").input_value() == "Claw"
        assert engine.page.locator("#age").input_value() == "30"
