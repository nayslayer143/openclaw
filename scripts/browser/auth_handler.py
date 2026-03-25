#!/usr/bin/env python3
"""
Auth handler — OAuth flows, username/password login, encrypted session persistence, MFA handoff.

Session persistence: cookies stored as Fernet-encrypted JSON per domain.
MFA handoff: pauses execution and sends Telegram alert; resumes when Jordan replies.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet
from browser.security import _derive_key, get_audit_logger
from browser.browser_engine import BrowserEngine


# ── Session Store ──────────────────────────────────────────────────────────────

class SessionStore:
    """
    Encrypted per-domain cookie/token store.
    Files stored at store_dir/<domain>.enc
    """

    def __init__(self, store_dir: Optional[Path] = None):
        if store_dir is None:
            store_dir = Path.home() / ".openclaw" / "browser-sessions"
        self._dir = Path(store_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._fernet = Fernet(_derive_key())

    def _path(self, domain: str) -> Path:
        safe = re.sub(r"[^a-zA-Z0-9._-]", "_", domain)
        return self._dir / f"{safe}.enc"

    def save(self, domain: str, cookies: list, extra: Optional[dict] = None):
        """Encrypt and save cookies (and optional extra data) for domain."""
        payload = {"cookies": cookies, "extra": extra or {}}
        plaintext = json.dumps(payload).encode()
        ciphertext = self._fernet.encrypt(plaintext)
        self._path(domain).write_bytes(ciphertext)

    def load(self, domain: str) -> Optional[list]:
        """Load and decrypt cookies for domain. Returns None if not found."""
        path = self._path(domain)
        if not path.exists():
            return None
        try:
            ciphertext = path.read_bytes()
            plaintext = self._fernet.decrypt(ciphertext)
            payload = json.loads(plaintext)
            return payload.get("cookies")
        except Exception:
            return None

    def load_extra(self, domain: str) -> Optional[dict]:
        """Load extra stored data (tokens etc.) for domain."""
        path = self._path(domain)
        if not path.exists():
            return None
        try:
            ciphertext = path.read_bytes()
            plaintext = self._fernet.decrypt(ciphertext)
            return json.loads(plaintext).get("extra", {})
        except Exception:
            return None

    def delete(self, domain: str):
        self._path(domain).unlink(missing_ok=True)

    def domains(self) -> list:
        return [p.stem for p in self._dir.glob("*.enc")]


# ── Login form detection ───────────────────────────────────────────────────────

def detect_login_form(page) -> Optional[dict]:
    """
    Scan page for a username/password login form.
    Returns dict with selectors if found, None if not.
    """
    username_selectors = [
        "input[type='email']",
        "input[name='username']",
        "input[name='email']",
        "input[name='user']",
        "input[name='login']",
        "input[id*='username']",
        "input[id*='email']",
        "input[autocomplete='username']",
        "input[autocomplete='email']",
    ]
    password_selectors = [
        "input[type='password']",
        "input[name='password']",
        "input[name='passwd']",
        "input[name='pass']",
    ]
    submit_selectors = [
        "button[type='submit']",
        "input[type='submit']",
        "button:has-text('Login')",
        "button:has-text('Sign in')",
        "button:has-text('Log in')",
    ]

    username_sel = None
    for sel in username_selectors:
        try:
            if page.locator(sel).count() > 0:
                username_sel = sel
                break
        except Exception:
            pass

    password_sel = None
    for sel in password_selectors:
        try:
            if page.locator(sel).count() > 0:
                password_sel = sel
                break
        except Exception:
            pass

    if not username_sel or not password_sel:
        return None

    submit_sel = None
    for sel in submit_selectors:
        try:
            if page.locator(sel).count() > 0:
                submit_sel = sel
                break
        except Exception:
            pass

    return {
        "username_selector": username_sel,
        "password_selector": password_sel,
        "submit_selector": submit_sel,
    }


# ── AuthHandler ───────────────────────────────────────────────────────────────

class AuthHandler:
    """
    High-level authentication helper attached to a BrowserEngine.
    """

    def __init__(self, engine: BrowserEngine, session_store: Optional[SessionStore] = None):
        self._engine = engine
        self._store = session_store or SessionStore()
        self._audit = get_audit_logger()

    def restore_session(self, domain: str) -> bool:
        """
        Load saved cookies into the browser context.
        Returns True if session was found and loaded, False otherwise.
        """
        cookies = self._store.load(domain)
        if cookies:
            self._engine.set_cookies(cookies)
            self._audit.log(f"https://{domain}", "session_restore", {"domain": domain})
            return True
        return False

    def save_session(self, domain: str):
        """Save current browser cookies for domain."""
        cookies = self._engine.get_cookies()
        self._store.save(domain, cookies)
        self._audit.log(f"https://{domain}", "session_save",
                        {"domain": domain, "cookie_count": len(cookies)})

    def login_with_password(
        self,
        url: str,
        username: str,
        password: str,
        username_sel: Optional[str] = None,
        password_sel: Optional[str] = None,
        submit_sel: Optional[str] = None,
        success_selector: Optional[str] = None,
    ) -> bool:
        """
        Navigate to login URL, fill credentials, submit.
        Auto-detects form selectors if not provided.
        Returns True if login appears successful, False if form not found.
        Credentials are never written to audit logs.
        """
        self._engine.navigate(url)

        if not username_sel or not password_sel:
            form = detect_login_form(self._engine.page)
            if not form:
                self._audit.log(url, "login_failed", {"reason": "form_not_detected"})
                return False
            username_sel = username_sel or form["username_selector"]
            password_sel = password_sel or form["password_selector"]
            submit_sel = submit_sel or form.get("submit_selector")

        page = self._engine.page
        page.fill(username_sel, username)
        time.sleep(0.3)
        page.fill(password_sel, password)
        time.sleep(0.2)

        if submit_sel:
            page.locator(submit_sel).click()
        else:
            page.keyboard.press("Enter")

        page.wait_for_load_state("domcontentloaded")

        if success_selector:
            try:
                page.wait_for_selector(success_selector, timeout=10000)
                self._audit.log(url, "login_success", {"username": "***"})
                return True
            except Exception:
                self._audit.log(url, "login_failed", {"reason": "success_selector_not_found"})
                return False

        self._audit.log(url, "login_attempted", {"username": "***"})
        return True

    def follow_oauth_flow(
        self,
        start_url: str,
        expected_redirect_domain: str,
        max_steps: int = 10,
    ) -> str:
        """
        Follow an OAuth redirect chain starting from start_url.
        Returns the final URL (should contain auth code or token).
        """
        self._engine.navigate(start_url)
        steps = 0
        while steps < max_steps:
            current = self._engine.current_url()
            if expected_redirect_domain in current:
                self._audit.log(current, "oauth_complete", {"steps": steps})
                return current
            try:
                self._engine.page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass
            new_url = self._engine.current_url()
            if new_url == current:
                break
            steps += 1

        final = self._engine.current_url()
        self._audit.log(final, "oauth_ended", {"steps": steps, "final_url": final})
        return final

    def mfa_handoff(
        self,
        chat_id: Optional[str] = None,
        message: str = "MFA required — please complete 2FA in browser. Reply /mfa-done when finished.",
        timeout_seconds: int = 300,
    ) -> bool:
        """
        Pause for MFA. Alert Jordan via Telegram and wait for manual completion.
        Returns True if Jordan signals done within timeout, False if timeout.
        """
        self._audit.log(self._engine.current_url(), "mfa_handoff", {"chat_id": chat_id})

        if chat_id:
            try:
                import os, requests
                bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
                if bot_token:
                    requests.post(
                        f"https://api.telegram.org/bot{bot_token}/sendMessage",
                        json={"chat_id": chat_id, "text": message},
                        timeout=10,
                    )
            except Exception:
                pass

        flag = Path("/tmp/openclaw-mfa-pending.flag")
        flag.write_text("pending")

        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            time.sleep(2)
            if not flag.exists():
                return True

        flag.unlink(missing_ok=True)
        return False
