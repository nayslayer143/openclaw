#!/usr/bin/env python3
"""
Claude Code callable shim — thin wrappers around browser pool + eyes + hands + auth.
Uses BrowserPool for persistent browser reuse across calls.
Returns structured dicts so Claude Code can inspect results.

Usage from Claude Code session:
    import sys; sys.path.insert(0, '/Users/nayslayer/openclaw/scripts')
    from browser.browser_tools import browser_open, browser_screenshot, browser_click
"""
from __future__ import annotations

import traceback
from pathlib import Path
from typing import Optional

from browser.pool import get_pool
from browser.eyes import Eyes
from browser.hands import Hands
from browser.auth_handler import AuthHandler, SessionStore


def _err(msg: str, exc: Exception = None) -> dict:
    return {
        "ok": False,
        "error": msg,
        "traceback": traceback.format_exc() if exc else None,
    }


def _get_engine(stealth: bool = False):
    """Get the persistent engine from the pool.
    Note: stealth is set at pool creation time. If the pool already exists,
    this parameter is ignored. Configure stealth via config.json or
    create a custom pool for stealth-specific workflows.
    """
    pool = get_pool(stealth=stealth)
    return pool.get()


def browser_open(
    url: str,
    wait_until: str = "domcontentloaded",
    extract: str = "dom",
    stealth: bool = False,
    session_domain: Optional[str] = None,
) -> dict:
    """
    Open a URL and return title + text content.
    extract: "dom" (default), "screenshot" (base64), "auto"
    session_domain: if set, load saved cookies for this domain first
    """
    try:
        engine = _get_engine(stealth)
        if session_domain:
            store = SessionStore()
            cookies = store.load(session_domain)
            if cookies:
                engine.set_cookies(cookies)
        engine.navigate(url, wait_until=wait_until)
        eyes = Eyes(engine)
        content = eyes.extract(mode=extract)
        return {
            "ok": True,
            "url": engine.current_url(),
            "title": eyes.title(),
            "content": content,
            "links": eyes.links()[:20],
        }
    except Exception as e:
        return _err(str(e), e)


def browser_screenshot(
    url: str,
    save_path: Optional[str] = None,
    full_page: bool = True,
    stealth: bool = False,
    element_selector: Optional[str] = None,
) -> dict:
    """
    Take a screenshot of a URL. Returns PNG bytes + optional save path.
    """
    try:
        engine = _get_engine(stealth)
        engine.navigate(url)
        eyes = Eyes(engine)
        path = Path(save_path) if save_path else None
        data = eyes.screenshot(full_page=full_page, save_path=path,
                               element_selector=element_selector)
        return {
            "ok": True,
            "url": engine.current_url(),
            "bytes": data,
            "size_bytes": len(data),
            "saved_to": str(path) if path else None,
        }
    except Exception as e:
        return _err(str(e), e)


def browser_click(url: str, selector: str, stealth: bool = False) -> dict:
    """
    Navigate to URL and click the first element matching selector.
    Returns URL after click.
    """
    try:
        engine = _get_engine(stealth)
        engine.navigate(url)
        hands = Hands(engine)
        hands.click(selector)
        engine.wait_for_load()
        eyes = Eyes(engine)
        return {
            "ok": True,
            "url": engine.current_url(),
            "title": eyes.title(),
        }
    except Exception as e:
        return _err(str(e), e)


def browser_fill(
    url: str,
    fields: dict,
    submit_selector: Optional[str] = None,
    stealth: bool = False,
) -> dict:
    """
    Navigate to URL, fill form fields, optionally submit.
    fields: {css_selector: value}
    Returns URL + title after form interaction.
    """
    try:
        engine = _get_engine(stealth)
        engine.navigate(url)
        hands = Hands(engine)
        hands.fill_form(fields)
        if submit_selector:
            hands.click(submit_selector)
            engine.wait_for_load()
        eyes = Eyes(engine)
        return {
            "ok": True,
            "url": engine.current_url(),
            "title": eyes.title(),
        }
    except Exception as e:
        return _err(str(e), e)


def browser_eval(url: str, js: str, stealth: bool = False) -> dict:
    """
    Navigate to URL and execute JavaScript, returning the result.
    """
    try:
        engine = _get_engine(stealth)
        engine.navigate(url)
        value = engine.evaluate(js)
        return {
            "ok": True,
            "url": engine.current_url(),
            "value": value,
        }
    except Exception as e:
        return _err(str(e), e)


def browser_login(
    url: str,
    username: str,
    password: str,
    save_session_domain: Optional[str] = None,
    stealth: bool = False,
) -> dict:
    """
    Log in to a website. Optionally saves the session for reuse.
    Credentials never appear in return values or logs.
    """
    try:
        engine = _get_engine(stealth)
        auth = AuthHandler(engine)
        success = auth.login_with_password(url, username, password)
        if success and save_session_domain:
            auth.save_session(save_session_domain)
        return {
            "ok": success,
            "url": engine.current_url(),
            "session_saved": bool(save_session_domain and success),
        }
    except Exception as e:
        return _err(str(e), e)


def browser_shutdown() -> dict:
    """Explicitly shut down the persistent browser. Next call relaunches."""
    try:
        get_pool().shutdown()
        return {"ok": True}
    except Exception as e:
        return _err(str(e), e)
