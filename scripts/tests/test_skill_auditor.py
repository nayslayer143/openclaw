#!/usr/bin/env python3
"""Unit tests for skill/MCP security audit system."""
import sys
import os
import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

_SCRIPTS = Path(__file__).parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


class TestFinding(unittest.TestCase):
    def test_finding_fields(self):
        from security.scanner import Finding
        f = Finding(
            category="obfuscation",
            severity="CRITICAL",
            line_no=42,
            snippet="eval(user_input)",
            context="line 41\neval(user_input)\nline 43",
        )
        self.assertEqual(f.category, "obfuscation")
        self.assertEqual(f.severity, "CRITICAL")
        self.assertEqual(f.line_no, 42)
        self.assertIn("eval", f.snippet)


if __name__ == "__main__":
    unittest.main()
