#!/usr/bin/env python3
"""
Reddit feed via PRAW (free, official API).

Drop-in alternative to ScrapeCreators Reddit. Implements the same
signal output format as last30days_feed.py so results are directly comparable.

Setup (one-time):
  1. Go to https://www.reddit.com/prefs/apps
  2. Click "create another app" → type: script
  3. Name: openclaw-research  redirect_uri: http://localhost:8080
  4. Copy client_id (under app name) and client_secret
  5. Add to .env: REDDIT_CLIENT_ID=... REDDIT_CLIENT_SECRET=...

Rate limits: 60 requests/min for OAuth (vs ~10 for public JSON). Free forever.
"""
from __future__ import annotations
import datetime
import json
import os
import sys
from typing import Optional

import praw

# ── Config ────────────────────────────────────────────────────────────────────

REDDIT_CLIENT_ID     = os.environ.get("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT    = os.environ.get("REDDIT_USER_AGENT", "openclaw-research/1.0")
REDDIT_USERNAME      = os.environ.get("REDDIT_USERNAME", "")   # optional, for higher limits
REDDIT_PASSWORD      = os.environ.get("REDDIT_PASSWORD", "")   # optional

_RESULTS_PER_QUERY   = int(os.environ.get("PRAW_RESULTS_PER_QUERY", "25"))
_COMMENT_LIMIT       = int(os.environ.get("PRAW_COMMENT_LIMIT", "5"))

# ── Sentiment ─────────────────────────────────────────────────────────────────

_BULLISH = frozenset({
    "surge", "rally", "bullish", "soar", "moon", "pump", "gains",
    "outperform", "breakout", "buy", "long", "green", "positive",
    "record", "beat", "strong", "growth", "boom", "up",
})
_BEARISH = frozenset({
    "crash", "dump", "bearish", "plunge", "drop", "fall", "sell", "short",
    "red", "negative", "collapse", "panic", "fear", "decline", "down",
    "weak", "risk", "concern", "miss", "wrong",
})


def _sentiment(text: str) -> str:
    lower = text.lower()
    bull = sum(1 for w in _BULLISH if w in lower)
    bear = sum(1 for w in _BEARISH if w in lower)
    if bull > bear and bull > 0:
        return "bullish"
    if bear > bull and bear > 0:
        return "bearish"
    return "neutral"


# ── PRAW client ───────────────────────────────────────────────────────────────

def _make_reddit() -> Optional[praw.Reddit]:
    if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
        sys.stderr.write("[praw_feed] Missing REDDIT_CLIENT_ID or REDDIT_CLIENT_SECRET\n")
        return None
    kwargs = dict(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        user_agent=REDDIT_USER_AGENT,
    )
    if REDDIT_USERNAME and REDDIT_PASSWORD:
        kwargs.update(username=REDDIT_USERNAME, password=REDDIT_PASSWORD)
    return praw.Reddit(**kwargs)


# ── Search ────────────────────────────────────────────────────────────────────

def search_reddit(
    topic: str,
    limit: int = _RESULTS_PER_QUERY,
    time_filter: str = "month",   # hour|day|week|month|year|all
    sort: str = "relevance",      # relevance|hot|top|new|comments
    subreddits: Optional[list[str]] = None,
) -> list[dict]:
    """Search Reddit via PRAW. Returns normalized post dicts.

    Args:
        topic:       Search query
        limit:       Max posts to return
        time_filter: Reddit time filter
        sort:        Sort order
        subreddits:  Optional list of subreddits to search; None = all of Reddit

    Returns:
        List of dicts with keys: id, title, url, subreddit, score, num_comments,
        date, selftext, relevance, direction, top_comments
    """
    reddit = _make_reddit()
    if reddit is None:
        return []

    now = datetime.datetime.utcnow().isoformat()
    posts = []

    try:
        if subreddits:
            for sub_name in subreddits:
                sub = reddit.subreddit(sub_name)
                for post in sub.search(topic, sort=sort, time_filter=time_filter, limit=limit):
                    posts.append(post)
        else:
            for post in reddit.subreddit("all").search(
                topic, sort=sort, time_filter=time_filter, limit=limit
            ):
                posts.append(post)
    except Exception as e:
        sys.stderr.write(f"[praw_feed] Search error: {e}\n")
        return []

    results = []
    for post in posts:
        title = post.title or ""
        body  = (post.selftext or "")[:300]
        combined = f"{title} {body}"

        # Fetch top comments (shallow, avoids extra API calls)
        top_comments = []
        try:
            post.comments.replace_more(limit=0)  # don't expand MoreComments
            for c in list(post.comments)[:_COMMENT_LIMIT]:
                if hasattr(c, "body") and c.body not in ("[deleted]", "[removed]"):
                    top_comments.append({
                        "score": c.score,
                        "body":  c.body[:200],
                        "author": str(c.author) if c.author else "[deleted]",
                    })
        except Exception:
            pass

        created = datetime.datetime.utcfromtimestamp(post.created_utc).strftime("%Y-%m-%d")

        results.append({
            "id":           f"R-praw-{post.id}",
            "title":        title,
            "url":          f"https://www.reddit.com{post.permalink}",
            "subreddit":    str(post.subreddit),
            "score":        post.score,
            "num_comments": post.num_comments,
            "date":         created,
            "selftext":     body,
            "relevance":    min(1.0, post.score / 500) if post.score > 0 else 0.3,
            "direction":    _sentiment(combined),
            "top_comments": top_comments,
            "source":       "reddit_praw",
            "fetched_at":   now,
        })

    return results


def to_signals(posts: list[dict], topic: str) -> list[dict]:
    """Convert PRAW post dicts to mirofish signal format."""
    now = datetime.datetime.utcnow().isoformat()
    signals = []
    for p in posts:
        signals.append({
            "source":      "reddit_praw",
            "ticker":      f"SENTIMENT:{topic[:20].upper().replace(' ', '_')}",
            "signal_type": "social_sentiment",
            "direction":   p["direction"],
            "amount_usd":  None,
            "description": f"[{p['direction']}|score={p['score']}] {p['title'][:180]}",
            "fetched_at":  now,
            "topic":       topic,
            "url":         p["url"],
            "relevance":   p["relevance"],
        })
    return signals


def is_configured() -> bool:
    return bool(REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("topic", help="Search topic")
    p.add_argument("--limit",       type=int, default=25)
    p.add_argument("--time-filter", default="month")
    p.add_argument("--subreddit",   action="append", help="Restrict to subreddit(s)")
    p.add_argument("--signals",     action="store_true", help="Output as signal dicts")
    args = p.parse_args()

    posts = search_reddit(
        args.topic,
        limit=args.limit,
        time_filter=args.time_filter,
        subreddits=args.subreddit,
    )
    if args.signals:
        print(json.dumps(to_signals(posts, args.topic), indent=2))
    else:
        print(json.dumps(posts, indent=2))
    sys.stderr.write(f"\n[praw_feed] {len(posts)} posts for '{args.topic}'\n")
