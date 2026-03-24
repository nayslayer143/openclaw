#!/usr/bin/env python3
"""
Resolution compatibility validator for cross-venue market matching.

Compares two MarketEvent resolution specs to determine if they resolve
identically. Flags ambiguity sources. Used by the cross-venue matcher
to enforce the v4.2 strategy rule: if settlement wording differs
materially, it is NOT arbitrage — it is a correlated bet.

Python 3.9 compatible via __future__ annotations.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from market_event import MarketEvent, ResolutionSpec, ContractSpec


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Minimum text similarity (0-1) for resolution texts to be considered compatible
MIN_RESOLUTION_SIMILARITY = 0.60

# Maximum allowed expiry difference (ms) — 24 hours
MAX_EXPIRY_DRIFT_MS = 24 * 60 * 60 * 1000

# Words that materially change settlement meaning
MATERIAL_KEYWORDS = frozenset({
    "close", "closing", "open", "opening", "intraday", "settlement",
    "midnight", "noon", "utc", "est", "et", "pt",
    "any", "all", "first", "last", "average", "median",
    "exceed", "reach", "touch", "sustain", "remain",
    "before", "after", "by", "on", "during",
    "major exchange", "coinbase", "binance", "cme", "nyse", "nasdaq",
    "official", "preliminary", "revised", "final",
    "annualized", "quarterly", "monthly", "weekly", "daily",
})

# Phrases that indicate high ambiguity risk
AMBIGUITY_PHRASES = [
    r"at\s+the\s+discretion",
    r"sole\s+judgment",
    r"may\s+be\s+adjusted",
    r"subject\s+to\s+change",
    r"n/a|tbd|tba",
    r"void|cancel",
    r"(early|delayed)\s+resolution",
]


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class ResolutionCompatibility:
    compatible: bool
    confidence: float                     # 0-1 confidence in the compatibility verdict
    text_similarity: float                # 0-1 text overlap score
    expiry_drift_ms: int                  # absolute difference in expiry timestamps
    incompatibility_reasons: list[str] = field(default_factory=list)
    ambiguity_flags: list[str] = field(default_factory=list)
    material_keyword_mismatches: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "compatible": self.compatible,
            "confidence": self.confidence,
            "text_similarity": self.text_similarity,
            "expiry_drift_ms": self.expiry_drift_ms,
            "incompatibility_reasons": list(self.incompatibility_reasons),
            "ambiguity_flags": list(self.ambiguity_flags),
            "material_keyword_mismatches": list(self.material_keyword_mismatches),
        }


# ---------------------------------------------------------------------------
# Text processing helpers
# ---------------------------------------------------------------------------

def _normalize_text(text: str) -> str:
    """Lowercase, collapse whitespace, strip punctuation for comparison."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_tokens(text: str) -> set[str]:
    """Extract word tokens from normalized text."""
    return set(_normalize_text(text).split())


def _jaccard_similarity(a: set[str], b: set[str]) -> float:
    """Jaccard index between two token sets."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    intersection = a & b
    union = a | b
    return len(intersection) / len(union)


def _extract_material_keywords(text: str) -> set[str]:
    """Extract material settlement keywords from text."""
    tokens = _extract_tokens(text)
    return tokens & MATERIAL_KEYWORDS


def _find_ambiguity_flags(text: str) -> list[str]:
    """Find phrases that indicate ambiguous resolution criteria."""
    normalized = _normalize_text(text)
    flags = []
    for pattern in AMBIGUITY_PHRASES:
        if re.search(pattern, normalized):
            flags.append(pattern)
    return flags


def _extract_numeric_thresholds(text: str) -> list[float]:
    """Extract numeric values that look like thresholds (prices, percentages)."""
    # Match patterns like $150,000  150k  150000  4.5%  0.75
    numbers = []
    for m in re.finditer(r"\$?([\d,]+(?:\.\d+)?)\s*[kK]?\b", text):
        try:
            val = float(m.group(1).replace(",", ""))
            if "k" in text[m.start():m.end()].lower():
                val *= 1000
            numbers.append(val)
        except ValueError:
            pass
    for m in re.finditer(r"([\d.]+)\s*%", text):
        try:
            numbers.append(float(m.group(1)))
        except ValueError:
            pass
    return numbers


# ---------------------------------------------------------------------------
# Core validation
# ---------------------------------------------------------------------------

def validate_resolution_compatibility(
    left: MarketEvent,
    right: MarketEvent,
) -> ResolutionCompatibility:
    """
    Compare two MarketEvents for settlement compatibility.

    Checks:
    1. Contract type compatibility
    2. Expiry window alignment
    3. Resolution text similarity
    4. Material keyword overlap
    5. Numeric threshold consistency
    6. Ambiguity detection

    Returns a ResolutionCompatibility with a GO/NO-GO verdict.
    """
    reasons: list[str] = []
    ambiguity: list[str] = []
    keyword_mismatches: list[str] = []

    # --- 1. Contract type ---
    if left.contract.contract_type != right.contract.contract_type:
        reasons.append(
            f"contract_type mismatch: {left.contract.contract_type} vs {right.contract.contract_type}"
        )

    # --- 2. Expiry alignment ---
    expiry_drift_ms = 0
    if left.contract.expiry_ts_ms and right.contract.expiry_ts_ms:
        expiry_drift_ms = abs(left.contract.expiry_ts_ms - right.contract.expiry_ts_ms)
        if expiry_drift_ms > MAX_EXPIRY_DRIFT_MS:
            reasons.append(
                f"expiry drift {expiry_drift_ms / 3600000:.1f}h exceeds {MAX_EXPIRY_DRIFT_MS / 3600000:.0f}h max"
            )
    elif left.contract.expiry_ts_ms or right.contract.expiry_ts_ms:
        ambiguity.append("one market missing expiry timestamp")

    # --- 3. Strike / bounds compatibility (for threshold/bracket) ---
    if left.contract.contract_type in ("threshold", "bracket"):
        if left.contract.strike != right.contract.strike:
            reasons.append(
                f"strike mismatch: {left.contract.strike} vs {right.contract.strike}"
            )
        if left.contract.lower_bound != right.contract.lower_bound:
            reasons.append(
                f"lower_bound mismatch: {left.contract.lower_bound} vs {right.contract.lower_bound}"
            )
        if left.contract.upper_bound != right.contract.upper_bound:
            reasons.append(
                f"upper_bound mismatch: {left.contract.upper_bound} vs {right.contract.upper_bound}"
            )

    # --- 4. Resolution text similarity ---
    left_text = left.resolution.resolution_text or left.question
    right_text = right.resolution.resolution_text or right.question

    left_tokens = _extract_tokens(left_text)
    right_tokens = _extract_tokens(right_text)

    text_similarity = _jaccard_similarity(left_tokens, right_tokens)
    if text_similarity < MIN_RESOLUTION_SIMILARITY:
        reasons.append(
            f"resolution text similarity {text_similarity:.2f} below {MIN_RESOLUTION_SIMILARITY} threshold"
        )

    # --- 5. Material keyword analysis ---
    left_material = _extract_material_keywords(left_text)
    right_material = _extract_material_keywords(right_text)

    # Keywords present in one but not the other
    left_only = left_material - right_material
    right_only = right_material - left_material

    if left_only or right_only:
        for kw in left_only:
            keyword_mismatches.append(f"{left.venue} has '{kw}', {right.venue} does not")
        for kw in right_only:
            keyword_mismatches.append(f"{right.venue} has '{kw}', {left.venue} does not")

        # Material keyword mismatch is a soft flag, not an auto-reject
        if len(left_only | right_only) >= 3:
            reasons.append(
                f"{len(left_only | right_only)} material keyword mismatches"
            )

    # --- 6. Numeric threshold consistency ---
    left_nums = set(_extract_numeric_thresholds(left_text))
    right_nums = set(_extract_numeric_thresholds(right_text))

    if left_nums and right_nums:
        if not left_nums & right_nums:
            reasons.append(
                f"no shared numeric thresholds: {sorted(left_nums)} vs {sorted(right_nums)}"
            )

    # --- 7. Ambiguity detection ---
    for text, venue in [(left_text, left.venue), (right_text, right.venue)]:
        for flag in _find_ambiguity_flags(text):
            ambiguity.append(f"{venue}: matched ambiguity pattern '{flag}'")

    # Merge ambiguity from both resolution specs
    for flag in left.resolution.ambiguity_flags:
        ambiguity.append(f"{left.venue}: {flag}")
    for flag in right.resolution.ambiguity_flags:
        ambiguity.append(f"{right.venue}: {flag}")

    # --- 8. Resolves-yes-if / resolves-no-if cross-check ---
    if left.resolution.resolves_yes_if and right.resolution.resolves_yes_if:
        yes_sim = _jaccard_similarity(
            _extract_tokens(left.resolution.resolves_yes_if),
            _extract_tokens(right.resolution.resolves_yes_if),
        )
        if yes_sim < 0.4:
            reasons.append(
                f"resolves_yes_if divergence: similarity {yes_sim:.2f}"
            )

    # --- Verdict ---
    compatible = len(reasons) == 0

    # Confidence scoring
    confidence = text_similarity
    if reasons:
        confidence *= max(0.1, 1.0 - 0.2 * len(reasons))
    if ambiguity:
        confidence *= max(0.5, 1.0 - 0.1 * len(ambiguity))
    confidence = max(0.0, min(1.0, confidence))

    return ResolutionCompatibility(
        compatible=compatible,
        confidence=confidence,
        text_similarity=text_similarity,
        expiry_drift_ms=expiry_drift_ms,
        incompatibility_reasons=reasons,
        ambiguity_flags=ambiguity,
        material_keyword_mismatches=keyword_mismatches,
    )


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from market_event import (
        MarketEvent, ContractSpec, ResolutionSpec, OutcomeBook,
        VenueFees, _ms_now,
    )

    print("=" * 70)
    print("Resolution Validator self-test")
    print("=" * 70)

    now = _ms_now()
    expiry = now + 30 * 24 * 3600 * 1000  # 30 days

    fees = VenueFees(taker_bps=2.0, maker_bps=0.0)

    def _make_event(
        venue: str,
        question: str,
        resolution_text: str,
        expiry_ts_ms: int = expiry,
        contract_type: str = "binary",
        strike: Optional[float] = None,
    ) -> MarketEvent:
        return MarketEvent(
            market_id=f"{venue}-test-001",
            venue=venue,
            title=question,
            question=question,
            category="crypto",
            contract=ContractSpec(
                contract_type=contract_type,
                underlying="BTC",
                strike=strike,
                expiry_ts_ms=expiry_ts_ms,
            ),
            resolution=ResolutionSpec(
                resolution_text=resolution_text,
            ),
            outcomes=[
                OutcomeBook(outcome="YES", bid=0.42, ask=0.44, last=0.43, bid_size=1000, ask_size=800),
                OutcomeBook(outcome="NO", bid=0.56, ask=0.58, last=0.57, bid_size=900, ask_size=700),
            ],
            volume_24h=500000.0,
            open_interest=100000.0,
            fees=fees,
            ts_ms=now,
            observed_at_ms=now,
            status="open",
        )

    # ---- Test 1: Compatible markets ----
    left = _make_event(
        "polymarket",
        "Will Bitcoin exceed $150k by July 2026?",
        "This market resolves YES if Bitcoin price exceeds $150,000 USD on any major exchange before July 1, 2026 00:00 UTC.",
    )
    right = _make_event(
        "kalshi",
        "Bitcoin to exceed $150,000 by July 2026",
        "Resolves YES if Bitcoin exceeds $150,000 on a major exchange before July 1 2026 midnight UTC.",
    )

    result = validate_resolution_compatibility(left, right)
    print(f"\n[1] Compatible markets (same underlying, similar text):")
    print(f"    compatible: {result.compatible}")
    print(f"    confidence: {result.confidence:.3f}")
    print(f"    text_sim:   {result.text_similarity:.3f}")
    print(f"    reasons:    {result.incompatibility_reasons}")
    print(f"    ambiguity:  {result.ambiguity_flags}")
    assert result.compatible, "Should be compatible"
    assert result.confidence > 0.5, "Should have decent confidence"
    print("    PASS")

    # ---- Test 2: Incompatible - different thresholds ----
    right2 = _make_event(
        "kalshi",
        "Bitcoin to exceed $200,000 by July 2026",
        "Resolves YES if Bitcoin exceeds $200,000 on a major exchange before July 1 2026.",
    )

    result2 = validate_resolution_compatibility(left, right2)
    print(f"\n[2] Different thresholds ($150k vs $200k):")
    print(f"    compatible: {result2.compatible}")
    print(f"    confidence: {result2.confidence:.3f}")
    print(f"    text_sim:   {result2.text_similarity:.3f}")
    print(f"    reasons:    {result2.incompatibility_reasons}")
    assert not result2.compatible, "Should be incompatible"
    print("    PASS")

    # ---- Test 3: Expiry mismatch ----
    right3 = _make_event(
        "kalshi",
        "Will Bitcoin exceed $150k by July 2026?",
        "This market resolves YES if Bitcoin price exceeds $150,000 USD on any major exchange before July 1, 2026 00:00 UTC.",
        expiry_ts_ms=expiry + 48 * 3600 * 1000,  # 48h drift
    )

    result3 = validate_resolution_compatibility(left, right3)
    print(f"\n[3] Expiry drift (48h):")
    print(f"    compatible: {result3.compatible}")
    print(f"    drift_h:    {result3.expiry_drift_ms / 3600000:.1f}")
    print(f"    reasons:    {result3.incompatibility_reasons}")
    assert not result3.compatible, "48h drift should be incompatible"
    print("    PASS")

    # ---- Test 4: Totally different markets ----
    right4 = _make_event(
        "kalshi",
        "Will the Fed cut rates in June 2026?",
        "Resolves YES if the Federal Reserve announces a rate cut at the June 2026 FOMC meeting.",
    )

    result4 = validate_resolution_compatibility(left, right4)
    print(f"\n[4] Completely different markets:")
    print(f"    compatible: {result4.compatible}")
    print(f"    text_sim:   {result4.text_similarity:.3f}")
    assert not result4.compatible, "Different markets should be incompatible"
    print("    PASS")

    # ---- Test 5: Ambiguity detection ----
    right5 = _make_event(
        "kalshi",
        "Will Bitcoin exceed $150k by July 2026?",
        "Resolves YES if Bitcoin exceeds $150,000. Resolution at the sole judgment of Kalshi. Subject to change.",
    )

    result5 = validate_resolution_compatibility(left, right5)
    print(f"\n[5] Ambiguity detection:")
    print(f"    ambiguity:  {result5.ambiguity_flags}")
    assert len(result5.ambiguity_flags) > 0, "Should detect ambiguity"
    print("    PASS")

    print("\n" + "=" * 70)
    print("All resolution validator tests passed.")
    print("=" * 70)
