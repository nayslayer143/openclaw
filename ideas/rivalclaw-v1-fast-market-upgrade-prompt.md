# RivalClaw v1 — Fast Market Scanner Upgrade

**Feed this to Claude Code with ~/rivalclaw/ mounted.**

---

```
# RivalClaw v1 — Fast Market Scanner Upgrade

Read ~/rivalclaw/CLAUDE.md before writing any code.
Read ~/rivalclaw/trading_brain.py to understand existing strategies.
Read ~/rivalclaw/polymarket_feed.py and ~/rivalclaw/kalshi_feed.py to understand existing feeds.
Read ~/rivalclaw/simulator.py to understand the orchestration loop.

## What This Is

An upgrade to RivalClaw v1's existing market selection and scoring. Right now RivalClaw trades whatever markets it finds. This upgrade adds a fast-market classification layer so it prioritizes markets that resolve quickly — maximizing capital velocity (how many times $1 cycles per day).

This is NOT RivalClaw v2. Do NOT restructure the codebase. Extend what exists.

## Core Insight

A 1% edge cycling 3x/day beats a 5% edge cycling once a week. RivalClaw should hunt the fastest-resolving markets first and deprioritize slow ones.

## Build 2 Things

### 1. Market Classifier: ~/rivalclaw/market_classifier.py

A new module that scores every market on resolution speed and clarity before trading_brain.py sees it.

**Resolution Speed Score:**
```python
def resolution_speed_score(market: dict) -> int:
    """
    +3 → resolves same-day (sports results, daily weather)
    +2 → resolves within 48h (weekend events, short-term weather)
    +1 → resolves within 7 days (weekly econ data)
     0 → unknown or ambiguous timing
    -1 → subjective resolution risk (narrative, interpretation needed)
    """
```

Classification heuristics (use title + category + resolution criteria):
- Sports keywords: "win", "beat", "game", "match", "score", "NBA", "NFL", "NHL", "soccer", "UFC" → +3
- Weather keywords: "rain", "snow", "temperature", "weather", "degrees", "inches" → +3
- Econ keywords: "CPI", "unemployment", "Fed", "rate", "jobless", "GDP", "inflation" → +2
- Event keywords: "announce", "launch", "keynote", "earnings" → +1 to +2 (check if timestamped)
- Politics without election day: "policy", "bill", "legislation" → 0 to -1
- Narrative/subjective: "will X happen", long-dated, no clear trigger → -1

**Resolution Clarity Score:**
```python
def resolution_clarity_score(market: dict) -> int:
    """
    +3 → objective data source (sports API, NOAA weather, official stats)
    +2 → official release (BLS, Fed, earnings report)
    +1 → semi-objective (event attendance, box office)
     0 → subjective or media-dependent
    """
```

**Time Decay Priority:**
```python
def time_decay_score(market: dict) -> int:
    """Based on scheduled resolution time vs now.
    <6h  → +3
    <24h → +2
    <72h → +1
    else → 0
    """
```

**Combined Market Priority Score:**
```python
def market_priority(market: dict) -> float:
    speed = resolution_speed_score(market)
    clarity = resolution_clarity_score(market)
    decay = time_decay_score(market)
    return (speed * 2) + (clarity * 2) + decay
```

Store the scores in rivalclaw.db. Add a table:
```sql
CREATE TABLE IF NOT EXISTS market_scores (
    market_id TEXT PRIMARY KEY,
    platform TEXT,
    title TEXT,
    speed_score INTEGER,
    clarity_score INTEGER,
    decay_score INTEGER,
    priority_score REAL,
    category TEXT,
    scored_at TEXT
);
```

### 2. Integration into existing pipeline

Modify simulator.py to use market_classifier.py:

**Before trading_brain.py processes markets:**
1. Run all fetched markets through market_classifier.py
2. Sort by priority_score descending
3. Pass only markets with priority_score >= 3 to the trading brain (configurable threshold)
4. Log skipped markets with reason to rivalclaw.log

**In trading_brain.py (extend, don't rewrite):**
- Add priority_score to the signal context so strategies can weight faster markets
- When two opportunities have similar expected edge, prefer the one with higher priority_score
- Add a `velocity_preference` parameter (default 1.5) that multiplies priority_score into the final trade ranking

**In the daily report (daily-update.sh or wherever reports generate):**
- Add a section: "Market Speed Breakdown"
  - How many markets scored +3/+2/+1/0/-1
  - Capital allocated to fast vs slow markets
  - PnL breakdown by speed tier
  - Capital velocity: total capital cycled / starting capital

## Category Detection Keywords (for the classifier)

```python
CATEGORY_PATTERNS = {
    "sports": {
        "keywords": ["win", "beat", "game", "match", "score", "playoff", "championship",
                     "NBA", "NFL", "NHL", "MLB", "UFC", "soccer", "football", "basketball",
                     "tennis", "boxing", "Super Bowl", "World Series", "finals"],
        "speed": 3, "clarity": 3
    },
    "weather": {
        "keywords": ["rain", "snow", "temperature", "degrees", "inches", "weather",
                     "hurricane", "tornado", "forecast", "NOAA", "precipitation",
                     "heat", "cold", "storm", "wind"],
        "speed": 3, "clarity": 3
    },
    "econ": {
        "keywords": ["CPI", "inflation", "unemployment", "jobless", "GDP", "Fed",
                     "interest rate", "FOMC", "payroll", "retail sales", "housing starts",
                     "consumer confidence", "PMI", "earnings"],
        "speed": 2, "clarity": 2
    },
    "event": {
        "keywords": ["announce", "launch", "keynote", "conference", "premiere",
                     "release", "debut", "unveil", "award", "Oscar", "Grammy",
                     "Emmy", "box office"],
        "speed": 1, "clarity": 1
    },
    "politics": {
        "keywords": ["election", "vote", "ballot", "primary", "caucus", "senate",
                     "congress", "bill", "legislation", "president", "governor"],
        "speed": 0, "clarity": 0  # override to +2/+2 if "election day" or "vote today"
    },
}
```

## Cross-Platform Speed Edge (important context)

Polymarket reacts faster to news (crypto-native crowd). Kalshi lags slightly but resolves more cleanly. This mismatch is structural, not temporary.

When the classifier detects the same market on both platforms:
- Flag it as cross-platform arb candidate
- Compute spread: abs(price_kalshi - price_polymarket)
- If spread > 5% AND priority_score >= 5 → high-confidence arb signal

This plugs into whatever cross-venue arb logic already exists in trading_brain.py.

## What NOT To Do
- Do NOT restructure the codebase or rename files
- Do NOT add new feeds — use existing polymarket_feed.py and kalshi_feed.py
- Do NOT change the self-tuner — let it adapt to the new market mix naturally
- Do NOT add new strategies — this is a market selection upgrade, not a strategy upgrade
- Do NOT remove any existing functionality

## Testing
- Verify classifier correctly categorizes 10+ sample market titles
- Verify priority_score is stored in rivalclaw.db
- Verify simulator.py filters low-priority markets before passing to brain
- Verify daily report includes speed breakdown
- Run a full simulation cycle and confirm it completes without errors

## Line Budget
- market_classifier.py: 150 lines max
- Changes to simulator.py: 30 lines max
- Changes to trading_brain.py: 20 lines max
- Total new/modified code: under 200 lines
```
