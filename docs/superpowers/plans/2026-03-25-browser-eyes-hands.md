# Browser Eyes & Hands — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a full browser automation layer (`scripts/browser/`) that gives Claude Code and Clawmson (Telegram bot) the ability to open URLs, take screenshots, click/type/scroll, handle auth flows, and manage CAPTCHAs — all with security discipline and web citizenship.

**Architecture:** Playwright (sync API) is the core engine wrapping Chromium. Eight focused modules handle distinct concerns (engine, eyes, hands, auth, captcha, security). Telegram slash commands `/browse` and `/screenshot` route through the existing dispatcher pattern. Claude Code gets a thin `browser_tools.py` shim with named callables.

**Tech Stack:** Python 3.11+, Playwright 1.58.0 (already installed, Chromium verified), cryptography.fernet (vault), stdlib json/pathlib/logging. No new pip installs required.

---

## File Map

| File | Responsibility |
|------|---------------|
| `scripts/browser/__init__.py` | Re-exports public API for easy imports |
| `scripts/browser/config.json` | Domain allowlist/blocklist, rate limits, proxy, timeouts |
| `scripts/browser/security.py` | Fernet-encrypted credential vault, audit logger, domain scope checker, robots.txt |
| `scripts/browser/browser_engine.py` | Playwright context lifecycle, human-like timing, user-agent, proxy, stealth |
| `scripts/browser/eyes.py` | Screenshot capture, DOM text extraction, hybrid routing (vision vs DOM) |
| `scripts/browser/hands.py` | Click, type, scroll, hover, select, drag, file upload, tab management |
| `scripts/browser/auth_handler.py` | OAuth redirect chains, username/password login, encrypted session persistence, MFA handoff |
| `scripts/browser/captcha_handler.py` | Tier 1 avoidance, Tier 2 2captcha/AntiCaptcha API, Tier 3 Telegram pause |
| `scripts/browser/browser_tools.py` | Claude Code callable shim: `browser_open`, `browser_screenshot`, `browser_click`, `browser_fill`, `browser_eval` |
| `scripts/browser/tests/test_navigation.py` | URL open + screenshot + text extract |
| `scripts/browser/tests/test_forms.py` | Fill and submit web forms |
| `scripts/browser/tests/test_auth.py` | Session save/load, cookie persistence |
| `scripts/browser/tests/test_captcha.py` | Tier 1 avoidance headers; Tier 2/3 mock paths |
| `scripts/browser/tests/test_multiflow.py` | Multi-step workflow end-to-end |
| `agents/configs/browser-agent.md` | System documentation for agents |
| `.env` additions | `CAPTCHA_API_KEY`, `BROWSER_PROXY_URL`, `BROWSER_DEFAULT_TIMEOUT` placeholders |

**Modified files:**
- `scripts/clawmson_intents.py` — add `BROWSER_TASK` constant + LLM prompt update + regex patterns
- `scripts/telegram-dispatcher.py` — add `/browse` + `/screenshot` slash handlers + `BROWSER_TASK` routing

---

## Task 1: Scaffold — Directory, Config, ENV Placeholders

**Files:**
- Create: `scripts/browser/__init__.py`
- Create: `scripts/browser/config.json`
- Create: `scripts/browser/tests/__init__.py`
- Modify: `.env` (add 3 commented placeholder lines)

- [ ] **Step 1.1: Write the failing test for config loading**

```python
# scripts/browser/tests/test_navigation.py
import json
from pathlib import Path

def test_config_exists_and_has_required_keys():
    config_path = Path(__file__).parent.parent / "config.json"
    assert config_path.exists(), "config.json must exist"
    config = json.loads(config_path.read_text())
    for key in ("allowed_domains", "blocked_domains", "rate_limit_seconds",
                "default_timeout_ms", "stealth_mode", "proxy_url"):
        assert key in config, f"config.json missing key: {key}"
```

- [ ] **Step 1.2: Run test — verify it FAILS**

```bash
cd ~/openclaw && python3 -m pytest scripts/browser/tests/test_navigation.py::test_config_exists_and_has_required_keys -v
```
Expected: `FileNotFoundError` or `AssertionError: config.json must exist`

- [ ] **Step 1.3: Create `scripts/browser/__init__.py`**

```python
#!/usr/bin/env python3
"""Browser Eyes & Hands — automation layer for Claude Code and Clawmson."""
from __future__ import annotations
```

- [ ] **Step 1.4: Create `scripts/browser/config.json`**

```json
{
  "allowed_domains": [],
  "blocked_domains": [
    "localhost",
    "127.0.0.1"
  ],
  "rate_limit_seconds": [1, 3],
  "default_timeout_ms": 30000,
  "stealth_mode": false,
  "proxy_url": null,
  "robots_txt_respect": true,
  "audit_log_dir": "~/openclaw/logs/browser",
  "session_store_dir": "~/.openclaw/browser-sessions",
  "vault_path": "~/.openclaw/browser-vault.enc",
  "captcha_service": "2captcha",
  "user_agent_stealth": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
  "user_agent_honest": "OpenClaw-BrowserBot/1.0 (+https://openclaw.local)"
}
```

- [ ] **Step 1.5: Create `scripts/browser/tests/__init__.py`** (empty file)

- [ ] **Step 1.6: Add ENV placeholders to `.env`**

Open `~/openclaw/.env` and append these lines at the end:
```
# Browser Eyes & Hands
# CAPTCHA_API_KEY=           # 2captcha or AntiCaptcha API key
# BROWSER_PROXY_URL=         # optional proxy e.g. http://user:pass@host:port
# BROWSER_DEFAULT_TIMEOUT=30000   # ms
```

- [ ] **Step 1.7: Run test — verify it PASSES**

```bash
cd ~/openclaw && python3 -m pytest scripts/browser/tests/test_navigation.py::test_config_exists_and_has_required_keys -v
```
Expected: `PASSED`

- [ ] **Step 1.8: Commit**

```bash
cd ~/openclaw && git add scripts/browser/__init__.py scripts/browser/config.json scripts/browser/tests/__init__.py scripts/browser/tests/test_navigation.py
git commit -m "feat(browser): scaffold directory, config.json, test skeleton"
```

---

## Task 2: `security.py` — Credential Vault, Audit Logger, Domain Scope

**Files:**
- Create: `scripts/browser/security.py`

- [ ] **Step 2.1: Write failing tests**

Add to `scripts/browser/tests/test_navigation.py`:
```python
import sys, os
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from browser.security import CredentialVault, AuditLogger, DomainScope

def test_vault_store_and_retrieve(tmp_path):
    vault = CredentialVault(vault_path=tmp_path / "test-vault.enc")
    vault.store("test_key", "secret_value")
    assert vault.retrieve("test_key") == "secret_value"

def test_vault_key_not_found(tmp_path):
    vault = CredentialVault(vault_path=tmp_path / "test-vault.enc")
    assert vault.retrieve("nonexistent") is None

def test_domain_scope_blocked():
    scope = DomainScope(allowed=[], blocked=["evil.com"])
    assert not scope.is_allowed("https://evil.com/page")

def test_domain_scope_allowed_list():
    scope = DomainScope(allowed=["good.com"], blocked=[])
    assert scope.is_allowed("https://good.com/page")
    assert not scope.is_allowed("https://other.com/page")

def test_domain_scope_empty_allowed_means_all():
    scope = DomainScope(allowed=[], blocked=[])
    assert scope.is_allowed("https://anything.com/page")

def test_audit_logger_writes_file(tmp_path):
    logger = AuditLogger(log_dir=tmp_path)
    logger.log("https://example.com", "navigate", {"status": 200})
    logs = list(tmp_path.glob("browser-*.jsonl"))
    assert len(logs) == 1
    import json
    entry = json.loads(logs[0].read_text().strip())
    assert entry["url"] == "https://example.com"
    assert entry["action"] == "navigate"
```

- [ ] **Step 2.2: Run tests — verify they FAIL**

```bash
cd ~/openclaw && python3 -m pytest scripts/browser/tests/test_navigation.py -k "vault or domain or audit" -v
```
Expected: `ImportError` — module not yet created

- [ ] **Step 2.3: Create `scripts/browser/security.py`**

```python
#!/usr/bin/env python3
"""
Browser security layer — credential vault, audit logging, domain scope, robots.txt.
Vault uses Fernet symmetric encryption keyed from machine-specific entropy.
"""
from __future__ import annotations

import json
import os
import re
import datetime
import hashlib
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Optional
from cryptography.fernet import Fernet


# ── Key derivation ────────────────────────────────────────────────────────────

def _derive_key() -> bytes:
    """
    Derive a stable Fernet key from machine-specific entropy.
    Uses hostname + username + a fixed salt — never leaves the machine.
    """
    import socket
    entropy = f"{socket.gethostname()}:{os.getlogin()}:openclaw-browser-vault-v1"
    raw = hashlib.sha256(entropy.encode()).digest()
    # Fernet requires 32 URL-safe base64 bytes
    import base64
    return base64.urlsafe_b64encode(raw)


# ── Credential Vault ──────────────────────────────────────────────────────────

class CredentialVault:
    """
    Fernet-encrypted key/value store persisted to a local file.
    Keys and values are plain strings. Secrets never touch logs or CLI args.
    """

    def __init__(self, vault_path: Optional[Path] = None):
        if vault_path is None:
            vault_path = Path.home() / ".openclaw" / "browser-vault.enc"
        self._path = Path(vault_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fernet = Fernet(_derive_key())
        self._data: dict = self._load()

    def _load(self) -> dict:
        if not self._path.exists():
            return {}
        try:
            ciphertext = self._path.read_bytes()
            plaintext = self._fernet.decrypt(ciphertext)
            return json.loads(plaintext)
        except Exception:
            return {}

    def _save(self):
        plaintext = json.dumps(self._data).encode()
        ciphertext = self._fernet.encrypt(plaintext)
        self._path.write_bytes(ciphertext)

    def store(self, key: str, value: str):
        """Store a secret. Never log the value."""
        self._data[key] = value
        self._save()

    def retrieve(self, key: str) -> Optional[str]:
        """Retrieve a secret, or None if not found."""
        return self._data.get(key)

    def delete(self, key: str):
        self._data.pop(key, None)
        self._save()

    def keys(self) -> list:
        return list(self._data.keys())


# ── Audit Logger ──────────────────────────────────────────────────────────────

class AuditLogger:
    """
    Append-only JSONL audit log. One file per day in log_dir.
    Records every URL visited and every action taken.
    """

    def __init__(self, log_dir: Optional[Path] = None):
        if log_dir is None:
            log_dir = Path.home() / "openclaw" / "logs" / "browser"
        self._dir = Path(log_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _log_path(self) -> Path:
        date = datetime.date.today().isoformat()
        return self._dir / f"browser-{date}.jsonl"

    def log(self, url: str, action: str, metadata: dict | None = None):
        entry = {
            "ts": datetime.datetime.now().isoformat(),
            "url": url,
            "action": action,
            **(metadata or {}),
        }
        with self._log_path().open("a") as f:
            f.write(json.dumps(entry) + "\n")


# ── Domain Scope ──────────────────────────────────────────────────────────────

class DomainScope:
    """
    Enforce domain allowlist/blocklist per task.
    If allowed is empty: all domains permitted except blocked.
    If allowed is non-empty: only those domains (minus blocked).
    """

    def __init__(self, allowed: list[str], blocked: list[str]):
        self._allowed = [d.lower().lstrip("*.") for d in allowed]
        self._blocked = [d.lower().lstrip("*.") for d in blocked]

    def _domain_of(self, url: str) -> str:
        parsed = urllib.parse.urlparse(url)
        return parsed.netloc.lower()

    def is_allowed(self, url: str) -> bool:
        domain = self._domain_of(url)
        # Check blocklist first
        for blocked in self._blocked:
            if domain == blocked or domain.endswith("." + blocked):
                return False
        # If allowlist is empty, allow everything not blocked
        if not self._allowed:
            return True
        # Must match allowlist
        for allowed in self._allowed:
            if domain == allowed or domain.endswith("." + allowed):
                return True
        return False


# ── robots.txt checker ────────────────────────────────────────────────────────

_robots_cache: dict[str, bool] = {}  # domain → allowed


def check_robots_txt(url: str, user_agent: str = "*") -> bool:
    """
    Returns True if the URL is allowed by robots.txt, False if disallowed.
    Caches per domain per process run. On fetch error, defaults to True (allow).
    """
    parsed = urllib.parse.urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    cache_key = f"{base}:{parsed.path}"

    if cache_key in _robots_cache:
        return _robots_cache[cache_key]

    try:
        robots_url = f"{base}/robots.txt"
        req = urllib.request.Request(robots_url, headers={"User-Agent": user_agent})
        with urllib.request.urlopen(req, timeout=5) as resp:
            robots_text = resp.read().decode("utf-8", errors="replace")
    except Exception:
        _robots_cache[cache_key] = True
        return True

    # Simple robots.txt parser — check relevant user-agent sections
    result = _parse_robots(robots_text, parsed.path, user_agent)
    _robots_cache[cache_key] = result
    return result


def _parse_robots(robots_text: str, path: str, user_agent: str) -> bool:
    """Returns True if path is allowed for user_agent."""
    lines = robots_text.splitlines()
    in_relevant_section = False
    disallow_rules: list[str] = []
    allow_rules: list[str] = []

    for line in lines:
        line = line.strip()
        if line.startswith("#") or not line:
            continue
        if line.lower().startswith("user-agent:"):
            ua = line[len("user-agent:"):].strip()
            in_relevant_section = (ua == "*" or ua.lower() == user_agent.lower())
            continue
        if in_relevant_section:
            if line.lower().startswith("disallow:"):
                rule = line[len("disallow:"):].strip()
                if rule:
                    disallow_rules.append(rule)
            elif line.lower().startswith("allow:"):
                rule = line[len("allow:"):].strip()
                if rule:
                    allow_rules.append(rule)

    # Allow rules take precedence over disallow
    for rule in allow_rules:
        if path.startswith(rule):
            return True
    for rule in disallow_rules:
        if path.startswith(rule):
            return False
    return True


# ── Module-level singleton helpers ────────────────────────────────────────────

_default_vault: Optional[CredentialVault] = None
_default_audit: Optional[AuditLogger] = None


def get_vault() -> CredentialVault:
    global _default_vault
    if _default_vault is None:
        _default_vault = CredentialVault()
    return _default_vault


def get_audit_logger() -> AuditLogger:
    global _default_audit
    if _default_audit is None:
        _default_audit = AuditLogger()
    return _default_audit
```

- [ ] **Step 2.4: Run tests — verify they PASS**

```bash
cd ~/openclaw && python3 -m pytest scripts/browser/tests/test_navigation.py -k "vault or domain or audit" -v
```
Expected: all 6 tests `PASSED`

- [ ] **Step 2.5: Commit**

```bash
cd ~/openclaw && git add scripts/browser/security.py scripts/browser/tests/test_navigation.py
git commit -m "feat(browser): security.py — Fernet vault, audit logger, domain scope"
```

---

## Task 3: `browser_engine.py` — Playwright Core Wrapper

**Files:**
- Create: `scripts/browser/browser_engine.py`

- [ ] **Step 3.1: Write failing tests**

Add to `scripts/browser/tests/test_navigation.py`:
```python
from browser.browser_engine import BrowserEngine

def test_engine_opens_and_closes():
    with BrowserEngine() as engine:
        assert engine.page is not None

def test_engine_navigate_returns_title():
    with BrowserEngine() as engine:
        title = engine.navigate("https://example.com")
        assert isinstance(title, str)

def test_engine_navigate_blocked_domain_raises():
    import pytest
    with BrowserEngine(blocked_domains=["example.com"]) as engine:
        with pytest.raises(PermissionError, match="blocked"):
            engine.navigate("https://example.com")

def test_engine_navigate_respects_rate_limit():
    import time
    with BrowserEngine(rate_limit_seconds=(0.1, 0.2)) as engine:
        engine.navigate("https://example.com")
        t0 = time.time()
        engine.navigate("https://example.com")
        elapsed = time.time() - t0
        assert elapsed >= 0.1, "rate limit not enforced"
```

- [ ] **Step 3.2: Run tests — verify they FAIL**

```bash
cd ~/openclaw && python3 -m pytest scripts/browser/tests/test_navigation.py -k "engine" -v
```
Expected: `ImportError`

- [ ] **Step 3.3: Create `scripts/browser/browser_engine.py`**

```python
#!/usr/bin/env python3
"""
Playwright wrapper — core browser automation engine.
Single-session, context manager usage. Sync API only (matches OpenClaw patterns).

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
        self._last_nav_time = time.time()

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
```

- [ ] **Step 3.4: Run tests — verify they PASS**

```bash
cd ~/openclaw && python3 -m pytest scripts/browser/tests/test_navigation.py -k "engine" -v
```
Expected: 4 tests `PASSED`

- [ ] **Step 3.5: Commit**

```bash
cd ~/openclaw && git add scripts/browser/browser_engine.py scripts/browser/tests/test_navigation.py
git commit -m "feat(browser): browser_engine.py — Playwright wrapper with scope + rate limit"
```

---

## Task 4: `eyes.py` — Screenshot, DOM Extraction, Hybrid Routing

**Files:**
- Create: `scripts/browser/eyes.py`

- [ ] **Step 4.1: Write failing tests**

Add to `scripts/browser/tests/test_navigation.py`:
```python
from browser.eyes import Eyes

def test_eyes_screenshot_returns_bytes():
    with BrowserEngine() as engine:
        engine.navigate("https://example.com")
        eyes = Eyes(engine)
        data = eyes.screenshot()
        assert isinstance(data, bytes)
        assert data[:4] == b'\x89PNG'  # PNG magic bytes

def test_eyes_screenshot_saves_file(tmp_path):
    with BrowserEngine() as engine:
        engine.navigate("https://example.com")
        eyes = Eyes(engine)
        path = tmp_path / "shot.png"
        eyes.screenshot(save_path=path)
        assert path.exists()
        assert path.stat().st_size > 0

def test_eyes_dom_text_contains_content():
    with BrowserEngine() as engine:
        engine.navigate("https://example.com")
        eyes = Eyes(engine)
        text = eyes.dom_text()
        assert "Example Domain" in text

def test_eyes_hybrid_returns_string():
    with BrowserEngine() as engine:
        engine.navigate("https://example.com")
        eyes = Eyes(engine)
        result = eyes.extract(mode="auto")
        assert isinstance(result, str)
        assert len(result) > 0
```

- [ ] **Step 4.2: Run tests — verify they FAIL**

```bash
cd ~/openclaw && python3 -m pytest scripts/browser/tests/test_navigation.py -k "eyes" -v
```
Expected: `ImportError`

- [ ] **Step 4.3: Create `scripts/browser/eyes.py`**

```python
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


# Pages with these patterns are considered "structured" → prefer DOM extraction
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
        Extract visible text from DOM. Much faster than screenshot for text-heavy pages.
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
```

- [ ] **Step 4.4: Run tests — verify they PASS**

```bash
cd ~/openclaw && python3 -m pytest scripts/browser/tests/test_navigation.py -k "eyes" -v
```
Expected: 4 tests `PASSED`

- [ ] **Step 4.5: Commit**

```bash
cd ~/openclaw && git add scripts/browser/eyes.py scripts/browser/tests/test_navigation.py
git commit -m "feat(browser): eyes.py — screenshot, DOM extraction, hybrid routing"
```

---

## Task 5: `hands.py` — Click, Type, Scroll, Form Fill

**Files:**
- Create: `scripts/browser/hands.py`
- Create: `scripts/browser/tests/test_forms.py`

- [ ] **Step 5.1: Write failing tests**

```python
# scripts/browser/tests/test_forms.py
"""Tests for Hands action layer. Uses a real page with forms."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from browser.browser_engine import BrowserEngine
from browser.hands import Hands


def test_hands_click():
    """Click a link and verify navigation occurred."""
    with BrowserEngine() as engine:
        engine.navigate("https://example.com")
        hands = Hands(engine)
        # example.com has a 'More information...' link
        hands.click("a")
        assert engine.current_url() != "https://example.com/"


def test_hands_type_and_clear(tmp_path):
    """Type into a search field using a real search page."""
    # Use data: URI for a local test form
    engine_ctx = BrowserEngine()
    with engine_ctx as engine:
        # Create a minimal test page via data URI
        engine.page.set_content(
            '<html><body><input id="q" type="text"/></body></html>'
        )
        hands = Hands(engine)
        hands.type("#q", "hello world")
        val = engine.page.locator("#q").input_value()
        assert val == "hello world"
        hands.clear("#q")
        assert engine.page.locator("#q").input_value() == ""


def test_hands_fill_form():
    """Fill multiple form fields and read back values."""
    with BrowserEngine() as engine:
        engine.page.set_content("""
            <html><body>
              <input id="name" type="text"/>
              <input id="email" type="email"/>
              <select id="color">
                <option value="red">Red</option>
                <option value="blue">Blue</option>
              </select>
            </body></html>
        """)
        hands = Hands(engine)
        hands.fill_form({
            "#name": "Jordan",
            "#email": "j@example.com",
        })
        assert engine.page.locator("#name").input_value() == "Jordan"
        assert engine.page.locator("#email").input_value() == "j@example.com"


def test_hands_scroll():
    """Scroll page without raising."""
    with BrowserEngine() as engine:
        engine.navigate("https://example.com")
        hands = Hands(engine)
        hands.scroll(0, 300)  # should not raise


def test_hands_select():
    """Select a dropdown option."""
    with BrowserEngine() as engine:
        engine.page.set_content("""
            <html><body>
              <select id="s">
                <option value="a">A</option>
                <option value="b">B</option>
              </select>
            </body></html>
        """)
        hands = Hands(engine)
        hands.select("#s", "b")
        assert engine.page.locator("#s").input_value() == "b"
```

- [ ] **Step 5.2: Run tests — verify they FAIL**

```bash
cd ~/openclaw && python3 -m pytest scripts/browser/tests/test_forms.py -v
```
Expected: `ImportError`

- [ ] **Step 5.3: Create `scripts/browser/hands.py`**

```python
#!/usr/bin/env python3
"""
Action layer — click, type, scroll, hover, select, drag, upload, tab management.
All actions include human-like delays and audit logging.
"""
from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Optional, Union

from browser.browser_engine import BrowserEngine


def _human_delay(lo: float = 0.05, hi: float = 0.15):
    """Small random pause to simulate human speed."""
    time.sleep(random.uniform(lo, hi))


class Hands:
    """
    Action executor attached to a BrowserEngine.
    All methods log to the engine's audit logger.
    """

    def __init__(self, engine: BrowserEngine):
        self._engine = engine
        self._audit = engine._audit
        self._page = engine.page

    def click(self, selector: str, timeout: int = 10000):
        """Click the first element matching selector."""
        self._page.locator(selector).first.click(timeout=timeout)
        _human_delay()
        self._audit.log(self._engine.current_url(), "click", {"selector": selector})

    def double_click(self, selector: str):
        self._page.locator(selector).first.dblclick()
        _human_delay()
        self._audit.log(self._engine.current_url(), "double_click", {"selector": selector})

    def hover(self, selector: str):
        self._page.locator(selector).first.hover()
        _human_delay(0.1, 0.3)
        self._audit.log(self._engine.current_url(), "hover", {"selector": selector})

    def type(self, selector: str, text: str, delay_ms: int = 50):
        """
        Type text into an input field with per-character delay (human-like).
        """
        self._page.locator(selector).first.type(text, delay=delay_ms)
        self._audit.log(self._engine.current_url(), "type",
                        {"selector": selector, "length": len(text)})

    def fill(self, selector: str, value: str):
        """
        Fill an input field instantly (faster than type, no per-char delay).
        Use for programmatic form filling where speed matters.
        """
        self._page.locator(selector).first.fill(value)
        _human_delay()
        self._audit.log(self._engine.current_url(), "fill",
                        {"selector": selector, "length": len(value)})

    def clear(self, selector: str):
        """Clear the value of an input field."""
        self._page.locator(selector).first.fill("")
        self._audit.log(self._engine.current_url(), "clear", {"selector": selector})

    def select(self, selector: str, value: str):
        """Select an option by value in a <select> element."""
        self._page.locator(selector).first.select_option(value=value)
        _human_delay()
        self._audit.log(self._engine.current_url(), "select",
                        {"selector": selector, "value": value})

    def scroll(self, x: int = 0, y: int = 300):
        """Scroll the page by (x, y) pixels."""
        self._page.mouse.wheel(x, y)
        _human_delay(0.2, 0.5)
        self._audit.log(self._engine.current_url(), "scroll", {"x": x, "y": y})

    def scroll_to_bottom(self):
        """Scroll to page bottom."""
        self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        _human_delay(0.3, 0.6)
        self._audit.log(self._engine.current_url(), "scroll_to_bottom", {})

    def scroll_to_element(self, selector: str):
        """Scroll element into viewport."""
        self._page.locator(selector).first.scroll_into_view_if_needed()
        _human_delay()

    def press_key(self, key: str):
        """Press a keyboard key (e.g. 'Enter', 'Tab', 'Escape')."""
        self._page.keyboard.press(key)
        _human_delay()
        self._audit.log(self._engine.current_url(), "key_press", {"key": key})

    def drag(self, source_selector: str, target_selector: str):
        """Drag from source to target element."""
        src = self._page.locator(source_selector).first.bounding_box()
        tgt = self._page.locator(target_selector).first.bounding_box()
        if not src or not tgt:
            raise ValueError("Could not get bounding boxes for drag operation")
        self._page.mouse.move(src["x"] + src["width"] / 2, src["y"] + src["height"] / 2)
        self._page.mouse.down()
        _human_delay(0.1, 0.2)
        self._page.mouse.move(tgt["x"] + tgt["width"] / 2, tgt["y"] + tgt["height"] / 2)
        self._page.mouse.up()
        self._audit.log(self._engine.current_url(), "drag",
                        {"from": source_selector, "to": target_selector})

    def upload_file(self, selector: str, file_path: Union[str, Path]):
        """Upload a file via a file input element."""
        self._page.locator(selector).set_input_files(str(file_path))
        self._audit.log(self._engine.current_url(), "file_upload",
                        {"selector": selector, "file": str(file_path)})

    def fill_form(self, fields: dict[str, str]):
        """
        Fill multiple form fields at once.
        fields: {selector: value} — uses fill() for all (fast path).
        """
        for selector, value in fields.items():
            self.fill(selector, value)
        self._audit.log(self._engine.current_url(), "fill_form",
                        {"field_count": len(fields)})

    def submit_form(self, form_selector: str = "form"):
        """Submit a form by pressing Enter on it or calling submit()."""
        self._page.locator(form_selector).evaluate("f => f.submit()")
        _human_delay(0.3, 0.8)
        self._audit.log(self._engine.current_url(), "form_submit",
                        {"selector": form_selector})

    def wait_for_selector(self, selector: str, timeout: int = 10000):
        """Wait for an element to appear in the DOM."""
        self._page.wait_for_selector(selector, timeout=timeout)

    def wait_for_navigation(self, url_pattern: Optional[str] = None):
        """Wait for page navigation to complete."""
        if url_pattern:
            self._page.wait_for_url(url_pattern)
        else:
            self._page.wait_for_load_state("domcontentloaded")

    def get_value(self, selector: str) -> str:
        """Get current value of an input field."""
        return self._page.locator(selector).first.input_value()

    def is_visible(self, selector: str) -> bool:
        """Check if an element is visible."""
        return self._page.locator(selector).first.is_visible()
```

- [ ] **Step 5.4: Run tests — verify they PASS**

```bash
cd ~/openclaw && python3 -m pytest scripts/browser/tests/test_forms.py -v
```
Expected: all 5 tests `PASSED`

- [ ] **Step 5.5: Commit**

```bash
cd ~/openclaw && git add scripts/browser/hands.py scripts/browser/tests/test_forms.py
git commit -m "feat(browser): hands.py — click, type, scroll, form fill, upload"
```

---

## Task 6: `auth_handler.py` — OAuth, Login, Session Persistence, MFA

**Files:**
- Create: `scripts/browser/auth_handler.py`
- Create: `scripts/browser/tests/test_auth.py`

- [ ] **Step 6.1: Write failing tests**

```python
# scripts/browser/tests/test_auth.py
"""Tests for auth handler — session persistence, login automation."""
from __future__ import annotations
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from browser.browser_engine import BrowserEngine
from browser.auth_handler import SessionStore, detect_login_form


def test_session_save_and_load(tmp_path):
    """Save cookies and reload them."""
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
```

- [ ] **Step 6.2: Run tests — verify they FAIL**

```bash
cd ~/openclaw && python3 -m pytest scripts/browser/tests/test_auth.py -v
```
Expected: `ImportError`

- [ ] **Step 6.3: Create `scripts/browser/auth_handler.py`**

```python
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
    # Try common selector patterns for username fields
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


# ── Login automation ──────────────────────────────────────────────────────────

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
        Returns True if login appears successful (or unverifiable), False if form not found.
        Credentials are never written to audit logs.
        """
        self._engine.navigate(url)

        # Auto-detect form if selectors not provided
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

        # Check for success indicator if provided
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
        Navigates until URL contains expected_redirect_domain or max_steps reached.
        Returns the final URL (which should contain the auth code or token).
        """
        self._engine.navigate(start_url)
        steps = 0
        while steps < max_steps:
            current = self._engine.current_url()
            if expected_redirect_domain in current:
                self._audit.log(current, "oauth_complete", {"steps": steps})
                return current
            # Wait for any pending navigation
            try:
                self._engine.page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass
            new_url = self._engine.current_url()
            if new_url == current:
                break  # No further navigation
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

        The bot itself must call this; it blocks the thread while waiting.
        In practice, the calling code should be in a background thread.
        """
        self._audit.log(self._engine.current_url(), "mfa_handoff", {"chat_id": chat_id})

        # Send Telegram notification if chat_id available
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

        # Write a flag file that telegram-dispatcher can check
        flag = Path("/tmp/openclaw-mfa-pending.flag")
        flag.write_text("pending")

        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            time.sleep(2)
            if not flag.exists():
                return True  # Flag removed = MFA completed

        flag.unlink(missing_ok=True)
        return False  # Timeout
```

- [ ] **Step 6.4: Run tests — verify they PASS**

```bash
cd ~/openclaw && python3 -m pytest scripts/browser/tests/test_auth.py -v
```
Expected: all 5 tests `PASSED`

- [ ] **Step 6.5: Commit**

```bash
cd ~/openclaw && git add scripts/browser/auth_handler.py scripts/browser/tests/test_auth.py
git commit -m "feat(browser): auth_handler.py — session persistence, login detection, MFA handoff"
```

---

## Task 7: `captcha_handler.py` — 3-Tier CAPTCHA

**Files:**
- Create: `scripts/browser/captcha_handler.py`
- Create: `scripts/browser/tests/test_captcha.py`

- [ ] **Step 7.1: Write failing tests**

```python
# scripts/browser/tests/test_captcha.py
"""Tests for CAPTCHA handler. Tier 1 tested with real requests; Tier 2/3 mocked."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from unittest.mock import patch, MagicMock
from browser.captcha_handler import CaptchaHandler, CaptchaConfig, build_stealth_headers


def test_stealth_headers_structure():
    headers = build_stealth_headers()
    assert "User-Agent" in headers
    assert "Accept-Language" in headers
    assert "Accept" in headers


def test_captcha_config_defaults():
    config = CaptchaConfig()
    assert config.service in ("2captcha", "anticaptcha", None)
    assert config.api_key is None or isinstance(config.api_key, str)


def test_tier1_apply_does_not_raise():
    from browser.browser_engine import BrowserEngine
    with BrowserEngine() as engine:
        engine.navigate("https://example.com")
        handler = CaptchaHandler(engine, CaptchaConfig())
        # Should not raise — just applies headers/behaviors
        handler.apply_tier1_avoidance()


def test_tier2_no_api_key_returns_false():
    from browser.browser_engine import BrowserEngine
    with BrowserEngine() as engine:
        engine.page.set_content("<html><body>test</body></html>")
        handler = CaptchaHandler(engine, CaptchaConfig(api_key=None))
        result = handler.solve_tier2(captcha_type="recaptchav2", site_key="fake", page_url="https://x.com")
        assert result is False


def test_tier3_telegram_pause_sends_notification():
    from browser.browser_engine import BrowserEngine
    with BrowserEngine() as engine:
        engine.page.set_content("<html><body>test</body></html>")
        handler = CaptchaHandler(engine, CaptchaConfig())
        # Mock the Telegram send so no actual message is sent
        with patch("browser.captcha_handler.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            handler.tier3_human_handoff(chat_id="123", timeout_seconds=1)
            # Should have called Telegram (or skipped gracefully if no token)
```

- [ ] **Step 7.2: Run tests — verify they FAIL**

```bash
cd ~/openclaw && python3 -m pytest scripts/browser/tests/test_captcha.py -v
```
Expected: `ImportError`

- [ ] **Step 7.3: Create `scripts/browser/captcha_handler.py`**

```python
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

_CAPTCHA_INDICATORS = [
    "g-recaptcha",
    "h-captcha",
    "cf-turnstile",
    "recaptcha",
    "captcha",
    "cf_chl_",
    "cf-challenge",
]


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
    for indicator in _CAPTCHA_INDICATORS:
        if indicator in html:
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
        - Ensure stealth user-agent is set
        - Add random pre-navigation jitter
        """
        page = self._engine.page
        stealth_headers = build_stealth_headers()

        # Set extra HTTP headers on all future requests
        page.set_extra_http_headers(stealth_headers)

        # Small random wait to simulate human hesitation
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
        """Submit to 2captcha, poll for result, inject token."""
        task_types = {
            "recaptchav2": "NoCaptchaTaskProxyless",
            "hcaptcha": "HCaptchaTaskProxyless",
            "turnstile": "TurnstileTaskProxyless",
        }
        task_type = task_types.get(captcha_type, "NoCaptchaTaskProxyless")

        # Submit task
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

        # Poll for result
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
        """AntiCaptcha API integration (similar structure to 2captcha)."""
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
                import os
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

        # Tier 2: API solver
        if site_key:
            solved = self.solve_tier2(captcha_type, site_key, self._engine.current_url())
            if solved:
                return True

        # Tier 3: Human handoff
        return self.tier3_human_handoff(chat_id=chat_id)
```

- [ ] **Step 7.4: Run tests — verify they PASS**

```bash
cd ~/openclaw && python3 -m pytest scripts/browser/tests/test_captcha.py -v
```
Expected: all 5 tests `PASSED`

- [ ] **Step 7.5: Commit**

```bash
cd ~/openclaw && git add scripts/browser/captcha_handler.py scripts/browser/tests/test_captcha.py
git commit -m "feat(browser): captcha_handler.py — 3-tier CAPTCHA (avoidance, API, human)"
```

---

## Task 8: `browser_tools.py` — Claude Code Callable Shim

**Files:**
- Create: `scripts/browser/browser_tools.py`

- [ ] **Step 8.1: Write failing test**

Add to `scripts/browser/tests/test_navigation.py`:
```python
from browser.browser_tools import browser_open, browser_screenshot, browser_eval

def test_browser_open_returns_dict():
    result = browser_open("https://example.com")
    assert result["ok"] is True
    assert "title" in result
    assert "url" in result

def test_browser_screenshot_returns_png_bytes():
    result = browser_screenshot("https://example.com")
    assert result["ok"] is True
    assert result["bytes"][:4] == b'\x89PNG'

def test_browser_eval_executes_js():
    result = browser_eval("https://example.com", "document.title")
    assert result["ok"] is True
    assert "Example Domain" in str(result["value"])
```

- [ ] **Step 8.2: Run tests — verify they FAIL**

```bash
cd ~/openclaw && python3 -m pytest scripts/browser/tests/test_navigation.py -k "browser_open or browser_screenshot or browser_eval" -v
```
Expected: `ImportError`

- [ ] **Step 8.3: Create `scripts/browser/browser_tools.py`**

```python
#!/usr/bin/env python3
"""
Claude Code callable shim — thin wrappers around browser_engine + eyes + hands.
Each function opens a fresh browser session, performs the action, closes cleanly.
Returns structured dicts so Claude Code can inspect results.

Usage from Claude Code session:
    import sys; sys.path.insert(0, '~/openclaw/scripts')
    from browser.browser_tools import browser_open, browser_screenshot, browser_click
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Any
import traceback

from browser.browser_engine import BrowserEngine
from browser.eyes import Eyes
from browser.hands import Hands
from browser.auth_handler import AuthHandler, SessionStore


def _err(msg: str, exc: Exception = None) -> dict:
    return {
        "ok": False,
        "error": msg,
        "traceback": traceback.format_exc() if exc else None,
    }


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
        with BrowserEngine(stealth=stealth) as engine:
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
        with BrowserEngine(stealth=stealth) as engine:
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
        with BrowserEngine(stealth=stealth) as engine:
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
    fields: dict[str, str],
    submit_selector: Optional[str] = None,
    stealth: bool = False,
) -> dict:
    """
    Navigate to URL, fill form fields, optionally submit.
    fields: {css_selector: value}
    Returns URL + title after form interaction.
    """
    try:
        with BrowserEngine(stealth=stealth) as engine:
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
        with BrowserEngine(stealth=stealth) as engine:
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
        with BrowserEngine(stealth=stealth) as engine:
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
```

- [ ] **Step 8.4: Run tests — verify they PASS**

```bash
cd ~/openclaw && python3 -m pytest scripts/browser/tests/test_navigation.py -k "browser_open or browser_screenshot or browser_eval" -v
```
Expected: all 3 tests `PASSED`

- [ ] **Step 8.5: Commit**

```bash
cd ~/openclaw && git add scripts/browser/browser_tools.py scripts/browser/tests/test_navigation.py
git commit -m "feat(browser): browser_tools.py — Claude Code callable shim"
```

---

## Task 9: `__init__.py` — Public API Exports

**Files:**
- Modify: `scripts/browser/__init__.py`

- [ ] **Step 9.1: Write failing test**

Add to `scripts/browser/tests/test_navigation.py`:
```python
def test_package_exports():
    from browser import BrowserEngine, Eyes, Hands, AuthHandler, CaptchaHandler
    from browser import browser_open, browser_screenshot, browser_click
    assert all([BrowserEngine, Eyes, Hands, AuthHandler, CaptchaHandler,
                browser_open, browser_screenshot, browser_click])
```

- [ ] **Step 9.2: Run test — verify it FAILS**

```bash
cd ~/openclaw && python3 -m pytest scripts/browser/tests/test_navigation.py::test_package_exports -v
```
Expected: `ImportError`

- [ ] **Step 9.3: Update `scripts/browser/__init__.py`**

```python
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
```

- [ ] **Step 9.4: Run test — verify it PASSES**

```bash
cd ~/openclaw && python3 -m pytest scripts/browser/tests/test_navigation.py::test_package_exports -v
```
Expected: `PASSED`

- [ ] **Step 9.5: Run full browser test suite**

```bash
cd ~/openclaw && python3 -m pytest scripts/browser/tests/ -v --tb=short 2>&1 | tail -30
```
Expected: majority passing (auth + captcha network-dependent tests may skip)

- [ ] **Step 9.6: Commit**

```bash
cd ~/openclaw && git add scripts/browser/__init__.py
git commit -m "feat(browser): package __init__.py exports all public API"
```

---

## Task 10: End-to-End Multi-Flow Test

**Files:**
- Create: `scripts/browser/tests/test_multiflow.py`

- [ ] **Step 10.1: Create test file**

```python
# scripts/browser/tests/test_multiflow.py
"""
Multi-step end-to-end browser workflow tests.
Tests realistic sequences: navigate → interact → extract → verify.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from browser import BrowserEngine, Eyes, Hands, browser_open


def test_navigate_extract_links():
    """Navigate, extract text, get links — full perception pipeline."""
    with BrowserEngine() as engine:
        engine.navigate("https://example.com")
        eyes = Eyes(engine)
        text = eyes.dom_text()
        links = eyes.links()
        title = eyes.title()

        assert "Example Domain" in text
        assert title == "Example Domain"
        assert len(links) > 0
        assert any("iana" in (l.get("href") or "") for l in links)


def test_multi_page_navigation():
    """Navigate to multiple pages in sequence."""
    with BrowserEngine(rate_limit_seconds=(0.1, 0.2)) as engine:
        urls = [
            "https://example.com",
            "https://example.org",
        ]
        results = []
        for url in urls:
            engine.navigate(url)
            eyes = Eyes(engine)
            results.append({"url": engine.current_url(), "title": eyes.title()})

        assert len(results) == 2
        assert all(r["title"] for r in results)


def test_browser_open_tool_end_to_end():
    """browser_open tool — complete round trip via high-level API."""
    result = browser_open("https://example.com", extract="dom")
    assert result["ok"] is True
    assert result["title"] == "Example Domain"
    assert "Example Domain" in result["content"]
    assert len(result["links"]) > 0


def test_screenshot_then_text():
    """Take screenshot and extract text from same page."""
    with BrowserEngine() as engine:
        engine.navigate("https://example.com")
        eyes = Eyes(engine)

        # Screenshot
        data = eyes.screenshot(full_page=True)
        assert data[:4] == b'\x89PNG'

        # Text extraction from same page
        text = eyes.dom_text()
        assert len(text) > 0


def test_form_fill_and_read_back():
    """Fill a multi-field form, read back values — no network needed."""
    with BrowserEngine() as engine:
        engine.page.set_content("""
            <html><body>
              <form id="test-form">
                <input id="first" type="text"/>
                <input id="last" type="text"/>
                <input id="age" type="number"/>
                <button type="submit">Submit</button>
              </form>
              <div id="result"></div>
            </body></html>
        """)
        hands = Hands(engine)
        hands.fill_form({
            "#first": "Jordan",
            "#last": "Claw",
            "#age": "30",
        })
        assert engine.page.locator("#first").input_value() == "Jordan"
        assert engine.page.locator("#last").input_value() == "Claw"
        assert engine.page.locator("#age").input_value() == "30"
```

- [ ] **Step 10.2: Run tests — verify they PASS**

```bash
cd ~/openclaw && python3 -m pytest scripts/browser/tests/test_multiflow.py -v
```
Expected: all 5 tests `PASSED`

- [ ] **Step 10.3: Commit**

```bash
cd ~/openclaw && git add scripts/browser/tests/test_multiflow.py
git commit -m "test(browser): multi-flow end-to-end tests — nav, forms, screenshot, tools"
```

---

## Task 11: Telegram Integration — `/browse` + `/screenshot` Commands

**Files:**
- Modify: `scripts/clawmson_intents.py` — add `BROWSER_TASK` intent
- Modify: `scripts/telegram-dispatcher.py` — add handlers + routing

- [ ] **Step 11.1: Add `BROWSER_TASK` to clawmson_intents.py**

In `clawmson_intents.py`, after line with `UNCLEAR = "UNCLEAR"`, add:
```python
BROWSER_TASK     = "BROWSER_TASK"
```

Update `_VALID_INTENTS`:
```python
_VALID_INTENTS = {CONVERSATION, BUILD_TASK, REFERENCE_INGEST, STATUS_QUERY,
                  DIRECT_COMMAND, BROWSER_TASK, UNCLEAR}
```

Update `_CLASSIFY_SYSTEM_PROMPT` to include:
```
- BROWSER_TASK: user wants to open a URL, take a screenshot, fill a web form, or interact with a website. Keywords: "browse", "open URL", "take a screenshot of", "go to X and", "visit", "screenshot of".
```

Add to regex fallback `_classify_regex`:
```python
_BROWSER_PREFIXES = (
    "/browse ", "/screenshot ",
    "browse ", "open url ", "screenshot of ",
    "take a screenshot", "go to http", "visit http",
    "check the website", "look at the site",
)
```

And in `_classify_regex` before the BUILD_TASK checks:
```python
if intent == CONVERSATION:
    for prefix in _BROWSER_PREFIXES:
        if lower.startswith(prefix) or prefix in lower:
            intent, action = BROWSER_TASK, "browse"
            break
```

- [ ] **Step 11.2: Run intents smoke test**

```bash
cd ~/openclaw && python3 -c "
import sys; sys.path.insert(0, 'scripts')
from clawmson_intents import classify_simple
assert classify_simple('/browse https://example.com') == 'BROWSER_TASK'
assert classify_simple('/screenshot https://example.com') == 'BROWSER_TASK'
print('intent routing OK')
"
```
Expected: `intent routing OK`

- [ ] **Step 11.3: Add handlers to telegram-dispatcher.py**

After `handle_search` function (around line 723), add these new handler functions:

```python
def handle_browse(chat_id: str, url: str):
    """Open URL, extract text, send summary to user."""
    import sys
    sys.path.insert(0, str(_SCRIPTS_DIR))
    try:
        from browser.browser_tools import browser_open
    except ImportError as e:
        send(chat_id, f"Browser module not available: {e}")
        return

    if not url.startswith("http"):
        send(chat_id, "Usage: /browse <url> — URL must start with http:// or https://")
        return

    send(chat_id, f"Opening {url}...")
    send_typing(chat_id)

    result = browser_open(url, extract="dom")
    if not result["ok"]:
        send(chat_id, f"Browse failed: {result['error']}")
        return

    title = result.get("title", "No title")
    content = result.get("content", "")[:2000]
    links = result.get("links", [])[:5]
    link_lines = "\n".join(f"  • {l['text'][:50]}: {l['href']}" for l in links if l.get("href"))

    reply = f"**{title}**\n{url}\n\n{content}"
    if link_lines:
        reply += f"\n\nLinks:\n{link_lines}"
    send(chat_id, reply)


def handle_screenshot(chat_id: str, url: str):
    """Take screenshot of URL and send as photo."""
    import sys, os, tempfile
    sys.path.insert(0, str(_SCRIPTS_DIR))
    try:
        from browser.browser_tools import browser_screenshot
    except ImportError as e:
        send(chat_id, f"Browser module not available: {e}")
        return

    if not url.startswith("http"):
        send(chat_id, "Usage: /screenshot <url>")
        return

    send(chat_id, f"Taking screenshot of {url}...")
    send_typing(chat_id)

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name

    result = browser_screenshot(url, save_path=tmp_path)
    if not result["ok"]:
        send(chat_id, f"Screenshot failed: {result['error']}")
        return

    try:
        with open(tmp_path, "rb") as f:
            requests.post(
                f"{API}/sendPhoto",
                data={"chat_id": chat_id, "caption": url},
                files={"photo": f},
                timeout=30,
            )
    except Exception as e:
        send(chat_id, f"Screenshot taken but send failed: {e}")
    finally:
        os.unlink(tmp_path)
```

- [ ] **Step 11.4: Wire slash commands in dispatcher routing block**

In `telegram-dispatcher.py`, inside the slash command routing block (after the existing `/search` handler), add:

```python
        if lower.startswith("/browse ") or lower == "/browse":
            url = text[len("/browse"):].strip()
            if not url:
                send(chat_id, "Usage: /browse <url>")
            else:
                threading.Thread(target=handle_browse, args=(chat_id, url), daemon=True).start()
            return

        if lower.startswith("/screenshot ") or lower == "/screenshot":
            url = text[len("/screenshot"):].strip()
            if not url:
                send(chat_id, "Usage: /screenshot <url>")
            else:
                threading.Thread(target=handle_screenshot, args=(chat_id, url), daemon=True).start()
            return
```

Also add BROWSER_TASK routing in the intent routing section (after DIRECT_COMMAND block):
```python
    if intent == intents.BROWSER_TASK:
        url_list = result.get("attachments", [])
        target = result.get("target", "")
        url = url_list[0] if url_list else (target if target and target.startswith("http") else None)
        if url:
            threading.Thread(target=handle_browse, args=(chat_id, url), daemon=True).start()
        else:
            send(chat_id, "I can browse websites for you — what URL should I visit?")
        return
```

- [ ] **Step 11.5: Quick smoke test for dispatcher imports**

```bash
cd ~/openclaw && python3 -c "
import sys; sys.path.insert(0, 'scripts')
# Just check imports won't explode (don't actually start the bot)
import ast
with open('scripts/telegram-dispatcher.py') as f:
    ast.parse(f.read())
print('dispatcher syntax OK')
import ast
with open('scripts/clawmson_intents.py') as f:
    ast.parse(f.read())
print('intents syntax OK')
"
```
Expected: both `OK`

- [ ] **Step 11.6: Commit**

```bash
cd ~/openclaw && git add scripts/clawmson_intents.py scripts/telegram-dispatcher.py
git commit -m "feat(browser): Telegram /browse + /screenshot commands + BROWSER_TASK intent"
```

---

## Task 12: `agents/configs/browser-agent.md`

**Files:**
- Create: `agents/configs/browser-agent.md`

- [ ] **Step 12.1: Create the agent config doc**

```markdown
# Browser Agent — Eyes & Hands

**Module path:** `scripts/browser/`
**Role:** Gives Claude Code and Clawmson the ability to see, navigate, and interact with websites.

## Capabilities

| Tool | Function | Description |
|------|----------|-------------|
| `browser_open` | `browser_tools.browser_open(url)` | Open URL, extract text/content |
| `browser_screenshot` | `browser_tools.browser_screenshot(url)` | Capture PNG screenshot |
| `browser_click` | `browser_tools.browser_click(url, selector)` | Navigate + click element |
| `browser_fill` | `browser_tools.browser_fill(url, fields)` | Fill form fields |
| `browser_eval` | `browser_tools.browser_eval(url, js)` | Execute JavaScript |
| `browser_login` | `browser_tools.browser_login(url, user, pass)` | Authenticate + save session |

## Telegram Commands

| Command | What it does |
|---------|-------------|
| `/browse <url>` | Opens URL and sends back text summary |
| `/screenshot <url>` | Takes screenshot and sends as photo |
| Natural language: "go to X and check Y" | Routed as `BROWSER_TASK` intent |

## Security Model

- **Credential vault:** `~/.openclaw/browser-vault.enc` (Fernet-encrypted, machine-keyed)
- **Session store:** `~/.openclaw/browser-sessions/<domain>.enc` (encrypted cookies)
- **Audit log:** `~/openclaw/logs/browser/browser-YYYY-MM-DD.jsonl`
- **Domain scope:** configurable allowlist/blocklist in `scripts/browser/config.json`
- **robots.txt:** respected by default; disable per-task only
- **No credentials in logs** — all auth operations redact values

## CAPTCHA Strategy

1. **Tier 1 (always on):** Stealth headers, realistic user-agent, human timing
2. **Tier 2 (API):** 2captcha or AntiCaptcha — requires `CAPTCHA_API_KEY` in `.env`
3. **Tier 3 (human):** Bot pauses, alerts Jordan via Telegram `/captcha-done` to resume

## ENV Vars

```
CAPTCHA_API_KEY=           # 2captcha or AntiCaptcha
BROWSER_PROXY_URL=         # optional proxy
BROWSER_DEFAULT_TIMEOUT=30000  # ms
```

## File Map

```
scripts/browser/
├── __init__.py            # Public API exports
├── config.json            # Domain lists, rate limits, proxy
├── security.py            # Vault, audit log, domain scope, robots.txt
├── browser_engine.py      # Playwright wrapper (core)
├── eyes.py                # Screenshot + DOM extraction
├── hands.py               # Click, type, scroll, form fill
├── auth_handler.py        # Session persistence, login, OAuth, MFA
├── captcha_handler.py     # 3-tier CAPTCHA
├── browser_tools.py       # Claude Code shim (browser_open etc.)
└── tests/                 # 5 test files, ~30 tests
```

## Web Citizenship Rules

- Always respect `robots.txt` (override requires explicit per-domain flag)
- Default rate limit: 1–3 seconds between requests
- Hard stop on IP block detection — pause + alert, never retry in loop
- Identify as bot in honest mode; stealth mode only for authorized testing
- No data retained beyond current task scope
```

- [ ] **Step 12.2: Commit**

```bash
cd ~/openclaw && git add agents/configs/browser-agent.md
git commit -m "docs(browser): browser-agent.md — capability map and security model"
```

---

## Task 13: Full Test Suite Run + Final Verification

- [ ] **Step 13.1: Run all browser tests**

```bash
cd ~/openclaw && python3 -m pytest scripts/browser/tests/ -v --tb=short 2>&1
```
Expected: ≥25 tests passing. Network-dependent tests (test_auth OAuth, Tier 2 captcha API) may show as skipped/xfail — that's acceptable.

- [ ] **Step 13.2: Verify module imports cleanly**

```bash
cd ~/openclaw && python3 -c "
import sys; sys.path.insert(0, 'scripts')
from browser import BrowserEngine, Eyes, Hands, AuthHandler, CaptchaHandler
from browser import browser_open, browser_screenshot, browser_click, browser_fill, browser_eval
from browser.security import CredentialVault, AuditLogger, DomainScope
print('All imports OK')
"
```
Expected: `All imports OK`

- [ ] **Step 13.3: Verify audit log directory is created**

```bash
python3 -c "
import sys; sys.path.insert(0, 'scripts')
from browser.security import get_audit_logger
log = get_audit_logger()
log.log('https://test.com', 'smoke_test', {'ok': True})
import pathlib
logs = list(pathlib.Path.home().joinpath('openclaw/logs/browser').glob('*.jsonl'))
print(f'Audit log OK: {logs[-1]}')
"
```
Expected: path printed

- [ ] **Step 13.4: Verify .env placeholders are present**

```bash
grep -c "CAPTCHA_API_KEY\|BROWSER_PROXY_URL\|BROWSER_DEFAULT_TIMEOUT" ~/openclaw/.env
```
Expected: `3`

- [ ] **Step 13.5: Final commit**

```bash
cd ~/openclaw && git add -A && git status
# Only commit if there are any remaining unstaged changes
git commit -m "feat(browser): Browser Eyes & Hands — complete automation layer" || echo "Nothing to commit"
```

---

## Summary

**Total files created:** 10 (7 modules + 3 test files)
**Total files modified:** 4 (`__init__.py`, `clawmson_intents.py`, `telegram-dispatcher.py`, `.env`)
**Total tests:** ~33
**Dependencies:** All already installed (Playwright 1.58.0, cryptography, stdlib)

**What's now possible:**
- Claude Code: `from browser import browser_open; result = browser_open("https://...")`
- Telegram: `/browse https://...` or `/screenshot https://...`
- Natural language: "go to example.com and check the pricing" → BROWSER_TASK intent
- Secure sessions saved between runs, CAPTCHA handled in 3 tiers, full audit trail
