#!/usr/bin/env python3
"""
test_baseline_2.py — Session login + restore baseline test.

Phase 1: Log into https://app.example.com/login, save session to encrypted store.
Phase 2: Open the same site using only the saved session (no re-login).
         Print whether the session restore worked.

Credentials are sourced from the CredentialVault (never hardcoded in running
logic). On first run the vault is seeded once at the top of this script.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the scripts/ directory importable so `browser.*` resolves correctly.
sys.path.insert(0, str(Path(__file__).parent))

from browser.security import get_vault, get_audit_logger
from browser.browser_tools import browser_login, browser_open, browser_shutdown


# ── Target configuration ──────────────────────────────────────────────────────

LOGIN_URL    = "https://app.example.com/login"
SITE_URL     = "https://app.example.com/"
DOMAIN       = "app.example.com"

# Vault keys — credentials are stored/retrieved under these names.
VAULT_KEY_USER = "example_com_username"
VAULT_KEY_PASS = "example_com_password"


# ── Step 0: Seed credentials into the vault (idempotent) ──────────────────────
# The vault is Fernet-encrypted at rest (~/.openclaw/browser-vault.enc).
# We only write if the keys are absent, so re-running this script never
# overwrites credentials that were manually rotated.

def _seed_vault():
    vault = get_vault()
    if vault.retrieve(VAULT_KEY_USER) is None:
        vault.store(VAULT_KEY_USER, "admin")
    if vault.retrieve(VAULT_KEY_PASS) is None:
        vault.store(VAULT_KEY_PASS, "secretpass123")


# ── Phase 1: Login + save session ─────────────────────────────────────────────

def phase1_login_and_save() -> bool:
    """
    Navigate to the login page, submit credentials, save the resulting
    session cookies to the encrypted SessionStore.

    Returns True if login reported success, False otherwise.
    """
    vault    = get_vault()
    username = vault.retrieve(VAULT_KEY_USER)
    password = vault.retrieve(VAULT_KEY_PASS)

    print("[phase1] Logging in …")
    result = browser_login(
        url=LOGIN_URL,
        username=username,
        password=password,
        save_session_domain=DOMAIN,   # triggers AuthHandler.save_session()
        stealth=False,
    )

    if result.get("ok"):
        print(f"[phase1] Login succeeded. Final URL: {result.get('url')}")
        print(f"[phase1] Session saved for domain '{DOMAIN}': {result.get('session_saved')}")
    else:
        print(f"[phase1] Login failed: {result.get('error')}")

    return bool(result.get("ok"))


# ── Phase 2: Restore session + verify ─────────────────────────────────────────

def phase2_restore_session() -> bool:
    """
    Open the site by injecting the previously saved cookies — no login form
    interaction at all.  Checks whether we land on an authenticated page
    (heuristic: the post-login URL should NOT contain '/login').

    Returns True if session restore appears to have worked, False otherwise.
    """
    print("\n[phase2] Opening site with saved session (no re-login) …")
    result = browser_open(
        url=SITE_URL,
        wait_until="domcontentloaded",
        extract="dom",
        session_domain=DOMAIN,        # browser_open injects saved cookies before navigation
    )

    if not result.get("ok"):
        print(f"[phase2] Navigation failed: {result.get('error')}")
        return False

    final_url = result.get("url", "")
    title     = result.get("title", "")
    print(f"[phase2] Final URL : {final_url}")
    print(f"[phase2] Page title: {title}")

    # Heuristic: if we were redirected back to a login page, the session
    # did not restore.  A real implementation would check for a known
    # authenticated element or URL prefix.
    session_ok = "/login" not in final_url
    return session_ok


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    audit = get_audit_logger()
    audit.log(SITE_URL, "test_baseline_2_start", {})

    _seed_vault()

    # Phase 1 — login
    login_ok = phase1_login_and_save()
    if not login_ok:
        print("\n[result] FAIL — could not log in during Phase 1.")
        browser_shutdown()
        sys.exit(1)

    # Shut down the browser between phases to prove the session survives
    # a fresh browser launch (cookies come from encrypted disk store, not memory).
    browser_shutdown()
    print("\n[phase1→2] Browser shut down. Starting fresh browser for Phase 2 …\n")

    # Phase 2 — restore
    restore_ok = phase2_restore_session()

    print()
    if restore_ok:
        print("[result] SUCCESS — session restored without re-login.")
    else:
        print("[result] FAIL — session restore did not work (redirected to login or error).")

    browser_shutdown()
    audit.log(SITE_URL, "test_baseline_2_end", {"login_ok": login_ok, "restore_ok": restore_ok})
    sys.exit(0 if restore_ok else 1)


if __name__ == "__main__":
    main()
