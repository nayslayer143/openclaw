#!/usr/bin/env python3
"""
Mirofish trading brain — arbitrage detection + Ollama market analysis.
Produces TradeDecision objects for simulator to execute.
"""
from __future__ import annotations
import os
import json
import re
import requests
from dataclasses import dataclass
from typing import Any

OLLAMA_BASE_URL   = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
MIROFISH_MODEL    = os.environ.get("MIROFISH_MODEL", "qwen3:30b")
OLLAMA_TIMEOUT    = int(os.environ.get("MIROFISH_OLLAMA_TIMEOUT", "180"))
MAX_POSITION_PCT = float(os.environ.get("MIROFISH_MAX_POSITION_PCT", "0.10"))
ARB_THRESHOLD = 0.03
ARB_POSITION_PCT = 0.05  # Fixed 5% of portfolio for arb trades


@dataclass
class TradeDecision:
    market_id:   str
    question:    str
    direction:   str    # YES | NO
    confidence:  float
    reasoning:   str
    strategy:    str
    amount_usd:  float
    entry_price: float
    shares:      float


def _kelly_size(confidence: float, entry_price: float, balance: float) -> float | None:
    """
    Correct Kelly criterion for prediction markets.
    b = payout odds (e.g., entry=0.30 → b=2.33x)
    kelly = (confidence * b - (1 - confidence)) / b
    Returns None if kelly ≤ 0 (negative edge).
    """
    if entry_price <= 0 or entry_price >= 1:
        return None
    b = (1.0 / entry_price) - 1.0
    kelly = (confidence * b - (1.0 - confidence)) / b
    if kelly <= 0:
        return None
    return min(kelly * balance, MAX_POSITION_PCT * balance)


def _check_arbitrage(market: dict) -> TradeDecision | None:
    """
    Pure-math arbitrage check. No Ollama needed.
    Flags if abs(yes + no - 1.0) > ARB_THRESHOLD.
    Single-leg: buy whichever side is underpriced (< 0.50).
    Fixed 5% sizing — Kelly doesn't apply cleanly to arb.
    """
    yes_p = market.get("yes_price", 0) or 0
    no_p  = market.get("no_price", 0) or 0
    gap = abs(yes_p + no_p - 1.0)
    if gap <= ARB_THRESHOLD:
        return None

    # Buy the side furthest below its theoretical fair value
    # In a binary market: fair_no = 1 - yes_p, fair_yes = 1 - no_p
    if no_p < 1 - yes_p:
        direction, entry_price = "NO", no_p
    else:
        direction, entry_price = "YES", yes_p

    confidence = min(gap / 0.10, 1.0)
    reasoning = (f"Arbitrage: YES={yes_p:.3f} + NO={no_p:.3f} = {yes_p+no_p:.3f} "
                 f"(gap={gap:.3f} > {ARB_THRESHOLD})")

    market_id = market.get("market_id", "")
    question = market.get("question", "")
    if not market_id:
        return None

    return TradeDecision(
        market_id=market_id,
        question=question,
        direction=direction,
        confidence=confidence,
        reasoning=reasoning,
        strategy="arbitrage",
        amount_usd=0.0,  # sized by analyze() using ARB_POSITION_PCT
        entry_price=entry_price,
        shares=0.0,
    )


def _call_ollama(prompt: str) -> str:
    """Call Ollama and return the response text."""
    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": MIROFISH_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            },
            timeout=OLLAMA_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "")
    except Exception as e:
        print(f"[mirofish/brain] Ollama error: {e}")
        return ""


def _extract_json(text: str) -> list[dict]:
    """Extract JSON array from LLM response with regex fallback."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r'\[.*\]', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return []


def analyze(
    markets: list[dict],
    wallet: dict[str, Any],
    signals: list[dict] | None = None,
) -> list[TradeDecision]:
    """
    Main entry point. Returns list of TradeDecisions sorted by confidence desc.
    Step 1: Arbitrage fast-path (no Ollama).
    Step 2: Ollama analysis for momentum/contrarian/news_catalyst on remaining markets.
    Kelly ≤ 0 decisions are excluded before returning.
    """
    balance = wallet.get("balance", 1000.0)
    decisions: list[TradeDecision] = []

    # Step 1: Arbitrage fast-path
    arb_market_ids = set()
    for market in markets:
        arb = _check_arbitrage(market)
        if arb:
            arb.amount_usd = ARB_POSITION_PCT * balance
            arb.shares = arb.amount_usd / arb.entry_price if arb.entry_price > 0 else 0
            decisions.append(arb)
            arb_market_ids.add(market["market_id"])

    # Step 2: Ollama analysis for non-arb markets
    non_arb = [m for m in markets if m["market_id"] not in arb_market_ids]
    if not non_arb:
        return sorted(decisions, key=lambda d: d.confidence, reverse=True)

    open_positions = wallet.get("open_positions", 0)
    market_lines = "\n".join(
        f'- [{m["market_id"]}] {m["question"][:80]} | YES={m["yes_price"]:.2f} NO={m["no_price"]:.2f} vol=${m["volume"]:,.0f}'
        for m in non_arb[:30]
    )

    # Build optional UW signals block
    signals_block = ""
    if signals:
        recent = sorted(signals, key=lambda s: s.get("fetched_at", ""), reverse=True)[:20]
        signal_lines = "\n".join(
            f'- [{s.get("source", "").upper()}] {s.get("ticker", "?")} '
            f'{s.get("direction", "")} {s.get("signal_type", "")} '
            f'— {s.get("description", "")}'
            for s in recent
        )
        signals_block = (
            f"\nActive market signals (Unusual Whales):\n{signal_lines}\n\n"
            "When analyzing Polymarket markets, consider whether any of these signals "
            "suggest a related outcome is more or less likely. A bullish options sweep "
            "on NVDA is a signal that sophisticated money expects NVDA to rise — factor "
            "this into any Polymarket market about Nvidia price, earnings, or "
            "company performance.\n"
        )

    prompt = f"""You are Mirofish, a prediction market paper trading system.
Current portfolio: ${balance:.2f} balance, {open_positions} open positions.

Analyze these Polymarket markets and identify trading opportunities using:
- momentum: YES price trending upward strongly (>5% over recent snapshots)
- contrarian: YES price moved >20% in one direction (likely overreaction)
- news_catalyst: you know of recent news that changes the true probability significantly

For each opportunity, calculate:
- Expected true probability vs current market price
- Confidence (0.0-1.0) in your edge
- Direction (YES or NO)
- One-sentence reasoning

Markets:
{market_lines}
{signals_block}
Return ONLY a JSON array (no explanation), max 5 opportunities:
[
  {{
    "market_id": "...",
    "direction": "YES|NO",
    "confidence": 0.0-1.0,
    "strategy": "momentum|contrarian|news_catalyst",
    "reasoning": "one sentence",
    "entry_price": 0.0
  }}
]
Only include opportunities where you have genuine edge (confidence > 0.6).
If no clear opportunities, return [].
"""

    raw = _call_ollama(prompt)
    parsed = _extract_json(raw)

    # Build lookup once so each iteration is O(1)
    market_by_id = {m["market_id"]: m for m in non_arb}

    for item in parsed:
        market_id  = item.get("market_id", "")
        direction  = item.get("direction", "").upper()
        confidence = float(item.get("confidence", 0))
        strategy   = item.get("strategy", "news_catalyst")
        reasoning  = item.get("reasoning", "")

        if not market_id or direction not in ("YES", "NO") or confidence <= 0:
            continue

        # Always use actual market price — ignore any LLM-provided entry_price
        mkt = market_by_id.get(market_id)
        if not mkt:
            continue
        entry_price = mkt["yes_price"] if direction == "YES" else mkt["no_price"]
        question = mkt["question"]

        if entry_price <= 0 or entry_price >= 1:
            continue

        amount = _kelly_size(confidence, entry_price, balance)
        if amount is None:
            continue  # negative edge — skip

        decisions.append(TradeDecision(
            market_id=market_id, question=question, direction=direction,
            confidence=confidence, reasoning=reasoning, strategy=strategy,
            amount_usd=amount, entry_price=entry_price,
            shares=amount / entry_price,
        ))

    return sorted(decisions, key=lambda d: d.confidence, reverse=True)
