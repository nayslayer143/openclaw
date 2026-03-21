# AutoResearch Domain: prediction-market

## Purpose
Monitor prediction markets (Polymarket, Kalshi, Manifold) for arbitrage signals and high-confidence trade opportunities. Identify mispricings, analyze market sentiment vs real-world data, generate trade recommendations for Clawmpson's trading workflow.

## Model
- Analysis: `qwen3:32b` (fast reasoning)
- Deep synthesis: `llama3.3:70b` (confidence scoring, cross-market correlation)

## Data Sources
- Polymarket API: https://polymarket.com (public markets + order book)
- Kalshi API: https://kalshi.com (US-regulated event contracts)
- Manifold Markets: https://manifold.markets (community predictions)
- Serper web search: current events for ground-truth calibration

## Research Focus
1. Markets where prediction probability diverges >15% from base rate evidence
2. Correlated markets trading at inconsistent spreads (arbitrage)
3. Upcoming binary events with clear resolution criteria
4. Sports/politics/crypto markets with high volume + identifiable edge

## Output Format: dataset (JSON)
```json
{
  "scan_date": "...",
  "opportunities": [{
    "market": "...",
    "platform": "polymarket|kalshi|manifold",
    "url": "...",
    "current_odds": 0.0,
    "estimated_true_probability": 0.0,
    "edge": 0.0,
    "confidence": "low|medium|high",
    "evidence": "...",
    "recommended_action": "buy_yes|buy_no|pass",
    "max_position_usd": 0,
    "resolution_date": "..."
  }],
  "meta": {"total_scanned": 0, "high_confidence": 0}
}
```

## Constraints
- Paper trading only until 10 successful predictions verified (no real capital)
- Never recommend positions >$50 without Tier-2 Jordan approval
- Flag any market with <$10K liquidity as illiquid — skip
- Log all recommendations to autoresearch/outputs/datasets/ for backtest
