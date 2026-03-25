# RivalClaw v2 — Fast Market Scanner + Evolution Strategy

**Date:** 2026-03-24
**Source:** Chad (ChatGPT) — strategy session on fast-resolving markets + $10K/$1M questions
**Status:** PARKED — do not implement yet. V2 will run on a separate siloed instance based on RivalClaw v1.
**Current RivalClaw v1:** ~/rivalclaw/ (8 strategies, hedge engine, self-tuner, Polymarket + Kalshi + CoinGecko)

---

## Key Insight: Capital Velocity > Edge Size

Fastest-resolving markets = highest capital velocity = best for arb loops.
A 1% edge that cycles 3x/day beats a 5% edge that cycles once a week.

---

## Fast Market Taxonomy (by resolution speed)

### Tier S — Same-day resolution
1. **Sports** — NBA, NHL, soccer daily match winners. Resolve minutes after game end. ~85% of Kalshi volume. Polymarket crossed $1B+ sports volume.
2. **Weather** — "Will it rain in NYC tomorrow?" / "Will temp exceed 70F?" Uses NOAA data. Binary, timestamped, no interpretation. Underexploited.

### Tier A — Scheduled events (predictable timing)
3. **Economic releases** — CPI, jobless claims, Fed decisions. Exact timestamps. Official sources. Less frequent (weekly/monthly).
4. **Event binaries** — "Will Apple announce X today?" Fast only if tied to timestamped event.

### Tier B — Medium speed
5. **Entertainment/culture** — "Will X movie be #1?" Resolve in 1-3 days. Interpretation lag risk.

### Avoid (kills velocity)
- Long-dated macro, narrative markets, politics (unless election day), subjective markets

---

## Platform Speed Comparison

| Factor | Polymarket | Kalshi |
|--------|-----------|--------|
| Crowd reaction | Faster (crypto-native) | Slightly slower |
| Resolution | ~2hr challenge window | ~3hr after confirmation |
| Resolution rules | Sometimes messier | Cleaner, more deterministic |
| Net | Faster to trade | More predictable payout |

**Arb window:** Polymarket reacts first → Kalshi lags → structural mismatch = persistent arb surface.

---

## Fast Market Scanner Spec (for RivalClaw)

### Step 1: Ingest Markets
Pull from both platforms: market_id, title, platform, resolution_criteria, scheduled_resolution_time, category, liquidity/volume, bid/ask spread.

### Step 2: Resolution Speed Score
- +3 → resolves same-day (sports, weather)
- +2 → resolves within 48h
- +1 → resolves within 7 days
- 0 → unknown/ambiguous
- -1 → subjective resolution risk

### Step 3: Resolution Clarity Score
- +3 → objective data source (sports result, weather reading)
- +2 → official release (CPI, Fed)
- +1 → semi-objective (event attendance)
- 0 → subjective/media-based

### Step 4: Time Decay Priority
```
time_to_resolution = resolution_time - now
if <6h  → +3
if <24h → +2
if <72h → +1
else    → 0
```

### Step 5: Cross-Platform Arb Detection
Match similar markets via fuzzy title similarity + same underlying event.
```
arb_spread = abs(price_kalshi - price_polymarket)
Flag if: spread > 5% AND both resolve <48h
```

### Step 6: Final Score
```
final_score = (speed * 2) + (clarity * 2) + time_decay + liquidity + arb_spread_bonus
```

### Step 7: Output
```json
{
  "market_pair": ["kalshi_id", "polymarket_id"],
  "category": "sports/weather/econ",
  "time_to_resolution": "X hours",
  "arb_spread": "X%",
  "confidence": "HIGH / MEDIUM / LOW"
}
```

---

## The $10K Questions (Strategy Optimization)

1. **Price discovery leadership** — Does Polymarket or Kalshi lead by category? If one leads by 30-120s, stop doing arb → do predictive execution.
2. **True latency stack** — API latency + order delay + fill probability + resolution delay. Most bots see 5% arb but capture 1-2%.
3. **Executable arb rate** — % of detected arbs that actually fill on BOTH sides. Most visible arbs are too thin, already gone, or bait.
4. **Capital velocity ceiling** — How many times can $1 cycle per day? Sports = 1-2x, weather = 1x, econ = occasional.
5. **Resolution ambiguity risk** — Weather station discrepancies, stat corrections, "did X attend?" edge cases. Need resolution risk model, not just price model.
6. **Correlated failure** — Both platforms can be wrong simultaneously. Arb ≠ risk-free.
7. **Liquidity anticipation** — What markets open in next 1-3h? Early positioning > late arb.
8. **Bot detection** — Quote stuffing, fake spreads, latency bait. If you don't model other bots, you ARE the liquidity.
9. **Unfair advantage** — Pure arb gets commoditized. Need: faster infra, better classification, niche markets (weather), predictive models.
10. **When NOT to trade** — Low liquidity traps, ambiguous resolution, fake spreads, high slippage windows. Best trade is often no trade.

---

## The $1M Questions (System Evolution)

1. **Become the price discovery engine** — Compute "true probability" across platforms, act first.
2. **Manufacture liquidity** — Quote both sides on thin markets, shape spreads, capture flow from slower traders. Trader → market maker.
3. **Create markets that don't exist** — Hyper-local weather, creator economy, AI benchmarks. Define the market = define the edge.
4. **Predict resolution before the market** — Weather models vs public perception, sports injury data vs odds, econ nowcasting.
5. **Compounding loop** — Trade → learn (fill rate, slippage, timing) → update model → improve. Intelligence compounds, speed doesn't.
6. **Structural inefficiency** — Regulatory fragmentation, timezone gaps, data delays, resolution rule differences. Durable, not temporary.
7. **Front-run market creation** — News momentum, social spikes, scheduled events → be first in new markets.
8. **Autonomous organism** — Scout → Analyst → Trader → Auditor → Strategist. Runs continuously, improves itself, allocates dynamically.
9. **Hybrid human+bot** — Humans still win in ambiguity, narrative shifts, intuition. Capture those signals.
10. **Success destruction** — If this works, spreads tighten, competitors emerge. Second-order moat: proprietary data, better models, market-making, owning distribution.

---

## RivalClaw v2 Architecture (NOT YET — separate siloed instance)

Four-module evolution:
1. **Scout** — Market discovery + anticipation (find markets before they're crowded)
2. **Oracle** — True probability engine (cross-platform consensus + external signals)
3. **Executor** — Arb + directional trades (latency-aware, fill-rate-optimized)
4. **Maker** — Liquidity provision on thin markets (shape spreads, capture flow)

**Implementation plan:** Build v2 on a NEW siloed OpenClaw instance based on RivalClaw v1's codebase. Do NOT modify v1 directly — v1 continues running as the control group for scientific comparison.

---

## Relationship to Other Parked Ideas

- **ArbClaw** (parked): Lean arb speed test for Clawmpson execution lag hypothesis
- **Moltbook** (parked): Distribution channel for agent social network
- **RivalClaw v2** (this file): Evolution from arb bot → market intelligence system
- **GitHub Intel Pipeline** (ready to build): Continuous repo crawler → Gonzoclaw review page → approved integrations dispatched to any of the 3 bots

All feed the same meta-question: are we building trading bots, or market infrastructure?
