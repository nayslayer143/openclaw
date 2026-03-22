import sys, os
# Prevent model_router from creating ~/.openclaw/clawmson.db at import time
os.environ.setdefault("MODEL_ROUTER_SKIP_INIT", "1")

from unittest.mock import patch, MagicMock
from pathlib import Path
import model_router as router

def test_get_loaded_models_parses_api_ps():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "models": [
            {"name": "qwen2.5:7b", "size": 5033164800, "size_vram": 4937433088},
            {"name": "qwen3:30b",  "size": 19000000000, "size_vram": 18500000000},
        ]
    }
    mock_resp.raise_for_status = MagicMock()
    with patch('model_router.requests.get', return_value=mock_resp):
        router._ps_cache = None  # bust cache
        models = router.get_loaded_models()
    assert "qwen2.5:7b" in models
    assert "qwen3:30b" in models

def test_get_loaded_models_returns_empty_on_error():
    with patch('model_router.requests.get', side_effect=Exception("down")):
        router._ps_cache = None
        models = router.get_loaded_models()
    assert models == []

def test_get_vram_used_gb_sums_size_vram_fields():
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "models": [
            {"name": "qwen2.5:7b",  "size_vram": 4937433088},
            {"name": "qwen3:30b",   "size_vram": 18500000000},
        ]
    }
    with patch('model_router.requests.get', return_value=mock_resp):
        router._ps_cache = None
        used = router._get_vram_used_gb()
    expected = (4937433088 + 18500000000) / 1e9
    assert abs(used - expected) < 0.001

def test_intent_to_task_covers_all_known_intents():
    known_intents = ["CONVERSATION", "UNCLEAR", "BUILD_TASK",
                     "REFERENCE_INGEST", "STATUS_QUERY", "DIRECT_COMMAND"]
    for intent in known_intents:
        result = router.INTENT_TO_TASK.get(intent)
        assert result is not None, f"{intent} has no entry in INTENT_TO_TASK"
        assert result in router.FALLBACK_CHAINS, \
            f"INTENT_TO_TASK[{intent}]={result!r} not in FALLBACK_CHAINS"
