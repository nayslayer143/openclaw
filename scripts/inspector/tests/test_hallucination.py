"""
Tests for HallucinationDetector (Task 6).
"""

import pytest
from unittest.mock import MagicMock, patch
import json
import tempfile
import os
from inspector.hallucination_detector import HallucinationDetector, GroundingResult


def test_grounded_within_5_cents():
    poly = MagicMock()
    poly.get_price_at.return_value = 0.52
    hd = HallucinationDetector(db=MagicMock(), poly=poly)
    assert hd.check_price_claim("0xABC", 0.51, "2026-03-24T10:00:00") == GroundingResult.GROUNDED


def test_partially_grounded_5_to_15_cents():
    poly = MagicMock()
    poly.get_price_at.return_value = 0.60
    hd = HallucinationDetector(db=MagicMock(), poly=poly)
    assert hd.check_price_claim("0xABC", 0.50, "2026-03-24T10:00:00") == GroundingResult.PARTIALLY_GROUNDED


def test_hallucinated_over_15_cents():
    poly = MagicMock()
    poly.get_price_at.return_value = 0.20
    hd = HallucinationDetector(db=MagicMock(), poly=poly)
    assert hd.check_price_claim("0xABC", 0.75, "2026-03-24T10:00:00") == GroundingResult.HALLUCINATED


def test_unverifiable_when_no_price_history():
    poly = MagicMock()
    poly.get_price_at.return_value = None
    hd = HallucinationDetector(db=MagicMock(), poly=poly)
    assert hd.check_price_claim("0xABC", 0.5, "2026-03-24T10:00:00") == GroundingResult.UNVERIFIABLE


def test_market_existence_hallucinated_when_missing():
    poly = MagicMock()
    poly.get_market.return_value = None
    hd = HallucinationDetector(db=MagicMock(), poly=poly)
    assert hd.check_market_existence("0xDEAD") == GroundingResult.HALLUCINATED


def test_market_existence_grounded_when_found():
    poly = MagicMock()
    poly.get_market.return_value = {"question": "Will X?"}
    hd = HallucinationDetector(db=MagicMock(), poly=poly)
    assert hd.check_market_existence("0xABC") == GroundingResult.GROUNDED


def test_run_on_signals_missing_file():
    hd = HallucinationDetector(db=MagicMock(), poly=MagicMock())
    result = hd.run_on_signals("/nonexistent/path/signals.json")
    assert result["checked"] == 0
    assert "error" in result


def test_run_on_signals_processes_entries():
    poly = MagicMock()
    poly.get_price_at.return_value = 0.51
    db = MagicMock()
    db.insert.return_value = 1
    hd = HallucinationDetector(db=db, poly=poly)

    signals = [{"id": "sig-1", "current_yes_price": 0.50, "scan_time": "2026-03-24T10:00:00",
                "market_id": "0xABC"}]
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(signals, f)
        tmp_path = f.name
    try:
        result = hd.run_on_signals(tmp_path)
        assert result["checked"] == 1
        assert db.insert.call_count == 1
    finally:
        os.unlink(tmp_path)
