# Browser Persistent Sessions & Multi-Tab Orchestration

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the launch-per-call BrowserEngine with a persistent singleton that stays alive across calls, and add a TabManager for named multi-tab orchestration — enabling parallel page work, session reuse, and massive speed improvement.

**Architecture:** A `BrowserPool` singleton manages one long-lived Playwright browser + context. `TabManager` creates/tracks/switches named tabs (Playwright Pages) within that context. Eyes and Hands accept an explicit `page` parameter so they can operate on any tab. The existing `browser_tools.py` shim switches from `with BrowserEngine()` to pool-based calls. localStorage/sessionStorage are persisted alongside cookies in `SessionStore`.

**Tech Stack:** Playwright 1.58.0 sync API, Python 3.9, cryptography (Fernet), existing test patterns (pytest, `page.set_content()` for local tests)

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `scripts/browser/pool.py` | **Create** | `BrowserPool` singleton — manages Playwright lifecycle, one browser + context alive across calls |
| `scripts/browser/tab_manager.py` | **Create** | `TabManager` — named tabs, create/switch/close/list, parallel page iteration |
| `scripts/browser/browser_engine.py` | **Modify** | Add `page` parameter to methods so they work with any tab, not just `self.page`. Keep context manager backward-compatible. |
| `scripts/browser/eyes.py` | **Modify** | Accept optional `page` override in constructor so Eyes can attach to any tab |
| `scripts/browser/hands.py` | **Modify** | Accept optional `page` override in constructor so Hands can attach to any tab |
| `scripts/browser/auth_handler.py` | **Modify** | `SessionStore.save()` persists localStorage/sessionStorage alongside cookies |
| `scripts/browser/browser_tools.py` | **Modify** | Switch from `with BrowserEngine()` to `BrowserPool.get()` for all 6 tool functions |
| `scripts/browser/__init__.py` | **Modify** | Export `BrowserPool`, `TabManager` |
| `scripts/browser/config.json` | **Modify** | Add `pool_max_idle_seconds` config key (default 300) |
| `scripts/browser/tests/test_pool.py` | **Create** | Tests for BrowserPool lifecycle |
| `scripts/browser/tests/test_tab_manager.py` | **Create** | Tests for TabManager create/switch/close/list |
| `scripts/browser/tests/test_persistent_session.py` | **Create** | Tests for localStorage persistence and session reuse |
| `scripts/browser/tests/test_tab_aware.py` | **Create** | Tests for Eyes/Hands operating on specific tabs |
| `scripts/browser/demo.py` | **Create** | Updated demo showcasing persistent pool + multi-tab |

---

## Task 1: BrowserPool Singleton

**Files:**
- Create: `scripts/browser/pool.py`
- Create: `scripts/browser/tests/test_pool.py`
- Modify: `scripts/browser/config.json`

The pool manages one Playwright browser that stays alive. It tracks idle time and auto-shuts after `pool_max_idle_seconds`. Thread-safe via a simple lock.

- [ ] **Step 1: Add config key**

In `scripts/browser/config.json`, add after `"vault_path"`:
```json
"pool_max_idle_seconds": 300,
```

- [ ] **Step 2: Write failing tests**

Create `scripts/browser/tests/test_pool.py`:
```python
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
```

- [ ] **Step 3: Run tests — verify they fail**

```bash
cd ~/openclaw && python3 -m pytest scripts/browser/tests/test_pool.py -v
```
Expected: `ModuleNotFoundError: No module named 'browser.pool'`

- [ ] **Step 4: Implement BrowserPool**

Create `scripts/browser/pool.py`:
```python
#!/usr/bin/env python3
"""
Persistent browser pool — keeps one Playwright browser alive across calls.
Replaces the launch-per-call pattern for massive speed improvement.

Usage:
    pool = BrowserPool()
    engine = pool.get()          # launches on first call, reuses after
    engine.navigate("https://...")
    pool.shutdown()              # explicit teardown (or auto-idle timeout)
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from browser.browser_engine import BrowserEngine, _load_config


class BrowserPool:
    """
    Singleton-style persistent browser manager.
    Keeps one BrowserEngine alive and reuses it across get() calls.
    Thread-safe. Auto-shutdown after idle timeout.
    """

    def __init__(
        self,
        headless: bool = True,
        stealth: bool = False,
        max_idle_seconds: Optional[int] = None,
        **engine_kwargs,
    ):
        config = _load_config()
        self._headless = headless
        self._stealth = stealth
        self._max_idle = max_idle_seconds or config.get("pool_max_idle_seconds", 300)
        self._engine_kwargs = engine_kwargs  # forwarded to BrowserEngine
        self._engine: Optional[BrowserEngine] = None
        self._lock = threading.Lock()
        self._last_access: float = 0.0
        self._idle_timer: Optional[threading.Timer] = None
        self._generation: int = 0  # incremented on each launch, prevents stale timer race

    def get(self) -> BrowserEngine:
        """
        Return the persistent BrowserEngine, launching if needed.
        Resets the idle timer on each access.
        """
        with self._lock:
            if self._engine is None or not self._is_browser_alive():
                self._launch()
            self._last_access = time.time()
            self._reset_idle_timer()
            return self._engine

    def shutdown(self):
        """Explicitly close the browser and free resources."""
        with self._lock:
            self._cancel_idle_timer()
            if self._engine is not None:
                self._engine.__exit__(None, None, None)
                self._engine = None

    def is_alive(self) -> bool:
        """Check if the pool has an active browser."""
        with self._lock:
            return self._engine is not None and self._is_browser_alive()

    def _launch(self):
        """Launch a fresh BrowserEngine (called under lock)."""
        self._generation += 1
        engine = BrowserEngine(
            headless=self._headless,
            stealth=self._stealth,
            **self._engine_kwargs,
        )
        engine.__enter__()
        self._engine = engine

    def _is_browser_alive(self) -> bool:
        """Check if the underlying browser is still connected."""
        try:
            return (
                self._engine is not None
                and self._engine._browser is not None
                and self._engine._browser.is_connected()
            )
        except Exception:
            return False

    def _reset_idle_timer(self):
        """Cancel existing timer and start a new idle countdown."""
        self._cancel_idle_timer()
        gen = self._generation  # capture current generation
        self._idle_timer = threading.Timer(
            self._max_idle, self._idle_shutdown, args=(gen,)
        )
        self._idle_timer.daemon = True
        self._idle_timer.start()

    def _cancel_idle_timer(self):
        if self._idle_timer is not None:
            self._idle_timer.cancel()
            self._idle_timer = None

    def _idle_shutdown(self, gen: int):
        """Called by idle timer — shutdown only if generation matches (prevents stale timer race)."""
        with self._lock:
            if gen != self._generation:
                return  # stale timer from a previous browser lifecycle
            elapsed = time.time() - self._last_access
            if elapsed >= self._max_idle:
                self._cancel_idle_timer()
                if self._engine is not None:
                    self._engine.__exit__(None, None, None)
                    self._engine = None


# ── Module-level default pool ────────────────────────────────────────────────

_default_pool: Optional[BrowserPool] = None
_pool_lock = threading.Lock()


def get_pool(**kwargs) -> BrowserPool:
    """Return the module-level default BrowserPool singleton."""
    global _default_pool
    with _pool_lock:
        if _default_pool is None:
            _default_pool = BrowserPool(**kwargs)
        return _default_pool
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
cd ~/openclaw && python3 -m pytest scripts/browser/tests/test_pool.py -v
```
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
cd ~/openclaw && git add scripts/browser/pool.py scripts/browser/tests/test_pool.py scripts/browser/config.json
git commit -m "feat(browser): BrowserPool — persistent browser singleton with idle timeout"
```

---

## Task 2: TabManager

**Files:**
- Create: `scripts/browser/tab_manager.py`
- Create: `scripts/browser/tests/test_tab_manager.py`

TabManager operates on a BrowserEngine's context. Named tabs, create/get/close/list/iterate.

- [ ] **Step 1: Write failing tests**

Create `scripts/browser/tests/test_tab_manager.py`:
```python
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
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd ~/openclaw && python3 -m pytest scripts/browser/tests/test_tab_manager.py -v
```
Expected: `ModuleNotFoundError: No module named 'browser.tab_manager'`

- [ ] **Step 3: Implement TabManager**

Create `scripts/browser/tab_manager.py`:
```python
#!/usr/bin/env python3
"""
Multi-tab orchestration — named tabs within a single browser context.

Usage:
    tabs = TabManager(engine)
    search = tabs.create("search")
    docs = tabs.create("docs")
    search.goto("https://google.com")
    docs.goto("https://docs.python.org")
    tabs.switch("search")  # set active tab
"""
from __future__ import annotations

from typing import Optional
from playwright.sync_api import Page

from browser.browser_engine import BrowserEngine
from browser.security import get_audit_logger


class TabManager:
    """
    Manages named tabs (Playwright Pages) within a BrowserEngine's context.
    Each tab is a real browser tab that can be independently navigated.
    """

    def __init__(self, engine: BrowserEngine):
        self._engine = engine
        self._context = engine._context
        self._audit = get_audit_logger()
        self._tabs: dict[str, Page] = {}
        self._active: Optional[str] = None

    def create(self, name: str) -> Page:
        """
        Create a new named tab. Returns the Playwright Page.
        If a tab with this name already exists, returns the existing one.
        """
        if name in self._tabs:
            return self._tabs[name]

        page = self._context.new_page()
        self._tabs[name] = page
        self._active = name
        self._audit.log("about:blank", "tab_create", {"name": name})
        return page

    def get(self, name: str) -> Optional[Page]:
        """Get a tab by name. Returns None if not found."""
        return self._tabs.get(name)

    def switch(self, name: str) -> Page:
        """
        Set the active tab. Returns the Page.
        Raises KeyError if tab doesn't exist.
        """
        if name not in self._tabs:
            raise KeyError(f"No tab named '{name}'")
        self._active = name
        page = self._tabs[name]
        page.bring_to_front()
        self._audit.log(page.url, "tab_switch", {"name": name})
        return page

    def close(self, name: str):
        """
        Close a named tab. If it's the active tab, switch to another.
        """
        if name not in self._tabs:
            return

        page = self._tabs.pop(name)
        was_active = self._active == name

        try:
            self._audit.log(page.url, "tab_close", {"name": name})
            page.close()
        except Exception:
            pass

        if was_active:
            if self._tabs:
                self._active = next(iter(self._tabs))
            else:
                self._active = None

    def list_tabs(self) -> list[str]:
        """Return list of all tab names."""
        return list(self._tabs.keys())

    def count(self) -> int:
        """Return number of open tabs."""
        return len(self._tabs)

    def active_name(self) -> Optional[str]:
        """Return the name of the active tab, or None."""
        return self._active

    def active_page(self) -> Optional[Page]:
        """Return the active tab's Page, or None."""
        if self._active:
            return self._tabs.get(self._active)
        return None

    def close_all(self):
        """Close all tabs."""
        for name in list(self._tabs.keys()):
            self.close(name)
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd ~/openclaw && python3 -m pytest scripts/browser/tests/test_tab_manager.py -v
```
Expected: 10 passed (9 original + 1 close_all)

- [ ] **Step 5: Commit**

```bash
cd ~/openclaw && git add scripts/browser/tab_manager.py scripts/browser/tests/test_tab_manager.py
git commit -m "feat(browser): TabManager — named multi-tab orchestration"
```

---

## Task 3: Make Eyes & Hands Tab-Aware

**Files:**
- Modify: `scripts/browser/eyes.py`
- Modify: `scripts/browser/hands.py`
- Create: `scripts/browser/tests/test_tab_aware.py`

Eyes and Hands currently hardcode `engine.page`. Add an optional `page` parameter so they can operate on any tab returned by TabManager.

- [ ] **Step 1: Write failing tests**

Create `scripts/browser/tests/test_tab_aware.py`:
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from browser.pool import BrowserPool
from browser.tab_manager import TabManager
from browser.eyes import Eyes
from browser.hands import Hands


def test_eyes_on_specific_tab():
    """Eyes can attach to a specific tab page."""
    pool = BrowserPool()
    try:
        engine = pool.get()
        tm = TabManager(engine)
        page_a = tm.create("a")
        page_b = tm.create("b")

        page_a.goto("https://example.com", wait_until="domcontentloaded")
        page_b.set_content("<html><body><h1>Tab B Content</h1></body></html>")

        eyes_a = Eyes(engine, page=page_a)
        eyes_b = Eyes(engine, page=page_b)

        assert "Example Domain" in eyes_a.title()
        assert "Tab B Content" in eyes_b.dom_text()
    finally:
        pool.shutdown()


def test_hands_on_specific_tab():
    """Hands can operate on a specific tab page."""
    pool = BrowserPool()
    try:
        engine = pool.get()
        tm = TabManager(engine)
        page = tm.create("form-tab")

        page.set_content("""
            <html><body>
              <input id="name" type="text"/>
              <button id="btn">Click</button>
            </body></html>
        """)

        hands = Hands(engine, page=page)
        hands.fill("#name", "Jordan")
        assert page.locator("#name").input_value() == "Jordan"
    finally:
        pool.shutdown()


def test_eyes_default_to_engine_page():
    """Eyes without explicit page still uses engine.page (backward compat)."""
    pool = BrowserPool()
    try:
        engine = pool.get()
        engine.navigate("https://example.com")
        eyes = Eyes(engine)
        assert "Example Domain" in eyes.title()
    finally:
        pool.shutdown()


def test_parallel_tab_work():
    """Navigate two tabs independently and read content from both."""
    pool = BrowserPool()
    try:
        engine = pool.get()
        tm = TabManager(engine)

        news = tm.create("news")
        docs = tm.create("docs")

        news.goto("https://example.com", wait_until="domcontentloaded")
        docs.set_content("<html><body><p>Documentation page</p></body></html>")

        eyes_news = Eyes(engine, page=news)
        eyes_docs = Eyes(engine, page=docs)

        assert "Example" in eyes_news.title()
        assert "Documentation page" in eyes_docs.dom_text()
    finally:
        pool.shutdown()
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd ~/openclaw && python3 -m pytest scripts/browser/tests/test_tab_aware.py -v
```
Expected: `TypeError: Eyes.__init__() got an unexpected keyword argument 'page'`

- [ ] **Step 3: Update Eyes to accept optional page**

In `scripts/browser/eyes.py`, change the `__init__` from:
```python
def __init__(self, engine: BrowserEngine):
    self._engine = engine
    self._audit = engine._audit
```
To:
```python
def __init__(self, engine: BrowserEngine, page: Optional[Page] = None):
    self._engine = engine
    self._page = page or engine.page
    self._audit = engine._audit
```

Add `from playwright.sync_api import Page` to imports. Add `from typing import Optional` if not present.

Then replace every `self._engine.page` reference inside Eyes methods with `self._page`. Specifically:
- `screenshot()`: `page = self._page` (line 42 currently reads `page = self._engine.page`)
- `dom_text()`: `page = self._page` (line 79 currently reads `page = self._engine.page`)
- `dom_html()`: `return self._page.locator(selector).inner_html()` (line 90 currently reads `self._engine.page`)
- `extract()`: `text = self._page.locator("body").inner_text()` (line 112)
- `links()`: `page = self._page` (line 122)
- `title()`: `return self._page.title()` (line 136)
- `meta()`: `page = self._page` (line 140)

- [ ] **Step 4: Update Hands to accept optional page**

In `scripts/browser/hands.py`, change the `__init__` from:
```python
def __init__(self, engine: BrowserEngine):
    self._engine = engine
    self._audit = engine._audit
    self._page = engine.page
```
To:
```python
def __init__(self, engine: BrowserEngine, page: Optional[Page] = None):
    self._engine = engine
    self._audit = engine._audit
    self._page = page or engine.page
```

Add `from playwright.sync_api import Page` to imports. The rest of Hands already uses `self._page` so no further changes needed.

- [ ] **Step 5: Run tests — verify they pass**

```bash
cd ~/openclaw && python3 -m pytest scripts/browser/tests/test_tab_aware.py -v
```
Expected: 4 passed

- [ ] **Step 6: Run full test suite — verify no regressions**

```bash
cd ~/openclaw && python3 -m pytest scripts/browser/tests/ -v
```
Expected: All tests pass (39 original + 5 pool + 10 tab_manager + 4 tab_aware = 58)

- [ ] **Step 7: Commit**

```bash
cd ~/openclaw && git add scripts/browser/eyes.py scripts/browser/hands.py scripts/browser/tests/test_tab_aware.py
git commit -m "feat(browser): make Eyes & Hands tab-aware with optional page parameter"
```

---

## Task 4: Persist localStorage & sessionStorage

**Files:**
- Modify: `scripts/browser/auth_handler.py` (SessionStore)
- Create: `scripts/browser/tests/test_persistent_session.py`

SessionStore already supports an `extra` dict field — we just need to verify that localStorage persistence works through it. No code changes to SessionStore needed; this task validates the pattern. Depends on BrowserPool from Task 1.

- [ ] **Step 1: Write failing tests**

Create `scripts/browser/tests/test_persistent_session.py`:
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from browser.pool import BrowserPool
from browser.auth_handler import SessionStore


def test_save_and_restore_storage(tmp_path):
    """Save localStorage data and restore it on a new page."""
    pool = BrowserPool()
    try:
        engine = pool.get()

        # Set some localStorage on a real page
        engine.navigate("https://example.com")
        engine.evaluate("localStorage.setItem('auth_token', 'test-jwt-123')")
        engine.evaluate("localStorage.setItem('user_id', '42')")

        # Save session with storage
        store = SessionStore(store_dir=tmp_path)
        cookies = engine.get_cookies()
        storage = engine.evaluate("""
            (() => {
                const data = {};
                for (let i = 0; i < localStorage.length; i++) {
                    const key = localStorage.key(i);
                    data[key] = localStorage.getItem(key);
                }
                return data;
            })()
        """)
        store.save("example.com", cookies, extra={"localStorage": storage})

        # Verify we can load it back
        loaded_extra = store.load_extra("example.com")
        assert loaded_extra is not None
        assert loaded_extra["localStorage"]["auth_token"] == "test-jwt-123"
        assert loaded_extra["localStorage"]["user_id"] == "42"
    finally:
        pool.shutdown()


def test_restore_storage_to_page(tmp_path):
    """Restore localStorage to a fresh page."""
    pool = BrowserPool()
    try:
        engine = pool.get()
        engine.navigate("https://example.com")

        # Pre-save some storage data
        store = SessionStore(store_dir=tmp_path)
        store.save("example.com", [], extra={
            "localStorage": {"theme": "dark", "lang": "en"}
        })

        # Load and inject into page
        extra = store.load_extra("example.com")
        if extra and "localStorage" in extra:
            for key, value in extra["localStorage"].items():
                engine.evaluate(
                    f"localStorage.setItem({repr(key)}, {repr(value)})"
                )

        # Verify
        theme = engine.evaluate("localStorage.getItem('theme')")
        assert theme == "dark"
    finally:
        pool.shutdown()
```

- [ ] **Step 2: Run tests — verify they pass**

These tests use the existing `SessionStore.save(extra=...)` and `load_extra()` APIs which already exist. They should pass as-is — this validates the feature works for storage persistence without code changes.

```bash
cd ~/openclaw && python3 -m pytest scripts/browser/tests/test_persistent_session.py -v
```
Expected: 2 passed (the storage save/restore mechanism is already built into SessionStore's `extra` field)

- [ ] **Step 3: Commit**

```bash
cd ~/openclaw && git add scripts/browser/tests/test_persistent_session.py
git commit -m "test(browser): verify localStorage persistence via SessionStore extra field"
```

---

## Task 5: Switch browser_tools.py to BrowserPool

**Files:**
- Modify: `scripts/browser/browser_tools.py`
- Modify: `scripts/browser/__init__.py`

This is the big integration — all 6 tool functions switch from `with BrowserEngine()` (launch/teardown per call) to `get_pool().get()` (reuse persistent browser). The pool auto-shuts after 5 minutes idle.

- [ ] **Step 1: Write failing test for pool-based tool**

Add to `scripts/browser/tests/test_pool.py`:
```python
def test_browser_tools_reuse_pool():
    """Two consecutive browser_open calls reuse the same browser."""
    from browser.browser_tools import browser_open, browser_shutdown
    from browser.pool import get_pool

    # First call — launches browser
    r1 = browser_open("https://example.com")
    assert r1["ok"] is True

    pool = get_pool()
    assert pool.is_alive(), "Pool should be alive after browser_open"

    # Second call — reuses browser (no re-launch)
    r2 = browser_open("https://example.org")
    assert r2["ok"] is True

    pool.shutdown()


def test_browser_shutdown_tool():
    """browser_shutdown() kills the pool and returns ok."""
    from browser.browser_tools import browser_open, browser_shutdown
    from browser.pool import get_pool

    browser_open("https://example.com")
    assert get_pool().is_alive()

    result = browser_shutdown()
    assert result["ok"] is True
    assert not get_pool().is_alive()
```

- [ ] **Step 2: Run test — verify it fails**

```bash
cd ~/openclaw && python3 -m pytest scripts/browser/tests/test_pool.py::test_browser_tools_reuse_pool -v
```
Expected: FAIL (browser_tools still uses `with BrowserEngine()`, pool won't be alive)

- [ ] **Step 3: Rewrite browser_tools.py to use pool**

Replace the contents of `scripts/browser/browser_tools.py` with:
```python
#!/usr/bin/env python3
"""
Claude Code callable shim — thin wrappers around browser pool + eyes + hands + auth.
Uses BrowserPool for persistent browser reuse across calls.
Returns structured dicts so Claude Code can inspect results.

Usage from Claude Code session:
    import sys; sys.path.insert(0, '/Users/nayslayer/openclaw/scripts')
    from browser.browser_tools import browser_open, browser_screenshot, browser_click
"""
from __future__ import annotations

import traceback
from pathlib import Path
from typing import Optional

from browser.pool import get_pool
from browser.eyes import Eyes
from browser.hands import Hands
from browser.auth_handler import AuthHandler, SessionStore


def _err(msg: str, exc: Exception = None) -> dict:
    return {
        "ok": False,
        "error": msg,
        "traceback": traceback.format_exc() if exc else None,
    }


def _get_engine(stealth: bool = False):
    """Get the persistent engine from the pool.
    Note: stealth is set at pool creation time. If the pool already exists,
    this parameter is ignored. Configure stealth via config.json or
    create a custom pool for stealth-specific workflows.
    """
    pool = get_pool(stealth=stealth)
    return pool.get()


def browser_open(
    url: str,
    wait_until: str = "domcontentloaded",
    extract: str = "dom",
    stealth: bool = False,
    session_domain: Optional[str] = None,
) -> dict:
    """
    Open a URL and return title + text content.
    extract: "dom" (default), "screenshot" (base64), "auto"
    session_domain: if set, load saved cookies for this domain first
    """
    try:
        engine = _get_engine(stealth)
        if session_domain:
            store = SessionStore()
            cookies = store.load(session_domain)
            if cookies:
                engine.set_cookies(cookies)
        engine.navigate(url, wait_until=wait_until)
        eyes = Eyes(engine)
        content = eyes.extract(mode=extract)
        return {
            "ok": True,
            "url": engine.current_url(),
            "title": eyes.title(),
            "content": content,
            "links": eyes.links()[:20],
        }
    except Exception as e:
        return _err(str(e), e)


def browser_screenshot(
    url: str,
    save_path: Optional[str] = None,
    full_page: bool = True,
    stealth: bool = False,
    element_selector: Optional[str] = None,
) -> dict:
    """
    Take a screenshot of a URL. Returns PNG bytes + optional save path.
    """
    try:
        engine = _get_engine(stealth)
        engine.navigate(url)
        eyes = Eyes(engine)
        path = Path(save_path) if save_path else None
        data = eyes.screenshot(full_page=full_page, save_path=path,
                               element_selector=element_selector)
        return {
            "ok": True,
            "url": engine.current_url(),
            "bytes": data,
            "size_bytes": len(data),
            "saved_to": str(path) if path else None,
        }
    except Exception as e:
        return _err(str(e), e)


def browser_click(url: str, selector: str, stealth: bool = False) -> dict:
    """
    Navigate to URL and click the first element matching selector.
    Returns URL after click.
    """
    try:
        engine = _get_engine(stealth)
        engine.navigate(url)
        hands = Hands(engine)
        hands.click(selector)
        engine.wait_for_load()
        eyes = Eyes(engine)
        return {
            "ok": True,
            "url": engine.current_url(),
            "title": eyes.title(),
        }
    except Exception as e:
        return _err(str(e), e)


def browser_fill(
    url: str,
    fields: dict,
    submit_selector: Optional[str] = None,
    stealth: bool = False,
) -> dict:
    """
    Navigate to URL, fill form fields, optionally submit.
    fields: {css_selector: value}
    Returns URL + title after form interaction.
    """
    try:
        engine = _get_engine(stealth)
        engine.navigate(url)
        hands = Hands(engine)
        hands.fill_form(fields)
        if submit_selector:
            hands.click(submit_selector)
            engine.wait_for_load()
        eyes = Eyes(engine)
        return {
            "ok": True,
            "url": engine.current_url(),
            "title": eyes.title(),
        }
    except Exception as e:
        return _err(str(e), e)


def browser_eval(url: str, js: str, stealth: bool = False) -> dict:
    """
    Navigate to URL and execute JavaScript, returning the result.
    """
    try:
        engine = _get_engine(stealth)
        engine.navigate(url)
        value = engine.evaluate(js)
        return {
            "ok": True,
            "url": engine.current_url(),
            "value": value,
        }
    except Exception as e:
        return _err(str(e), e)


def browser_login(
    url: str,
    username: str,
    password: str,
    save_session_domain: Optional[str] = None,
    stealth: bool = False,
) -> dict:
    """
    Log in to a website. Optionally saves the session for reuse.
    Credentials never appear in return values or logs.
    """
    try:
        engine = _get_engine(stealth)
        auth = AuthHandler(engine)
        success = auth.login_with_password(url, username, password)
        if success and save_session_domain:
            auth.save_session(save_session_domain)
        return {
            "ok": success,
            "url": engine.current_url(),
            "session_saved": bool(save_session_domain and success),
        }
    except Exception as e:
        return _err(str(e), e)


def browser_shutdown() -> dict:
    """Explicitly shut down the persistent browser. Next call relaunches."""
    try:
        get_pool().shutdown()
        return {"ok": True}
    except Exception as e:
        return _err(str(e), e)
```

- [ ] **Step 4: Update __init__.py exports**

Replace `scripts/browser/__init__.py` with this exact content:
```python
#!/usr/bin/env python3
"""Browser Eyes & Hands — automation layer for Claude Code and Clawmson."""
from __future__ import annotations

from browser.browser_engine import BrowserEngine
from browser.eyes import Eyes
from browser.hands import Hands
from browser.auth_handler import AuthHandler, SessionStore
from browser.captcha_handler import CaptchaHandler, CaptchaConfig
from browser.security import CredentialVault, AuditLogger, DomainScope
from browser.pool import BrowserPool, get_pool
from browser.tab_manager import TabManager
from browser.browser_tools import (
    browser_open,
    browser_screenshot,
    browser_click,
    browser_fill,
    browser_eval,
    browser_login,
    browser_shutdown,
)

__all__ = [
    "BrowserEngine", "Eyes", "Hands",
    "AuthHandler", "SessionStore",
    "CaptchaHandler", "CaptchaConfig",
    "CredentialVault", "AuditLogger", "DomainScope",
    "BrowserPool", "get_pool", "TabManager",
    "browser_open", "browser_screenshot", "browser_click",
    "browser_fill", "browser_eval", "browser_login",
    "browser_shutdown",
]
```

- [ ] **Step 5: Run the new test — verify it passes**

```bash
cd ~/openclaw && python3 -m pytest scripts/browser/tests/test_pool.py::test_browser_tools_reuse_pool -v
```
Expected: PASS

- [ ] **Step 6: Run full test suite — verify no regressions**

```bash
cd ~/openclaw && python3 -m pytest scripts/browser/tests/ -v
```
Expected: All tests pass. Note: some existing tests use `with BrowserEngine()` directly — that still works (context manager is untouched). The pool is an addition, not a replacement of the context manager.

- [ ] **Step 7: Commit**

```bash
cd ~/openclaw && git add scripts/browser/browser_tools.py scripts/browser/__init__.py
git commit -m "feat(browser): switch browser_tools to BrowserPool for persistent reuse

Adds browser_shutdown() tool. Exports BrowserPool, get_pool, TabManager."
```

---

## Task 6: Integration Demo & Smoke Test

**Files:**
- Modify: `scripts/browser/demo.py`

Update the demo script to show off persistent sessions and multi-tab.

- [ ] **Step 1: Rewrite demo.py**

Replace `scripts/browser/demo.py` with:
```python
#!/usr/bin/env python3
"""Live demo of Browser Eyes & Hands v2 — persistent session + multi-tab."""

import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from browser.pool import BrowserPool
from browser.tab_manager import TabManager
from browser.eyes import Eyes
from browser.hands import Hands

def main():
    print("\n🦞 Browser Eyes & Hands v2 — Persistent + Multi-Tab Demo\n")

    pool = BrowserPool(headless=False)
    engine = pool.get()
    tabs = TabManager(engine)

    try:
        # --- Tab 1: Hacker News ---
        print("📍 Opening Tab 1: Hacker News...")
        news_page = tabs.create("news")
        news_page.goto("https://news.ycombinator.com", wait_until="domcontentloaded")
        news_eyes = Eyes(engine, page=news_page)
        print(f"   Title: {news_eyes.title()}")
        time.sleep(1)

        # --- Tab 2: Example.com ---
        print("\n📍 Opening Tab 2: Example.com...")
        example_page = tabs.create("example")
        example_page.goto("https://example.com", wait_until="domcontentloaded")
        example_eyes = Eyes(engine, page=example_page)
        print(f"   Title: {example_eyes.title()}")
        time.sleep(1)

        # --- Read from both tabs without switching ---
        print(f"\n👁️  Tab count: {tabs.count()}")
        print(f"   Tabs open: {tabs.list_tabs()}")
        print(f"\n👁️  News tab title: {news_eyes.title()}")
        print(f"   Example tab title: {example_eyes.title()}")

        # --- Switch and interact ---
        print("\n🤚 Switching to news tab and scrolling...")
        tabs.switch("news")
        news_hands = Hands(engine, page=news_page)
        news_hands.scroll(x=0, y=600)
        time.sleep(1)

        # --- Links from news tab ---
        print("\n👁️  Top 5 HN links:")
        links = news_eyes.links()[:10]
        count = 0
        for link in links:
            text = link.get("text", "").strip()[:60]
            if text and count < 5:
                print(f"   • {text}")
                count += 1

        # --- Screenshot both tabs ---
        out_dir = Path(__file__).parent / "demo_output"
        out_dir.mkdir(exist_ok=True)

        print("\n📸 Screenshotting both tabs...")
        news_shot = out_dir / "demo-news.png"
        news_eyes.screenshot(save_path=news_shot)
        print(f"   News → {news_shot}")

        example_shot = out_dir / "demo-example.png"
        example_eyes.screenshot(save_path=example_shot)
        print(f"   Example → {example_shot}")

        # --- Demonstrate pool persistence ---
        print("\n♻️  Browser is still alive (persistent pool)...")
        print(f"   Pool alive: {pool.is_alive()}")

        # --- Close one tab ---
        print("\n🗑️  Closing example tab...")
        tabs.close("example")
        print(f"   Remaining tabs: {tabs.list_tabs()}")

        time.sleep(2)
        print("\n✅ Demo complete. Shutting down pool.\n")

    finally:
        pool.shutdown()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the demo (headed)**

```bash
cd ~/openclaw && HEADED=1 SLOW_MO=400 python3 scripts/browser/demo.py
```
Expected: Chromium opens, two tabs appear, both navigate, scroll on one, screenshots saved, one tab closes, pool shuts down.

- [ ] **Step 3: Commit**

```bash
cd ~/openclaw && git add scripts/browser/demo.py
git commit -m "feat(browser): update demo for persistent pool + multi-tab showcase"
```

---

## Task 7: Final Full Suite + Cleanup

- [ ] **Step 1: Run entire test suite**

```bash
cd ~/openclaw && python3 -m pytest scripts/browser/tests/ -v --tb=short
```
Expected: All tests pass (39 original + new pool/tab/tab-aware/persistent tests).

- [ ] **Step 2: Verify no import cycles or broken exports**

```bash
cd ~/openclaw && python3 -c "from browser import BrowserPool, get_pool, TabManager, browser_shutdown; print('All exports OK')"
```

- [ ] **Step 3: Final commit if any cleanup needed**

```bash
cd ~/openclaw && git status
# If clean, no commit needed. If there are stray files, add and commit.
```
