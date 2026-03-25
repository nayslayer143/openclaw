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
