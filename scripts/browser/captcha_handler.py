#!/usr/bin/env python3
"""
CAPTCHA handling — 3-tier strategy.
Tier 1: Avoidance (headers, timing, realistic UA).
Tier 2: 2captcha / AntiCaptcha API solver.
Tier 3: Human-in-the-loop via Telegram pause.

Handles: hCaptcha, reCAPTCHA v2/v3, Cloudflare Turnstile.
"""
from __future__ import annotations

import os
import time
import random
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

import requests


# ── Stealth headers ───────────────────────────────────────────────────────────

def build_stealth_headers(locale: str = "en-US,en;q=0.9") -> dict:
    """HTTP headers that mimic a real Chrome browser on macOS."""
    return {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": locale,
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }


# ── Config ─────────────────────────────────────────────────────────────────────

@dataclass
class CaptchaConfig:
    service: Optional[str] = field(
        default_factory=lambda: os.environ.get("CAPTCHA_SERVICE", "2captcha")
    )
    api_key: Optional[str] = field(
        default_factory=lambda: os.environ.get("CAPTCHA_API_KEY")
    )
    poll_interval: float = 5.0
    max_wait: float = 120.0


# ── CAPTCHA detection ─────────────────────────────────────────────────────────

def detect_captcha_on_page(page) -> Optional[str]:
    """
    Scan page HTML for known CAPTCHA indicators.
    Returns captcha type string or None.
    """
    try:
        html = page.content().lower()
    except Exception:
        return None

    if "g-recaptcha" in html or "recaptcha/api.js" in html:
        return "recaptchav2"
    if "h-captcha" in html or "hcaptcha.com" in html:
        return "hcaptcha"
    if "cf-turnstile" in html or "challenges.cloudflare.com/turnstile" in html:
        return "turnstile"
    if any(ind in html for ind in ("cf_chl_", "cf-challenge", "captcha")):
        return "unknown_captcha"
    return None


# ── Handler ───────────────────────────────────────────────────────────────────

class CaptchaHandler:

    def __init__(self, engine, config: Optional[CaptchaConfig] = None):
        self._engine = engine
        self._config = config or CaptchaConfig()
        self._audit = engine._audit

    def apply_tier1_avoidance(self):
        """
        Apply stealth behaviors to reduce CAPTCHA triggering:
        - Set realistic HTTP headers via route interception
        - Add random pre-navigation jitter
        """
        page = self._engine.page
        stealth_headers = build_stealth_headers()
        page.set_extra_http_headers(stealth_headers)
        time.sleep(random.uniform(0.5, 1.5))
        self._audit.log(
            self._engine.current_url(), "captcha_tier1_applied", {}
        )

    def solve_tier2(self, captcha_type: str, site_key: str, page_url: str) -> bool:
        """
        Submit CAPTCHA to 2captcha or AntiCaptcha for solving.
        Returns True if solved and token injected, False if failed/not configured.
        """
        if not self._config.api_key:
            self._audit.log(page_url, "captcha_tier2_skip", {"reason": "no_api_key"})
            return False

        service = self._config.service or "2captcha"
        self._audit.log(page_url, "captcha_tier2_start",
                        {"service": service, "type": captcha_type})

        try:
            if service == "2captcha":
                return self._solve_2captcha(captcha_type, site_key, page_url)
            elif service == "anticaptcha":
                return self._solve_anticaptcha(captcha_type, site_key, page_url)
            else:
                return False
        except Exception as e:
            self._audit.log(page_url, "captcha_tier2_error", {"error": str(e)})
            return False

    def _solve_2captcha(self, captcha_type: str, site_key: str, page_url: str) -> bool:
        task_types = {
            "recaptchav2": "NoCaptchaTaskProxyless",
            "hcaptcha": "HCaptchaTaskProxyless",
            "turnstile": "TurnstileTaskProxyless",
        }
        task_type = task_types.get(captcha_type, "NoCaptchaTaskProxyless")

        resp = requests.post(
            "https://api.2captcha.com/createTask",
            json={
                "clientKey": self._config.api_key,
                "task": {
                    "type": task_type,
                    "websiteURL": page_url,
                    "websiteKey": site_key,
                }
            },
            timeout=30,
        )
        data = resp.json()
        task_id = data.get("taskId")
        if not task_id:
            return False

        deadline = time.time() + self._config.max_wait
        while time.time() < deadline:
            time.sleep(self._config.poll_interval)
            result_resp = requests.post(
                "https://api.2captcha.com/getTaskResult",
                json={"clientKey": self._config.api_key, "taskId": task_id},
                timeout=30,
            )
            result = result_resp.json()
            if result.get("status") == "ready":
                token = result.get("solution", {}).get("gRecaptchaResponse")
                if token:
                    return self._inject_token(token, captcha_type)
        return False

    def _solve_anticaptcha(self, captcha_type: str, site_key: str, page_url: str) -> bool:
        task_types = {
            "recaptchav2": "NoCaptchaTaskProxyless",
            "hcaptcha": "HCaptchaTaskProxyless",
        }
        task_type = task_types.get(captcha_type, "NoCaptchaTaskProxyless")

        resp = requests.post(
            "https://api.anti-captcha.com/createTask",
            json={
                "clientKey": self._config.api_key,
                "task": {
                    "type": task_type,
                    "websiteURL": page_url,
                    "websiteKey": site_key,
                }
            },
            timeout=30,
        )
        data = resp.json()
        task_id = data.get("taskId")
        if not task_id:
            return False

        deadline = time.time() + self._config.max_wait
        while time.time() < deadline:
            time.sleep(self._config.poll_interval)
            result_resp = requests.post(
                "https://api.anti-captcha.com/getTaskResult",
                json={"clientKey": self._config.api_key, "taskId": task_id},
                timeout=30,
            )
            result = result_resp.json()
            if result.get("status") == "ready":
                token = result.get("solution", {}).get("gRecaptchaResponse")
                if token:
                    return self._inject_token(token, captcha_type)
        return False

    def _inject_token(self, token: str, captcha_type: str) -> bool:
        """Inject solved CAPTCHA token into the page."""
        page = self._engine.page
        try:
            if captcha_type in ("recaptchav2", "recaptchav3"):
                page.evaluate(
                    f"document.getElementById('g-recaptcha-response').innerHTML = '{token}';"
                )
            elif captcha_type == "hcaptcha":
                page.evaluate(
                    f"document.querySelector('[name=h-captcha-response]').value = '{token}';"
                )
            self._audit.log(self._engine.current_url(), "captcha_token_injected",
                            {"type": captcha_type})
            return True
        except Exception as e:
            self._audit.log(self._engine.current_url(), "captcha_inject_failed",
                            {"error": str(e)})
            return False

    def tier3_human_handoff(
        self,
        chat_id: Optional[str] = None,
        timeout_seconds: int = 300,
        message: str = "CAPTCHA detected — please solve it manually. Reply /captcha-done when finished.",
    ) -> bool:
        """
        Pause for human CAPTCHA solving. Alerts Jordan via Telegram.
        Returns True if solved within timeout, False otherwise.
        """
        self._audit.log(self._engine.current_url(), "captcha_tier3_start", {})

        if chat_id:
            try:
                bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
                if bot_token:
                    requests.post(
                        f"https://api.telegram.org/bot{bot_token}/sendMessage",
                        json={"chat_id": chat_id, "text": message},
                        timeout=10,
                    )
            except Exception:
                pass

        flag = Path("/tmp/openclaw-captcha-pending.flag")
        flag.write_text("pending")

        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            time.sleep(2)
            if not flag.exists():
                self._audit.log(self._engine.current_url(), "captcha_tier3_solved", {})
                return True

        flag.unlink(missing_ok=True)
        self._audit.log(self._engine.current_url(), "captcha_tier3_timeout", {})
        return False

    def handle(
        self,
        chat_id: Optional[str] = None,
        site_key: Optional[str] = None,
    ) -> bool:
        """
        Full CAPTCHA handling pipeline:
        1. Apply Tier 1 avoidance
        2. Detect CAPTCHA type on page
        3. If detected: try Tier 2, fall back to Tier 3
        Returns True if handled/resolved, False if failed.
        """
        self.apply_tier1_avoidance()
        captcha_type = detect_captcha_on_page(self._engine.page)

        if not captcha_type:
            return True  # No CAPTCHA detected

        self._audit.log(self._engine.current_url(), "captcha_detected",
                        {"type": captcha_type})

        if site_key:
            solved = self.solve_tier2(captcha_type, site_key, self._engine.current_url())
            if solved:
                return True

        return self.tier3_human_handoff(chat_id=chat_id)
