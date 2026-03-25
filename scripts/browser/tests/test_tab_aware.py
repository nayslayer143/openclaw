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
