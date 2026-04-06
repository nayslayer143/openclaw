#!/usr/bin/env python3
from __future__ import annotations
"""
AutoScholar — HuggingFace paper discovery, digestion, and routing.
Part of OpenClaw's research pipeline.

Layers:
  1. DB helpers      — save/retrieve papers and digests from clawmson.db
  2. Discovery       — search HF, embed + rank by relevance
  3. Digestion       — fetch paper markdown, extract insights via gemma4:26b-A4B (MoE)
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
from urllib.parse import quote as _url_quote

# Add scripts/ to path so clawmson_db is importable when this module
# is run directly (e.g. from cron). When imported by telegram-dispatcher,
# scripts/ is already on sys.path.
_SCRIPTS_DIR = Path(__file__).parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import clawmson_db as db

# ── Constants ─────────────────────────────────────────────────────────────────

OLLAMA_BASE_URL       = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
DIGEST_MODEL          = os.environ.get("SCHOLAR_DIGEST_MODEL", "gemma4:26b")
EMBED_MODEL           = os.environ.get("SCHOLAR_EMBED_MODEL", "nomic-embed-text")
RELEVANCE_THRESHOLD   = float(os.environ.get("SCHOLAR_RELEVANCE_THRESHOLD", "0.75"))
HF_REQUEST_TIMEOUT    = 30  # seconds for all HuggingFace HTTP calls

OPENCLAW_ROOT   = Path.home() / "openclaw"
WATCHLIST_PATH  = Path(__file__).parent / "watchlist.json"
REPOMAN_INBOX   = Path.home() / "repo-man" / "inbox"

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

# ── Watchlist ─────────────────────────────────────────────────────────────────

def load_watchlist() -> list[dict]:
    """Load watchlist entries from watchlist.json. Returns [] if missing or broken."""
    if not WATCHLIST_PATH.exists():
        return []
    try:
        return json.loads(WATCHLIST_PATH.read_text()).get("entries", [])
    except Exception as e:
        print(f"[scholar] watchlist load failed: {e}")
        return []


def _watchlist_search_terms() -> list[str]:
    """Collect all search_terms across all watchlist entries."""
    terms: list[str] = []
    for entry in load_watchlist():
        terms.extend(entry.get("monitor", {}).get("search_terms", []))
    return terms


# ── Repo Man inbox push ───────────────────────────────────────────────────────

def _push_to_repoman(
    paper_id: str,
    priority: str,
    findings: list,
    techniques: list,
    relevance: str,
) -> bool:
    """
    Drop a structured JSON file into ~/repo-man/inbox/ after a successful digest.
    Repo Man picks these up for security scoring, OpenClaw routing, and dispatch
    block generation. Never raises — errors are logged and swallowed.

    Drop schema: repoman-inbox-v1
    """
    try:
        REPOMAN_INBOX.mkdir(parents=True, exist_ok=True)

        # Re-fetch title + url from DB (paper is guaranteed present at call site)
        with db._get_conn() as conn:
            row = conn.execute(
                "SELECT title, url FROM papers WHERE paper_id=?", (paper_id,)
            ).fetchone()
        title = (row["title"] if row else None) or paper_id
        url = (row["url"] if row else None) or f"https://huggingface.co/papers/{paper_id}"

        # Build summary and action recommendation
        summary_parts: list[str] = []
        if findings:
            summary_parts.append("Findings: " + " | ".join(str(f) for f in findings[:5]))
        if relevance:
            summary_parts.append(f"Relevance: {relevance}")
        summary = " ".join(summary_parts) or title

        action = "Review paper findings and identify applicable improvements."
        if techniques:
            action = "Implement: " + "; ".join(str(t) for t in techniques[:3]) + "."
        if relevance:
            action += f" Context: {relevance}"

        # Structured content block for Repo Man's analysis pipeline
        content_lines = [f"Priority: {priority}", "", "Key Findings:"]
        content_lines += [f"- {f}" for f in (findings or [])]
        if techniques:
            content_lines += ["", "Implementable Techniques:"]
            content_lines += [f"- {t}" for t in techniques]
        if relevance:
            content_lines += ["", f"Relevance:\n{relevance}"]
        extracted_content = "\n".join(content_lines)

        drop = {
            "schema": "repoman-inbox-v1",
            "source": "autoresearch-scholar",
            "dropped_at": datetime.datetime.utcnow().isoformat(),
            "raw_input": url,
            "source_type": "generic_url",
            "title": title,
            "extracted_content": extracted_content,
            "pre_analysis": {
                "backend": "ollama",
                "summary": summary,
                "key_ideas": [str(t) for t in (techniques or [])],
                "relevance_tags": ["research", "paper", priority.lower(), "autoresearch-scholar"],
                "novelty_score": None,
                "action_recommendation": action,
            },
            "priority": priority,
        }

        slug = re.sub(r"[^a-z0-9]+", "-", paper_id.lower())[:30].strip("-")
        ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        fname = f"scholar-{slug}-{ts}.json"
        (REPOMAN_INBOX / fname).write_text(json.dumps(drop, indent=2))
        print(f"[scholar] → repo-man inbox: {fname}")
        return True
    except Exception as e:
        print(f"[scholar] repoman push failed for {paper_id}: {e}")
        return False


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


# ── Embedding + relevance ranking ─────────────────────────────────────────────

def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def embed_text(text: str) -> list[float]:
    """Embed text using nomic-embed-text via Ollama."""
    resp = requests.post(
        f"{OLLAMA_BASE_URL}/api/embeddings",
        json={"model": EMBED_MODEL, "prompt": text},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["embedding"]


def _get_goal_vector() -> list[float]:
    """Return cached goal vector, embedding once on first call."""
    global _GOAL_VECTOR
    if _GOAL_VECTOR is None:
        _GOAL_VECTOR = embed_text(_GOAL_TEXT)
    return _GOAL_VECTOR


def rank_by_relevance(candidates: list[dict]) -> list[dict]:
    """
    Embed each candidate's abstract and rank by cosine similarity
    against the project goal vector. Attaches relevance_score to each dict.
    Returns sorted list (highest score first).
    """
    goal = _get_goal_vector()
    for candidate in candidates:
        abstract = candidate.get("abstract") or candidate.get("title") or ""
        try:
            vec = embed_text(abstract)
            candidate["relevance_score"] = round(_cosine(goal, vec), 4)
        except Exception as e:
            print(f"[scholar] embed failed for {candidate.get('paper_id')}: {e}")
            candidate["relevance_score"] = 0.0
    return sorted(candidates, key=lambda c: c["relevance_score"], reverse=True)


# ── Discovery ─────────────────────────────────────────────────────────────────

def _known_paper_ids() -> set[str]:
    """Return set of paper_ids already in DB."""
    with db._get_conn() as conn:
        rows = conn.execute("SELECT paper_id FROM papers").fetchall()
    return {r["paper_id"] for r in rows}


def search_papers(query: str | None = None, limit: int = 20) -> list[dict]:
    """
    Fetch papers from HuggingFace API. Deduplicates against known DB papers.
    If query is None, fetches trending papers.
    Returns list of candidate dicts with paper_id, title, abstract, authors, url.
    """
    if query:
        url = f"https://huggingface.co/api/papers?search={_url_quote(query)}"
    else:
        url = "https://huggingface.co/api/papers"

    resp = requests.get(url, timeout=HF_REQUEST_TIMEOUT)
    resp.raise_for_status()
    raw = resp.json()

    known = _known_paper_ids()
    candidates = []
    for item in raw[:limit * 2]:  # fetch extra to account for dedup
        pid = item.get("id") or item.get("paper_id", "")
        if not pid or pid in known:
            continue
        candidates.append({
            "paper_id": pid,
            "title":    item.get("title", ""),
            "authors":  json.dumps([a.get("name", a) if isinstance(a, dict) else a
                                    for a in item.get("authors", [])]),
            "abstract": item.get("summary") or item.get("abstract", ""),
            "url":      f"https://huggingface.co/papers/{pid}",
        })
        if len(candidates) >= limit:
            break
    return candidates


def discover(query: str | None = None, limit: int = 10) -> list[dict]:
    """
    Full discovery pipeline:
    1. Search HF (or trending if no query)
    2. Rank by relevance against goal vector
    3. Save all candidates to DB
    4. Return ranked list
    """
    candidates = search_papers(query=query, limit=limit * 2)
    if not candidates:
        return []
    ranked = rank_by_relevance(candidates)
    for paper in ranked:
        save_paper(
            paper_id=paper["paper_id"],
            title=paper["title"],
            authors=paper.get("authors"),
            abstract=paper.get("abstract"),
            url=paper.get("url"),
            relevance_score=paper.get("relevance_score"),
        )
    return ranked[:limit]


# ── Digestion ─────────────────────────────────────────────────────────────────

def fetch_paper_markdown(paper_id: str) -> str:
    """
    Fetch full paper markdown from HuggingFace.
    On HTTP error: fall back to abstract from DB.
    If paper not in DB either: return empty string.
    """
    try:
        resp = requests.get(
            f"https://huggingface.co/papers/{paper_id}.md",
            timeout=HF_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.text
    except requests.exceptions.RequestException:
        pass
    # Fallback: abstract from DB
    with db._get_conn() as conn:
        row = conn.execute(
            "SELECT abstract FROM papers WHERE paper_id=?", (paper_id,)
        ).fetchone()
    if row and row["abstract"]:
        return row["abstract"]
    return ""


_DIGEST_PROMPT = """\
Given this research paper, extract:
1. KEY_FINDINGS: 3-7 bullet points of the most important findings
2. IMPLEMENTABLE_TECHNIQUES: specific techniques we could build right now, \
in the context of: agent orchestration, prediction markets, memory architectures, \
local LLM optimization, multi-agent systems, RAG, tool use, web business automation
3. LINKED_MODELS: any HuggingFace model/dataset IDs mentioned
4. RELEVANCE_TO_BUILDS: how this relates to the above domains
5. PRIORITY: P1 (use now) / P2 (useful soon) / P3 (interesting later)

Return JSON only.\
"""


def _extract_title_from_markdown(md: str) -> str | None:
    """Extract first # Heading from markdown. Returns None if not found."""
    for line in md.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return None


def _strip_json_fences(raw: str) -> str:
    """Remove markdown code fences from LLM response, handling leading text."""
    raw = raw.strip()
    # Try to find a JSON fence block anywhere in the response
    match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", raw)
    if match:
        return match.group(1).strip()
    # No fence found — return as-is (may or may not be valid JSON)
    return raw


def digest_paper(paper_id: str) -> dict:
    """
    Fetch and digest a paper. Saves digest to DB and runs action routing.

    Returns the parsed digest dict on success, or {"error": "...", ...} on failure.
    Never raises.
    """
    # Check if paper is in DB
    with db._get_conn() as conn:
        row = conn.execute("SELECT * FROM papers WHERE paper_id=?",
                           (paper_id,)).fetchone()
    in_db = row is not None

    # Fetch content
    content = fetch_paper_markdown(paper_id)
    if not content:
        return {"error": "unknown_paper", "paper_id": paper_id}

    # If paper wasn't in DB, save a placeholder row with extracted title
    if not in_db:
        title = _extract_title_from_markdown(content) or paper_id
        save_paper(
            paper_id=paper_id,
            title=title,
            authors=None,
            abstract=None,
            url=f"https://huggingface.co/papers/{paper_id}",
            relevance_score=None,
        )

    # Build prompt — truncate content to avoid overwhelming the model
    prompt_content = content[:8000] if len(content) > 8000 else content
    prompt = f"{_DIGEST_PROMPT}\n\n---\n\n{prompt_content}"

    # Call gemma4:26b-A4B (MoE)
    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": DIGEST_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"num_ctx": int(os.environ.get("OPENCLAW_NUM_CTX", "16384"))},
            },
            timeout=120,
        )
        resp.raise_for_status()
        raw = resp.json().get("message", {}).get("content", "")
    except Exception as e:
        print(f"[scholar] Ollama call failed for {paper_id}: {e}")
        return {"error": "ollama_failed", "paper_id": paper_id}

    # Defensive JSON parsing
    try:
        parsed = json.loads(_strip_json_fences(raw))
    except json.JSONDecodeError:
        print(f"[scholar] JSON parse failed for {paper_id}. Raw: {raw[:200]}")
        return {"error": "parse_failed", "raw": raw[:200]}

    findings     = parsed.get("KEY_FINDINGS", [])
    techniques   = parsed.get("IMPLEMENTABLE_TECHNIQUES", [])
    models       = parsed.get("LINKED_MODELS", [])
    relevance    = parsed.get("RELEVANCE_TO_BUILDS", "")
    priority     = parsed.get("PRIORITY", "P3")

    # Persist
    actions = _route_paper_actions(paper_id, priority, techniques, models, relevance)
    save_digest(
        paper_id=paper_id,
        findings=json.dumps(findings),
        techniques=json.dumps(techniques),
        models=json.dumps(models),
        relevance=relevance,
        priority=priority,
        action=",".join(actions) if actions else "none",
    )
    mark_digested(paper_id)
    _push_to_repoman(paper_id, priority, findings, techniques, relevance)

    return {
        "paper_id": paper_id,
        "key_findings": findings,
        "implementable_techniques": techniques,
        "linked_models": models,
        "relevance_to_builds": relevance,
        "priority": priority,
        "actions": actions,
    }


def _route_paper_actions(paper_id: str, priority: str, techniques: list,
                          models: list, relevance: str) -> list[str]:
    """
    Route paper to downstream outputs. All matching rules fire.
    Returns list of action strings taken (may be empty).
    """
    actions = []
    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    slug = re.sub(r"[^a-z0-9]+", "-", paper_id.lower())[:30].strip("-")

    # Fetch paper title for output files
    with db._get_conn() as conn:
        row = conn.execute("SELECT title FROM papers WHERE paper_id=?",
                           (paper_id,)).fetchone()
    title = row["title"] if row else paper_id

    # Rule 1: P1 + implementable techniques → improvement proposal
    if priority == "P1" and isinstance(techniques, list) and len(techniques) > 0:
        path = OPENCLAW_ROOT / "improvements" / f"scholar-{slug}-{today}.md"
        path.write_text(
            f"# Scholar Improvement: {title}\n\n"
            f"**Paper:** https://huggingface.co/papers/{paper_id}\n"
            f"**Priority:** {priority}\n\n"
            f"## Implementable Techniques\n\n"
            + "\n".join(f"- {t}" for t in techniques) + "\n\n"
            f"## Relevance\n\n{relevance}\n"
        )
        actions.append("improvement")

    # Rule 2: Linked models → bakeoff queue
    if isinstance(models, list) and len(models) > 0:
        bakeoff = OPENCLAW_ROOT / "benchmark" / "bakeoff-queue.md"
        entry = (
            f"\n## {today} — {paper_id}\n"
            f"- Title: {title}\n"
            f"- Models: {', '.join(models)}\n"
            f"- Source: autoscholar\n"
        )
        with open(bakeoff, "a") as f:
            f.write(entry)
        actions.append("bakeoff")

    # Rule 3: P1 + non-empty relevance → build context note
    if priority == "P1" and relevance and relevance.strip():
        path = OPENCLAW_ROOT / "autoresearch" / "outputs" / "papers" / \
               f"academic-{slug}-{today}.md"
        path.write_text(
            f"# Academic Note: {title}\n\n"
            f"**Paper:** https://huggingface.co/papers/{paper_id}\n"
            f"**Priority:** {priority}\n\n"
            f"## Relevance to Active Builds\n\n{relevance}\n"
        )
        actions.append("build_note")

    return actions


# ── Batch digestion ───────────────────────────────────────────────────────────

def digest_batch(paper_ids: list[str], delay: float = 5) -> list[dict]:
    """
    Digest multiple papers with a delay between calls.
    Use delay=0 in tests to avoid real sleep.
    """
    results = []
    for i, pid in enumerate(paper_ids):
        result = digest_paper(pid)
        results.append(result)
        if delay > 0 and i < len(paper_ids) - 1:
            time.sleep(delay)
    return results


# ── Auto mode ─────────────────────────────────────────────────────────────────

def auto_mode(domains: list[str] | None = None) -> dict:
    """
    Overnight cron entry point.
    Discovers papers across configured domains, digests qualifying papers,
    writes daily digest report, returns summary dict.
    """
    if domains is None:
        domains = DEFAULT_DOMAINS

    # Merge watchlist search terms so overnight sweep covers monitored papers
    watchlist_terms = _watchlist_search_terms()
    merged_domains = list(domains) + [t for t in watchlist_terms if t not in domains]

    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    all_candidates: list[dict] = []

    for keyword in merged_domains:
        try:
            candidates = discover(query=keyword, limit=20)
            all_candidates.extend(candidates)
        except Exception as e:
            print(f"[scholar] discover failed for '{keyword}': {e}")

    # Deduplicate across domains
    seen: set[str] = set()
    unique = []
    for p in all_candidates:
        if p["paper_id"] not in seen:
            seen.add(p["paper_id"])
            unique.append(p)

    # Filter by relevance threshold
    to_digest = [p for p in unique if (p.get("relevance_score") or 0) >= RELEVANCE_THRESHOLD]

    # Digest qualifying papers
    digest_results = digest_batch([p["paper_id"] for p in to_digest], delay=5)

    # Collect actions taken
    actions_taken: list[str] = []
    for r in digest_results:
        for a in r.get("actions", []):
            if a not in actions_taken:
                actions_taken.append(a)

    # Write daily digest report
    summary = get_recent_papers(days=1)
    report_path = (OPENCLAW_ROOT / "autoresearch" / "outputs" / "papers" /
                   f"academic-scholar-digest-{today}.md")
    digested_count = len([r for r in digest_results if "error" not in r])
    top_titles = summary.get("top_titles", [])

    report_lines = [
        f"# AutoScholar Daily Digest — {today}\n",
        f"**Discovered:** {len(unique)} papers\n",
        f"**Digested:** {digested_count} papers\n",
        f"**Actions:** {', '.join(actions_taken) or 'none'}\n\n",
        "## Top Papers\n",
    ]
    for title in top_titles:
        report_lines.append(f"- {title}\n")
    report_path.write_text("".join(report_lines))

    return {
        "discovered": len(unique),
        "digested": digested_count,
        "actions_taken": actions_taken,
        "top_titles": top_titles,
    }


# ── ClawTeam shim ─────────────────────────────────────────────────────────────

def get_paper_for_debate(paper_id: str, full: bool = False) -> dict:
    """
    Return structured paper data for ClawTeam debate pattern.

    - Full data returned when paper has been digested.
    - Partial data (title/abstract/url, digest fields None) if not yet digested.
    - {"error": "not_found"} if paper_id is unknown.
    - full=True triggers a live fetch of paper markdown (slow, may fail).
    """
    with db._get_conn() as conn:
        paper = conn.execute(
            "SELECT * FROM papers WHERE paper_id=?", (paper_id,)
        ).fetchone()
        if not paper:
            return {"error": "not_found"}
        digest = conn.execute(
            "SELECT * FROM paper_digests WHERE paper_id=?", (paper_id,)
        ).fetchone()

    result = {
        "title":                  paper["title"],
        "abstract":               paper["abstract"],
        "url":                    paper["url"],
        "key_findings":           json.loads(digest["key_findings"]) if digest and digest["key_findings"] else None,
        "implementable_techniques": json.loads(digest["implementable_techniques"]) if digest and digest["implementable_techniques"] else None,
        "relevance_to_builds":    digest["relevance_to_builds"] if digest else None,
        "full_markdown":          None,
    }
    if full:
        result["full_markdown"] = fetch_paper_markdown(paper_id) or None
    return result
