# Trading Volume Ramp: Fix Dormant Bots + Data Harvester

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Get all 6 trading bots actively placing bets, add a high-volume data harvester, and fix the Live Cash Position chart. Target: 200-500+ paper trades/hour for rapid strategy evaluation.

**Architecture:** Fix filter/config issues in CalendarClaw, NewsClaw, SentimentClaw so they actually trade. Add a new `dataharvester.py` that uses pure math (no LLM) to systematically bet small amounts across all available markets. Fix the balance chart seed bug.

**Tech Stack:** Python 3, SQLite, Kalshi/Polymarket feeds (existing), cron

---

## File Map

| Action | File | Purpose |
|--------|------|---------|
| Modify | `scripts/mirofish/calendarclaw.py` | Relax filters, increase caps |
| Modify | `scripts/mirofish/newsclaw.py` | Fix timeout, add non-LLM fallback |
| Modify | `scripts/mirofish/sentimentclaw.py` | Drop snapshot requirement to 1 |
| Create | `scripts/mirofish/dataharvester.py` | High-volume non-LLM systematic bettor |
| Modify | `dashboard/index.html` | Fix Live Cash Position chart seed |
| Modify | crontab | Add harvester, increase frequencies |

---

### Task 1: Fix CalendarClaw Filters

**Files:**
- Modify: `scripts/mirofish/calendarclaw.py:33-37` (constants) and `:40-76` (event families)

The crypto_daily family has `pre_window_hours: 2` which excludes markets 63hrs away. MIN_ENTRY=0.08 rejects cheap Bitcoin range contracts at $0.01-0.05. MAX_TRADES_PER_RUN=8 is too conservative.

- [ ] **Step 1: Update constants (lines 33-37)**

```python
MAX_TRADES_PER_RUN = 30       # was 8
POSITION_PCT = 0.03           # was 0.04 (smaller bets, more volume)
MIN_ENTRY = 0.03              # was 0.08 (allow cheap contracts)
MAX_ENTRY = 0.97              # was 0.92
MIN_EDGE_SCORE = 0.35         # was 0.45 (more permissive)
```

- [ ] **Step 2: Widen event family windows (lines 40-76)**

Update `crypto_daily` pre_window from 2 to 72 hours:
```python
"crypto_daily": {
    "keywords": ["bitcoin price range", "ethereum price", "btc", "eth", "bnb", "doge", "solana"],
    "pre_window_hours": 72,        # was 2
    "post_window_hours": 0.5,
    "typical_move": 0.06,
    "confidence_boost": 0.10,
},
```

Update `weather` pre_window from 6 to 48:
```python
"weather": {
    "keywords": ["temperature", "weather", "max temp", "min temp"],
    "pre_window_hours": 48,        # was 6
    "post_window_hours": 1,
    "typical_move": 0.12,
    "confidence_boost": 0.15,
},
```

- [ ] **Step 3: Lower the close_window lower bound (line 173-174)**

Change `hours_to_close > 0.1` to `hours_to_close > 0.05` to catch markets resolving in the next 3 minutes.

- [ ] **Step 4: Test manually**

```bash
cd /Users/nayslayer/openclaw && python3 -m scripts.mirofish.calendarclaw
```

Expected: Should place trades (check logs for "calendarclaw" trades placed).

- [ ] **Step 5: Verify in DB**

```bash
sqlite3 ~/.openclaw/clawmson.db "SELECT count(*) FROM paper_trades WHERE strategy='calendarclaw'"
```

Expected: Count > 0.

- [ ] **Step 6: Commit**

```bash
git add scripts/mirofish/calendarclaw.py
git commit -m "Uncap CalendarClaw: 72h crypto window, MIN_ENTRY 0.03, 30 trades/run"
```

---

### Task 2: Fix NewsClaw Timeout + Add Non-LLM Fallback

**Files:**
- Modify: `scripts/mirofish/newsclaw.py:30-36` (constants) and LLM call section

NewsClaw fails because: (a) Ollama timeout is 60s (too short for qwen2.5:7b), (b) RSS feeds may return no new items, (c) even with headlines, LLM matching is slow. Fix: increase timeout AND add a keyword-based fallback that doesn't need LLM.

- [ ] **Step 1: Update constants (lines 30-36)**

```python
MAX_TRADES_PER_RUN = 20       # was 6
POSITION_PCT = 0.03           # was 0.04
MIN_ENTRY = 0.03              # was 0.08
MAX_ENTRY = 0.97              # was 0.92
MIN_EDGE_SCORE = 0.40         # was 0.72 (way too high — almost nothing passes)
```

- [ ] **Step 2: Increase Ollama timeout (line ~193)**

Find the `requests.post` call to Ollama and change timeout from 60 to 180:

```python
resp = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=180)  # was 60
```

- [ ] **Step 3: Add keyword fallback after the LLM match section**

After the LLM matching function, add a fallback that matches headlines to markets using simple keyword overlap (no LLM needed). This ensures trades happen even when Ollama is slow/down:

```python
def keyword_match_fallback(headlines, markets):
    """Match headlines to markets by keyword overlap when LLM is unavailable."""
    matches = []
    for h in headlines:
        h_words = set(h.get("title", "").lower().split())
        for m in markets:
            m_words = set(m.get("title", "").lower().split())
            overlap = h_words & m_words - {"the", "a", "an", "in", "on", "at", "to", "of", "is", "and", "or", "for", "will", "be"}
            if len(overlap) >= 3:
                matches.append({
                    "headline": h["title"],
                    "market_id": m["ticker"],
                    "question": m["title"],
                    "direction": "YES",  # default; headline mentions = attention = YES bias
                    "confidence": min(0.5 + len(overlap) * 0.05, 0.85),
                    "reasoning": f"keyword overlap: {overlap}",
                })
    return matches
```

In the main flow, wrap the LLM call in try/except and fall back:

```python
try:
    llm_matches = match_headlines_to_markets(headlines, markets)
except Exception as e:
    print(f"[news] LLM failed ({e}), using keyword fallback")
    llm_matches = keyword_match_fallback(headlines, markets)
```

- [ ] **Step 4: Add more RSS feeds for crypto/prediction market coverage**

Append to `RSS_FEEDS` list:
```python
RSS_FEEDS = [
    "https://feeds.bbci.co.uk/news/rss.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
    "https://feeds.reuters.com/reuters/topNews",
    "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "https://cointelegraph.com/rss",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
]
```

- [ ] **Step 5: Test manually**

```bash
cd /Users/nayslayer/openclaw && python3 -m scripts.mirofish.newsclaw
```

- [ ] **Step 6: Commit**

```bash
git add scripts/mirofish/newsclaw.py
git commit -m "Uncap NewsClaw: 180s timeout, keyword fallback, crypto RSS, 20 trades/run"
```

---

### Task 3: Fix SentimentClaw Snapshot Requirement

**Files:**
- Modify: `scripts/mirofish/sentimentclaw.py:27-32` (constants) and `:106-107` (snapshot check)

SentimentClaw requires 3+ price snapshots but only 1 exists per market. Fix: work with 1 snapshot using absolute price levels instead of requiring historical comparison.

- [ ] **Step 1: Update constants (lines 27-32)**

```python
MAX_TRADES_PER_RUN = 25       # was 6
POSITION_PCT = 0.03           # was 0.03 (keep)
MIN_ENTRY = 0.03              # was 0.08
MAX_ENTRY = 0.97              # was 0.92
VOLUME_SPIKE_MULT = 1.2       # was 1.5 (easier to trigger)
PRICE_STALE_THRESHOLD = 0.05  # was 0.02 (more permissive)
```

- [ ] **Step 2: Change snapshot requirement from 3 to 1 (line 106-107)**

Replace:
```python
if len(vol_history) < 3:
    continue
```

With:
```python
if len(vol_history) < 1:
    continue
```

- [ ] **Step 3: Fix baseline calc for single-snapshot case (lines 110-112)**

Replace:
```python
current_vol = volumes[0]
baseline_vol = sum(volumes[1:]) / len(volumes[1:]) if len(volumes) > 1 else 0
```

With:
```python
current_vol = volumes[0]
if len(volumes) > 1:
    baseline_vol = sum(volumes[1:]) / len(volumes[1:])
else:
    # Single snapshot: use absolute volume threshold instead
    baseline_vol = 5000  # treat $5k as "normal" — anything above triggers
```

- [ ] **Step 4: Add absolute-price fallback for single-snapshot case**

After the volume spike check, add a secondary strategy for markets with only 1 snapshot — trade based on extreme pricing (contracts near 0 or 1 are likely mispriced):

```python
# Fallback: extreme pricing strategy (no history needed)
if len(vol_history) == 1 and not direction:
    ya = _norm(vol_history[0].get("yes_ask") or vol_history[0].get("yes_bid", 0.5))
    if ya < 0.15:
        direction = "YES"
        entry = ya
        score = 0.55
        thesis = f"extreme low price {ya:.2f} — mean-reversion bet"
    elif ya > 0.85:
        direction = "NO"
        entry = _norm(vol_history[0].get("no_ask") or vol_history[0].get("no_bid", 0.5))
        score = 0.55
        thesis = f"extreme high price {ya:.2f} — fade to fair value"
```

- [ ] **Step 5: Test manually**

```bash
cd /Users/nayslayer/openclaw && python3 -m scripts.mirofish.sentimentclaw
```

- [ ] **Step 6: Commit**

```bash
git add scripts/mirofish/sentimentclaw.py
git commit -m "Uncap SentimentClaw: single-snapshot mode, extreme-price fallback, 25 trades/run"
```

---

### Task 4: Create Data Harvester (High-Volume Non-LLM Bettor)

**Files:**
- Create: `scripts/mirofish/dataharvester.py`

Pure-math systematic bettor. No LLM. Scans ALL available Kalshi + Polymarket markets, places small $3-5 paper bets on any market with exploitable pricing. Strategies: (1) fair-value deviation, (2) spread capture, (3) near-expiry convergence. Target: 50+ trades per run, runs every 2 minutes.

- [ ] **Step 1: Create dataharvester.py**

```python
#!/usr/bin/env python3
"""
DataHarvester — high-volume non-LLM systematic bettor.
Places small paper bets across ALL available markets for data collection.
No Ollama. Pure math. Runs every 2 minutes via cron.
"""
import os, sys, sqlite3, time, json, requests
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(os.environ.get("CLAWMSON_DB_PATH", Path.home() / ".openclaw" / "clawmson.db"))

MAX_TRADES_PER_RUN = 50
BET_SIZE_USD = 4.0           # small fixed bet size
MIN_ENTRY = 0.03
MAX_ENTRY = 0.97
MIN_HOURS_TO_CLOSE = 0.05   # 3 minutes
MAX_HOURS_TO_CLOSE = 168     # 7 days
FAIR_VALUE = 0.50            # prior assumption for unknown markets
EDGE_THRESHOLD = 0.08        # 8% deviation from fair value triggers trade
DASHBOARD_URL = "http://127.0.0.1:7080/api/trading/notify"


def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def get_open_ids(conn):
    rows = conn.execute("SELECT market_id FROM paper_trades WHERE status='open'").fetchall()
    return {r["market_id"] for r in rows}


def get_balance(conn):
    starting = 1000.0
    ctx = conn.execute(
        "SELECT value FROM context WHERE chat_id='mirofish' AND key='starting_balance'"
    ).fetchone()
    if ctx:
        starting = float(ctx[0])
    closed_pnl = conn.execute(
        "SELECT COALESCE(SUM(pnl), 0) FROM paper_trades WHERE status IN ('closed_win','closed_loss','expired')"
    ).fetchone()[0]
    return starting + closed_pnl


def fetch_kalshi_markets(conn):
    """Get all cached Kalshi markets from DB."""
    rows = conn.execute("""
        SELECT ticker, title, yes_bid, yes_ask, no_bid, no_ask,
               volume, close_time, event_ticker
        FROM kalshi_markets
        WHERE status='open' AND close_time IS NOT NULL
        ORDER BY close_time ASC
    """).fetchall()
    return [dict(r) for r in rows]


def fetch_polymarket_markets(conn):
    """Get all cached Polymarket markets from DB."""
    rows = conn.execute("""
        SELECT market_id, question, yes_price, no_price, volume, end_date
        FROM market_data
        WHERE end_date IS NOT NULL
        GROUP BY market_id
        HAVING fetched_at = MAX(fetched_at)
        ORDER BY end_date ASC
    """).fetchall()
    return [dict(r) for r in rows]


def hours_until(iso_str):
    """Parse ISO datetime and return hours from now."""
    try:
        if iso_str.endswith("Z"):
            iso_str = iso_str[:-1] + "+00:00"
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return (dt - now).total_seconds() / 3600
    except Exception:
        return None


def score_kalshi(m):
    """Score a Kalshi market. Returns (direction, entry, confidence, thesis) or None."""
    ya = float(m.get("yes_ask") or 0)
    na = float(m.get("no_ask") or 0)
    yb = float(m.get("yes_bid") or 0)

    # Strategy 1: Fair-value deviation (contracts far from 0.50)
    mid = (ya + yb) / 2 if ya > 0 and yb > 0 else ya if ya > 0 else 0.5
    deviation = abs(mid - FAIR_VALUE)

    if deviation >= EDGE_THRESHOLD:
        if mid < FAIR_VALUE - EDGE_THRESHOLD and ya > 0 and MIN_ENTRY <= ya <= MAX_ENTRY:
            conf = min(0.5 + deviation, 0.85)
            return ("YES", ya, conf, f"underpriced YES mid={mid:.3f}")
        elif mid > FAIR_VALUE + EDGE_THRESHOLD and na > 0 and MIN_ENTRY <= na <= MAX_ENTRY:
            conf = min(0.5 + deviation, 0.85)
            return ("NO", na, conf, f"overpriced YES mid={mid:.3f}")

    # Strategy 2: Near-expiry convergence (< 2h to close, strong lean)
    h = hours_until(m.get("close_time", ""))
    if h and h < 2:
        if mid > 0.75 and ya > 0 and ya <= MAX_ENTRY:
            return ("YES", ya, 0.65, f"near-expiry lean YES mid={mid:.3f} {h:.1f}h left")
        elif mid < 0.25 and na > 0 and na <= MAX_ENTRY:
            return ("NO", na, 0.65, f"near-expiry lean NO mid={mid:.3f} {h:.1f}h left")

    # Strategy 3: Spread capture (wide spread = opportunity)
    if ya > 0 and yb > 0:
        spread = ya - yb
        if spread > 0.10 and ya <= MAX_ENTRY:
            # Buy the cheaper side
            if ya < 0.5:
                return ("YES", ya, 0.50, f"spread capture YES spread={spread:.3f}")
            elif na > 0 and na <= MAX_ENTRY:
                return ("NO", na, 0.50, f"spread capture NO spread={spread:.3f}")

    return None


def score_polymarket(m):
    """Score a Polymarket market. Returns (direction, entry, confidence, thesis) or None."""
    yp = float(m.get("yes_price") or 0.5)
    np = float(m.get("no_price") or 0.5)

    deviation = abs(yp - FAIR_VALUE)
    if deviation >= EDGE_THRESHOLD:
        if yp < FAIR_VALUE - EDGE_THRESHOLD and MIN_ENTRY <= yp <= MAX_ENTRY:
            return ("YES", yp, min(0.5 + deviation, 0.85), f"poly underpriced YES={yp:.3f}")
        elif yp > FAIR_VALUE + EDGE_THRESHOLD and MIN_ENTRY <= np <= MAX_ENTRY:
            return ("NO", np, min(0.5 + deviation, 0.85), f"poly overpriced YES={yp:.3f}")

    return None


def place_trade(conn, market_id, question, direction, entry, confidence, thesis, balance):
    """Insert paper trade directly into DB."""
    amount = min(BET_SIZE_USD, balance * 0.05)
    if amount < 1:
        return False
    shares = amount / entry if entry > 0 else 0
    if shares <= 0:
        return False

    ts = datetime.now(timezone.utc).isoformat()
    conn.execute("""
        INSERT INTO paper_trades
        (market_id, question, direction, shares, entry_price, amount_usd,
         status, confidence, reasoning, strategy, opened_at)
        VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?)
    """, (
        market_id, question[:200], direction, shares, entry, amount,
        confidence, f"dataharvester: {thesis}", "dataharvester", ts,
    ))
    return True


def run():
    conn = get_conn()
    balance = get_balance(conn)
    open_ids = get_open_ids(conn)
    placed = 0
    now_utc = datetime.now(timezone.utc)

    print(f"[harvester] {now_utc.isoformat()} balance=${balance:.2f} open={len(open_ids)}")

    # Scan Kalshi markets
    kalshi = fetch_kalshi_markets(conn)
    for m in kalshi:
        if placed >= MAX_TRADES_PER_RUN:
            break
        ticker = m.get("ticker", "")
        if ticker in open_ids:
            continue
        h = hours_until(m.get("close_time", ""))
        if h is None or h < MIN_HOURS_TO_CLOSE or h > MAX_HOURS_TO_CLOSE:
            continue
        result = score_kalshi(m)
        if result:
            direction, entry, conf, thesis = result
            if place_trade(conn, ticker, m.get("title", "")[:200], direction, entry, conf, thesis, balance):
                placed += 1
                open_ids.add(ticker)
                print(f"  [K] {direction} {entry:.3f} c={conf:.2f} | {m.get('title','')[:50]} | {thesis}")

    # Scan Polymarket markets
    poly = fetch_polymarket_markets(conn)
    for m in poly:
        if placed >= MAX_TRADES_PER_RUN:
            break
        mid = m.get("market_id", "")
        if mid in open_ids:
            continue
        h = hours_until(m.get("end_date", ""))
        if h is None or h < MIN_HOURS_TO_CLOSE or h > MAX_HOURS_TO_CLOSE:
            continue
        result = score_polymarket(m)
        if result:
            direction, entry, conf, thesis = result
            if place_trade(conn, mid, m.get("question", "")[:200], direction, entry, conf, thesis, balance):
                placed += 1
                open_ids.add(mid)
                print(f"  [P] {direction} {entry:.3f} c={conf:.2f} | {m.get('question','')[:50]} | {thesis}")

    conn.commit()
    conn.close()

    print(f"[harvester] placed {placed} trades")

    # Notify dashboard
    if placed > 0:
        try:
            requests.post(DASHBOARD_URL, json={"source": "dataharvester", "trades": placed}, timeout=5)
        except Exception:
            pass


if __name__ == "__main__":
    run()
```

- [ ] **Step 2: Test manually**

```bash
cd /Users/nayslayer/openclaw && python3 -m scripts.mirofish.dataharvester
```

Expected: Places 10-50 trades depending on available markets.

- [ ] **Step 3: Verify in DB**

```bash
sqlite3 ~/.openclaw/clawmson.db "SELECT count(*) FROM paper_trades WHERE strategy='dataharvester'"
```

- [ ] **Step 4: Commit**

```bash
git add scripts/mirofish/dataharvester.py
git commit -m "feat: DataHarvester — high-volume non-LLM systematic bettor (50 trades/run)"
```

---

### Task 5: Fix Live Cash Position Chart

**Files:**
- Modify: `dashboard/index.html` (seedBalanceHistory function)

Chart requires `balanceHistory.length >= 2` but with few closed trades, only 1 point exists. Fix: always seed at least 2 points.

- [ ] **Step 1: Find seedBalanceHistory function and add minimum seed**

After `seedBalanceHistory(d)` builds the initial array, add:

```javascript
// Ensure at least 2 points so chart renders
if (balanceHistory.length < 2) {
  const base = (d.wallet && d.wallet.starting_balance) || 1000
  while (balanceHistory.length < 2) {
    balanceHistory.unshift({ time: Date.now() - 60000 * (2 - balanceHistory.length), balance: base })
  }
}
```

- [ ] **Step 2: Bump version to v24.5**

- [ ] **Step 3: Restart server and verify chart renders**

```bash
lsof -ti :7080 | xargs kill -9 2>/dev/null; sleep 2
cd /Users/nayslayer/openclaw/dashboard && nohup python3 server.py > /dev/null 2>&1 &
sleep 3; curl -s http://127.0.0.1:7080/ | grep "v24.5"
```

- [ ] **Step 4: Commit**

```bash
git add dashboard/index.html
git commit -m "Fix Live Cash Position: seed chart with 2+ points so it always renders"
```

---

### Task 6: Update Crontab for Maximum Volume

**Current state:** CalendarClaw/NewsClaw/SentimentClaw every 5min, PhantomClaw every 2min, simulator every 30min.

**Target state:** Add dataharvester every 2min, keep sub-agents at 5min (they're cheap), keep PhantomClaw at 2min.

- [ ] **Step 1: Add dataharvester to crontab**

```bash
(crontab -l; echo "*/2 * * * * cd /Users/nayslayer/openclaw && python3 -m scripts.mirofish.dataharvester >> logs/dataharvester.log 2>&1") | crontab -
```

- [ ] **Step 2: Verify crontab**

```bash
crontab -l | grep -E "harvester|calendar|news|sentiment|phantom"
```

Expected: All 5 bots scheduled.

- [ ] **Step 3: Monitor first 5 minutes of output**

```bash
tail -f logs/dataharvester.log logs/calendarclaw.log logs/newsclaw.log logs/sentimentclaw.log
```

- [ ] **Step 4: Commit plan doc**

```bash
git add docs/superpowers/plans/2026-03-24-trading-volume-ramp.md
git commit -m "docs: trading volume ramp plan — fix 3 dormant bots + data harvester"
```

---

### Task 7: Register DataHarvester in Dashboard

**Files:**
- Modify: `dashboard/server.py` (~line 1084+) — add dataharvester stats to the `/api/trading/dashboard` response
- Modify: `dashboard/index.html` — add harvester to the agent cards section

- [ ] **Step 1: In server.py, add dataharvester to the agents dict**

In the `get_trading_dashboard()` function, after the sentimentclaw agent stats block, add dataharvester using the same pattern:

```python
# DataHarvester stats
dh_stats = {"trades": 0, "wins": 0, "losses": 0, "pnl": 0, "open": 0, "win_rate": 0, "positions": []}
try:
    dh_closed = conn.execute("""
        SELECT COUNT(*) as n, SUM(CASE WHEN status='closed_win' THEN 1 ELSE 0 END) as w,
               COALESCE(SUM(pnl), 0) as p
        FROM paper_trades WHERE strategy='dataharvester' AND status IN ('closed_win','closed_loss','expired')
    """).fetchone()
    dh_open = conn.execute("""
        SELECT * FROM paper_trades WHERE strategy='dataharvester' AND status='open'
        ORDER BY opened_at DESC
    """).fetchall()
    dh_positions = []
    for po in dh_open:
        dh_positions.append(dict(po))
    dhn = dh_closed["n"] or 0
    dhw = dh_closed["w"] or 0
    dhp = dh_closed["p"] or 0
    dh_stats = {
        "trades": dhn, "wins": dhw, "losses": dhn - dhw,
        "pnl": round(dhp, 2),
        "win_rate": round(dhw / dhn * 100, 1) if dhn > 0 else 0,
        "open": len(dh_open),
        "positions": dh_positions[:20],
    }
except Exception as e:
    dh_stats["error"] = str(e)
```

Add to the agents dict in the response:
```python
"agents": {
    "calendarclaw": cal_stats,
    "newsclaw": news_stats,
    "sentimentclaw": sent_stats,
    "dataharvester": dh_stats,
},
```

- [ ] **Step 2: In index.html, add dataharvester to agentConfigs array**

Find the `agentConfigs` array in renderTrading() and add:
```javascript
{name: 'dataharvester', pnl: 'dhPnl', wl: 'dhWL', open: 'dhOpen', body: 'dhBody', color: '#ff6600'},
```

- [ ] **Step 3: Add dataharvester HTML card in the bot cards grid**

Add a new card after SentimentClaw in the HTML, following the same pattern.

- [ ] **Step 4: Add dataharvester to buildUnifiedFeed agent loop**

In the `buildUnifiedFeed` function, add `'dataharvester'` to the agent names loop:
```javascript
for (const [name, cfg] of [['calendarclaw','#00c8ff'],['newsclaw','#ffc800'],['sentimentclaw','#00ff88'],['dataharvester','#ff6600']]) {
```

- [ ] **Step 5: Restart server, verify harvester card appears**

- [ ] **Step 6: Commit**

```bash
git add dashboard/server.py dashboard/index.html
git commit -m "feat: DataHarvester dashboard card + unified feed integration"
```

---

## Expected Outcome After All Tasks

| Bot | Before | After |
|-----|--------|-------|
| PhantomClaw | 12/run, every 2min | 12/run, every 2min (unchanged) |
| RivalClaw | ~25 open, every 1min | ~25 open, every 1min (unchanged) |
| Clawmpson (simulator) | 5/run, every 30min | 5/run, every 30min (unchanged) |
| CalendarClaw | 0 trades ever | 30/run, every 5min |
| NewsClaw | 0 trades ever | 20/run, every 5min |
| SentimentClaw | 0 trades ever | 25/run, every 5min |
| **DataHarvester** | **N/A** | **50/run, every 2min** |

**Conservative estimate:** 200-400 trades/hour across all bots.
**Live Cash Position:** Chart now renders with 2+ seed points.
