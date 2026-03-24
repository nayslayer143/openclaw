"""Tests for terminal-relay.py pure functions."""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Import module with hyphen in name
_mod = importlib.import_module("terminal-relay")
strip_ansi = _mod.strip_ansi
redact_secrets = _mod.redact_secrets
detect_event_type = _mod.detect_event_type
extract_summary = _mod.extract_summary


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

    def test_detects_traceback(self):
        output = "Traceback (most recent call last):\n  File 'x.py'\nValueError: bad"
        assert detect_event_type(output) == "error"

    def test_detects_error_prefix(self):
        assert detect_event_type("Error: connection refused") == "error"

    def test_detects_build_failure_syntax(self):
        assert detect_event_type("SyntaxError: invalid syntax") == "build_failure"

    def test_detects_build_failure_import(self):
        assert detect_event_type("ModuleNotFoundError: No module named 'foo'") == "build_failure"

    def test_detects_test_failure_pytest(self):
        output = "FAILED tests/test_foo.py::test_bar - AssertionError"
        assert detect_event_type(output) == "test_failure"

    def test_detects_test_failure_jest(self):
        assert detect_event_type("Tests:  2 failed, 3 passed") == "test_failure"

    def test_returns_none_for_clean_output(self):
        assert detect_event_type("Successfully installed package-1.0") is None

    def test_build_failure_takes_priority_over_error(self):
        output = "Error: SyntaxError: unexpected EOF"
        assert detect_event_type(output) == "build_failure"

    def test_test_failure_takes_priority_over_error(self):
        output = "FAILED test_x.py\nAssertionError: 1 != 2"
        assert detect_event_type(output) == "test_failure"


class TestExtractSummary:
    """One-line summary extraction from output."""

    def test_extracts_error_line(self):
        output = "running stuff\nmore stuff\nValueError: bad input"
        result = extract_summary(output, "error")
        assert "ValueError" in result

    def test_extracts_test_failure_line(self):
        output = "collecting...\nFAILED test_foo.py::test_bar"
        result = extract_summary(output, "test_failure")
        assert "FAILED" in result

    def test_truncates_long_summaries(self):
        output = "Error: " + "x" * 300
        result = extract_summary(output, "error")
        assert len(result) <= 200

    def test_handles_empty_output(self):
        assert extract_summary("", "error") == ""
