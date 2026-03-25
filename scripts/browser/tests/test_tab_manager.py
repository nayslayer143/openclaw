import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from browser.pool import BrowserPool
from browser.tab_manager import TabManager


@pytest.fixture
def pool_and_tabs():
    pool = BrowserPool()
    engine = pool.get()
    tm = TabManager(engine)
    yield tm, engine
    pool.shutdown()


def test_create_named_tab(pool_and_tabs):
    """Create a named tab and verify it exists."""
    tm, engine = pool_and_tabs
    page = tm.create("search")
    assert page is not None
    assert "search" in tm.list_tabs()


def test_get_tab_by_name(pool_and_tabs):
    """Retrieve a tab by name."""
    tm, engine = pool_and_tabs
    created = tm.create("news")
    retrieved = tm.get("news")
    assert created is retrieved


def test_get_nonexistent_returns_none(pool_and_tabs):
    """Getting a tab that doesn't exist returns None."""
    tm, engine = pool_and_tabs
    assert tm.get("ghost") is None


def test_switch_tab(pool_and_tabs):
    """Switch changes the active tab."""
    tm, engine = pool_and_tabs
    tm.create("tab-a")
    tm.create("tab-b")
    page_b = tm.switch("tab-b")
    assert tm.active_name() == "tab-b"
    page_a = tm.switch("tab-a")
    assert tm.active_name() == "tab-a"


def test_close_tab(pool_and_tabs):
    """Close removes the tab and it's no longer listed."""
    tm, engine = pool_and_tabs
    tm.create("temp")
    assert "temp" in tm.list_tabs()
    tm.close("temp")
    assert "temp" not in tm.list_tabs()


def test_close_active_tab_switches_to_another(pool_and_tabs):
    """Closing the active tab switches to another open tab."""
    tm, engine = pool_and_tabs
    tm.create("keep")
    tm.create("remove")
    tm.switch("remove")
    assert tm.active_name() == "remove"
    tm.close("remove")
    assert tm.active_name() != "remove"
    assert tm.active_name() is not None


def test_list_tabs(pool_and_tabs):
    """list_tabs returns all named tabs."""
    tm, engine = pool_and_tabs
    tm.create("alpha")
    tm.create("beta")
    tm.create("gamma")
    names = tm.list_tabs()
    assert "alpha" in names
    assert "beta" in names
    assert "gamma" in names


def test_tab_count(pool_and_tabs):
    """Count of tabs is accurate."""
    tm, engine = pool_and_tabs
    tm.create("one")
    tm.create("two")
    assert tm.count() == 2


def test_navigate_in_specific_tab(pool_and_tabs):
    """Navigate in a named tab without switching active."""
    tm, engine = pool_and_tabs
    page_a = tm.create("site-a")
    page_b = tm.create("site-b")
    page_a.goto("https://example.com", wait_until="domcontentloaded")
    page_b.goto("https://example.org", wait_until="domcontentloaded")
    assert "example.com" in page_a.url
    assert "example.org" in page_b.url


def test_close_all(pool_and_tabs):
    """close_all removes every tab."""
    tm, engine = pool_and_tabs
    tm.create("x")
    tm.create("y")
    tm.create("z")
    assert tm.count() == 3
    tm.close_all()
    assert tm.count() == 0
    assert tm.active_name() is None
