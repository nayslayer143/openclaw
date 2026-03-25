#!/usr/bin/env python3
"""
Last30Days DataFeed — wraps the last30days skill as a mirofish DataFeed.

Runs last30days.py for configured topics and converts social/web findings
into trading-brain-compatible sentiment signals. Cached in clawmson.db.

Satisfies the DataFeed protocol (base_feed.py) duck-type interface.

Usage:
    from autoresearch.last30days_feed import fetch, get_cached, source_name
"""
from __future__ import annotations
import datetime
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Optional

source_name = "last30days"

# Path to last30days.py script (installed by skill audit 2026-03-24)
_SKILL_DIR = Path.home() / ".claude" / "skills" / "last30days" / "scripts"
_LAST30DAYS_PY = _SKILL_DIR / "last30days.py"

# Topics to research (space-separated topics relevant to prediction markets)
# Override with LAST30DAYS_TOPICS env var (comma-separated)
_DEFAULT_TOPICS = [
    "Polymarket prediction market",
    "Kalshi prediction market",
    "US election betting odds",
]

# Cache TTL in hours
_CACHE_TTL_HOURS = float(os.environ.get("LAST30DAYS_CACHE_TTL_HOURS", "6"))
_TIMEOUT = int(os.environ.get("LAST30DAYS_TIMEOUT", "180"))


# ── Sentiment keywords ────────────────────────────────────────────────────────

_BULLISH_WORDS = frozenset({
    "surge", "rally", "bullish", "soar", "moon", "ath", "pump", "gains",
    "outperform", "breakout", "upside", "buy", "long", "green", "positive",
    "record", "beat", "exceeds", "strong", "growth", "boom",
})
_BEARISH_WORDS = frozenset({
    "crash", "dump", "bearish", "plunge", "drop", "fall", "sell", "short",
    "red", "negative", "miss", "below", "collapse", "panic", "fear",
    "decline", "down", "weak", "risk", "concern", "problem",
})


def _infer_direction(text: str) -> str:
    """Simple keyword-based sentiment: bullish / bearish / neutral."""
    lower = text.lower()
    bull = sum(1 for w in _BULLISH_WORDS if w in lower)
    bear = sum(1 for w in _BEARISH_WORDS if w in lower)
    if bull > bear and bull > 0:
        return "bullish"
    if bear > bull and bear > 0:
        return "bearish"
    return "neutral"


# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    db_path = Path(os.environ.get(
        "CLAWMSON_DB_PATH",
        Path.home() / ".openclaw" / "clawmson.db",
    ))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    _ensure_table(conn)
    return conn


def _ensure_table(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS last30days_signals (
            id INTEGER PRIMARY KEY,
            source TEXT NOT NULL,
            ticker TEXT,
            signal_type TEXT,
            direction TEXT,
            amount_usd REAL,
            description TEXT,
            fetched_at TEXT,
            topic TEXT,
            url TEXT,
            relevance REAL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_l30d_fetched ON last30days_signals(fetched_at)
    """)
    conn.commit()


def _cache_signals(signals: list[dict]):
    if not signals:
        return
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM last30days_signals")
        conn.executemany(
            """INSERT INTO last30days_signals
               (source, ticker, signal_type, direction, amount_usd, description, fetched_at, topic, url, relevance)
               VALUES (:source, :ticker, :signal_type, :direction, :amount_usd, :description,
                       :fetched_at, :topic, :url, :relevance)""",
            signals,
        )
        conn.commit()
    finally:
        conn.close()


def _is_cache_fresh() -> bool:
    try:
        conn = _get_conn()
        row = conn.execute(
            "SELECT MAX(fetched_at) FROM last30days_signals"
        ).fetchone()
        conn.close()
        if not row or not row[0]:
            return False
        last = datetime.datetime.fromisoformat(row[0])
        age = (datetime.datetime.utcnow() - last).total_seconds() / 3600
        return age < _CACHE_TTL_HOURS
    except Exception:
        return False


# ── Core logic ────────────────────────────────────────────────────────────────

def _run_last30days(topic: str) -> list[dict]:
    """Run last30days.py for a topic, return list of normalized items."""
    if not _LAST30DAYS_PY.exists():
        sys.stderr.write(f"[last30days_feed] Skill not found at {_LAST30DAYS_PY}\n")
        return []

    cmd = [
        sys.executable, str(_LAST30DAYS_PY),
        topic,
        "--emit=json",
        "--quick",   # faster for background feed; use --deep for overnight runs
        "--sources=auto",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            cwd=str(_SKILL_DIR),
        )
    except subprocess.TimeoutExpired:
        sys.stderr.write(f"[last30days_feed] Timeout for topic: {topic}\n")
        return []
    except Exception as e:
        sys.stderr.write(f"[last30days_feed] Error running last30days: {e}\n")
        return []

    if result.returncode != 0:
        sys.stderr.write(f"[last30days_feed] Non-zero exit for '{topic}': {result.stderr[:200]}\n")
        return []

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        sys.stderr.write(f"[last30days_feed] Invalid JSON output for '{topic}'\n")
        return []

    # last30days --emit=json returns {"items": [...], "summary": "...", ...}
    items = data if isinstance(data, list) else data.get("items", [])
    return items


def _normalize_items(items: list[dict], topic: str) -> list[dict]:
    """Convert last30days items to mirofish signal dicts."""
    signals = []
    now = datetime.datetime.utcnow().isoformat()

    for i, item in enumerate(items):
        text = (
            item.get("text")
            or item.get("title")
            or item.get("content")
            or item.get("summary")
            or ""
        )
        if not text:
            continue

        url = item.get("url", "")
        relevance = float(item.get("relevance") or item.get("relevance_score") or 0.5)
        source_tag = item.get("source", item.get("id", f"item{i}"))
        direction = _infer_direction(text)

        # Only include items with meaningful relevance
        if relevance < 0.3:
            continue

        signals.append({
            "source": f"last30days:{source_tag[:20]}",
            "ticker": f"SENTIMENT:{topic[:20].upper().replace(' ', '_')}",
            "signal_type": "social_sentiment",
            "direction": direction,
            "amount_usd": None,
            "description": f"[{direction}|rel={relevance:.2f}] {text[:200]}",
            "fetched_at": now,
            "topic": topic,
            "url": url,
            "relevance": relevance,
        })

    return signals


def fetch(topics: Optional[list[str]] = None, deep: bool = False) -> list[dict]:
    """Fetch fresh last30days signals for all configured topics.

    Args:
        topics: Override default topics (list of strings)
        deep: If True, use --deep mode (slower but more thorough)

    Returns:
        List of signal dicts compatible with mirofish DataFeed protocol.
    """
    env_topics = os.environ.get("LAST30DAYS_TOPICS", "")
    if topics is None:
        if env_topics:
            topics = [t.strip() for t in env_topics.split(",") if t.strip()]
        else:
            topics = _DEFAULT_TOPICS

    all_signals: list[dict] = []

    for topic in topics:
        sys.stderr.write(f"[last30days_feed] Researching: {topic}\n")
        items = _run_last30days(topic)
        signals = _normalize_items(items, topic)
        all_signals.extend(signals)
        sys.stderr.write(f"[last30days_feed] {len(signals)} signals from '{topic}'\n")

    _cache_signals(all_signals)
    return all_signals


def get_cached() -> list[dict]:
    """Return cached signals from clawmson.db (no network call).

    Used by trading brain when calling feeds inside position evaluation.
    Returns empty list if cache is empty or expired.
    """
    if not _is_cache_fresh():
        return []
    try:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT * FROM last30days_signals ORDER BY relevance DESC LIMIT 50"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        sys.stderr.write(f"[last30days_feed] Cache read error: {e}\n")
        return []


# ── Watchlist integration ─────────────────────────────────────────────────────

def run_overnight_watchlist(topics: Optional[list[str]] = None) -> dict:
    """Run a deep overnight research pass and persist to last30days SQLite DB.

    Connects to the skill's own SQLite watchlist (--store flag) so findings
    accumulate over time and can be queried with store.py.

    Args:
        topics: Override topics. Defaults to LAST30DAYS_TOPICS env or _DEFAULT_TOPICS.

    Returns:
        Summary dict: {topic: signal_count, ...}
    """
    env_topics = os.environ.get("LAST30DAYS_TOPICS", "")
    if topics is None:
        if env_topics:
            topics = [t.strip() for t in env_topics.split(",") if t.strip()]
        else:
            topics = _DEFAULT_TOPICS

    results = {}
    for topic in topics:
        sys.stderr.write(f"[last30days_feed] Overnight deep research: {topic}\n")
        cmd = [
            sys.executable, str(_LAST30DAYS_PY),
            topic,
            "--deep",
            "--store",
            "--emit=json",
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
                cwd=str(_SKILL_DIR),
            )
            if result.returncode == 0:
                try:
                    data = json.loads(result.stdout)
                    items = data if isinstance(data, list) else data.get("items", [])
                    results[topic] = len(items)
                except Exception:
                    results[topic] = -1
            else:
                results[topic] = 0
        except subprocess.TimeoutExpired:
            results[topic] = -1
            sys.stderr.write(f"[last30days_feed] Timeout on overnight run for: {topic}\n")

    return results


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Last30Days DataFeed")
    parser.add_argument("--topic", help="Override topic (repeatable)", action="append")
    parser.add_argument("--overnight", action="store_true", help="Run deep overnight pass")
    parser.add_argument("--cached", action="store_true", help="Print cached signals only")
    args = parser.parse_args()

    if args.cached:
        sigs = get_cached()
        print(json.dumps(sigs, indent=2))
    elif args.overnight:
        summary = run_overnight_watchlist(args.topic)
        print(json.dumps(summary, indent=2))
    else:
        sigs = fetch(args.topic)
        print(json.dumps(sigs, indent=2))
