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
