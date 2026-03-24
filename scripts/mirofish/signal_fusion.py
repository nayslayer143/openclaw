#!/usr/bin/env python3
"""
Signal fusion layer — normalizes ExternalSignals with time-decay,
maps entities to prediction markets, and produces fused signal scores
that inform trading decisions.

Phase 5D Steps 1-2: ExternalSignal time-decay + entity/market mapping.

The fusion layer:
1. Ingests signals from UW, Crucix, spot feeds
2. Applies exponential time-decay based on signal half-life
3. Maps entity keys (BTC, XLE, rates) to relevant prediction markets
4. Produces a fused score per market: weighted sum of decayed signals

Python 3.9 compatible via __future__ annotations.
"""
from __future__ import annotations

import math
import os
import re
import time
from dataclasses import dataclass, field

from scripts.mirofish.market_event import ExternalSignal, MarketEvent


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_HALF_LIFE_HOURS = float(os.environ.get("SIGNAL_DEFAULT_HALFLIFE", "24.0"))
MIN_SIGNAL_STRENGTH = float(os.environ.get("SIGNAL_MIN_STRENGTH", "0.05"))
MAX_FUSED_SIGNALS = int(os.environ.get("SIGNAL_MAX_FUSED", "10"))


# ---------------------------------------------------------------------------
# Entity → Market Mapping
# ---------------------------------------------------------------------------

# Maps entity keys to regex patterns that match prediction market questions
ENTITY_PATTERNS: dict[str, list[re.Pattern]] = {
    "BTC": [
        re.compile(r"\b(?:BTC|Bitcoin)\b", re.IGNORECASE),
    ],
    "ETH": [
        re.compile(r"\b(?:ETH|Ethereum|Ether)\b", re.IGNORECASE),
    ],
    "SOL": [
        re.compile(r"\b(?:SOL|Solana)\b", re.IGNORECASE),
    ],
    "XRP": [
        re.compile(r"\b(?:XRP|Ripple)\b", re.IGNORECASE),
    ],
    # Sectors
    "XLE": [
        re.compile(r"\b(?:oil|energy|XLE|crude|petroleum|OPEC)\b", re.IGNORECASE),
    ],
    "XLF": [
        re.compile(r"\b(?:bank|financial|XLF|Goldman|JPMorgan|finance)\b", re.IGNORECASE),
    ],
    "defense": [
        re.compile(r"\b(?:defense|military|weapons|NATO|war|conflict|missile)\b", re.IGNORECASE),
    ],
    # Macro
    "rates": [
        re.compile(r"\b(?:Fed|FOMC|interest rate|rate cut|rate hike|federal reserve)\b", re.IGNORECASE),
    ],
    "inflation": [
        re.compile(r"\b(?:CPI|inflation|price index|deflation)\b", re.IGNORECASE),
    ],
    "GDP": [
        re.compile(r"\b(?:GDP|recession|economic growth|economy)\b", re.IGNORECASE),
    ],
    # Events
    "election": [
        re.compile(r"\b(?:election|vote|president|congress|senate|governor|poll)\b", re.IGNORECASE),
    ],
    "climate": [
        re.compile(r"\b(?:climate|temperature|weather|hurricane|flood|wildfire)\b", re.IGNORECASE),
    ],
}

# Reverse map: entity_key aliases → canonical key
ENTITY_ALIASES: dict[str, str] = {
    "bitcoin": "BTC", "btc": "BTC",
    "ethereum": "ETH", "eth": "ETH", "ether": "ETH",
    "solana": "SOL", "sol": "SOL",
    "ripple": "XRP", "xrp": "XRP",
    "oil": "XLE", "energy": "XLE", "crude": "XLE",
    "bank": "XLF", "financial": "XLF",
    "military": "defense", "war": "defense",
    "fed": "rates", "fomc": "rates", "interest": "rates",
    "cpi": "inflation",
    "gdp": "GDP", "recession": "GDP",
    "vote": "election", "president": "election",
}


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class DecayedSignal:
    signal: ExternalSignal
    decayed_strength: float     # strength * decay_factor
    decay_factor: float         # 0-1, based on age and half-life
    age_hours: float

    def to_dict(self) -> dict:
        return {
            "signal_id": self.signal.signal_id,
            "source": self.signal.source,
            "entity_key": self.signal.entity_key,
            "direction": self.signal.direction,
            "decayed_strength": self.decayed_strength,
            "decay_factor": self.decay_factor,
            "age_hours": self.age_hours,
        }


@dataclass
class FusedMarketScore:
    market_id: str
    question: str
    bullish_score: float        # sum of bullish decayed strengths
    bearish_score: float        # sum of bearish decayed strengths
    net_score: float            # bullish - bearish (-1 to 1)
    signal_count: int
    top_signals: list[DecayedSignal] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "market_id": self.market_id,
            "bullish_score": self.bullish_score,
            "bearish_score": self.bearish_score,
            "net_score": self.net_score,
            "signal_count": self.signal_count,
            "top_signals": [s.to_dict() for s in self.top_signals[:5]],
        }


# ---------------------------------------------------------------------------
# Time decay
# ---------------------------------------------------------------------------

def apply_decay(signal: ExternalSignal, now_ms: int | None = None) -> DecayedSignal:
    """
    Apply exponential time-decay to a signal based on its half-life.
    decay = 0.5 ^ (age / half_life)
    """
    if now_ms is None:
        now_ms = int(time.time() * 1000)

    age_ms = max(0, now_ms - signal.ts_ms)
    age_hours = age_ms / (1000 * 3600)

    half_life = signal.half_life_hours or DEFAULT_HALF_LIFE_HOURS
    if half_life <= 0:
        half_life = DEFAULT_HALF_LIFE_HOURS

    decay_factor = math.pow(0.5, age_hours / half_life)
    decayed_strength = signal.strength * decay_factor

    return DecayedSignal(
        signal=signal,
        decayed_strength=decayed_strength,
        decay_factor=decay_factor,
        age_hours=age_hours,
    )


def decay_signals(
    signals: list[ExternalSignal],
    now_ms: int | None = None,
) -> list[DecayedSignal]:
    """Apply decay to all signals and filter out weak ones."""
    decayed = [apply_decay(s, now_ms) for s in signals]
    return [d for d in decayed if d.decayed_strength >= MIN_SIGNAL_STRENGTH]


# ---------------------------------------------------------------------------
# Entity mapping
# ---------------------------------------------------------------------------

def canonicalize_entity(key: str) -> str:
    """Resolve an entity key to its canonical form."""
    return ENTITY_ALIASES.get(key.lower(), key)


def match_entity_to_market(entity_key: str, market_question: str) -> bool:
    """Check if an entity key is relevant to a market question."""
    canonical = canonicalize_entity(entity_key)
    patterns = ENTITY_PATTERNS.get(canonical, [])
    return any(p.search(market_question) for p in patterns)


def find_relevant_signals(
    market: dict | MarketEvent,
    signals: list[DecayedSignal],
) -> list[DecayedSignal]:
    """Find signals relevant to a specific market."""
    if isinstance(market, MarketEvent):
        question = market.question
    else:
        question = market.get("question", "")

    relevant = []
    for ds in signals:
        entity = ds.signal.entity_key
        if match_entity_to_market(entity, question):
            relevant.append(ds)

    # Sort by decayed strength descending
    relevant.sort(key=lambda d: d.decayed_strength, reverse=True)
    return relevant[:MAX_FUSED_SIGNALS]


# ---------------------------------------------------------------------------
# Fusion scoring
# ---------------------------------------------------------------------------

def compute_fused_score(
    market: dict | MarketEvent,
    signals: list[DecayedSignal],
) -> FusedMarketScore:
    """
    Compute a fused signal score for a market from relevant decayed signals.
    Bullish signals push YES, bearish push NO.
    """
    if isinstance(market, MarketEvent):
        market_id = market.market_id
        question = market.question
    else:
        market_id = market.get("market_id", "")
        question = market.get("question", "")

    relevant = find_relevant_signals(market, signals)

    bullish = 0.0
    bearish = 0.0

    for ds in relevant:
        weighted = ds.decayed_strength * ds.signal.confidence
        if ds.signal.direction == "bullish":
            bullish += weighted
        elif ds.signal.direction == "bearish":
            bearish += weighted
        # neutral signals don't contribute

    # Normalize to -1..1 range
    total = bullish + bearish
    net = (bullish - bearish) / total if total > 0 else 0.0

    return FusedMarketScore(
        market_id=market_id,
        question=question,
        bullish_score=bullish,
        bearish_score=bearish,
        net_score=net,
        signal_count=len(relevant),
        top_signals=relevant,
    )


def fuse_all_markets(
    markets: list[dict],
    raw_signals: list[ExternalSignal],
    now_ms: int | None = None,
) -> list[FusedMarketScore]:
    """
    Compute fused scores for all markets. Returns scores sorted by
    absolute net_score descending (strongest signal conviction first).
    """
    decayed = decay_signals(raw_signals, now_ms)
    scores = [compute_fused_score(m, decayed) for m in markets]
    # Only return markets with signals
    scores = [s for s in scores if s.signal_count > 0]
    scores.sort(key=lambda s: abs(s.net_score), reverse=True)
    return scores


# ---------------------------------------------------------------------------
# Signal conversion helpers
# ---------------------------------------------------------------------------

def uw_signal_to_external(signal_dict: dict) -> ExternalSignal | None:
    """Convert a UW signal dict to an ExternalSignal."""
    try:
        ts_str = signal_dict.get("fetched_at", "")
        ts_ms = int(time.time() * 1000)
        if ts_str:
            import datetime
            dt = datetime.datetime.fromisoformat(ts_str)
            ts_ms = int(dt.timestamp() * 1000)

        direction = signal_dict.get("direction", "neutral").lower()
        if direction not in ("bullish", "bearish", "neutral"):
            direction = "neutral"

        return ExternalSignal(
            signal_id=f"uw-{signal_dict.get('ticker', '')}-{ts_str[:16]}",
            source="unusual_whales",
            ts_ms=ts_ms,
            entity_type="ticker",
            entity_key=signal_dict.get("ticker", ""),
            direction=direction,
            strength=0.7,
            confidence=0.6,
            horizon_hours=48.0,
            half_life_hours=24.0,
            metadata={"signal_type": signal_dict.get("signal_type", "")},
        )
    except Exception:
        return None


def crucix_signal_to_external(signal_dict: dict) -> ExternalSignal | None:
    """Convert a Crucix signal dict to an ExternalSignal."""
    try:
        ts_str = signal_dict.get("fetched_at", "")
        ts_ms = int(time.time() * 1000)
        if ts_str:
            import datetime
            dt = datetime.datetime.fromisoformat(ts_str)
            ts_ms = int(dt.timestamp() * 1000)

        direction = signal_dict.get("direction", "neutral").lower()
        if direction not in ("bullish", "bearish", "neutral"):
            direction = "neutral"

        return ExternalSignal(
            signal_id=f"crucix-{signal_dict.get('ticker', '')}-{ts_str[:16]}",
            source="crucix",
            ts_ms=ts_ms,
            entity_type="macro",
            entity_key=signal_dict.get("ticker", ""),
            direction=direction,
            strength=0.5,
            confidence=0.5,
            horizon_hours=72.0,
            half_life_hours=48.0,
            metadata={"source": signal_dict.get("source", "")},
        )
    except Exception:
        return None


def convert_raw_signals(raw_signals: list[dict]) -> list[ExternalSignal]:
    """Convert raw signal dicts from feeds into ExternalSignal objects."""
    externals = []
    for s in raw_signals:
        source = s.get("source", "")
        if "uw" in source.lower() or "unusual" in source.lower() or "whale" in source.lower():
            ext = uw_signal_to_external(s)
        else:
            ext = crucix_signal_to_external(s)
        if ext:
            externals.append(ext)
    return externals
