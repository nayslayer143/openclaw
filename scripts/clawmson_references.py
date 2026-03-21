#!/usr/bin/env python3
from __future__ import annotations
"""
Clawmson reference / link ingestion.
Fetches URLs, extracts readable text, summarizes via Ollama, stores in DB.
"""

import re
import requests as _http
from clawmson_db import save_reference, list_references, search_references
from clawmson_chat import chat

_URL_RE = re.compile(r'https?://[^\s]+')


def extract_urls(text: str) -> list:
    return _URL_RE.findall(text)


def _fetch_url(url: str) -> tuple:
    """
    Fetch URL and extract clean readable text.
    Returns (title, content).
    Tries trafilatura first, falls back to raw requests + HTML strip.
    """
    # trafilatura is the preferred extractor
    try:
        import trafilatura
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            content = trafilatura.extract(
                downloaded,
                include_comments=False,
                include_tables=True,
                no_fallback=False,
            )
            # Attempt metadata for title
            try:
                from trafilatura.metadata import extract_metadata
                meta  = extract_metadata(downloaded)
                title = meta.title if meta and meta.title else url
            except Exception:
                title = url
            return title, (content or "")
    except ImportError:
        pass
    except Exception:
        pass

    # Fallback: raw HTTP + crude HTML strip
    try:
        r = _http.get(url, timeout=20,
                      headers={"User-Agent": "Mozilla/5.0 (compatible; Clawmson/1.0)"})
        r.raise_for_status()
        text = re.sub(r'<[^>]+>', ' ', r.text)
        text = re.sub(r'\s+', ' ', text).strip()
        return url, text[:8000]
    except Exception as e:
        return url, f"(Could not fetch URL: {e})"


def _summarize(title: str, content: str) -> str:
    """Summarize article content via Ollama (3-5 sentences)."""
    if not content or len(content) < 100:
        return content or "(no content extracted)"
    prompt = (
        f"Summarize this article in 3-5 concise sentences. "
        f"Title: {title}\n\nContent:\n{content[:4000]}"
    )
    return chat([], prompt)


def ingest_url(chat_id: str, url: str) -> str:
    """Fetch, summarize, store a single URL. Returns reply text for Telegram."""
    title, content = _fetch_url(url)
    summary        = _summarize(title, content)
    save_reference(chat_id, url, title, summary, content[:16000])
    short_title    = title if title != url else url[:60]
    return f"Saved: {short_title}\n\n{summary}"


def ingest_urls_in_message(chat_id: str, text: str) -> list:
    """
    Find all URLs in message text, ingest up to 3, return list of reply strings.
    """
    urls    = extract_urls(text)[:3]
    results = []
    for url in urls:
        result = ingest_url(chat_id, url)
        results.append(result)
    return results


def format_references(refs: list) -> str:
    if not refs:
        return "No references saved yet."
    lines = ["Saved references:"]
    for r in refs:
        title = r.get("title") or r.get("url", "?")
        ts    = r.get("timestamp", "")[:10]
        lines.append(f"• [{ts}] {title}")
    return "\n".join(lines)
