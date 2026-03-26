#!/usr/bin/env python3
"""
test_baseline_4.py — Contact form automation baseline test.

Visits https://contact.example.com/form, handles any CAPTCHA,
fills in name/email/message, submits, and prints the confirmation.

Usage:
    python test_baseline_4.py

Optional env vars:
    CAPTCHA_API_KEY      — 2captcha or AntiCaptcha API key (Tier 2 solving)
    CAPTCHA_SERVICE      — "2captcha" (default) or "anticaptcha"
    TELEGRAM_BOT_TOKEN   — Telegram bot token for Tier 3 human handoff
    TELEGRAM_CHAT_ID     — Chat ID for the Tier 3 alert message
    HEADED=1             — Launch browser in visible (headed) mode for debugging
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Ensure the scripts/ directory is on the path so `browser.*` imports work.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from browser.pool import BrowserPool
from browser.eyes import Eyes
from browser.hands import Hands
from browser.captcha_handler import CaptchaHandler, detect_captcha_on_page

# ── Constants ─────────────────────────────────────────────────────────────────

TARGET_URL = "https://contact.example.com/form"

FORM_DATA = {
    "name": "Jordan",
    "email": "jordan@openclaw.com",
    "message": "Testing automation",
}

# CSS selectors — covers common name patterns; the loop below tries each in order
# and fills whichever locator resolves first.
FIELD_SELECTOR_CANDIDATES = {
    "name": [
        'input[name="name"]',
        'input[name="full_name"]',
        'input[name="fullName"]',
        'input[id="name"]',
        'input[placeholder*="name" i]',
        'input[aria-label*="name" i]',
    ],
    "email": [
        'input[type="email"]',
        'input[name="email"]',
        'input[id="email"]',
        'input[placeholder*="email" i]',
        'input[aria-label*="email" i]',
    ],
    "message": [
        'textarea[name="message"]',
        'textarea[name="body"]',
        'textarea[id="message"]',
        'textarea[placeholder*="message" i]',
        'textarea[aria-label*="message" i]',
        'textarea',
    ],
}

SUBMIT_SELECTOR_CANDIDATES = [
    'button[type="submit"]',
    'input[type="submit"]',
    'button:has-text("Submit")',
    'button:has-text("Send")',
    'button:has-text("Send Message")',
    '[data-testid="submit"]',
]

CONFIRMATION_SELECTORS = [
    '.confirmation',
    '.success',
    '[class*="confirm"]',
    '[class*="success"]',
    '[role="alert"]',
    'h1',
    'h2',
    'p',
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_selector(page, candidates: list[str]) -> str | None:
    """Return the first selector from candidates that matches a visible element."""
    for sel in candidates:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=2000):
                return sel
        except Exception:
            continue
    return None


def _extract_site_key(page) -> str | None:
    """
    Attempt to scrape the CAPTCHA site key from the page HTML.
    Covers reCAPTCHA, hCaptcha, and Cloudflare Turnstile.
    """
    html = page.content()
    import re
    patterns = [
        r'data-sitekey=["\']([^"\']+)["\']',    # reCAPTCHA / hCaptcha
        r'"sitekey"\s*:\s*"([^"]+)"',             # JSON inline config
        r'sitekey:\s*["\']([^"\']+)["\']',        # JS object literal
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _capture_confirmation(page) -> str:
    """
    Attempt to extract a human-readable confirmation message after submit.
    Tries several common selectors; falls back to page title + first paragraph.
    """
    for sel in CONFIRMATION_SELECTORS:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=3000):
                text = loc.inner_text().strip()
                if text:
                    return text
        except Exception:
            continue
    # Last-resort fallback
    try:
        return page.title() or "(no confirmation text found)"
    except Exception:
        return "(could not read confirmation)"


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    print(f"[test_baseline_4] Target: {TARGET_URL}")
    print("[test_baseline_4] Starting browser pool (stealth=True) ...")

    pool = BrowserPool(headless=True, stealth=True)
    engine = pool.get()

    try:
        page = engine.page
        eyes = Eyes(engine)
        hands = Hands(engine)

        # ── Step 1: Navigate ──────────────────────────────────────────────────
        print(f"[1/5] Navigating to {TARGET_URL} ...")
        engine.navigate(TARGET_URL, wait_until="domcontentloaded")
        print(f"      Title: {eyes.title()}")
        print(f"      URL:   {engine.current_url()}")

        # ── Step 2: CAPTCHA handling (Tier 1 → 2 → 3) ────────────────────────
        print("[2/5] Running CAPTCHA check ...")
        captcha_handler = CaptchaHandler(engine)

        # Tier 1: apply stealth headers + jitter (always runs)
        captcha_handler.apply_tier1_avoidance()

        captcha_type = detect_captcha_on_page(page)
        if captcha_type:
            print(f"      CAPTCHA detected: {captcha_type}")
            site_key = _extract_site_key(page)
            print(f"      Site key: {site_key or '(not found — Tier 2 will skip)'}")

            # Tier 2: automated solver via 2captcha / AntiCaptcha
            solved = False
            if site_key and os.environ.get("CAPTCHA_API_KEY"):
                print("      Attempting Tier 2 (API solver) ...")
                solved = captcha_handler.solve_tier2(captcha_type, site_key, TARGET_URL)
                if solved:
                    print("      Tier 2: CAPTCHA solved.")
                else:
                    print("      Tier 2: solver failed or timed out.")

            # Tier 3: human handoff via Telegram
            if not solved:
                chat_id = os.environ.get("TELEGRAM_CHAT_ID")
                print(f"      Falling back to Tier 3 (human handoff, chat_id={chat_id}) ...")
                solved = captcha_handler.tier3_human_handoff(
                    chat_id=chat_id,
                    timeout_seconds=300,
                    message=(
                        "OpenClaw test_baseline_4: CAPTCHA on contact form. "
                        "Please solve it and delete /tmp/openclaw-captcha-pending.flag "
                        "when done."
                    ),
                )
                if solved:
                    print("      Tier 3: CAPTCHA resolved by human.")
                else:
                    raise RuntimeError("CAPTCHA could not be solved (Tier 3 timed out).")
        else:
            print("      No CAPTCHA detected — proceeding.")

        # ── Step 3: Locate and fill form fields ───────────────────────────────
        print("[3/5] Filling form fields ...")

        resolved_selectors: dict[str, str] = {}
        for field, candidates in FIELD_SELECTOR_CANDIDATES.items():
            sel = _resolve_selector(page, candidates)
            if sel is None:
                raise RuntimeError(
                    f"Could not find a visible input for field '{field}'. "
                    f"Tried: {candidates}"
                )
            resolved_selectors[field] = sel
            print(f"      {field}: matched '{sel}'")

        # Scroll the form into view before filling (handles lazy-loaded forms)
        hands.scroll_to_element(resolved_selectors["name"])

        # Fill using Hands.fill_form (fast-fill path; no per-char delay)
        fields_to_fill = {
            resolved_selectors["name"]:    FORM_DATA["name"],
            resolved_selectors["email"]:   FORM_DATA["email"],
            resolved_selectors["message"]: FORM_DATA["message"],
        }
        hands.fill_form(fields_to_fill)
        print(f"      Filled: name={FORM_DATA['name']!r}, "
              f"email={FORM_DATA['email']!r}, "
              f"message={FORM_DATA['message']!r}")

        # Brief pause — let any JS validators run before we submit
        time.sleep(0.5)

        # ── Step 4: Submit ────────────────────────────────────────────────────
        print("[4/5] Submitting form ...")
        submit_sel = _resolve_selector(page, SUBMIT_SELECTOR_CANDIDATES)
        if submit_sel:
            print(f"      Submit button matched: '{submit_sel}'")
            hands.click(submit_sel)
            engine.wait_for_load(state="domcontentloaded")
        else:
            # Fallback: trigger form.submit() directly
            print("      No submit button found — calling form.submit() directly.")
            hands.submit_form("form")

        print(f"      Post-submit URL: {engine.current_url()}")

        # ── Step 5: Capture confirmation ─────────────────────────────────────
        print("[5/5] Capturing confirmation ...")
        # Give the page a moment to render any dynamic confirmation messages
        time.sleep(1)
        confirmation = _capture_confirmation(page)

        print("\n" + "=" * 60)
        print("CONFIRMATION:")
        print(confirmation)
        print("=" * 60)

        return {"ok": True, "confirmation": confirmation, "url": engine.current_url()}

    except Exception as exc:
        import traceback
        print(f"\n[ERROR] {exc}")
        traceback.print_exc()
        return {"ok": False, "error": str(exc)}

    finally:
        pool.shutdown()
        print("[test_baseline_4] Browser pool shut down.")


if __name__ == "__main__":
    result = run()
    sys.exit(0 if result.get("ok") else 1)
