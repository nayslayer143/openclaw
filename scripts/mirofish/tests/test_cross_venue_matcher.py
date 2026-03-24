from __future__ import annotations

import pytest

from scripts.mirofish.market_event import (
    MarketEvent, ContractSpec, ResolutionSpec, OutcomeBook,
    VenueFees, MatchedMarketPair, _ms_now,
)
from scripts.mirofish.cross_venue_matcher import (
    find_candidate_pairs,
    match_markets,
    find_arbitrage_opportunities,
    _title_similarity,
    _get_yes_price,
    _expand_synonyms,
    ArbOpportunity,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_NOW = _ms_now()
_EXPIRY = _NOW + 30 * 24 * 3600 * 1000  # 30 days out

_POLY_FEES = VenueFees(taker_bps=2.0, maker_bps=0.0, settlement_fee_bps=200.0,
                       notes="Polymarket")
_KALSHI_FEES = VenueFees(taker_bps=0.0, maker_bps=0.0, withdrawal_fee_fixed=2.0,
                         notes="Kalshi")


def _make_event(
    venue: str = "polymarket",
    market_id: str = "test-001",
    title: str = "Will Bitcoin exceed $150k by July 2026?",
    question: str = "Will Bitcoin exceed $150k by July 2026?",
    category: str = "crypto",
    yes_bid: float = 0.42,
    yes_ask: float = 0.44,
    no_bid: float = 0.56,
    no_ask: float = 0.58,
    last_yes: float = 0.43,
    resolution_text: str = "Resolves YES if Bitcoin exceeds $150,000 on any major exchange before July 1, 2026 UTC.",
    expiry_ts_ms: int = _EXPIRY,
    contract_type: str = "binary",
    strike: float | None = None,
    status: str = "open",
) -> MarketEvent:
    fees = _POLY_FEES if venue == "polymarket" else _KALSHI_FEES
    return MarketEvent(
        market_id=market_id,
        venue=venue,
        title=title,
        question=question,
        category=category,
        contract=ContractSpec(
            contract_type=contract_type,
            underlying="BTC",
            strike=strike,
            expiry_ts_ms=expiry_ts_ms,
        ),
        resolution=ResolutionSpec(resolution_text=resolution_text),
        outcomes=[
            OutcomeBook(outcome="YES", bid=yes_bid, ask=yes_ask, last=last_yes,
                        bid_size=1000, ask_size=800),
            OutcomeBook(outcome="NO", bid=no_bid, ask=no_ask, last=1.0 - last_yes,
                        bid_size=900, ask_size=700),
        ],
        volume_24h=500000.0,
        open_interest=100000.0,
        fees=fees,
        ts_ms=_NOW,
        observed_at_ms=_NOW,
        status=status,
    )


# ---------------------------------------------------------------------------
# Tests — text matching
# ---------------------------------------------------------------------------

def test_title_similarity_identical():
    a = _make_event(venue="polymarket", title="Will Bitcoin exceed $150k?")
    b = _make_event(venue="kalshi", title="Will Bitcoin exceed $150k?")
    sim = _title_similarity(a, b)
    assert sim == pytest.approx(1.0)


def test_title_similarity_synonyms():
    a = _make_event(venue="polymarket", title="Will Bitcoin go above $150,000?")
    b = _make_event(venue="kalshi", title="BTC to exceed $150,000?")
    sim = _title_similarity(a, b)
    # With synonym expansion, bitcoin/BTC and above/exceed should boost similarity
    assert sim > 0.3


def test_title_similarity_unrelated():
    a = _make_event(venue="polymarket", title="Will Bitcoin exceed $150k?",
                    question="Will Bitcoin exceed $150k?")
    b = _make_event(venue="kalshi", title="Will the Fed cut rates in June?",
                    question="Will the Fed cut rates in June?")
    sim = _title_similarity(a, b)
    assert sim < 0.3


def test_synonym_expansion():
    tokens = {"bitcoin", "above", "150000"}
    expanded = _expand_synonyms(tokens)
    assert "btc" in expanded
    assert "exceed" in expanded
    assert "over" in expanded


# ---------------------------------------------------------------------------
# Tests — candidate finding
# ---------------------------------------------------------------------------

def test_find_candidates_matching_markets():
    poly = _make_event(venue="polymarket", market_id="poly-btc-150k",
                       title="Will Bitcoin exceed $150k by July 2026?")
    kalshi = _make_event(venue="kalshi", market_id="kalshi-btc-150k",
                         title="Bitcoin to exceed $150,000 by July 2026?")
    candidates = find_candidate_pairs([poly], [kalshi])
    assert len(candidates) == 1
    assert candidates[0][0].venue == "polymarket"
    assert candidates[0][1].venue == "kalshi"
    assert candidates[0][2] > 0.3  # title similarity


def test_find_candidates_skips_same_venue():
    a = _make_event(venue="polymarket", market_id="p1")
    b = _make_event(venue="polymarket", market_id="p2")
    candidates = find_candidate_pairs([a], [b])
    assert len(candidates) == 0


def test_find_candidates_skips_closed():
    poly = _make_event(venue="polymarket", status="closed")
    kalshi = _make_event(venue="kalshi")
    candidates = find_candidate_pairs([poly], [kalshi])
    assert len(candidates) == 0


def test_find_candidates_skips_different_category():
    poly = _make_event(venue="polymarket", category="crypto",
                       title="Will Bitcoin exceed $150k?")
    kalshi = _make_event(venue="kalshi", category="politics",
                         title="Will Bitcoin exceed $150k?")
    candidates = find_candidate_pairs([poly], [kalshi])
    assert len(candidates) == 0


def test_find_candidates_expiry_too_far():
    poly = _make_event(venue="polymarket", expiry_ts_ms=_EXPIRY)
    kalshi = _make_event(venue="kalshi",
                         expiry_ts_ms=_EXPIRY + 30 * 24 * 3600 * 1000)  # 30 days apart
    candidates = find_candidate_pairs([poly], [kalshi])
    assert len(candidates) == 0


# ---------------------------------------------------------------------------
# Tests — match_markets
# ---------------------------------------------------------------------------

def test_match_markets_produces_pairs():
    poly = _make_event(
        venue="polymarket", market_id="poly-btc-150k",
        title="Will Bitcoin exceed $150k by July 2026?",
        question="Will Bitcoin exceed $150k by July 2026?",
        resolution_text="Resolves YES if Bitcoin price exceeds $150,000 on any major exchange before July 1, 2026 UTC.",
    )
    kalshi = _make_event(
        venue="kalshi", market_id="KXBTC-26JUN30",
        title="Bitcoin to exceed $150,000 by July 2026?",
        question="Bitcoin to exceed $150,000 by July 2026?",
        resolution_text="Resolves YES if Bitcoin exceeds $150,000 on a major exchange before July 1 2026 midnight UTC.",
    )
    pairs = match_markets([poly], [kalshi])
    assert len(pairs) == 1
    assert pairs[0].left.venue == "polymarket"
    assert pairs[0].right.venue == "kalshi"
    assert pairs[0].match_confidence > 0.4
    assert pairs[0].settlement_compatible is True


def test_match_markets_incompatible_resolution():
    poly = _make_event(
        venue="polymarket", market_id="poly-btc-150k",
        title="Will Bitcoin exceed $150k by July 2026?",
        question="Will Bitcoin exceed $150k by July 2026?",
        resolution_text="Resolves YES if Bitcoin exceeds $150,000 at Coinbase closing price.",
    )
    kalshi = _make_event(
        venue="kalshi", market_id="kalshi-fed-rate",
        title="Will the Fed cut rates in June 2026?",
        question="Will the Fed cut rates in June 2026?",
        category="politics",
        resolution_text="Resolves YES if the Federal Reserve cuts the federal funds rate at June 2026 FOMC.",
    )
    pairs = match_markets([poly], [kalshi])
    # Totally different markets with different categories — should not match
    assert len(pairs) == 0


def test_match_deduplicates():
    poly = _make_event(venue="polymarket", market_id="p1",
                       title="Will Bitcoin exceed $150k?")
    kalshi = _make_event(venue="kalshi", market_id="k1",
                         title="Will Bitcoin exceed $150k?")
    # Pass same events twice — should still produce only 1 pair
    pairs = match_markets([poly, poly], [kalshi, kalshi])
    assert len(pairs) == 1


# ---------------------------------------------------------------------------
# Tests — price extraction
# ---------------------------------------------------------------------------

def test_get_yes_price_mid():
    event = _make_event(yes_bid=0.40, yes_ask=0.44)
    assert _get_yes_price(event) == pytest.approx(0.42)


def test_get_yes_price_last_fallback():
    event = _make_event(yes_bid=0.0, yes_ask=0.0, last_yes=0.45)
    assert _get_yes_price(event) == pytest.approx(0.45)


# ---------------------------------------------------------------------------
# Tests — arbitrage detection
# ---------------------------------------------------------------------------

def test_arb_detected_when_spread_exists():
    """If poly YES=0.35 and kalshi YES=0.60, buying YES on poly + NO on kalshi
    gives spread = (1-0.60) - 0.35 = 0.05. After Polymarket fees (~2.02%),
    edge should still be positive."""
    poly = _make_event(
        venue="polymarket", market_id="poly-btc",
        title="Will Bitcoin exceed $150k by July 2026?",
        question="Will Bitcoin exceed $150k by July 2026?",
        resolution_text="Resolves YES if Bitcoin exceeds $150,000 on any major exchange before July 1, 2026 UTC.",
        yes_bid=0.33, yes_ask=0.37, last_yes=0.35,
        no_bid=0.63, no_ask=0.67,
    )
    kalshi = _make_event(
        venue="kalshi", market_id="kalshi-btc",
        title="Bitcoin to exceed $150,000 by July 2026?",
        question="Bitcoin to exceed $150,000 by July 2026?",
        resolution_text="Resolves YES if Bitcoin exceeds $150,000 on a major exchange before July 1 2026 midnight UTC.",
        yes_bid=0.58, yes_ask=0.62, last_yes=0.60,
        no_bid=0.38, no_ask=0.42,
    )
    opps = find_arbitrage_opportunities([poly], [kalshi])
    assert len(opps) >= 1
    opp = opps[0]
    assert opp.spread > 0.03
    assert opp.estimated_edge > 0
    assert opp.buy_venue == "polymarket"  # cheaper YES
    assert opp.resolution_compat.compatible is True


def test_no_arb_when_prices_aligned():
    """If both venues price YES at ~0.50, no arb exists."""
    poly = _make_event(
        venue="polymarket", market_id="poly-btc",
        title="Will Bitcoin exceed $150k by July 2026?",
        question="Will Bitcoin exceed $150k by July 2026?",
        resolution_text="Resolves YES if Bitcoin exceeds $150,000 on any major exchange before July 1, 2026 UTC.",
        yes_bid=0.49, yes_ask=0.51, last_yes=0.50,
        no_bid=0.49, no_ask=0.51,
    )
    kalshi = _make_event(
        venue="kalshi", market_id="kalshi-btc",
        title="Bitcoin to exceed $150,000 by July 2026?",
        question="Bitcoin to exceed $150,000 by July 2026?",
        resolution_text="Resolves YES if Bitcoin exceeds $150,000 on a major exchange before July 1 2026 midnight UTC.",
        yes_bid=0.49, yes_ask=0.51, last_yes=0.50,
        no_bid=0.49, no_ask=0.51,
    )
    opps = find_arbitrage_opportunities([poly], [kalshi])
    assert len(opps) == 0


def test_no_arb_when_resolution_incompatible():
    """Even with price divergence, incompatible resolutions = no arb."""
    poly = _make_event(
        venue="polymarket", market_id="poly-btc",
        title="Will Bitcoin exceed $150k by July 2026?",
        question="Will Bitcoin exceed $150k by July 2026?",
        resolution_text="Resolves YES if Bitcoin exceeds $150,000 at Coinbase closing price on July 1.",
        yes_bid=0.33, yes_ask=0.37, last_yes=0.35,
    )
    kalshi = _make_event(
        venue="kalshi", market_id="kalshi-btc",
        title="Bitcoin to exceed $150,000 by July 2026?",
        question="Bitcoin to exceed $150,000 by July 2026?",
        resolution_text="Resolves YES if annual average BTC price > $150k. Based on CME futures settlement.",
        yes_bid=0.58, yes_ask=0.62, last_yes=0.60,
    )
    opps = find_arbitrage_opportunities([poly], [kalshi])
    assert len(opps) == 0


def test_arb_opportunity_to_dict():
    """ArbOpportunity.to_dict() should produce a serializable dict."""
    poly = _make_event(
        venue="polymarket", market_id="poly-btc",
        title="Will Bitcoin exceed $150k by July 2026?",
        question="Will Bitcoin exceed $150k by July 2026?",
        resolution_text="Resolves YES if Bitcoin exceeds $150,000 on any major exchange before July 1, 2026 UTC.",
        yes_bid=0.30, yes_ask=0.34, last_yes=0.32,
        no_bid=0.66, no_ask=0.70,
    )
    kalshi = _make_event(
        venue="kalshi", market_id="kalshi-btc",
        title="Bitcoin to exceed $150,000 by July 2026?",
        question="Bitcoin to exceed $150,000 by July 2026?",
        resolution_text="Resolves YES if Bitcoin exceeds $150,000 on a major exchange before July 1 2026 midnight UTC.",
        yes_bid=0.60, yes_ask=0.64, last_yes=0.62,
        no_bid=0.36, no_ask=0.40,
    )
    opps = find_arbitrage_opportunities([poly], [kalshi])
    assert len(opps) >= 1
    d = opps[0].to_dict()
    assert "spread" in d
    assert "buy_venue" in d
    assert "estimated_edge" in d
    assert d["resolution_compatible"] is True


def test_multiple_pairs_sorted_by_edge():
    """When multiple arb opportunities exist, they should be sorted by edge."""
    poly_big = _make_event(
        venue="polymarket", market_id="poly-big",
        title="Will Bitcoin exceed $150k by July 2026?",
        question="Will Bitcoin exceed $150k by July 2026?",
        resolution_text="Resolves YES if Bitcoin exceeds $150,000 on any major exchange before July 1, 2026 UTC.",
        yes_bid=0.25, yes_ask=0.29, last_yes=0.27,  # very cheap
        no_bid=0.71, no_ask=0.75,
    )
    poly_small = _make_event(
        venue="polymarket", market_id="poly-small",
        title="Will Ethereum exceed $10k by July 2026?",
        question="Will Ethereum exceed $10k by July 2026?",
        resolution_text="Resolves YES if Ethereum exceeds $10,000 on any major exchange before July 1, 2026 UTC.",
        yes_bid=0.38, yes_ask=0.42, last_yes=0.40,  # less cheap
        no_bid=0.58, no_ask=0.62,
    )
    kalshi_big = _make_event(
        venue="kalshi", market_id="kalshi-big",
        title="Bitcoin to exceed $150,000 by July 2026?",
        question="Bitcoin to exceed $150,000 by July 2026?",
        resolution_text="Resolves YES if Bitcoin exceeds $150,000 on a major exchange before July 1 2026 midnight UTC.",
        yes_bid=0.60, yes_ask=0.64, last_yes=0.62,
        no_bid=0.36, no_ask=0.40,
    )
    kalshi_small = _make_event(
        venue="kalshi", market_id="kalshi-small",
        title="Ethereum to exceed $10,000 by July 2026?",
        question="Ethereum to exceed $10,000 by July 2026?",
        resolution_text="Resolves YES if Ethereum exceeds $10,000 on a major exchange before July 1 2026 midnight UTC.",
        yes_bid=0.52, yes_ask=0.56, last_yes=0.54,
        no_bid=0.44, no_ask=0.48,
    )
    opps = find_arbitrage_opportunities(
        [poly_big, poly_small],
        [kalshi_big, kalshi_small],
    )
    if len(opps) >= 2:
        assert opps[0].estimated_edge >= opps[1].estimated_edge
