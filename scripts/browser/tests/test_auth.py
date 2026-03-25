#!/usr/bin/env python3
"""Tests for auth handler — session persistence, login form detection."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from browser.browser_engine import BrowserEngine
from browser.auth_handler import SessionStore, detect_login_form


def test_session_save_and_load(tmp_path):
    store = SessionStore(store_dir=tmp_path)
    fake_cookies = [{"name": "session", "value": "abc123", "domain": "example.com",
                     "path": "/", "secure": True, "httpOnly": True}]
    store.save("example.com", fake_cookies)
    loaded = store.load("example.com")
    assert loaded == fake_cookies


def test_session_not_found_returns_none(tmp_path):
    store = SessionStore(store_dir=tmp_path)
    assert store.load("nonexistent.com") is None


def test_session_overwrite(tmp_path):
    store = SessionStore(store_dir=tmp_path)
    store.save("a.com", [{"name": "k", "value": "v1", "domain": "a.com", "path": "/"}])
    store.save("a.com", [{"name": "k", "value": "v2", "domain": "a.com", "path": "/"}])
    loaded = store.load("a.com")
    assert loaded[0]["value"] == "v2"


def test_detect_login_form_found():
    with BrowserEngine() as engine:
        engine.page.set_content("""
            <html><body>
              <form>
                <input type="text" name="username"/>
                <input type="password" name="password"/>
                <button type="submit">Login</button>
              </form>
            </body></html>
        """)
        result = detect_login_form(engine.page)
        assert result is not None
        assert "username_selector" in result
        assert "password_selector" in result


def test_detect_login_form_not_found():
    with BrowserEngine() as engine:
        engine.page.set_content("<html><body><p>No form here.</p></body></html>")
        result = detect_login_form(engine.page)
        assert result is None
