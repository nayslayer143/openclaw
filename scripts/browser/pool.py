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
        self._engine_kwargs = engine_kwargs
        self._engine: Optional[BrowserEngine] = None
        self._lock = threading.Lock()
        self._last_access: float = 0.0
        self._idle_timer: Optional[threading.Timer] = None
        self._generation: int = 0

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
        gen = self._generation
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
        """Called by idle timer — shutdown only if generation matches."""
        with self._lock:
            if gen != self._generation:
                return
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
