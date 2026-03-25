#!/usr/bin/env python3
"""
NewsClaw — event-driven prediction market trading.
Monitors RSS feeds for breaking news, matches to open markets, trades before reprice.

Uses qwen2.5:7b for fast event classification + market matching.
Runs every 5 minutes. LLM-assisted but fast (single focused prompt).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import datetime
import time
import requests
from pathlib import Path

def _load_env():
    env_file = Path.home() / "openclaw" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

# Config
MAX_TRADES_PER_RUN = 20       # was 6
POSITION_PCT = 0.03           # was 0.04
MIN_ENTRY = 0.03              # was 0.08
MAX_ENTRY = 0.97              # was 0.92
OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
NEWSCLAW_MODEL = os.environ.get("NEWSCLAW_MODEL", "qwen2.5:7b")
MIN_EDGE_SCORE = 0.40         # was 0.72 (way too high)

# RSS feeds (Tier 1 and 2 sources)
RSS_FEEDS = [
    "https://feeds.bbci.co.uk/news/rss.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
    "https://feeds.reuters.com/reuters/topNews",
    "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "https://cointelegraph.com/rss",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
]

SEEN_FILE = Path.home() / "openclaw" / "logs" / ".newsclaw_seen.json"


def _get_conn():
    db_path = Path(os.environ.get("CLAWMSON_DB_PATH",
                                   Path.home() / ".openclaw" / "clawmson.db"))
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _notify():
    try:
        requests.post("http://127.0.0.1:7080/api/trading/notify", timeout=2)
    except Exception:
        pass


def _norm(v):
    if v is None: return 0
    f = float(v)
    return f / 100.0 if f > 1 else f


def _get_balance(conn) -> float:
    """NewsClaw's own $1000 virtual wallet — only counts its own trades."""
    try:
        pnl = conn.execute("SELECT COALESCE(SUM(pnl), 0) FROM paper_trades WHERE strategy='newsclaw' AND status IN ('closed_win','closed_loss','expired')").fetchone()[0]
        return 1000.0 + pnl
    except Exception:
        return 1000.0


def _load_seen() -> set:
    if SEEN_FILE.exists():
        try:
            return set(json.loads(SEEN_FILE.read_text()))
        except Exception:
            pass
    return set()


def _save_seen(seen: set):
    # Keep last 500 to prevent unbounded growth
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(list(seen)[-500:]))


def _hash_headline(text: str) -> str:
    return hashlib.md5(text.lower().strip().encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# RSS ingestion
# ---------------------------------------------------------------------------
def fetch_headlines() -> list[dict]:
    """Fetch fresh headlines from RSS feeds."""
    headlines = []
    seen = _load_seen()

    for feed_url in RSS_FEEDS:
        try:
            resp = requests.get(feed_url, timeout=10)
            if resp.status_code != 200:
                continue

            # Simple XML parsing (no lxml dependency)
            text = resp.text
            items = re.findall(r'<item>(.*?)</item>', text, re.DOTALL)
            if not items:
                items = re.findall(r'<entry>(.*?)</entry>', text, re.DOTALL)

            for item in items[:10]:
                title_match = re.search(r'<title[^>]*>(.*?)</title>', item, re.DOTALL)
                if not title_match:
                    continue
                title = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', title_match.group(1)).strip()
                title = re.sub(r'<[^>]+>', '', title).strip()

                h = _hash_headline(title)
                if h in seen:
                    continue
                seen.add(h)

                desc_match = re.search(r'<description[^>]*>(.*?)</description>', item, re.DOTALL)
                desc = ""
                if desc_match:
                    desc = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', desc_match.group(1)).strip()
                    desc = re.sub(r'<[^>]+>', '', desc).strip()

                headlines.append({
                    "title": title,
                    "description": desc[:300],
                    "source": feed_url.split("/")[2],
                    "hash": h,
                })

        except Exception as e:
            continue

    _save_seen(seen)
    return headlines


# ---------------------------------------------------------------------------
# LLM matching: headline → market
# ---------------------------------------------------------------------------
def match_headlines_to_markets(headlines: list[dict], markets: list[dict]) -> list[dict]:
    """Use LLM to match breaking headlines to open prediction markets."""
    if not headlines or not markets:
        return []

    # Build market list for prompt
    market_lines = "\n".join(
        f'- [{m["ticker"]}] {m["title"][:60]} YES={_norm(m["yes_ask"]):.2f}'
        for m in markets[:40]
    )

    headline_lines = "\n".join(
        f'- [{h["hash"]}] {h["title"]}'
        for h in headlines[:15]
    )

    prompt = f"""You are NewsClaw, a fast event-driven trading signal agent.

BREAKING HEADLINES:
{headline_lines}

OPEN PREDICTION MARKETS:
{market_lines}

For each headline that DIRECTLY affects an open market's outcome:
1. Which market(s) does it affect?
2. Does it make YES or NO more likely?
3. How confident are you (0.0-1.0)?
4. One-sentence why

Return ONLY a JSON array. If no matches, return [].
[{{"headline_hash": "...", "market_id": "...", "direction": "YES|NO", "confidence": 0.0-1.0, "reasoning": "..."}}]
"""

    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={"model": NEWSCLAW_MODEL, "messages": [{"role": "user", "content": prompt}], "stream": False},
            timeout=180,
        )
        resp.raise_for_status()
        text = resp.json().get("message", {}).get("content", "")

        # Extract JSON
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            m = re.search(r'\[.*\]', text, re.DOTALL)
            if m:
                return json.loads(m.group())
    except Exception as e:
        print(f"[news] LLM error: {e}")

    return []


def keyword_match_fallback(headlines, markets):
    """Match headlines to markets by keyword overlap when LLM is unavailable."""
    stopwords = {"the", "a", "an", "in", "on", "at", "to", "of", "is", "and", "or", "for", "will", "be", "has", "have", "it", "its", "this", "that", "with"}
    matches = []
    for h in headlines:
        h_words = set(h.get("title", "").lower().split()) - stopwords
        for m in markets:
            m_title = m.get("title", "") or m.get("question", "") or ""
            m_words = set(m_title.lower().split()) - stopwords
            overlap = h_words & m_words
            if len(overlap) >= 3:
                # Determine direction from headline sentiment (simple)
                title_lower = h.get("title", "").lower()
                direction = "NO" if any(w in title_lower for w in ["fall", "drop", "crash", "decline", "down", "risk", "fear"]) else "YES"
                ya = float(m.get("yes_ask") or m.get("yes_bid") or 0.5)
                na = float(m.get("no_ask") or m.get("no_bid") or 0.5)
                entry = ya if direction == "YES" else na
                matches.append({
                    "headline": h["title"],
                    "market_id": m.get("ticker", m.get("market_id", "")),
                    "question": m_title,
                    "direction": direction,
                    "entry": entry,
                    "confidence": min(0.5 + len(overlap) * 0.05, 0.85),
                    "reasoning": f"keyword overlap: {overlap}",
                })
    return matches


def run():
    try:
        from scripts.mirofish.paper_wallet import check_circuit_breaker, reset_wallet
        breaker = check_circuit_breaker()
        if breaker:
            print("[news] Circuit breaker")
            reset_wallet()
            _notify()
            return
    except Exception:
        pass

    conn = _get_conn()
    balance = _get_balance(conn)
    open_ids = set(r[0] for r in conn.execute("SELECT market_id FROM paper_trades WHERE status='open'").fetchall())

    # Fetch headlines
    headlines = fetch_headlines()
    if not headlines:
        print("[news] No new headlines")
        conn.close()
        return

    print(f"[news] {len(headlines)} new headlines")

    # Get active markets
    markets = conn.execute("""
        SELECT km.ticker, km.title, km.yes_bid, km.yes_ask, km.no_bid, km.no_ask,
               km.close_time, km.event_ticker, km.volume_24h
        FROM kalshi_markets km
        INNER JOIN (SELECT ticker, MAX(fetched_at) as latest FROM kalshi_markets GROUP BY ticker) l
        ON km.ticker = l.ticker AND km.fetched_at = l.latest
        WHERE (km.yes_ask > 0 OR km.yes_bid > 0) AND km.close_time IS NOT NULL
    """).fetchall()

    try:
        llm_matches = match_headlines_to_markets(headlines, [dict(m) for m in markets])
    except Exception as e:
        print(f"[news] LLM failed ({e}), using keyword fallback")
        llm_matches = keyword_match_fallback(headlines, [dict(m) for m in markets])
    matches = llm_matches
    placed = 0

    for match in matches:
        if placed >= MAX_TRADES_PER_RUN:
            break

        market_id = match.get("market_id", "")
        direction = match.get("direction", "").upper()
        confidence = float(match.get("confidence", 0))

        if not market_id or direction not in ("YES", "NO") or confidence < 0.65:
            continue
        if market_id in open_ids:
            continue

        # Find market data
        mkt = None
        for m in markets:
            if m["ticker"] == market_id:
                mkt = m
                break
        if not mkt:
            continue

        ya = _norm(mkt["yes_ask"]) or _norm(mkt["yes_bid"])
        na = _norm(mkt["no_ask"]) or _norm(mkt["no_bid"])
        entry = ya if direction == "YES" else na

        if entry < MIN_ENTRY or entry > MAX_ENTRY:
            continue

        amount = min(POSITION_PCT * balance, balance * 0.10)
        if amount < 2:
            continue

        shares = amount / entry
        reasoning = match.get("reasoning", "news catalyst")

        try:
            conn.execute("""
                INSERT INTO paper_trades
                (market_id, question, direction, shares, entry_price, amount_usd,
                 status, confidence, reasoning, strategy, opened_at)
                VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?)
            """, (
                market_id, (mkt["title"] or "")[:200], direction, shares, entry, amount,
                confidence,
                f"newsclaw: {reasoning[:150]}",
                "newsclaw", datetime.datetime.utcnow().isoformat(),
            ))
            conn.commit()
            placed += 1
            open_ids.add(market_id)
            print(f"[news] {direction} ${amount:.0f} '{mkt['title'][:40]}' conf={confidence:.2f}")
        except Exception as e:
            print(f"[news] Error: {e}")

    # Resolve
    resolved = 0
    try:
        from scripts.mirofish.kalshi_feed import _call_kalshi
        trades = conn.execute(
            "SELECT id, market_id, direction, entry_price, shares FROM paper_trades WHERE status='open' AND strategy='newsclaw'"
        ).fetchall()
        for t in trades:
            data = _call_kalshi("GET", f"/markets/{t['market_id']}")
            if not data: continue
            m = data.get("market", data)
            result = m.get("result", "")
            if not result: continue
            we_won = (result == t["direction"].lower())
            exit_price = 1.0 if we_won else 0.0
            pnl = t["shares"] * (exit_price - t["entry_price"])
            conn.execute("UPDATE paper_trades SET exit_price=?, pnl=?, status=?, closed_at=? WHERE id=?",
                         (exit_price, pnl, "closed_win" if we_won else "closed_loss", datetime.datetime.utcnow().isoformat(), t["id"]))
            resolved += 1
        if resolved: conn.commit()
    except Exception:
        pass

    conn.close()
    if placed > 0 or resolved > 0:
        print(f"[news] Placed {placed}, resolved {resolved}")
        _notify()


if __name__ == "__main__":
    _load_env()
    run()
