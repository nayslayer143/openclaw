"""Tests for terminal-relay.py pure functions."""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Import module with hyphen in name
_mod = importlib.import_module("terminal-relay")
strip_ansi = _mod.strip_ansi
redact_secrets = _mod.redact_secrets


class TestStripAnsi:
    """ANSI escape sequence removal."""

    def test_removes_color_codes(self):
        assert strip_ansi("\x1b[31mERROR\x1b[0m") == "ERROR"

    def test_removes_cursor_movement(self):
        assert strip_ansi("\x1b[2J\x1b[Hhello") == "hello"

    def test_removes_osc_sequences(self):
        assert strip_ansi("\x1b]0;title\x07text") == "text"

    def test_preserves_plain_text(self):
        assert strip_ansi("normal output here") == "normal output here"

    def test_handles_nested_sequences(self):
        raw = "\x1b[1m\x1b[31mBOLD RED\x1b[0m normal"
        assert strip_ansi(raw) == "BOLD RED normal"

    def test_handles_256_color(self):
        assert strip_ansi("\x1b[38;5;196mred\x1b[0m") == "red"


class TestRedactSecrets:
    """Secret/credential redaction."""

    def test_redacts_openai_key(self):
        assert "[REDACTED]" in redact_secrets("key is sk-abc123def456ghi789jkl012")

    def test_redacts_aws_key(self):
        assert "[REDACTED]" in redact_secrets("AKIAIOSFODNN7EXAMPLE")

    def test_redacts_bearer_token(self):
        assert "[REDACTED]" in redact_secrets("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.test")

    def test_redacts_jwt(self):
        assert "[REDACTED]" in redact_secrets("token=eyJhbGciOiJIUzI1NiJ9.payload.sig")

    def test_redacts_env_values(self):
        result = redact_secrets("using key my-super-secret-value-123", env_values=["my-super-secret-value-123"])
        assert "my-super-secret-value-123" not in result
        assert "[REDACTED]" in result

    def test_redacts_key_value_patterns(self):
        result = redact_secrets("GITHUB_SECRET_KEY=ghp_abc123xyz")
        assert "ghp_abc123xyz" not in result

    def test_preserves_normal_text(self):
        assert redact_secrets("normal log output") == "normal log output"

    def test_redacts_ssh_key_header(self):
        assert "[REDACTED]" in redact_secrets("-----BEGIN RSA PRIVATE KEY-----")

    def test_skips_short_env_values(self):
        result = redact_secrets("value is abc", env_values=["abc"])
        assert result == "value is abc"


class TestDetectEventType:
    """Terminal output event classification."""
    pass


class TestExtractSummary:
    """One-line summary extraction from output."""
    pass
