#!/usr/bin/env python3
from __future__ import annotations
"""
Twitter Scout — extraction + categorization engine.
Tries nitter → fxtwitter → oembed in order. Falls back gracefully on failure.
"""

import os
import re
import json
import time
import requests
from bs4 import BeautifulSoup

NITTER_INSTANCES = [
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
    "https://nitter.net",
]
RATE_LIMIT_DELAY = 0.5    # seconds between URLs (per-URL, not per-request)
REQUEST_TIMEOUT  = 15     # seconds per HTTP request
SCOUT_MODEL      = os.environ.get("OLLAMA_SCOUT_MODEL", "qwen2.5:7b")
OLLAMA_BASE_URL  = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

_GITHUB_RE = re.compile(r'https?://github\.com/[\w.-]+/[\w.-]+')
_TWITTER_STATUS_RE = re.compile(r'https?://(x\.com|twitter\.com)/(\w+)/status/(\d+)')

_CATEGORIZE_SYSTEM = """\
You are an AI research scout for OpenClaw, a multimodal AI workspace. \
Categorize this tweet and extract actionable intelligence.

Categories:
- tool: A new tool, library, framework, or software that could improve our AI/dev workflow
- technique: A prompting technique, coding pattern, or methodology worth trying
- business_intel: Business insights, market data, funding news, or competitive intelligence
- code_pattern: Specific code snippets, architectures, or implementations to study
- market_intel: Market trends, pricing strategies, user behavior data, or opportunity signals
- irrelevant: Not actionable for an AI agent automation setup

Return JSON: {"category": str, "relevance_score": int (1-10), \
"summary": str (1 sentence), "action_items": [str]}"""


def extract_github_repos(text: str) -> list:
    """Find github.com/owner/repo URLs in text. Returns deduplicated list."""
    return list(dict.fromkeys(_GITHUB_RE.findall(text)))


def parse_nitter(html: str) -> dict | None:
    """Parse nitter HTML page. Returns tweet dict or None if parse fails."""
    try:
        soup = BeautifulSoup(html, "html.parser")
        content = soup.find(class_="tweet-content")
        if not content:
            return None
        text = content.get_text(strip=True)
        if not text:
            return None

        author = ""
        username_tag = soup.find(class_="username")
        if username_tag:
            author = username_tag.get_text(strip=True).lstrip("@")

        timestamp = ""
        time_tag = soup.find("span", class_="tweet-date")
        if time_tag:
            a = time_tag.find("a")
            if a:
                timestamp = a.get("title", "")

        media_urls = [
            img["src"] for img in soup.find_all("img", class_="still-image")
            if img.get("src")
        ]

        linked_urls = [
            a["href"] for a in content.find_all("a")
            if a.get("href") and a["href"].startswith("http")
        ]

        return {
            "author": author,
            "text": text,
            "media_urls": media_urls,
            "linked_urls": linked_urls,
            "timestamp": timestamp,
            "raw_html": html[:4000],
            "method": "nitter",
        }
    except Exception:
        return None


def _nitter_url(tweet_url: str, instance: str) -> str:
    """Convert a twitter/x URL to a nitter instance URL."""
    m = _TWITTER_STATUS_RE.search(tweet_url)
    if not m:
        return tweet_url
    username, status_id = m.group(2), m.group(3)
    return f"{instance}/{username}/status/{status_id}"


def _try_nitter(tweet_url: str) -> dict | None:
    """Try all nitter instances. Returns parsed dict or None."""
    for instance in NITTER_INSTANCES:
        url = _nitter_url(tweet_url, instance)
        try:
            r = requests.get(
                url, timeout=REQUEST_TIMEOUT,
                headers={"User-Agent": "Mozilla/5.0 (compatible; Clawmson/1.0)"},
                allow_redirects=True,
            )
            if r.status_code == 200:
                result = parse_nitter(r.text)
                if result:
                    print(f"[twitter] nitter success via {instance}")
                    return result
        except Exception as e:
            print(f"[twitter] nitter {instance} failed: {e}")
    return None


def parse_fxtwitter(url: str) -> dict | None:
    """Fetch fxtwitter version and parse Open Graph tags."""
    try:
        fx_url = _TWITTER_STATUS_RE.sub(
            lambda m: f"https://fxtwitter.com/{m.group(2)}/status/{m.group(3)}",
            url
        )
        r = requests.get(
            fx_url, timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 (compatible; Clawmson/1.0)"},
        )
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        desc = soup.find("meta", {"property": "og:description"})
        author_tag = soup.find("meta", {"property": "og:title"})
        text = desc["content"] if desc and desc.get("content") else ""
        author = author_tag["content"].split(" on ")[0] if author_tag and author_tag.get("content") else ""
        if not text:
            return None
        return {
            "author": author,
            "text": text,
            "media_urls": [],
            "linked_urls": [],
            "timestamp": "",
            "raw_html": r.text[:4000],
            "method": "fxtwitter",
        }
    except Exception as e:
        print(f"[twitter] fxtwitter failed: {e}")
        return None


def _try_fxtwitter(tweet_url: str) -> dict | None:
    return parse_fxtwitter(tweet_url)


def parse_oembed(url: str) -> dict | None:
    """Use Twitter OEmbed API. Strips HTML tags from returned html field."""
    try:
        r = requests.get(
            "https://publish.twitter.com/oembed",
            params={"url": url},
            timeout=REQUEST_TIMEOUT,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        html = data.get("html", "")
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()
        author = data.get("author_name", "")
        if not text:
            return None
        return {
            "author": author,
            "text": text,
            "media_urls": [],
            "linked_urls": [],
            "timestamp": "",
            "raw_html": html[:4000],
            "method": "oembed",
        }
    except Exception as e:
        print(f"[twitter] oembed failed: {e}")
        return None


def _try_oembed(tweet_url: str) -> dict | None:
    return parse_oembed(tweet_url)


def extract_tweet(url: str) -> dict:
    """
    Try nitter → fxtwitter → oembed. Returns tweet dict on success,
    or {"extraction_failed": True, "methods_tried": [...], "url": url} on total failure.
    """
    methods_tried = []

    result = _try_nitter(url)
    if result:
        return result
    methods_tried.append("nitter")

    result = _try_fxtwitter(url)
    if result:
        return result
    methods_tried.append("fxtwitter")

    result = _try_oembed(url)
    if result:
        return result
    methods_tried.append("oembed")

    print(f"[twitter] all extraction methods failed for {url}")
    return {"extraction_failed": True, "methods_tried": methods_tried, "url": url}


def categorize_tweet(tweet_text: str, linked_urls: list) -> dict:
    """
    Send tweet text to Ollama for categorization.
    Returns {category, relevance_score, summary, action_items}.
    Falls back to categorization_failed if Ollama is unreachable.
    """
    user_msg = f"Tweet: {tweet_text}"
    if linked_urls:
        user_msg += f"\nLinked URLs: {', '.join(linked_urls)}"

    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": SCOUT_MODEL,
                "messages": [
                    {"role": "system", "content": _CATEGORIZE_SYSTEM},
                    {"role": "user", "content": user_msg},
                ],
                "stream": False,
                "format": "json",
            },
            timeout=60,
        )
        resp.raise_for_status()
        raw = resp.json().get("message", {}).get("content", "")
        result = json.loads(raw)
        result.setdefault("category", "irrelevant")
        result.setdefault("relevance_score", 5)
        result.setdefault("summary", "")
        result.setdefault("action_items", [])
        return result
    except Exception as e:
        print(f"[twitter] categorize_tweet failed: {e}")
        return {
            "category": "categorization_failed",
            "relevance_score": 0,
            "summary": "",
            "action_items": [],
        }


def process_batch(urls: list) -> dict:
    """
    Process a list of Twitter URLs. Rate-limited per URL (not per HTTP request).
    Returns {results: [...], stats: {total, succeeded, failed, by_category: {}}}
    """
    results = []
    by_category: dict = {}

    for i, url in enumerate(urls):
        extraction = extract_tweet(url)
        if extraction.get("extraction_failed"):
            cat_result = {
                "category": "extraction_failed",
                "relevance_score": 0,
                "summary": "",
                "action_items": [],
            }
        else:
            cat_result = categorize_tweet(
                extraction.get("text", ""),
                extraction.get("linked_urls", []),
            )

        record = {
            "url": url,
            "extraction": extraction,
            "categorization": cat_result,
        }
        results.append(record)
        cat = cat_result.get("category", "unknown")
        by_category[cat] = by_category.get(cat, 0) + 1

        # Rate limit: sleep after each URL except the last
        if i < len(urls) - 1:
            time.sleep(RATE_LIMIT_DELAY)

    succeeded = sum(1 for r in results if not r["extraction"].get("extraction_failed"))
    return {
        "results": results,
        "stats": {
            "total": len(urls),
            "succeeded": succeeded,
            "failed": len(urls) - succeeded,
            "by_category": by_category,
        },
    }
