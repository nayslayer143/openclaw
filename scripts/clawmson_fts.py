#!/usr/bin/env python3
from __future__ import annotations
"""FTS5 full-text search across all Hermes memory layers."""
import sqlite3 as _sqlite3
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

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

if not FTS5_AVAILABLE:
    import warnings
    warnings.warn("[clawmson_fts] FTS5 not available — search disabled", stacklevel=1)

import clawmson_db as db


def index(chat_id: str, source: str, source_id: int,
          content: str, ts: str, conn=None):
    """Insert one item into memory_fts. No-op if FTS5 unavailable."""
    if not FTS5_AVAILABLE:
        return
    if not content or not content.strip():
        return
    sql = ("INSERT INTO memory_fts (content, source, chat_id, source_id, ts)"
           " VALUES (?, ?, ?, ?, ?)")
    params = (content, source, chat_id, source_id, ts)
    if conn is not None:
        conn.execute(sql, params)
    else:
        with db._get_conn() as c:
            c.execute(sql, params)


def remove(source: str, source_id: int, conn=None):
    """Delete item from memory_fts by source + source_id. No-op if FTS5 unavailable."""
    if not FTS5_AVAILABLE:
        return
    sql = "DELETE FROM memory_fts WHERE source=? AND source_id=?"
    params = (source, source_id)
    if conn is not None:
        conn.execute(sql, params)
    else:
        with db._get_conn() as c:
            c.execute(sql, params)


def search(chat_id: str, query: str, limit: int = 10) -> list[dict]:
    """
    BM25-ranked FTS5 search scoped to chat_id.
    Returns list of {source, content, snippet, ts, rank}.
    Returns [] if FTS5 unavailable or query is empty.

    Query is phrase-quoted before MATCH to handle multi-word queries.
    OperationalError (malformed FTS5 query) is caught and returns [].
    """
    if not FTS5_AVAILABLE or not query or not query.strip():
        return []

    # Phrase-quote for exact phrase matching; escape any embedded quotes
    safe_query = query.strip().replace('"', '""')
    fts_query = f'"{safe_query}"'

    try:
        with db._get_conn() as conn:
            rows = conn.execute(
                "SELECT source, source_id, content,"
                " snippet(memory_fts, 0, '>>', '<<', '...', 8) AS snippet,"
                " ts, rank"
                " FROM memory_fts"
                " WHERE memory_fts MATCH ? AND chat_id = ?"
                " ORDER BY rank LIMIT ?",
                (fts_query, chat_id, limit)
            ).fetchall()
        return [dict(r) for r in rows]
    except _sqlite3.OperationalError:
        return []


def format_results(results: list[dict]) -> str:
    """Format search results for Telegram /search reply.
    Each result: '[source] snippet (ts)'
    Returns 'No results found.' if list is empty.
    """
    if not results:
        return "No results found."
    lines = []
    for r in results:
        ts_short = r.get("ts", "")[:10]
        snippet = r.get("snippet") or r.get("content", "")[:100]
        lines.append(f"[{r['source']}] {snippet} ({ts_short})")
    return "\n".join(lines)
