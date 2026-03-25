import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from browser.pool import BrowserPool


def test_pool_returns_engine():
    """Pool.get() returns a usable BrowserEngine."""
    pool = BrowserPool()
    try:
        engine = pool.get()
        assert engine.page is not None
        assert engine._browser is not None
    finally:
        pool.shutdown()


def test_pool_reuses_same_browser():
    """Calling get() twice returns the same engine (no re-launch)."""
    pool = BrowserPool()
    try:
        e1 = pool.get()
        browser_id_1 = id(e1._browser)
        e2 = pool.get()
        browser_id_2 = id(e2._browser)
        assert browser_id_1 == browser_id_2
    finally:
        pool.shutdown()


def test_pool_shutdown_closes_browser():
    """After shutdown(), the engine is gone."""
    pool = BrowserPool()
    engine = pool.get()
    assert engine._browser is not None
    pool.shutdown()
    assert pool._engine is None


def test_pool_get_after_shutdown_relaunches():
    """get() after shutdown() creates a fresh browser."""
    pool = BrowserPool()
    e1 = pool.get()
    pool.shutdown()
    e2 = pool.get()
    assert e2._browser is not None
    assert e2.page is not None
    pool.shutdown()


def test_pool_is_alive():
    """is_alive() reflects browser state."""
    pool = BrowserPool()
    assert not pool.is_alive()
    pool.get()
    assert pool.is_alive()
    pool.shutdown()
    assert not pool.is_alive()
