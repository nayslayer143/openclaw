#!/usr/bin/env python3
"""
Cross-venue market matcher — finds matching prediction markets across venues
and identifies arbitrage opportunities.

Takes MarketEvent lists from multiple venues, finds candidate pairs by text
similarity + category + expiry proximity, runs resolution validation, and
produces MatchedMarketPair objects with arbitrage signals.

v4.2 strategy rule: if settlement wording differs materially, it is NOT
arbitrage — it is a correlated bet. The resolution_validator enforces this.

Python 3.9 compatible via __future__ annotations.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from scripts.mirofish.market_event import (
    MarketEvent,
    MatchedMarketPair,
    OutcomeBook,
)
from scripts.mirofish.resolution_validator import (
    validate_resolution_compatibility,
    ResolutionCompatibility,
    _jaccard_similarity,
    _extract_tokens,
    _normalize_text,
)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Minimum title/question similarity to consider a candidate pair
MIN_TITLE_SIMILARITY = 0.30

# Minimum resolution compatibility confidence to emit a match
MIN_MATCH_CONFIDENCE = 0.40

# Maximum expiry drift (ms) for candidate filtering (7 days — loose pre-filter)
MAX_CANDIDATE_EXPIRY_DRIFT_MS = 7 * 24 * 60 * 60 * 1000

# Minimum price divergence to flag as arb opportunity
MIN_ARB_SPREAD = 0.03  # 3 cents on a $0-$1 contract

# Synonyms for fuzzy matching (venue-specific phrasing)
_SYNONYMS = {
    "bitcoin": {"btc", "bitcoin", "xbt"},
    "ethereum": {"eth", "ethereum", "ether"},
    "above": {"above", "exceed", "over", "greater", "higher"},
    "below": {"below", "under", "less", "lower"},
    "by": {"by", "before", "prior"},
    "federal reserve": {"fed", "federal reserve", "fomc"},
}


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class ArbOpportunity:
    pair: MatchedMarketPair
    spread: float                        # price divergence (positive = arb exists)
    buy_venue: str                       # venue to buy YES
    sell_venue: str                      # venue to buy NO (synthetic sell)
    buy_price: float                     # YES price on buy_venue
    sell_price: float                    # 1 - YES price on sell_venue (= NO price)
    estimated_edge: float                # spread minus estimated fees
    resolution_compat: ResolutionCompatibility

    def to_dict(self) -> dict:
        return {
            "pair_id": self.pair.pair_id,
            "spread": self.spread,
            "buy_venue": self.buy_venue,
            "sell_venue": self.sell_venue,
            "buy_price": self.buy_price,
            "sell_price": self.sell_price,
            "estimated_edge": self.estimated_edge,
            "resolution_compatible": self.resolution_compat.compatible,
            "resolution_confidence": self.resolution_compat.confidence,
            "incompatibility_reasons": self.resolution_compat.incompatibility_reasons,
        }


# ---------------------------------------------------------------------------
# Text matching helpers
# ---------------------------------------------------------------------------

def _expand_synonyms(tokens: set[str]) -> set[str]:
    """Expand tokens with known synonyms for better cross-venue matching."""
    expanded = set(tokens)
    for canonical, synonyms in _SYNONYMS.items():
        if tokens & synonyms:
            expanded |= synonyms
    return expanded


def _title_similarity(a: MarketEvent, b: MarketEvent) -> float:
    """
    Compute title/question similarity with synonym expansion.
    Uses max of (title vs title, question vs question, title vs question).
    """
    a_title_tokens = _expand_synonyms(_extract_tokens(a.title))
    b_title_tokens = _expand_synonyms(_extract_tokens(b.title))

    a_q_tokens = _expand_synonyms(_extract_tokens(a.question))
    b_q_tokens = _expand_synonyms(_extract_tokens(b.question))

    sims = [
        _jaccard_similarity(a_title_tokens, b_title_tokens),
        _jaccard_similarity(a_q_tokens, b_q_tokens),
        _jaccard_similarity(a_title_tokens, b_q_tokens),
        _jaccard_similarity(a_q_tokens, b_title_tokens),
    ]
    return max(sims)


def _category_compatible(a: MarketEvent, b: MarketEvent) -> bool:
    """Check if categories are compatible (same or one is empty)."""
    if not a.category or not b.category:
        return True
    return a.category.lower() == b.category.lower()


def _expiry_within_range(a: MarketEvent, b: MarketEvent) -> bool:
    """Check if expiry timestamps are within candidate range."""
    if not a.contract.expiry_ts_ms or not b.contract.expiry_ts_ms:
        return True  # can't filter if missing
    drift = abs(a.contract.expiry_ts_ms - b.contract.expiry_ts_ms)
    return drift <= MAX_CANDIDATE_EXPIRY_DRIFT_MS


# ---------------------------------------------------------------------------
# Price extraction
# ---------------------------------------------------------------------------

def _get_yes_price(event: MarketEvent) -> float | None:
    """Extract the YES mid-price from outcomes."""
    for o in event.outcomes:
        if o.outcome.upper() == "YES":
            if o.bid and o.ask and o.bid > 0 and o.ask > 0:
                return (o.bid + o.ask) / 2.0
            if o.last and o.last > 0:
                return o.last
            if o.bid and o.bid > 0:
                return o.bid
            if o.ask and o.ask > 0:
                return o.ask
    return None


def _get_no_price(event: MarketEvent) -> float | None:
    """Extract the NO mid-price from outcomes."""
    for o in event.outcomes:
        if o.outcome.upper() == "NO":
            if o.bid and o.ask and o.bid > 0 and o.ask > 0:
                return (o.bid + o.ask) / 2.0
            if o.last and o.last > 0:
                return o.last
            if o.bid and o.bid > 0:
                return o.bid
            if o.ask and o.ask > 0:
                return o.ask
    return None


def _estimate_fee_cost(event: MarketEvent) -> float:
    """Estimate round-trip fee cost as a decimal (e.g., 0.02 for 2%)."""
    fees = event.fees
    # taker_bps is in basis points — 100 bps = 1%
    taker_pct = fees.taker_bps / 10000.0
    settlement_pct = fees.settlement_fee_bps / 10000.0
    return taker_pct + settlement_pct


# ---------------------------------------------------------------------------
# Core matching
# ---------------------------------------------------------------------------

def find_candidate_pairs(
    left_events: list[MarketEvent],
    right_events: list[MarketEvent],
) -> list[tuple[MarketEvent, MarketEvent, float]]:
    """
    Find candidate market pairs across two venue lists.
    Returns (left, right, title_similarity) tuples that pass pre-filters.
    """
    candidates = []

    for left in left_events:
        if left.status != "open":
            continue
        for right in right_events:
            if right.status != "open":
                continue
            if left.venue == right.venue:
                continue

            # Pre-filters
            if not _category_compatible(left, right):
                continue
            if not _expiry_within_range(left, right):
                continue

            sim = _title_similarity(left, right)
            if sim >= MIN_TITLE_SIMILARITY:
                candidates.append((left, right, sim))

    # Sort by similarity descending
    candidates.sort(key=lambda x: x[2], reverse=True)
    return candidates


def match_markets(
    left_events: list[MarketEvent],
    right_events: list[MarketEvent],
) -> list[MatchedMarketPair]:
    """
    Find and validate cross-venue market matches.
    Returns MatchedMarketPair objects for pairs that pass resolution validation.
    """
    candidates = find_candidate_pairs(left_events, right_events)
    matched: list[MatchedMarketPair] = []
    seen_pairs: set[tuple[str, str]] = set()

    for left, right, title_sim in candidates:
        # Dedup: don't match same pair twice
        pair_key = tuple(sorted([left.market_id, right.market_id]))
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)

        # Run resolution validation
        compat = validate_resolution_compatibility(left, right)

        # Combine title similarity with resolution confidence
        match_confidence = (title_sim * 0.4 + compat.confidence * 0.6)

        if match_confidence < MIN_MATCH_CONFIDENCE:
            continue

        pair_id = f"xv-{left.venue[:4]}-{right.venue[:4]}-{left.market_id[:20]}"

        # Build the underlying key from shared tokens
        left_tokens = _extract_tokens(left.question)
        right_tokens = _extract_tokens(right.question)
        shared = left_tokens & right_tokens
        underlying_key = "-".join(sorted(shared)[:5]) if shared else left.contract.underlying

        pair = MatchedMarketPair(
            pair_id=pair_id,
            left=left,
            right=right,
            match_confidence=match_confidence,
            settlement_compatible=compat.compatible,
            incompatibility_reasons=compat.incompatibility_reasons,
            normalized_underlying_key=underlying_key,
        )
        matched.append(pair)

    return matched


def find_arbitrage_opportunities(
    left_events: list[MarketEvent],
    right_events: list[MarketEvent],
    min_spread: float = MIN_ARB_SPREAD,
) -> list[ArbOpportunity]:
    """
    Find cross-venue arbitrage opportunities.

    An arb exists when:
    1. Two markets on the same question are settlement-compatible
    2. YES price on venue A + YES price on venue B < 1.0 (or > 1.0)
       equivalently: YES_A < (1 - YES_B), meaning you can buy YES cheap
       on one venue and NO cheap on the other

    Only returns opportunities where resolution is compatible.
    """
    pairs = match_markets(left_events, right_events)
    opportunities: list[ArbOpportunity] = []

    for pair in pairs:
        # Only arb on settlement-compatible pairs
        compat = validate_resolution_compatibility(pair.left, pair.right)
        if not compat.compatible:
            continue

        left_yes = _get_yes_price(pair.left)
        right_yes = _get_yes_price(pair.right)

        if left_yes is None or right_yes is None:
            continue

        # Arb check: buy YES on cheaper venue, buy NO on other venue
        # If left_yes + right_yes < 1.0: buy both YES for guaranteed profit
        # If left_yes + right_yes > 1.0: market is overpriced somewhere
        # Cross-venue arb: buy YES where cheaper, buy NO (1-YES) where more expensive

        # Scenario 1: left YES is cheaper → buy YES on left, NO on right
        spread_1 = (1.0 - right_yes) - left_yes  # sell_price - buy_price
        # Scenario 2: right YES is cheaper → buy YES on right, NO on left
        spread_2 = (1.0 - left_yes) - right_yes

        if spread_1 >= spread_2 and spread_1 >= min_spread:
            buy_venue = pair.left.venue
            sell_venue = pair.right.venue
            buy_price = left_yes
            sell_price = 1.0 - right_yes
            spread = spread_1
        elif spread_2 >= min_spread:
            buy_venue = pair.right.venue
            sell_venue = pair.left.venue
            buy_price = right_yes
            sell_price = 1.0 - left_yes
            spread = spread_2
        else:
            continue

        # Estimate fees
        left_fees = _estimate_fee_cost(pair.left)
        right_fees = _estimate_fee_cost(pair.right)
        total_fees = left_fees + right_fees
        estimated_edge = spread - total_fees

        if estimated_edge <= 0:
            continue  # fees eat the spread

        opportunities.append(ArbOpportunity(
            pair=pair,
            spread=spread,
            buy_venue=buy_venue,
            sell_venue=sell_venue,
            buy_price=buy_price,
            sell_price=sell_price,
            estimated_edge=estimated_edge,
            resolution_compat=compat,
        ))

    # Sort by estimated edge descending
    opportunities.sort(key=lambda x: x.estimated_edge, reverse=True)
    return opportunities
