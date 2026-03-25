#!/usr/bin/env python3
"""
Pytest configuration for browser tests.
Ensures the module-level BrowserPool singleton is shut down after each test
so it does not leak Playwright state into subsequent tests.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest


@pytest.fixture(autouse=True)
def shutdown_default_pool():
    """Shut down the singleton pool after each test to prevent state leakage."""
    yield
    try:
        import browser.pool as pool_module
        if pool_module._default_pool is not None:
            pool_module._default_pool.shutdown()
            pool_module._default_pool = None
    except Exception:
        pass
