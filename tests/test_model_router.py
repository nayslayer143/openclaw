import sys, os, sqlite3, tempfile
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

def test_init_db_creates_tables():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        tmp = f.name
    try:
        with patch.object(router, 'DB_PATH', Path(tmp)):
            router._init_db()
        conn = sqlite3.connect(tmp)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert "routing_log" in tables
        assert "model_stats" in tables
    finally:
        os.unlink(tmp)


def _mock_ps(loaded: list[str], vram_gb: float = 0.0):
    """Helper: patch _get_ps to return given loaded models at given VRAM usage."""
    size_vram = int(vram_gb * 1e9 / max(len(loaded), 1)) if loaded else 0
    return {
        "models": [
            {"name": n, "size": size_vram, "size_vram": size_vram}
            for n in loaded
        ]
    }

def test_select_prefers_loaded_model():
    with patch('model_router._get_ps', return_value=_mock_ps(["devstral-small-2"], 15.0)):
        model = router._select_from_chain(
            ["qwen3-coder-next", "devstral-small-2", "deepseek-coder:6.7b"],
            vram_used_gb=15.0
        )
    assert model == "devstral-small-2"

def test_select_falls_back_to_fits_in_vram():
    # Nothing loaded, but 10GB free — deepseek-coder:6.7b (3.8GB) fits
    with patch('model_router._get_ps', return_value=_mock_ps([], 80.0)):
        model = router._select_from_chain(
            ["qwen3-coder-next", "devstral-small-2", "deepseek-coder:6.7b"],
            vram_used_gb=80.0
        )
    assert model == "deepseek-coder:6.7b"

def test_select_unconditional_last_when_nothing_fits():
    # 89.5 GB used, nothing loaded, nothing fits
    with patch('model_router._get_ps', return_value=_mock_ps([], 89.5)):
        model = router._select_from_chain(
            ["qwen3-coder-next", "devstral-small-2", "deepseek-coder:6.7b"],
            vram_used_gb=89.5
        )
    assert model == "deepseek-coder:6.7b"  # last in chain

def test_select_single_model_chain():
    with patch('model_router._get_ps', return_value=_mock_ps([], 50.0)):
        model = router._select_from_chain(["qwen3-vl:32b"], vram_used_gb=50.0)
    assert model == "qwen3-vl:32b"

def test_route_with_task_type_bypasses_classification():
    with patch('model_router._get_ps', return_value=_mock_ps(["qwen2.5:7b"], 4.7)):
        with patch('model_router._log_routing'):
            model = router.route("hello", task_type="chat")
    assert model == "qwen2.5:7b"

def test_route_intent_maps_to_task_type():
    with patch('model_router._get_ps', return_value=_mock_ps(["qwen3-coder-next"], 51.0)):
        with patch('model_router._log_routing'):
            model = router.route("build a login form", intent="BUILD_TASK")
    assert model == "qwen3-coder-next"

def test_route_has_image_forces_vision():
    with patch('model_router._get_ps', return_value=_mock_ps(["qwen3-vl:32b"], 20.0)):
        with patch('model_router._log_routing'):
            model = router.route("what's in this image?", has_image=True)
    assert model == "qwen3-vl:32b"

def test_route_env_override_bypasses_all_logic():
    with patch.dict(os.environ, {"OLLAMA_CHAT_MODEL": "my-custom-model"}):
        model = router.route("hello", task_type="chat")
    assert model == "my-custom-model"

def test_route_vision_env_override():
    with patch.dict(os.environ, {"OLLAMA_VISION_MODEL": "my-vision-model"}):
        model = router.route("what's in this?", has_image=True)
    assert model == "my-vision-model"

def test_route_unknown_intent_defaults_to_chat():
    with patch('model_router._get_ps', return_value=_mock_ps(["qwen2.5:7b"], 4.7)):
        with patch('model_router._log_routing'):
            model = router.route("yo", intent="UNKNOWN_THING")
    assert model == "qwen2.5:7b"
