#!/usr/bin/env python3
"""
Mirofish trading brain — arbitrage detection + Ollama market analysis.
Produces TradeDecision objects for simulator to execute.
"""
from __future__ import annotations
import os
import json
import re
import math
import requests
from dataclasses import dataclass
from typing import Any

OLLAMA_BASE_URL   = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
MIROFISH_MODEL    = os.environ.get("MIROFISH_MODEL", "gemma4:31b")
OLLAMA_TIMEOUT    = int(os.environ.get("MIROFISH_OLLAMA_TIMEOUT", "180"))
MAX_POSITION_PCT = float(os.environ.get("MIROFISH_MAX_POSITION_PCT", "0.10"))
MERGED_SIGNAL_LIMIT = int(os.environ.get("MERGED_SIGNAL_LIMIT", "30"))
ARB_THRESHOLD = 0.03
ARB_POSITION_PCT = 0.05  # Fixed 5% of portfolio for arb trades
PRICE_LAG_MIN_EDGE = float(os.environ.get("PRICE_LAG_MIN_EDGE", "0.05"))
PRICE_LAG_LATENCY_PENALTY = float(os.environ.get("PRICE_LAG_LATENCY_PENALTY", "0.005"))
PRICE_LAG_MAX_HORIZON = int(os.environ.get("PRICE_LAG_MAX_HORIZON", "180"))
CROSS_VENUE_POSITION_PCT = float(os.environ.get("CROSS_VENUE_POSITION_PCT", "0.05"))
USE_DYNAMIC_ALLOCATION = os.environ.get("MIROFISH_DYNAMIC_ALLOC", "1") == "1"


def _get_allocation(strategy: str) -> float:
    """Get dynamic allocation for a strategy, falling back to fixed sizing."""
    if not USE_DYNAMIC_ALLOCATION:
        if strategy in ("arbitrage", "cross_venue_arb"):
            return ARB_POSITION_PCT
        return MAX_POSITION_PCT

    try:
        from scripts.mirofish.strategy_tracker import get_strategy_allocation
        allocs = get_strategy_allocation()
        alloc = allocs.get(strategy, 0.0)
        # Scale allocation to position size (tournament gives 0-1 share,
        # multiply by max position to get actual sizing)
        return max(0.01, min(MAX_POSITION_PCT, alloc * MAX_POSITION_PCT * 2))
    except Exception:
        if strategy in ("arbitrage", "cross_venue_arb"):
            return ARB_POSITION_PCT
        return MAX_POSITION_PCT


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
    metadata:    dict | None = None


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


# ── Cross-venue arb ───────────────────────────────────────────────────────

def _check_cross_venue_arb(
    polymarket_events: list,
    kalshi_events: list,
    balance: float,
) -> list[TradeDecision]:
    """
    Cross-venue arbitrage: find price divergences between Polymarket and Kalshi
    on the same underlying question, validated by resolution compatibility.
    Returns TradeDecision list (buy-side leg only — paper wallet is single-venue).
    """
    if not polymarket_events or not kalshi_events:
        return []

    try:
        from scripts.mirofish.cross_venue_matcher import find_arbitrage_opportunities
    except ImportError:
        return []

    opportunities = find_arbitrage_opportunities(polymarket_events, kalshi_events)
    decisions = []

    for opp in opportunities:
        amount = CROSS_VENUE_POSITION_PCT * balance
        # Paper trade the buy leg (cheaper YES side)
        if opp.buy_venue == "polymarket":
            market_id = opp.pair.left.market_id
            question = opp.pair.left.question
        else:
            market_id = opp.pair.right.market_id
            question = opp.pair.right.question

        decisions.append(TradeDecision(
            market_id=market_id,
            question=question,
            direction="YES",
            confidence=min(opp.estimated_edge / 0.10, 1.0),
            reasoning=(
                f"Cross-venue arb: buy YES@{opp.buy_price:.3f} on {opp.buy_venue}, "
                f"sell@{opp.sell_price:.3f} on {opp.sell_venue}, "
                f"spread={opp.spread:.3f}, edge={opp.estimated_edge:.3f}"
            ),
            strategy="cross_venue_arb",
            amount_usd=amount,
            entry_price=opp.buy_price,
            shares=amount / opp.buy_price if opp.buy_price > 0 else 0,
            metadata={
                "buy_venue": opp.buy_venue,
                "sell_venue": opp.sell_venue,
                "buy_price": opp.buy_price,
                "sell_price": opp.sell_price,
                "spread": opp.spread,
                "estimated_edge": opp.estimated_edge,
                "pair_id": opp.pair.pair_id,
                "match_confidence": opp.pair.match_confidence,
                "settlement_compatible": opp.resolution_compat.compatible,
            },
        ))

    return decisions


# ── Price-lag arb helpers ──────────────────────────────────────────────────

_CRYPTO_ASSETS = {
    "BTC": re.compile(r"\b(?:BTC|Bitcoin)\b", re.IGNORECASE),
    "ETH": re.compile(r"\b(?:ETH|Ethereum)\b", re.IGNORECASE),
}

_BINARY_ABOVE_RE = re.compile(
    r"(?:above|over|exceed|reach|hit)\s*\$?([\d,]+\.?\d*[kK]?)", re.IGNORECASE
)
_BINARY_BELOW_RE = re.compile(
    r"(?:below|under|drop)\s*\$?([\d,]+\.?\d*[kK]?)", re.IGNORECASE
)
_BRACKET_RE = re.compile(
    r"\$?([\d,]+\.?\d*[kK]?)\s*[-\u2013]\s*\$?([\d,]+\.?\d*[kK]?)"
)


def _parse_price_string(s: str) -> float | None:
    """Normalize price strings: '$50,000' / '50k' / '1,234.56' → float."""
    if not s or not s.strip():
        return None
    s = s.strip().replace(",", "").replace("$", "")
    multiplier = 1.0
    if s.lower().endswith("k"):
        multiplier = 1000.0
        s = s[:-1]
    try:
        return float(s) * multiplier
    except ValueError:
        return None


def _detect_crypto_contract(market: dict) -> tuple | None:
    """Detect if a market is a crypto price contract.

    Returns: (asset, contract_type, params_dict) or None.
    - binary_threshold: params = {"threshold": float}
    - continuous_bracket: params = {"bracket_low": float, "bracket_high": float}
    """
    question = market.get("question", "")
    asset = None
    for a, pattern in _CRYPTO_ASSETS.items():
        if pattern.search(question):
            asset = a
            break
    if not asset:
        return None

    # Try bracket first (more specific pattern)
    m = _BRACKET_RE.search(question)
    if m:
        low = _parse_price_string(m.group(1))
        high = _parse_price_string(m.group(2))
        if low is not None and high is not None and low < high:
            return (asset, "continuous_bracket", {"bracket_low": low, "bracket_high": high})

    # Try binary above
    m = _BINARY_ABOVE_RE.search(question)
    if m:
        threshold = _parse_price_string(m.group(1))
        if threshold is not None:
            return (asset, "binary_threshold", {"threshold": threshold})

    # Try binary below
    m = _BINARY_BELOW_RE.search(question)
    if m:
        threshold = _parse_price_string(m.group(1))
        if threshold is not None:
            return (asset, "binary_threshold", {"threshold": threshold})

    return None


def _compute_binary_dislocation(
    spot: float, threshold: float, market_yes: float,
    market_no: float, days_to_expiry: int,
) -> tuple[float, str, float] | None:
    """Compute dislocation for binary threshold contract.

    Returns: (raw_dislocation, direction, implied_prob) or None.
    """
    distance_pct = abs(threshold - spot) / spot if spot > 0 else 999
    vol_factor = 0.5 * math.sqrt(max(days_to_expiry, 1) / 30)

    # Implied probability that price reaches/stays above threshold
    implied_prob = max(0.01, min(0.99, 1.0 - distance_pct / vol_factor))

    # Dislocation against market prices
    if implied_prob > market_yes:
        raw_dislocation = implied_prob - market_yes
        direction = "YES"
    else:
        implied_no = 1.0 - implied_prob
        raw_dislocation = implied_no - market_no
        direction = "NO"

    raw_dislocation = max(raw_dislocation, 0.0)
    return (raw_dislocation, direction, implied_prob)


def _compute_bracket_dislocation(
    spot: float, bracket_low: float, bracket_high: float,
    market_yes: float, days_to_expiry: int,
) -> tuple[float, str, float] | None:
    """Compute dislocation for continuous bracket contract."""
    bracket_width = bracket_high - bracket_low
    center = (bracket_low + bracket_high) / 2

    if bracket_low <= spot <= bracket_high:
        dist_from_center = abs(spot - center) / (bracket_width / 2) if bracket_width > 0 else 1
        implied_prob = max(0.05, 0.7 * (1.0 - dist_from_center))
    else:
        if spot < bracket_low:
            dist = (bracket_low - spot) / spot if spot > 0 else 999
        else:
            dist = (spot - bracket_high) / spot if spot > 0 else 999
        vol_factor = 0.5 * math.sqrt(max(days_to_expiry, 1) / 30)
        implied_prob = max(0.01, min(0.40, 0.3 * (1.0 - dist / vol_factor)))

    raw_dislocation = abs(implied_prob - market_yes)
    direction = "YES" if implied_prob > market_yes else "NO"
    return (raw_dislocation, direction, implied_prob)


def _decay_multiplier(days_to_expiry: int) -> float:
    """Inverted linear decay: near expiry = strong signal, far = weak."""
    return max(0.1, 1.0 - days_to_expiry / PRICE_LAG_MAX_HORIZON)


def _check_price_lag_arb(
    market: dict, spot_prices: dict[str, float], balance: float,
) -> "TradeDecision | None":
    """Check if a Polymarket crypto contract has a price-lag dislocation."""
    detection = _detect_crypto_contract(market)
    if not detection:
        return None

    asset, contract_type, params = detection
    spot = spot_prices.get(asset)
    if not spot or spot <= 0:
        return None

    # Parse end_date
    end_date_str = market.get("end_date")
    if not end_date_str:
        return None
    try:
        import datetime as dt
        end_date = dt.datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
        days_to_expiry = (end_date.replace(tzinfo=None) - dt.datetime.utcnow()).days
    except (ValueError, TypeError):
        return None
    if days_to_expiry <= 0:
        return None

    market_yes = market.get("yes_price", 0) or 0
    market_no = market.get("no_price", 1.0 - market_yes)

    # Compute dislocation based on contract type
    if contract_type == "binary_threshold":
        result = _compute_binary_dislocation(
            spot, params["threshold"], market_yes, market_no, days_to_expiry
        )
    elif contract_type == "continuous_bracket":
        result = _compute_bracket_dislocation(
            spot, params["bracket_low"], params["bracket_high"],
            market_yes, days_to_expiry
        )
    else:
        return None

    if not result:
        return None
    raw_dislocation, direction, implied_prob = result

    # Apply edge decay and latency penalty
    decay = _decay_multiplier(days_to_expiry)
    decayed_edge = raw_dislocation * decay - PRICE_LAG_LATENCY_PENALTY
    if decayed_edge < PRICE_LAG_MIN_EDGE:
        return None

    # Size with Kelly
    entry_price = market_yes if direction == "YES" else market_no
    amount = _kelly_size(decayed_edge, entry_price, balance)
    if amount is None:
        return None

    # Build threshold/bracket for metadata
    threshold = params.get("threshold")
    bracket_low = params.get("bracket_low")
    bracket_high = params.get("bracket_high")

    reasoning = (
        f"Price-lag arb: {asset} spot=${spot:,.0f}, "
        f"implied={implied_prob:.2f} vs market={market_yes:.2f}, "
        f"raw={raw_dislocation:.3f}, decayed={decayed_edge:.3f}"
    )

    return TradeDecision(
        market_id=market.get("market_id", ""),
        question=market.get("question", ""),
        direction=direction,
        confidence=decayed_edge,
        reasoning=reasoning,
        strategy="price_lag_arb",
        amount_usd=amount,
        entry_price=entry_price,
        shares=amount / entry_price if entry_price > 0 else 0,
        metadata={
            "asset": asset,
            "contract_type": contract_type,
            "spot_price": spot,
            "threshold": threshold,
            "bracket_low": bracket_low,
            "bracket_high": bracket_high,
            "polymarket_price": market_yes,
            "raw_dislocation": raw_dislocation,
            "decayed_edge": decayed_edge,
            "days_to_expiry": float(days_to_expiry),
        },
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
    spot_prices: dict[str, float] | None = None,
    polymarket_events: list | None = None,
    kalshi_events: list | None = None,
) -> list[TradeDecision]:
    """
    Main entry point. Returns list of TradeDecisions sorted by confidence desc.
    Step 1: Single-venue arbitrage fast-path (no Ollama).
    Step 1.25: Cross-venue arb (Polymarket vs Kalshi, resolution-validated).
    Step 1.5: Price-lag arb (spot vs Polymarket dislocation).
    Step 2: Ollama analysis for momentum/contrarian/news_catalyst on remaining markets.
    Kelly ≤ 0 decisions are excluded before returning.
    """
    balance = wallet.get("balance", 1000.0)
    decisions: list[TradeDecision] = []

    # Step 1: Single-venue arbitrage fast-path
    arb_market_ids = set()
    arb_alloc = _get_allocation("arbitrage")
    for market in markets:
        arb = _check_arbitrage(market)
        if arb:
            arb.amount_usd = arb_alloc * balance
            arb.shares = arb.amount_usd / arb.entry_price if arb.entry_price > 0 else 0
            decisions.append(arb)
            arb_market_ids.add(market["market_id"])

    # Step 1.25: Cross-venue arb (Polymarket vs Kalshi)
    if polymarket_events and kalshi_events:
        xv_decisions = _check_cross_venue_arb(polymarket_events, kalshi_events, balance)
        for d in xv_decisions:
            if d.market_id not in arb_market_ids:
                decisions.append(d)
                arb_market_ids.add(d.market_id)

    # Step 1.5: Price-lag arb (spot vs Polymarket dislocation)
    if spot_prices:
        for market in [m for m in markets if m["market_id"] not in arb_market_ids]:
            pla = _check_price_lag_arb(market, spot_prices, balance)
            if pla:
                decisions.append(pla)
                arb_market_ids.add(market["market_id"])

    # Step 2: Ollama analysis for non-arb markets
    # Merge Polymarket + Kalshi into a single list for the LLM
    non_arb = [m for m in markets if m["market_id"] not in arb_market_ids]

    # Add Kalshi markets as flat dicts so LLM can analyze them too
    if kalshi_events:
        for ke in kalshi_events:
            if ke.market_id in arb_market_ids:
                continue
            yes_price = ke.outcomes[0].bid if ke.outcomes else 0
            no_price = ke.outcomes[1].bid if len(ke.outcomes) > 1 else (1.0 - yes_price)
            close_time = ""
            if ke.contract.expiry_ts_ms:
                import datetime as _dtc
                close_time = _dtc.datetime.utcfromtimestamp(ke.contract.expiry_ts_ms / 1000).isoformat() + "Z"
            non_arb.append({
                "market_id": ke.market_id,
                "question": ke.question,
                "yes_price": yes_price or 0.5,
                "no_price": no_price or 0.5,
                "volume": ke.volume_24h,
                "end_date": close_time,
                "close_time": close_time,
                "category": ke.category,
                "venue": "kalshi",
            })

    if not non_arb:
        return sorted(decisions, key=lambda d: d.confidence, reverse=True)

    # Sort by expiry: markets resolving soonest first (prefer fast feedback)
    import datetime as _dt
    _now = _dt.datetime.utcnow()
    _max_hours = 7 * 24  # only trade markets resolving within 7 days
    def _hours_to_expiry(m):
        ed = m.get("end_date") or m.get("close_time") or ""
        if not ed:
            return 999999
        try:
            dt = _dt.datetime.fromisoformat(str(ed).replace("Z", "+00:00"))
            return max(0, (dt.replace(tzinfo=None) - _now).total_seconds() / 3600)
        except (ValueError, TypeError):
            return 999999

    # Filter out markets resolving beyond 7 days — dead capital during testing phase
    non_arb = [m for m in non_arb if _hours_to_expiry(m) <= _max_hours]
    non_arb_sorted = sorted(non_arb, key=_hours_to_expiry)

    open_positions = wallet.get("open_positions", 0)

    def _expiry_label(m):
        h = _hours_to_expiry(m)
        if h < 1: return "⚡<1h"
        if h < 24: return f"🔥{h:.0f}h"
        if h < 168: return f"📅{h/24:.0f}d"
        return f"📆{h/24:.0f}d"

    market_lines = "\n".join(
        f'- [{m["market_id"]}] {m["question"][:70]} | YES={m["yes_price"]:.2f} NO={m["no_price"]:.2f} vol=${m["volume"]:,.0f} {_expiry_label(m)} [{m.get("venue","polymarket")[:5]}]'
        for m in non_arb_sorted[:40]
    )

    # Build two-pass signal blocks
    signals_block = ""
    if signals:
        # Partition signals for two-pass injection
        crucix_ideas = [s for s in signals if s.get("source") == "crucix_ideas"]
        regime_signals = [s for s in signals if s.get("source") == "crucix_delta"]
        raw_signals = [s for s in signals if s.get("source") not in ("crucix_ideas", "crucix_delta")]

        # Pass 1: Crucix OSINT Intelligence Summary (ideas + regime)
        ideas_block = ""
        if crucix_ideas or regime_signals:
            ideas_lines = []
            for rs in regime_signals:
                ideas_lines.append(f"Overall regime: {rs.get('description', 'unknown')}")
            for idea in crucix_ideas:
                ideas_lines.append(f"- {idea.get('description', '')}")
            ideas_block = (
                "\nCrucix OSINT Intelligence Summary:\n"
                + "\n".join(ideas_lines)
                + "\n"
            )

        # Pass 2: Raw signals (merged UW + Crucix, capped)
        raw_block = ""
        if raw_signals:
            recent = sorted(raw_signals, key=lambda s: s.get("fetched_at", ""), reverse=True)
            recent = recent[:MERGED_SIGNAL_LIMIT]
            signal_lines = "\n".join(
                f'- [{s.get("source", "").upper()}] {s.get("ticker", "?")} '
                f'{s.get("direction", "")} {s.get("signal_type", "")} '
                f'— {s.get("description", "")}'
                for s in recent
            )
            raw_block = (
                f"\nActive market signals:\n{signal_lines}\n\n"
                "When analyzing Polymarket markets, consider whether any of these signals "
                "suggest a related outcome is more or less likely. OSINT signals (geopolitical "
                "conflicts, economic indicators, military activity, environmental disasters) "
                "indicate macro regime shifts. Market flow signals (options sweeps, dark pool "
                "blocks, congressional trades) indicate where sophisticated money is positioning. "
                "Both can create edge in prediction markets tied to related outcomes.\n"
            )

        signals_block = ideas_block + raw_block

    prompt = f"""You are Mirofish, a prediction market paper trading system in TESTING PHASE.
Current portfolio: ${balance:.2f} balance, {open_positions} open positions.

CRITICAL: We are paper trading and need FAST FEEDBACK. Strongly prefer markets that resolve SOON:
- ⚡ Markets resolving in <1 hour = HIGHEST PRIORITY (15min crypto, hourly S&P/Nasdaq)
- 🔥 Markets resolving in <24 hours = HIGH PRIORITY (daily price ranges, sports tonight, weather today)
- 📅 Markets resolving in <7 days = MEDIUM (weekly events, near-term politics)
- 📆 Markets resolving in >7 days = LOW PRIORITY (only if edge is overwhelming)

Analyze these markets and identify trading opportunities using:
- momentum: YES price trending upward strongly (>5% over recent snapshots)
- contrarian: YES price moved >20% in one direction (likely overreaction)
- news_catalyst: you know of recent news that changes the true probability significantly

For each opportunity, calculate:
- Expected true probability vs current market price
- Confidence (0.0-1.0) in your edge
- Direction (YES or NO)
- One-sentence reasoning

Markets (sorted by expiry, soonest first):
{market_lines}
{signals_block}
Return ONLY a JSON array (no explanation), max 5 opportunities. PREFER SHORT-EXPIRY MARKETS:
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
