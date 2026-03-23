#!/usr/bin/env python3
from __future__ import annotations
"""
AutoScholar — HuggingFace paper discovery, digestion, and routing.
Part of OpenClaw's research pipeline.

Layers:
  1. DB helpers      — save/retrieve papers and digests from clawmson.db
  2. Discovery       — search HF, embed + rank by relevance
  3. Digestion       — fetch paper markdown, extract insights via qwen3:30b
  4. Action routing  — write improvements, bakeoff flags, build notes
  5. Auto mode       — overnight cron entry point
  6. ClawTeam shim   — get_paper_for_debate()
"""

import os
import sys
import json
import re
import time
import datetime
import math
import requests
from pathlib import Path

# Add scripts/ to path so clawmson_db is importable when this module
# is run directly (e.g. from cron). When imported by telegram-dispatcher,
# scripts/ is already on sys.path.
_SCRIPTS_DIR = Path(__file__).parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import clawmson_db as db

# ── Constants ─────────────────────────────────────────────────────────────────

OLLAMA_BASE_URL       = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
DIGEST_MODEL          = os.environ.get("SCHOLAR_DIGEST_MODEL", "qwen3:30b")
EMBED_MODEL           = os.environ.get("SCHOLAR_EMBED_MODEL", "nomic-embed-text")
RELEVANCE_THRESHOLD   = float(os.environ.get("SCHOLAR_RELEVANCE_THRESHOLD", "0.75"))
HF_REQUEST_TIMEOUT    = 30  # seconds for all HuggingFace HTTP calls

OPENCLAW_ROOT = Path.home() / "openclaw"

# ── Directory creation ────────────────────────────────────────────────────────
# Ensure output directories exist at import time.

for _d in [
    OPENCLAW_ROOT / "autoresearch" / "outputs" / "papers",
    OPENCLAW_ROOT / "improvements",
    OPENCLAW_ROOT / "benchmark",
]:
    _d.mkdir(parents=True, exist_ok=True)

# ── Project goal vector (embedded once, cached) ───────────────────────────────

_GOAL_TEXT = (
    "agent orchestration, prediction markets, memory architectures, "
    "local LLM optimization, multi-agent systems, RAG, tool use, "
    "web business automation, NFC cards, information products"
)
_GOAL_VECTOR: list[float] | None = None  # populated lazily on first embed call

# ── Default domain keywords for auto_mode ────────────────────────────────────

DEFAULT_DOMAINS = [
    "agent orchestration",
    "prediction markets",
    "memory architectures",
    "local LLM optimization",
    "multi-agent systems",
    "RAG retrieval augmented",
    "tool use LLM",
    "agentic systems",
]

# ── DB helpers ────────────────────────────────────────────────────────────────

def save_paper(paper_id: str, title: str, authors: str | None,
               abstract: str | None, url: str | None,
               relevance_score: float | None) -> None:
    """INSERT OR IGNORE a paper row. discovered_at set to UTC now."""
    ts = datetime.datetime.utcnow().isoformat()
    with db._get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO papers "
            "(paper_id, title, authors, abstract, url, relevance_score, discovered_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (paper_id, title, authors, abstract, url, relevance_score, ts)
        )


def mark_digested(paper_id: str) -> None:
    """Set digested=1 for a paper."""
    with db._get_conn() as conn:
        conn.execute("UPDATE papers SET digested=1 WHERE paper_id=?", (paper_id,))


def save_digest(paper_id: str, findings: str, techniques: str, models: str,
                relevance: str, priority: str, action: str) -> None:
    """Insert a paper_digests row. digested_at set to UTC now."""
    ts = datetime.datetime.utcnow().isoformat()
    with db._get_conn() as conn:
        conn.execute(
            "INSERT INTO paper_digests "
            "(paper_id, key_findings, implementable_techniques, linked_models, "
            " relevance_to_builds, priority, action_taken, digested_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (paper_id, findings, techniques, models, relevance, priority, action, ts)
        )


def get_undigested(limit: int = 20) -> list[dict]:
    """Return papers not yet digested, ordered by relevance_score DESC."""
    with db._get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM papers WHERE digested=0 ORDER BY relevance_score DESC LIMIT ?",
            (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_recent_papers(days: int = 7) -> dict:
    """
    Return summary of papers discovered in the last N days.
    Returns {"total": int, "digested": int, "top_titles": list[str]}
    """
    cutoff = (datetime.datetime.utcnow() - datetime.timedelta(days=days)).isoformat()
    with db._get_conn() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM papers WHERE discovered_at >= ?", (cutoff,)
        ).fetchone()[0]
        digested = conn.execute(
            "SELECT COUNT(*) FROM papers WHERE discovered_at >= ? AND digested=1",
            (cutoff,)
        ).fetchone()[0]
        top_rows = conn.execute(
            "SELECT title FROM papers WHERE discovered_at >= ? AND digested=1"
            " ORDER BY relevance_score DESC LIMIT 5",
            (cutoff,)
        ).fetchall()
    return {
        "total": total,
        "digested": digested,
        "top_titles": [r["title"] for r in top_rows],
    }
