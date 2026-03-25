#!/usr/bin/env python3
"""Tests for Hands action layer. Uses set_content() for local DOM tests — no network needed."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from browser.browser_engine import BrowserEngine
from browser.hands import Hands


def test_hands_type_and_clear():
    with BrowserEngine() as engine:
        engine.page.set_content(
            '<html><body><input id="q" type="text"/></body></html>'
        )
        hands = Hands(engine)
        hands.type("#q", "hello world")
        val = engine.page.locator("#q").input_value()
        assert val == "hello world"
        hands.clear("#q")
        assert engine.page.locator("#q").input_value() == ""


def test_hands_fill_form():
    with BrowserEngine() as engine:
        engine.page.set_content("""
            <html><body>
              <input id="name" type="text"/>
              <input id="email" type="email"/>
            </body></html>
        """)
        hands = Hands(engine)
        hands.fill_form({
            "#name": "Jordan",
            "#email": "j@example.com",
        })
        assert engine.page.locator("#name").input_value() == "Jordan"
        assert engine.page.locator("#email").input_value() == "j@example.com"


def test_hands_scroll():
    with BrowserEngine() as engine:
        engine.navigate("https://example.com")
        hands = Hands(engine)
        hands.scroll(0, 300)  # should not raise


def test_hands_select():
    with BrowserEngine() as engine:
        engine.page.set_content("""
            <html><body>
              <select id="s">
                <option value="a">A</option>
                <option value="b">B</option>
              </select>
            </body></html>
        """)
        hands = Hands(engine)
        hands.select("#s", "b")
        assert engine.page.locator("#s").input_value() == "b"


def test_hands_is_visible():
    with BrowserEngine() as engine:
        engine.page.set_content("""
            <html><body>
              <div id="visible">Hello</div>
              <div id="hidden" style="display:none">Hidden</div>
            </body></html>
        """)
        hands = Hands(engine)
        assert hands.is_visible("#visible") is True
        assert hands.is_visible("#hidden") is False
