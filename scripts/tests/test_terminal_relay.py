"""Tests for terminal-relay.py pure functions."""
import sys
from pathlib import Path

# Add scripts dir to path so we can import terminal-relay as a module
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestStripAnsi:
    """ANSI escape sequence removal."""
    pass


class TestRedactSecrets:
    """Secret/credential redaction."""
    pass


class TestDetectEventType:
    """Terminal output event classification."""
    pass


class TestExtractSummary:
    """One-line summary extraction from output."""
    pass
