import json
import sys
from pathlib import Path

# Add scripts/ to path for browser package imports
_SCRIPTS = Path(__file__).parent.parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

def test_config_exists_and_has_required_keys():
    config_path = Path(__file__).parent.parent / "config.json"
    assert config_path.exists(), "config.json must exist"
    config = json.loads(config_path.read_text())
    for key in ("allowed_domains", "blocked_domains", "rate_limit_seconds",
                "default_timeout_ms", "stealth_mode", "proxy_url"):
        assert key in config, f"config.json missing key: {key}"


# ── Security module tests ─────────────────────────────────────────────────────

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
    entry = json.loads(logs[0].read_text().strip())
    assert entry["url"] == "https://example.com"
    assert entry["action"] == "navigate"


# ── BrowserEngine tests ───────────────────────────────────────────────────────

import pytest
from browser.browser_engine import BrowserEngine


def test_engine_opens_and_closes():
    with BrowserEngine() as engine:
        assert engine.page is not None


def test_engine_navigate_returns_title():
    with BrowserEngine() as engine:
        title = engine.navigate("https://example.com")
        assert isinstance(title, str)


def test_engine_navigate_blocked_domain_raises():
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


# ── Eyes tests ────────────────────────────────────────────────────────────────

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


# ── browser_tools shim tests ──────────────────────────────────────────────────

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


def test_package_exports():
    from browser import BrowserEngine, Eyes, Hands, AuthHandler, CaptchaHandler
    from browser import browser_open, browser_screenshot, browser_click
    assert all([BrowserEngine, Eyes, Hands, AuthHandler, CaptchaHandler,
                browser_open, browser_screenshot, browser_click])
