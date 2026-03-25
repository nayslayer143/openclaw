#!/usr/bin/env python3
"""
Visual perception layer — screenshot capture and DOM text extraction.
Hybrid routing: "auto" mode picks DOM for text-heavy pages, screenshot for visual/JS-heavy.
"""
from __future__ import annotations

import re
import datetime
from pathlib import Path
from typing import Optional, Literal

from browser.browser_engine import BrowserEngine


# Pages with these URL patterns are considered "structured" → prefer DOM extraction
_STRUCTURED_URL_PATTERNS = re.compile(
    r"(api\.|/api/|\.json|/feed|/rss|/sitemap|docs\.|/docs/)", re.I
)


class Eyes:
    """
    Attaches to a BrowserEngine and provides perception methods.
    """

    def __init__(self, engine: BrowserEngine):
        self._engine = engine
        self._audit = engine._audit

    def screenshot(
        self,
        full_page: bool = True,
        save_path: Optional[Path] = None,
        element_selector: Optional[str] = None,
    ) -> bytes:
        """
        Capture screenshot of current page. Returns PNG bytes.
        If save_path is given, also writes to disk.
        If element_selector given, captures only that element.
        """
        page = self._engine.page
        kwargs: dict = {"full_page": full_page, "type": "png"}

        if element_selector:
            data = page.locator(element_selector).screenshot(**kwargs)
        else:
            data = page.screenshot(**kwargs)

        if save_path:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            Path(save_path).write_bytes(data)

        self._audit.log(
            self._engine.current_url(), "screenshot",
            {"full_page": full_page, "saved": str(save_path) if save_path else None}
        )
        return data

    def screenshot_timestamped(self, out_dir: Optional[Path] = None) -> Path:
        """
        Take a screenshot and save with a timestamped filename.
        Returns the saved Path.
        """
        if out_dir is None:
            out_dir = Path.home() / "openclaw" / "logs" / "browser" / "screenshots"
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        path = out_dir / f"shot-{ts}.png"
        self.screenshot(save_path=path)
        return path

    def dom_text(self, selector: str = "body") -> str:
        """
        Extract visible text from DOM. Faster than screenshot for text-heavy pages.
        Strips script/style content. Returns clean text.
        """
        page = self._engine.page
        # Remove script and style tags before extracting text
        page.evaluate("""
            document.querySelectorAll('script, style, noscript').forEach(el => el.remove());
        """)
        text = page.locator(selector).inner_text()
        self._audit.log(self._engine.current_url(), "dom_text", {"selector": selector})
        return text

    def dom_html(self, selector: str = "body") -> str:
        """Return raw HTML of selected element."""
        return self._engine.page.locator(selector).inner_html()

    def extract(self, mode: Literal["auto", "screenshot", "dom"] = "auto") -> str:
        """
        Hybrid extraction. Returns string representation of page content.
        - "dom": always use DOM text
        - "screenshot": always take screenshot, return base64 string
        - "auto": use DOM for structured/text pages, screenshot for visual pages
        """
        if mode == "dom":
            return self.dom_text()

        if mode == "screenshot":
            import base64
            return base64.b64encode(self.screenshot()).decode()

        # Auto: check URL and page type
        url = self._engine.current_url()
        if _STRUCTURED_URL_PATTERNS.search(url):
            return self.dom_text()

        # Check if page has significant visual content or minimal text
        text = self._engine.page.locator("body").inner_text()
        if len(text.strip()) < 200:
            # Sparse text — likely visual, use screenshot
            import base64
            return base64.b64encode(self.screenshot()).decode()

        return text

    def links(self) -> list[dict]:
        """Extract all links from current page. Returns list of {text, href}."""
        page = self._engine.page
        anchors = page.locator("a[href]").all()
        result = []
        for a in anchors:
            try:
                result.append({
                    "text": a.inner_text().strip()[:100],
                    "href": a.get_attribute("href"),
                })
            except Exception:
                pass
        return result

    def title(self) -> str:
        return self._engine.page.title()

    def meta(self) -> dict:
        """Extract meta tags as key/value dict."""
        page = self._engine.page
        metas = page.locator("meta").all()
        result = {}
        for m in metas:
            name = m.get_attribute("name") or m.get_attribute("property")
            content = m.get_attribute("content")
            if name and content:
                result[name] = content
        return result
