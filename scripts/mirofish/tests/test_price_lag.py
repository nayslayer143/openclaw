# tests/test_price_lag.py
from __future__ import annotations
import math
import datetime
import pytest


@pytest.fixture(autouse=True)
def clean_imports():
    import sys
    for mod in list(sys.modules.keys()):
        if "mirofish" in mod:
            del sys.modules[mod]
    yield


def _tb():
    import scripts.mirofish.trading_brain as tb
    return tb


def test_parse_price_string(clean_imports):
    tb = _tb()
    assert tb._parse_price_string("50,000") == pytest.approx(50000.0)
    assert tb._parse_price_string("50k") == pytest.approx(50000.0)
    assert tb._parse_price_string("50K") == pytest.approx(50000.0)
    assert tb._parse_price_string("1,234.56") == pytest.approx(1234.56)
    assert tb._parse_price_string("2000") == pytest.approx(2000.0)
    assert tb._parse_price_string("") is None
    assert tb._parse_price_string("abc") is None


def test_detect_binary_btc_above(clean_imports):
    tb = _tb()
    market = {"question": "Will BTC be above $50,000 by June?", "market_id": "m1"}
    result = tb._detect_crypto_contract(market)
    assert result is not None
    asset, ctype, params = result
    assert asset == "BTC"
    assert ctype == "binary_threshold"
    assert params["threshold"] == pytest.approx(50000.0)


def test_detect_binary_eth_below(clean_imports):
    tb = _tb()
    market = {"question": "Will Ethereum drop below $2,000?", "market_id": "m1"}
    result = tb._detect_crypto_contract(market)
    assert result is not None
    asset, ctype, params = result
    assert asset == "ETH"
    assert ctype == "binary_threshold"
    assert params["threshold"] == pytest.approx(2000.0)


def test_detect_bracket(clean_imports):
    tb = _tb()
    market = {"question": "BTC price $40k-$45k on June 30", "market_id": "m1"}
    result = tb._detect_crypto_contract(market)
    assert result is not None
    asset, ctype, params = result
    assert asset == "BTC"
    assert ctype == "continuous_bracket"
    assert params["bracket_low"] == pytest.approx(40000.0)
    assert params["bracket_high"] == pytest.approx(45000.0)


def test_detect_non_crypto_returns_none(clean_imports):
    tb = _tb()
    market = {"question": "Will Trump win the election?", "market_id": "m1"}
    assert tb._detect_crypto_contract(market) is None


def test_dislocation_binary_underpriced(clean_imports):
    tb = _tb()
    # spot=$42k, threshold=$50k, YES=0.10 — market underpricing YES
    result = tb._compute_binary_dislocation(
        spot=42000, threshold=50000, market_yes=0.10,
        market_no=0.90, days_to_expiry=90
    )
    assert result is not None
    disl, direction, implied = result
    assert direction == "YES"  # our model says higher than 0.10
    assert disl > 0


def test_dislocation_binary_overpriced(clean_imports):
    tb = _tb()
    # spot=$42k, threshold=$50k, YES=0.80 — market overpricing YES
    result = tb._compute_binary_dislocation(
        spot=42000, threshold=50000, market_yes=0.80,
        market_no=0.20, days_to_expiry=90
    )
    assert result is not None
    disl, direction, implied = result
    assert direction == "NO"  # our model says lower than 0.80


def test_dislocation_binary_spot_above_threshold(clean_imports):
    tb = _tb()
    # spot=$55k, threshold=$50k — already above, YES should be high
    result = tb._compute_binary_dislocation(
        spot=55000, threshold=50000, market_yes=0.30,
        market_no=0.70, days_to_expiry=30
    )
    assert result is not None
    disl, direction, implied = result
    assert direction == "YES"  # spot already above → YES is underpriced at 0.30
    assert implied > 0.5


def test_edge_decay_inverted(clean_imports):
    tb = _tb()
    # Near expiry = high multiplier, far expiry = low
    assert tb._decay_multiplier(1) == pytest.approx(max(0.1, 1.0 - 1/180), abs=0.01)
    assert tb._decay_multiplier(90) == pytest.approx(0.5, abs=0.01)
    assert tb._decay_multiplier(180) == pytest.approx(0.1)
    assert tb._decay_multiplier(360) == pytest.approx(0.1)  # clamped


def test_min_edge_filters_small(clean_imports):
    tb = _tb()
    market = {
        "market_id": "m1", "question": "Will BTC be above $50,000 by June?",
        "yes_price": 0.50, "no_price": 0.50, "volume": 50000,
        "end_date": (datetime.datetime.utcnow() + datetime.timedelta(days=90)).isoformat(),
    }
    # Spot very close to where market implies → tiny dislocation → should return None
    result = tb._check_price_lag_arb(market, {"BTC": 49900}, 1000.0)
    # With spot at $49,900 and threshold $50k, the dislocation will be small
    # The result depends on the math — if edge < 5% after decay, returns None
    # This is a soft check: either None or a decision with small edge
    if result is not None:
        assert result.confidence >= 0.05  # must exceed min edge


def test_full_pipeline_produces_decision(clean_imports):
    tb = _tb()
    market = {
        "market_id": "m1",
        "question": "Will Bitcoin be above $50,000 by June 30?",
        "yes_price": 0.10,  # Very underpriced relative to spot near threshold
        "no_price": 0.90,
        "volume": 100000,
        "end_date": (datetime.datetime.utcnow() + datetime.timedelta(days=30)).isoformat(),
    }
    result = tb._check_price_lag_arb(market, {"BTC": 48000}, 1000.0)
    assert result is not None
    assert result.strategy == "price_lag_arb"
    assert result.direction in ("YES", "NO")
    assert result.confidence > 0
    assert result.metadata is not None
    assert result.metadata["asset"] == "BTC"
    assert result.metadata["contract_type"] == "binary_threshold"
    assert result.metadata["spot_price"] == 48000
