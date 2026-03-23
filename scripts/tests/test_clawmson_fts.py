#!/usr/bin/env python3
"""Tests for FTS5 search module. All FTS tests require FTS5 support."""
from __future__ import annotations
import os
import sys
import unittest
from pathlib import Path

os.environ["CLAWMSON_DB_PATH"] = ":memory:"

_SCRIPTS = Path(__file__).parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import clawmson_db as db
db._init_db()

from clawmson_fts import FTS5_AVAILABLE
import clawmson_fts as fts


class TestFTSSchema(unittest.TestCase):
    @unittest.skipUnless(FTS5_AVAILABLE, "FTS5 not supported")
    def test_fts_tables_exist(self):
        """memory_fts and sessions tables exist after _init_db()."""
        with db._get_conn() as conn:
            all_names = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master"
            ).fetchall()}
        self.assertIn("memory_fts", all_names)
        self.assertIn("sessions", all_names)


if __name__ == "__main__":
    unittest.main()
