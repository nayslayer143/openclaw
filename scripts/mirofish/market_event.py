#!/usr/bin/env python3
"""
Canonical MarketEvent schema for MiroFish trading system.

Implements the dataclass hierarchy from openclaw-v4.2-strategy.md (Section 5).
All classes support to_dict() / from_dict() for serialization.
MarketEventNormalizer converts raw venue API responses into MarketEvent instances.

Python 3.9 compatible via __future__ annotations.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

Venue = Literal[
    "polymarket",
    "kalshi",
    "metaculus",
    "manifold",
]

ContractType = Literal[
    "binary",
    "threshold",
    "bracket",
    "multi_outcome",
]

Side = Literal["yes", "no"]

SignalSource = Literal[
    "polymarket",
    "kalshi",
    "unusual_whales",
    "crucix",
    "spot_feed",
    "research_agent",
    "simulation",
    "manual",
    "llm",
    "spot",
]

EntityType = Literal[
    "ticker",
    "sector",
    "macro",
    "event",
    "theme",
    "person",
]

Direction = Literal["bullish", "bearish", "neutral"]

MarketStatus = Literal["open", "halted", "closed", "resolved"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ms_now() -> int:
    """Current time as milliseconds since epoch."""
    return int(time.time() * 1000)


def _parse_json_field(val: Any) -> list:
    """Parse a field that may be a JSON string or already a list."""
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (ValueError, TypeError):
            pass
    return []


# ---------------------------------------------------------------------------
# Dataclasses — order matches the v4.2 strategy spec
# ---------------------------------------------------------------------------

@dataclass
class OrderBookLevel:
    price: float
    size: float

    def to_dict(self) -> dict:
        return {"price": self.price, "size": self.size}

    @classmethod
    def from_dict(cls, data: dict) -> OrderBookLevel:
        return cls(price=float(data["price"]), size=float(data["size"]))


@dataclass
class OutcomeBook:
    outcome: str                 # "YES", "NO", ">$120k", etc.
    bid: float
    ask: float
    last: float
    bid_size: float
    ask_size: float
    bids: list[OrderBookLevel] = field(default_factory=list)
    asks: list[OrderBookLevel] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "outcome": self.outcome,
            "bid": self.bid,
            "ask": self.ask,
            "last": self.last,
            "bid_size": self.bid_size,
            "ask_size": self.ask_size,
            "bids": [b.to_dict() for b in self.bids],
            "asks": [a.to_dict() for a in self.asks],
        }

    @classmethod
    def from_dict(cls, data: dict) -> OutcomeBook:
        return cls(
            outcome=str(data["outcome"]),
            bid=float(data["bid"]),
            ask=float(data["ask"]),
            last=float(data["last"]),
            bid_size=float(data["bid_size"]),
            ask_size=float(data["ask_size"]),
            bids=[OrderBookLevel.from_dict(b) for b in data.get("bids", [])],
            asks=[OrderBookLevel.from_dict(a) for a in data.get("asks", [])],
        )


@dataclass
class VenueFees:
    taker_bps: float
    maker_bps: float
    settlement_fee_bps: float = 0.0
    withdrawal_fee_fixed: float = 0.0
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "taker_bps": self.taker_bps,
            "maker_bps": self.maker_bps,
            "settlement_fee_bps": self.settlement_fee_bps,
            "withdrawal_fee_fixed": self.withdrawal_fee_fixed,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> VenueFees:
        return cls(
            taker_bps=float(data["taker_bps"]),
            maker_bps=float(data["maker_bps"]),
            settlement_fee_bps=float(data.get("settlement_fee_bps", 0.0)),
            withdrawal_fee_fixed=float(data.get("withdrawal_fee_fixed", 0.0)),
            notes=str(data.get("notes", "")),
        )


@dataclass
class ContractSpec:
    contract_type: ContractType
    underlying: str                      # "BTC", "US election", "Fed rate", etc.
    strike: Optional[float] = None       # for threshold/bracket contracts
    lower_bound: Optional[float] = None  # for bracket
    upper_bound: Optional[float] = None  # for bracket
    expiry_ts_ms: int = 0
    timezone: str = "UTC"

    def to_dict(self) -> dict:
        return {
            "contract_type": self.contract_type,
            "underlying": self.underlying,
            "strike": self.strike,
            "lower_bound": self.lower_bound,
            "upper_bound": self.upper_bound,
            "expiry_ts_ms": self.expiry_ts_ms,
            "timezone": self.timezone,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ContractSpec:
        return cls(
            contract_type=data["contract_type"],
            underlying=str(data["underlying"]),
            strike=float(data["strike"]) if data.get("strike") is not None else None,
            lower_bound=float(data["lower_bound"]) if data.get("lower_bound") is not None else None,
            upper_bound=float(data["upper_bound"]) if data.get("upper_bound") is not None else None,
            expiry_ts_ms=int(data.get("expiry_ts_ms", 0)),
            timezone=str(data.get("timezone", "UTC")),
        )


@dataclass
class ResolutionSpec:
    resolution_text: str
    source_rules_url: Optional[str] = None
    resolves_yes_if: Optional[str] = None
    resolves_no_if: Optional[str] = None
    ambiguity_flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "resolution_text": self.resolution_text,
            "source_rules_url": self.source_rules_url,
            "resolves_yes_if": self.resolves_yes_if,
            "resolves_no_if": self.resolves_no_if,
            "ambiguity_flags": list(self.ambiguity_flags),
        }

    @classmethod
    def from_dict(cls, data: dict) -> ResolutionSpec:
        return cls(
            resolution_text=str(data["resolution_text"]),
            source_rules_url=data.get("source_rules_url"),
            resolves_yes_if=data.get("resolves_yes_if"),
            resolves_no_if=data.get("resolves_no_if"),
            ambiguity_flags=list(data.get("ambiguity_flags", [])),
        )


@dataclass
class MarketEvent:
    market_id: str
    venue: Venue
    title: str
    question: str
    category: str
    contract: ContractSpec
    resolution: ResolutionSpec
    outcomes: list[OutcomeBook]
    volume_24h: float
    open_interest: float
    fees: VenueFees
    ts_ms: int                          # event timestamp in ms
    observed_at_ms: int                 # ingestion timestamp in ms
    status: MarketStatus
    raw_payload_ref: Optional[str] = None
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "market_id": self.market_id,
            "venue": self.venue,
            "title": self.title,
            "question": self.question,
            "category": self.category,
            "contract": self.contract.to_dict(),
            "resolution": self.resolution.to_dict(),
            "outcomes": [o.to_dict() for o in self.outcomes],
            "volume_24h": self.volume_24h,
            "open_interest": self.open_interest,
            "fees": self.fees.to_dict(),
            "ts_ms": self.ts_ms,
            "observed_at_ms": self.observed_at_ms,
            "status": self.status,
            "raw_payload_ref": self.raw_payload_ref,
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, data: dict) -> MarketEvent:
        return cls(
            market_id=str(data["market_id"]),
            venue=data["venue"],
            title=str(data["title"]),
            question=str(data["question"]),
            category=str(data["category"]),
            contract=ContractSpec.from_dict(data["contract"]),
            resolution=ResolutionSpec.from_dict(data["resolution"]),
            outcomes=[OutcomeBook.from_dict(o) for o in data["outcomes"]],
            volume_24h=float(data["volume_24h"]),
            open_interest=float(data["open_interest"]),
            fees=VenueFees.from_dict(data["fees"]),
            ts_ms=int(data["ts_ms"]),
            observed_at_ms=int(data["observed_at_ms"]),
            status=data["status"],
            raw_payload_ref=data.get("raw_payload_ref"),
            tags=list(data.get("tags", [])),
        )


@dataclass
class MatchedMarketPair:
    pair_id: str
    left: MarketEvent
    right: MarketEvent
    match_confidence: float             # 0-1 semantic + rules-based match
    settlement_compatible: bool
    incompatibility_reasons: list[str] = field(default_factory=list)
    normalized_underlying_key: str = ""

    def to_dict(self) -> dict:
        return {
            "pair_id": self.pair_id,
            "left": self.left.to_dict(),
            "right": self.right.to_dict(),
            "match_confidence": self.match_confidence,
            "settlement_compatible": self.settlement_compatible,
            "incompatibility_reasons": list(self.incompatibility_reasons),
            "normalized_underlying_key": self.normalized_underlying_key,
        }

    @classmethod
    def from_dict(cls, data: dict) -> MatchedMarketPair:
        return cls(
            pair_id=str(data["pair_id"]),
            left=MarketEvent.from_dict(data["left"]),
            right=MarketEvent.from_dict(data["right"]),
            match_confidence=float(data["match_confidence"]),
            settlement_compatible=bool(data["settlement_compatible"]),
            incompatibility_reasons=list(data.get("incompatibility_reasons", [])),
            normalized_underlying_key=str(data.get("normalized_underlying_key", "")),
        )


@dataclass
class ExternalSignal:
    signal_id: str
    source: SignalSource
    ts_ms: int
    entity_type: EntityType
    entity_key: str                     # "XLE", "defense", "rates", "BTC", etc.
    direction: Direction
    strength: float                     # normalized 0-1
    confidence: float                   # normalized 0-1
    horizon_hours: float
    half_life_hours: float = 24.0       # fusion layer applies time decay
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "signal_id": self.signal_id,
            "source": self.source,
            "ts_ms": self.ts_ms,
            "entity_type": self.entity_type,
            "entity_key": self.entity_key,
            "direction": self.direction,
            "strength": self.strength,
            "confidence": self.confidence,
            "horizon_hours": self.horizon_hours,
            "half_life_hours": self.half_life_hours,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> ExternalSignal:
        return cls(
            signal_id=str(data["signal_id"]),
            source=data["source"],
            ts_ms=int(data["ts_ms"]),
            entity_type=data["entity_type"],
            entity_key=str(data["entity_key"]),
            direction=data["direction"],
            strength=float(data["strength"]),
            confidence=float(data["confidence"]),
            horizon_hours=float(data["horizon_hours"]),
            half_life_hours=float(data.get("half_life_hours", 24.0)),
            metadata=dict(data.get("metadata", {})),
        )


# ---------------------------------------------------------------------------
# Normalizer — converts raw venue API responses to MarketEvent
# ---------------------------------------------------------------------------

# Default Polymarket fee schedule (as of 2026-03).
# Polymarket charges no maker fee, 2 bps taker, 2% settlement on profit.
_POLYMARKET_FEES = VenueFees(
    taker_bps=2.0,
    maker_bps=0.0,
    settlement_fee_bps=200.0,
    notes="Polymarket: 0 maker, 2bps taker, 2% settlement on profit",
)


class MarketEventNormalizer:
    """Converts raw venue API payloads into canonical MarketEvent objects."""

    # ------------------------------------------------------------------
    # Polymarket  (gamma-api.polymarket.com)
    # ------------------------------------------------------------------

    @staticmethod
    def normalize_polymarket(raw_data: dict) -> MarketEvent:
        """
        Convert a single market dict from the Polymarket Gamma API into a
        canonical MarketEvent.

        Expected raw_data keys (gamma API):
            conditionId / id, question, category, volume, outcomePrices,
            outcomes, endDate / end_date, tokens, description, slug, active,
            closed, liquidity, ...
        """
        now_ms = _ms_now()

        # --- identifiers ---
        market_id = str(raw_data.get("conditionId") or raw_data.get("id") or "")
        question = str(raw_data.get("question", ""))
        title = str(raw_data.get("title") or raw_data.get("question", ""))
        category = (raw_data.get("category") or "").lower()
        slug = raw_data.get("slug", "")

        # --- status ---
        is_closed = raw_data.get("closed", False)
        is_active = raw_data.get("active", True)
        if is_closed:
            status: MarketStatus = "closed"
        elif not is_active:
            status = "halted"
        else:
            status = "open"

        # --- volume / liquidity ---
        volume_24h = float(raw_data.get("volume", 0) or 0)
        open_interest = float(raw_data.get("liquidity", 0) or 0)

        # --- expiry ---
        end_date_str = raw_data.get("endDate") or raw_data.get("end_date") or ""
        expiry_ts_ms = 0
        if end_date_str:
            try:
                import datetime
                # Handle ISO format with or without timezone
                dt_str = end_date_str.replace("Z", "+00:00")
                dt = datetime.datetime.fromisoformat(dt_str)
                expiry_ts_ms = int(dt.timestamp() * 1000)
            except (ValueError, TypeError):
                pass

        # --- outcomes ---
        outcome_prices = _parse_json_field(raw_data.get("outcomePrices"))
        outcome_labels = _parse_json_field(raw_data.get("outcomes"))
        tokens = raw_data.get("tokens", []) or []

        outcomes: list[OutcomeBook] = []

        if outcome_prices and outcome_labels:
            # Gamma API format: parallel arrays
            for label, price_str in zip(outcome_labels, outcome_prices):
                try:
                    price = float(price_str)
                except (ValueError, TypeError):
                    price = 0.0
                outcomes.append(OutcomeBook(
                    outcome=str(label).upper(),
                    bid=price,
                    ask=price,
                    last=price,
                    bid_size=0.0,
                    ask_size=0.0,
                ))

        if not outcomes and tokens:
            # CLOB API fallback: tokens array
            for tok in tokens:
                outcome_label = (tok.get("outcome") or "").upper()
                try:
                    price = float(tok.get("price", 0) or 0)
                except (ValueError, TypeError):
                    price = 0.0
                outcomes.append(OutcomeBook(
                    outcome=outcome_label,
                    bid=price,
                    ask=price,
                    last=price,
                    bid_size=0.0,
                    ask_size=0.0,
                ))

        # --- contract spec ---
        # Polymarket markets are binary by default; multi-outcome when > 2 outcomes
        if len(outcomes) > 2:
            contract_type: ContractType = "multi_outcome"
        else:
            contract_type = "binary"

        # Attempt to infer underlying from category + question
        underlying = category or "general"

        contract = ContractSpec(
            contract_type=contract_type,
            underlying=underlying,
            expiry_ts_ms=expiry_ts_ms,
        )

        # --- resolution spec ---
        description = str(raw_data.get("description", ""))
        resolution = ResolutionSpec(
            resolution_text=description[:2000] if description else question,
            source_rules_url=f"https://polymarket.com/event/{slug}" if slug else None,
        )

        # --- tags ---
        tags: list[str] = []
        if category:
            tags.append(category)
        if slug:
            tags.append(f"slug:{slug}")

        return MarketEvent(
            market_id=market_id,
            venue="polymarket",
            title=title,
            question=question,
            category=category,
            contract=contract,
            resolution=resolution,
            outcomes=outcomes,
            volume_24h=volume_24h,
            open_interest=open_interest,
            fees=_POLYMARKET_FEES,
            ts_ms=now_ms,
            observed_at_ms=now_ms,
            status=status,
            raw_payload_ref=None,
            tags=tags,
        )

    # ------------------------------------------------------------------
    # Kalshi  (stub — not yet implemented)
    # ------------------------------------------------------------------

    @staticmethod
    def normalize_kalshi(raw_data: dict) -> MarketEvent:
        """
        Convert a single market dict from the Kalshi API into a canonical
        MarketEvent.

        Not yet implemented — Kalshi API integration is pending.
        """
        raise NotImplementedError(
            "Kalshi normalizer not yet implemented. "
            "See openclaw-v4.2-strategy.md Phase 5 for integration plan."
        )


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 70)
    print("MarketEvent schema self-test")
    print("=" * 70)

    # ---- 1. Create a MarketEvent from mock Polymarket gamma API data ----
    mock_polymarket_response = {
        "conditionId": "0xabc123def456",
        "question": "Will Bitcoin exceed $150k by July 2026?",
        "title": "Bitcoin $150k by July 2026",
        "category": "Crypto",
        "slug": "bitcoin-150k-july-2026",
        "volume": 2450000,
        "liquidity": 185000,
        "active": True,
        "closed": False,
        "endDate": "2026-07-01T00:00:00Z",
        "description": "This market resolves YES if Bitcoin price exceeds $150,000 USD on any major exchange before July 1, 2026 00:00 UTC.",
        "outcomePrices": ["0.42", "0.58"],
        "outcomes": ["Yes", "No"],
    }

    normalizer = MarketEventNormalizer()
    event = normalizer.normalize_polymarket(mock_polymarket_response)

    print(f"\n[1] Normalized Polymarket event:")
    print(f"    market_id : {event.market_id}")
    print(f"    venue     : {event.venue}")
    print(f"    title     : {event.title}")
    print(f"    question  : {event.question}")
    print(f"    category  : {event.category}")
    print(f"    status    : {event.status}")
    print(f"    contract  : {event.contract.contract_type} / {event.contract.underlying}")
    print(f"    expiry_ms : {event.contract.expiry_ts_ms}")
    print(f"    outcomes  : {[(o.outcome, o.bid) for o in event.outcomes]}")
    print(f"    volume_24h: ${event.volume_24h:,.0f}")
    print(f"    fees      : {event.fees.taker_bps}bps taker, {event.fees.settlement_fee_bps}bps settlement")
    print(f"    tags      : {event.tags}")

    # ---- 2. Round-trip serialization ----
    d = event.to_dict()
    event2 = MarketEvent.from_dict(d)

    assert event.market_id == event2.market_id, "market_id mismatch"
    assert event.venue == event2.venue, "venue mismatch"
    assert event.question == event2.question, "question mismatch"
    assert event.volume_24h == event2.volume_24h, "volume_24h mismatch"
    assert len(event.outcomes) == len(event2.outcomes), "outcomes length mismatch"
    assert event.outcomes[0].bid == event2.outcomes[0].bid, "outcome bid mismatch"
    assert event.contract.expiry_ts_ms == event2.contract.expiry_ts_ms, "expiry mismatch"
    assert event.fees.taker_bps == event2.fees.taker_bps, "fees mismatch"
    assert event.tags == event2.tags, "tags mismatch"
    print("\n[2] Round-trip serialization: PASS")

    # ---- 3. JSON serialization ----
    json_str = json.dumps(d, indent=2)
    assert json.loads(json_str) == d, "JSON round-trip failed"
    print(f"[3] JSON serialization: PASS ({len(json_str)} bytes)")

    # ---- 4. ExternalSignal round-trip ----
    signal = ExternalSignal(
        signal_id="sig-001",
        source="unusual_whales",
        ts_ms=_ms_now(),
        entity_type="ticker",
        entity_key="BTC",
        direction="bullish",
        strength=0.82,
        confidence=0.75,
        horizon_hours=48.0,
        half_life_hours=24.0,
        metadata={"flow_type": "calls", "volume_ratio": 3.2},
    )
    sig_d = signal.to_dict()
    signal2 = ExternalSignal.from_dict(sig_d)
    assert signal.signal_id == signal2.signal_id, "signal_id mismatch"
    assert signal.strength == signal2.strength, "strength mismatch"
    assert signal.metadata == signal2.metadata, "metadata mismatch"
    print("[4] ExternalSignal round-trip: PASS")

    # ---- 5. MatchedMarketPair round-trip ----
    pair = MatchedMarketPair(
        pair_id="pair-poly-kalshi-btc150k",
        left=event,
        right=event2,
        match_confidence=0.92,
        settlement_compatible=True,
        incompatibility_reasons=[],
        normalized_underlying_key="BTC-150k-Jul2026",
    )
    pair_d = pair.to_dict()
    pair2 = MatchedMarketPair.from_dict(pair_d)
    assert pair.pair_id == pair2.pair_id, "pair_id mismatch"
    assert pair.match_confidence == pair2.match_confidence, "match_confidence mismatch"
    assert pair.left.market_id == pair2.left.market_id, "left market_id mismatch"
    print("[5] MatchedMarketPair round-trip: PASS")

    # ---- 6. Kalshi stub raises NotImplementedError ----
    try:
        normalizer.normalize_kalshi({"id": "test"})
        assert False, "Should have raised NotImplementedError"
    except NotImplementedError:
        print("[6] Kalshi NotImplementedError: PASS")

    print("\n" + "=" * 70)
    print("All tests passed.")
    print("=" * 70)
