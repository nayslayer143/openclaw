#!/usr/bin/env python3
from __future__ import annotations
"""FTS5 full-text search across all Hermes memory layers."""

import sqlite3 as _sqlite3

# Probe FTS5 availability at module init
FTS5_AVAILABLE = False
_probe = _sqlite3.connect(":memory:")
try:
    _probe.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_check USING fts5(x)")
    FTS5_AVAILABLE = True
except Exception:
    pass
finally:
    _probe.close()
