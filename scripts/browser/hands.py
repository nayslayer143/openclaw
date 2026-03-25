#!/usr/bin/env python3
"""
Action layer — click, type, scroll, hover, select, drag, upload, tab management.
All actions include human-like delays and audit logging.
"""
from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Optional, Union

from browser.browser_engine import BrowserEngine
from playwright.sync_api import Page


def _human_delay(lo: float = 0.05, hi: float = 0.15):
    """Small random pause to simulate human speed."""
    time.sleep(random.uniform(lo, hi))


class Hands:
    """
    Action executor attached to a BrowserEngine.
    All methods log to the engine's audit logger.
    """

    def __init__(self, engine: BrowserEngine, page: Optional[Page] = None):
        self._engine = engine
        self._audit = engine._audit
        self._page = page or engine.page

    def click(self, selector: str, timeout: int = 10000):
        """Click the first element matching selector."""
        self._page.locator(selector).first.click(timeout=timeout)
        _human_delay()
        self._audit.log(self._engine.current_url(), "click", {"selector": selector})

    def double_click(self, selector: str):
        self._page.locator(selector).first.dblclick()
        _human_delay()
        self._audit.log(self._engine.current_url(), "double_click", {"selector": selector})

    def hover(self, selector: str):
        self._page.locator(selector).first.hover()
        _human_delay(0.1, 0.3)
        self._audit.log(self._engine.current_url(), "hover", {"selector": selector})

    def type(self, selector: str, text: str, delay_ms: int = 50):
        """
        Type text into an input field with per-character delay (human-like).
        """
        self._page.locator(selector).first.type(text, delay=delay_ms)
        self._audit.log(self._engine.current_url(), "type",
                        {"selector": selector, "length": len(text)})

    def fill(self, selector: str, value: str):
        """
        Fill an input field instantly (faster than type, no per-char delay).
        Use for programmatic form filling where speed matters.
        """
        self._page.locator(selector).first.fill(value)
        _human_delay()
        self._audit.log(self._engine.current_url(), "fill",
                        {"selector": selector, "length": len(value)})

    def clear(self, selector: str):
        """Clear the value of an input field."""
        self._page.locator(selector).first.fill("")
        self._audit.log(self._engine.current_url(), "clear", {"selector": selector})

    def select(self, selector: str, value: str):
        """Select an option by value in a <select> element."""
        self._page.locator(selector).first.select_option(value=value)
        _human_delay()
        self._audit.log(self._engine.current_url(), "select",
                        {"selector": selector, "value": value})

    def scroll(self, x: int = 0, y: int = 300):
        """Scroll the page by (x, y) pixels."""
        self._page.mouse.wheel(x, y)
        _human_delay(0.2, 0.5)
        self._audit.log(self._engine.current_url(), "scroll", {"x": x, "y": y})

    def scroll_to_bottom(self):
        """Scroll to page bottom."""
        self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        _human_delay(0.3, 0.6)
        self._audit.log(self._engine.current_url(), "scroll_to_bottom", {})

    def scroll_to_element(self, selector: str):
        """Scroll element into viewport."""
        self._page.locator(selector).first.scroll_into_view_if_needed()
        _human_delay()
        self._audit.log(self._engine.current_url(), "scroll_to_element", {"selector": selector})

    def press_key(self, selector_or_key: str, key: str = None):
        """Press a keyboard key (e.g. 'Enter', 'Tab', 'Escape').
        If only one arg given, presses that key globally.
        If two args, focuses selector then presses key.
        """
        if key is None:
            self._page.keyboard.press(selector_or_key)
            self._audit.log(self._engine.current_url(), "key_press", {"key": selector_or_key})
        else:
            self._page.locator(selector_or_key).first.press(key)
            self._audit.log(self._engine.current_url(), "key_press",
                            {"selector": selector_or_key, "key": key})
        _human_delay()

    def drag(self, source_selector: str, target_selector: str):
        """Drag from source to target element."""
        src = self._page.locator(source_selector).first.bounding_box()
        tgt = self._page.locator(target_selector).first.bounding_box()
        if not src or not tgt:
            raise ValueError("Could not get bounding boxes for drag operation")
        self._page.mouse.move(src["x"] + src["width"] / 2, src["y"] + src["height"] / 2)
        self._page.mouse.down()
        _human_delay(0.1, 0.2)
        self._page.mouse.move(tgt["x"] + tgt["width"] / 2, tgt["y"] + tgt["height"] / 2)
        self._page.mouse.up()
        self._audit.log(self._engine.current_url(), "drag",
                        {"from": source_selector, "to": target_selector})

    def upload_file(self, selector: str, file_path: Union[str, Path]):
        """Upload a file via a file input element."""
        self._page.locator(selector).set_input_files(str(file_path))
        self._audit.log(self._engine.current_url(), "file_upload",
                        {"selector": selector, "file": str(file_path)})

    def fill_form(self, fields: dict[str, str]):
        """
        Fill multiple form fields at once.
        fields: {selector: value} — uses fill() for all (fast path).
        """
        for selector, value in fields.items():
            self.fill(selector, value)
        self._audit.log(self._engine.current_url(), "fill_form",
                        {"field_count": len(fields)})

    def submit_form(self, form_selector: str = "form"):
        """Submit a form by calling submit() on it."""
        self._page.locator(form_selector).evaluate("f => f.submit()")
        _human_delay(0.3, 0.8)
        self._audit.log(self._engine.current_url(), "form_submit",
                        {"selector": form_selector})

    def wait_for_selector(self, selector: str, timeout: int = 10000):
        """Wait for an element to appear in the DOM."""
        self._page.wait_for_selector(selector, timeout=timeout)

    def wait_for_navigation(self, url_pattern: Optional[str] = None):
        """Wait for page navigation to complete."""
        if url_pattern:
            self._page.wait_for_url(url_pattern)
        else:
            self._page.wait_for_load_state("domcontentloaded")

    def get_value(self, selector: str) -> str:
        """Get current value of an input field."""
        return self._page.locator(selector).first.input_value()

    def is_visible(self, selector: str) -> bool:
        """Check if an element is visible."""
        return self._page.locator(selector).first.is_visible()
