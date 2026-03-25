#!/usr/bin/env python3
"""Browser Eyes & Hands — automation layer for Claude Code and Clawmson."""
from __future__ import annotations

from browser.browser_engine import BrowserEngine
from browser.eyes import Eyes
from browser.hands import Hands
from browser.auth_handler import AuthHandler, SessionStore
from browser.captcha_handler import CaptchaHandler, CaptchaConfig
from browser.security import CredentialVault, AuditLogger, DomainScope
from browser.browser_tools import (
    browser_open,
    browser_screenshot,
    browser_click,
    browser_fill,
    browser_eval,
    browser_login,
)

__all__ = [
    "BrowserEngine", "Eyes", "Hands",
    "AuthHandler", "SessionStore",
    "CaptchaHandler", "CaptchaConfig",
    "CredentialVault", "AuditLogger", "DomainScope",
    "browser_open", "browser_screenshot", "browser_click",
    "browser_fill", "browser_eval", "browser_login",
]
