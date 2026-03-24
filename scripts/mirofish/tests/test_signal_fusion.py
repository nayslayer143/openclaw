from __future__ import annotations
import time
import pytest
from scripts.mirofish.market_event import ExternalSignal
from scripts.mirofish.signal_fusion import (
    apply_decay, decay_signals, match_entity_to_market,
    canonicalize_entity, find_relevant_signals, compute_fused_score,
    fuse_all_markets, convert_raw_signals, DecayedSignal,
)


def _make_signal(
    entity_key="BTC", direction="bullish", strength=0.8,
    confidence=0.7, age_hours=0, half_life=24.0,
) -> ExternalSignal:
    now_ms = int(time.time() * 1000)
    return ExternalSignal(
        signal_id=f"test-{entity_key}-{age_hours}",
        source="unusual_whales",
        ts_ms=now_ms - int(age_hours * 3600 * 1000),
        entity_type="ticker",
        entity_key=entity_key,
        direction=direction,
        strength=strength,
        confidence=confidence,
        horizon_hours=48.0,
        half_life_hours=half_life,
    )


def test_fresh_signal_no_decay():
    sig = _make_signal(age_hours=0)
    d = apply_decay(sig)
    assert d.decay_factor == pytest.approx(1.0, abs=0.01)
    assert d.decayed_strength == pytest.approx(0.8, abs=0.01)


def test_signal_at_halflife():
    sig = _make_signal(age_hours=24, half_life=24.0)
    d = apply_decay(sig)
    assert d.decay_factor == pytest.approx(0.5, abs=0.01)
    assert d.decayed_strength == pytest.approx(0.4, abs=0.02)


def test_old_signal_heavily_decayed():
    sig = _make_signal(age_hours=72, half_life=24.0)
    d = apply_decay(sig)
    assert d.decay_factor < 0.15  # 3 half-lives


def test_decay_filters_weak():
    signals = [
        _make_signal(strength=0.8, age_hours=0),
        _make_signal(strength=0.01, age_hours=0),  # too weak after filter
    ]
    decayed = decay_signals(signals)
    assert len(decayed) >= 1


def test_entity_canonicalization():
    assert canonicalize_entity("bitcoin") == "BTC"
    assert canonicalize_entity("eth") == "ETH"
    assert canonicalize_entity("fed") == "rates"
    assert canonicalize_entity("unknown_thing") == "unknown_thing"


def test_entity_market_matching():
    assert match_entity_to_market("BTC", "Will Bitcoin exceed $150k?") is True
    assert match_entity_to_market("BTC", "Will the Fed cut rates?") is False
    assert match_entity_to_market("rates", "Will the Fed cut rates in June?") is True
    assert match_entity_to_market("defense", "Will NATO expand military spending?") is True


def test_find_relevant_signals():
    btc_sig = apply_decay(_make_signal(entity_key="BTC"))
    eth_sig = apply_decay(_make_signal(entity_key="ETH"))
    market = {"market_id": "m1", "question": "Will Bitcoin exceed $150k?"}
    relevant = find_relevant_signals(market, [btc_sig, eth_sig])
    assert len(relevant) == 1
    assert relevant[0].signal.entity_key == "BTC"


def test_fused_score_bullish():
    signals = [apply_decay(_make_signal(direction="bullish", strength=0.8))]
    market = {"market_id": "m1", "question": "Will Bitcoin go above $150k?"}
    score = compute_fused_score(market, signals)
    assert score.bullish_score > 0
    assert score.bearish_score == 0
    assert score.net_score > 0


def test_fused_score_mixed():
    signals = [
        apply_decay(_make_signal(direction="bullish", strength=0.8)),
        apply_decay(_make_signal(direction="bearish", strength=0.4)),
    ]
    market = {"market_id": "m1", "question": "Will Bitcoin go above $150k?"}
    score = compute_fused_score(market, signals)
    assert score.signal_count == 2
    assert score.bullish_score > score.bearish_score
    assert score.net_score > 0


def test_fuse_all_markets():
    signals = [_make_signal(entity_key="BTC", direction="bullish")]
    markets = [
        {"market_id": "btc-mkt", "question": "Bitcoin above $150k?"},
        {"market_id": "fed-mkt", "question": "Fed rate cut in June?"},
    ]
    scores = fuse_all_markets(markets, signals)
    # Only BTC market should have signals
    assert len(scores) == 1
    assert scores[0].market_id == "btc-mkt"


def test_convert_raw_signals():
    raw = [
        {"source": "unusual_whales", "ticker": "BTC", "direction": "bullish",
         "signal_type": "flow", "fetched_at": "2026-03-20T12:00:00"},
        {"source": "crucix_delta", "ticker": "oil", "direction": "bearish",
         "signal_type": "osint", "fetched_at": "2026-03-20T12:00:00"},
    ]
    externals = convert_raw_signals(raw)
    assert len(externals) == 2
    assert externals[0].source == "unusual_whales"
    assert externals[1].source == "crucix"


def test_fused_score_to_dict():
    signals = [apply_decay(_make_signal())]
    market = {"market_id": "m1", "question": "Bitcoin above $150k?"}
    score = compute_fused_score(market, signals)
    d = score.to_dict()
    assert "net_score" in d
    assert "signal_count" in d
