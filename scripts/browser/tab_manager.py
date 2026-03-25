#!/usr/bin/env python3
"""
Multi-tab orchestration — named tabs within a single browser context.

Usage:
    tabs = TabManager(engine)
    search = tabs.create("search")
    docs = tabs.create("docs")
    search.goto("https://google.com")
    docs.goto("https://docs.python.org")
    tabs.switch("search")  # set active tab
"""
from __future__ import annotations

from typing import Optional
from playwright.sync_api import Page

from browser.browser_engine import BrowserEngine
from browser.security import get_audit_logger


class TabManager:
    """
    Manages named tabs (Playwright Pages) within a BrowserEngine's context.
    Each tab is a real browser tab that can be independently navigated.
    """

    def __init__(self, engine: BrowserEngine):
        self._engine = engine
        self._context = engine._context
        self._audit = get_audit_logger()
        self._tabs: dict[str, Page] = {}
        self._active: Optional[str] = None

    def create(self, name: str) -> Page:
        """
        Create a new named tab. Returns the Playwright Page.
        If a tab with this name already exists, returns the existing one.
        """
        if name in self._tabs:
            return self._tabs[name]

        page = self._context.new_page()
        self._tabs[name] = page
        self._active = name
        self._audit.log("about:blank", "tab_create", {"name": name})
        return page

    def get(self, name: str) -> Optional[Page]:
        """Get a tab by name. Returns None if not found."""
        return self._tabs.get(name)

    def switch(self, name: str) -> Page:
        """
        Set the active tab. Returns the Page.
        Raises KeyError if tab doesn't exist.
        """
        if name not in self._tabs:
            raise KeyError(f"No tab named '{name}'")
        self._active = name
        page = self._tabs[name]
        page.bring_to_front()
        self._audit.log(page.url, "tab_switch", {"name": name})
        return page

    def close(self, name: str):
        """
        Close a named tab. If it's the active tab, switch to another.
        """
        if name not in self._tabs:
            return

        page = self._tabs.pop(name)
        was_active = self._active == name

        try:
            self._audit.log(page.url, "tab_close", {"name": name})
            page.close()
        except Exception:
            pass

        if was_active:
            if self._tabs:
                self._active = next(iter(self._tabs))
            else:
                self._active = None

    def list_tabs(self) -> list[str]:
        """Return list of all tab names."""
        return list(self._tabs.keys())

    def count(self) -> int:
        """Return number of open tabs."""
        return len(self._tabs)

    def active_name(self) -> Optional[str]:
        """Return the name of the active tab, or None."""
        return self._active

    def active_page(self) -> Optional[Page]:
        """Return the active tab's Page, or None."""
        if self._active:
            return self._tabs.get(self._active)
        return None

    def close_all(self):
        """Close all tabs."""
        for name in list(self._tabs.keys()):
            self.close(name)
