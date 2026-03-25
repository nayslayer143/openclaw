#!/usr/bin/env python3
"""
Playwright wrapper — core browser automation engine.
Single-session, context manager usage. Sync API only.

Usage:
    with BrowserEngine() as engine:
        engine.navigate("https://example.com")
        html = engine.content()
"""
from __future__ import annotations

import json
import os
import random
import time
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright, Page, BrowserContext, Playwright

from browser.security import DomainScope, get_audit_logger, check_robots_txt


_CONFIG_PATH = Path(__file__).parent / "config.json"


def _load_config() -> dict:
    if _CONFIG_PATH.exists():
        return json.loads(_CONFIG_PATH.read_text())
    return {}


class BrowserEngine:
    """
    Manages a Playwright browser context lifecycle.
    Use as a context manager: `with BrowserEngine() as engine`.
    """

    def __init__(
        self,
        headless: bool = True,
        stealth: bool = False,
        proxy_url: Optional[str] = None,
        allowed_domains: Optional[list] = None,
        blocked_domains: Optional[list] = None,
        rate_limit_seconds: tuple = (1.0, 3.0),
        timeout_ms: int = 30000,
        session_cookies: Optional[list] = None,
    ):
        config = _load_config()
        self._headless = headless
        self._stealth = stealth or config.get("stealth_mode", False)
        self._proxy_url = proxy_url or os.environ.get("BROWSER_PROXY_URL") or config.get("proxy_url")
        self._rate_limit = rate_limit_seconds
        self._timeout_ms = int(os.environ.get("BROWSER_DEFAULT_TIMEOUT", timeout_ms))
        self._session_cookies = session_cookies or []

        _allowed = allowed_domains if allowed_domains is not None else config.get("allowed_domains", [])
        _blocked = blocked_domains if blocked_domains is not None else config.get("blocked_domains", [])
        self._scope = DomainScope(allowed=_allowed, blocked=_blocked)
        self._audit = get_audit_logger()
        self._robots_respect = config.get("robots_txt_respect", True)
        self._user_agent = (
            config.get("user_agent_stealth") if self._stealth
            else config.get("user_agent_honest",
                "OpenClaw-BrowserBot/1.0 (+https://openclaw.local)")
        )

        # Set by __enter__
        self._pw: Optional[Playwright] = None
        self._browser = None
        self._context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._last_nav_time: float = 0.0

    def __enter__(self) -> "BrowserEngine":
        self._pw = sync_playwright().start()
        launch_kwargs: dict = {"headless": self._headless}
        if self._proxy_url:
            launch_kwargs["proxy"] = {"server": self._proxy_url}
        self._browser = self._pw.chromium.launch(**launch_kwargs)

        ctx_kwargs: dict = {
            "user_agent": self._user_agent,
            "viewport": {"width": 1280, "height": 800},
        }
        self._context = self._browser.new_context(**ctx_kwargs)
        self._context.set_default_timeout(self._timeout_ms)

        if self._session_cookies:
            self._context.add_cookies(self._session_cookies)

        self.page = self._context.new_page()
        return self

    def __exit__(self, *_):
        try:
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.stop()
        except Exception:
            pass

    def _enforce_rate_limit(self):
        """Wait a human-like random delay since last navigation."""
        lo, hi = self._rate_limit
        elapsed = time.time() - self._last_nav_time
        wait = random.uniform(lo, hi)
        if elapsed < wait:
            time.sleep(wait - elapsed)

    def navigate(self, url: str, wait_until: str = "domcontentloaded") -> str:
        """
        Navigate to URL. Checks domain scope and robots.txt.
        Returns page title. Raises PermissionError on scope/robots violations.
        """
        if not self._scope.is_allowed(url):
            raise PermissionError(f"Domain blocked by scope policy: {url}")

        if self._robots_respect and not check_robots_txt(url, self._user_agent):
            raise PermissionError(f"robots.txt disallows access: {url}")

        self._enforce_rate_limit()
        self.page.goto(url, wait_until=wait_until)
        title = self.page.title()
        self._audit.log(url, "navigate", {"title": title})
        self._last_nav_time = time.time()
        return title

    def content(self) -> str:
        """Return full HTML content of current page."""
        return self.page.content()

    def current_url(self) -> str:
        return self.page.url

    def wait_for_load(self, state: str = "domcontentloaded"):
        self.page.wait_for_load_state(state)

    def new_tab(self) -> Page:
        """Open a new page/tab in the same context."""
        new_page = self._context.new_page()
        self._audit.log(self.current_url(), "new_tab", {})
        return new_page

    def get_cookies(self) -> list:
        """Return all current cookies as a list of dicts."""
        return self._context.cookies()

    def set_cookies(self, cookies: list):
        """Inject cookies into the context."""
        self._context.add_cookies(cookies)

    def evaluate(self, js: str):
        """Execute JavaScript in current page context."""
        result = self.page.evaluate(js)
        self._audit.log(self.current_url(), "evaluate", {"js_snippet": js[:80]})
        return result
