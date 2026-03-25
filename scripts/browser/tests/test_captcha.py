#!/usr/bin/env python3
"""Tests for CAPTCHA handler. Tier 1 tested directly; Tier 2/3 mocked."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from unittest.mock import patch, MagicMock
from browser.captcha_handler import CaptchaHandler, CaptchaConfig, build_stealth_headers


def test_stealth_headers_structure():
    headers = build_stealth_headers()
    assert "User-Agent" in headers
    assert "Accept-Language" in headers
    assert "Accept" in headers
    assert "Chrome" in headers["User-Agent"]


def test_captcha_config_defaults():
    config = CaptchaConfig()
    assert config.service in ("2captcha", "anticaptcha", None)
    assert config.api_key is None or isinstance(config.api_key, str)


def test_tier1_apply_does_not_raise():
    from browser.browser_engine import BrowserEngine
    with BrowserEngine() as engine:
        engine.page.set_content("<html><body>test page</body></html>")
        handler = CaptchaHandler(engine, CaptchaConfig())
        handler.apply_tier1_avoidance()  # should not raise


def test_tier2_no_api_key_returns_false():
    from browser.browser_engine import BrowserEngine
    with BrowserEngine() as engine:
        engine.page.set_content("<html><body>test</body></html>")
        handler = CaptchaHandler(engine, CaptchaConfig(api_key=None))
        result = handler.solve_tier2(captcha_type="recaptchav2", site_key="fake",
                                     page_url="https://x.com")
        assert result is False


def test_tier3_telegram_sends_or_skips_gracefully():
    from browser.browser_engine import BrowserEngine
    with BrowserEngine() as engine:
        engine.page.set_content("<html><body>test</body></html>")
        handler = CaptchaHandler(engine, CaptchaConfig())
        # Remove flag file if left over
        Path("/tmp/openclaw-captcha-pending.flag").unlink(missing_ok=True)
        with patch("browser.captcha_handler.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            # timeout=1 so it returns quickly
            result = handler.tier3_human_handoff(chat_id=None, timeout_seconds=1)
            # Should return False (timed out, no one solved it)
            assert result is False
