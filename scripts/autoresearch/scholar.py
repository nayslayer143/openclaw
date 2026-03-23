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
