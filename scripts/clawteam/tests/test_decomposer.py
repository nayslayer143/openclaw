"""Tests for decomposer.py — qwen3:32b task→subtask decomposition."""
import json
import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def _make_decomposer_response(subtasks: list, pattern: str = "parallel") -> str:
    """Build the JSON string that the LLM returns."""
    return json.dumps({"pattern": pattern, "subtasks": subtasks})


def _patch_runner(response: str):
    return patch("clawteam.decomposer.run_agent", return_value=response)


def test_decompose_returns_subtask_list():
    from clawteam.decomposer import decompose
    llm_out = _make_decomposer_response([
        {"agent": "SCOUT", "prompt": "research X"},
        {"agent": "SCOUT", "prompt": "research Y"},
    ])
    with _patch_runner(llm_out):
        result = decompose("research X and Y")
    assert result["pattern"] == "parallel"
    assert len(result["subtasks"]) == 2
    assert result["subtasks"][0]["agent"] == "SCOUT"


def test_decompose_validates_agent_codenames():
    from clawteam.decomposer import decompose
    # UNKNOWN_AGENT should be replaced by fallback
    llm_out = _make_decomposer_response([
        {"agent": "UNKNOWN_AGENT", "prompt": "research something"},
    ])
    with _patch_runner(llm_out):
        result = decompose("research something")
    # Should fall back — SCOUT for research hint
    assert result["subtasks"][0]["agent"] in ("SCOUT", "AXIS", "FORGE", "VIGIL")


def test_decompose_falls_back_on_invalid_json():
    from clawteam.decomposer import decompose
    with _patch_runner("This is not JSON at all, sorry"):
        result = decompose("do something")
    # Should return a single fallback subtask, not crash
    assert len(result["subtasks"]) >= 1


def test_decompose_includes_model_for_each_subtask():
    from clawteam.decomposer import decompose
    llm_out = _make_decomposer_response([
        {"agent": "SCOUT", "prompt": "find competitors"},
    ])
    with _patch_runner(llm_out):
        result = decompose("find competitors")
    subtask = result["subtasks"][0]
    assert "model" in subtask
    assert subtask["model"]  # non-empty


def test_decompose_pattern_auto_selection_research():
    from clawteam.decomposer import decompose
    llm_out = _make_decomposer_response([{"agent": "SCOUT", "prompt": "research"}], "parallel")
    with _patch_runner(llm_out):
        result = decompose("research competitors in the NFC market")
    assert result["pattern"] == "parallel"


def test_decompose_uses_fallback_model_on_error():
    from clawteam.decomposer import decompose
    # Primary returns error string, fallback returns valid JSON
    llm_out = _make_decomposer_response([{"agent": "SCOUT", "prompt": "do it"}])
    call_count = {"n": 0}
    def side_effect(codename, model, prompt):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return "[ERROR] Ollama timeout"
        return llm_out
    with patch("clawteam.decomposer.run_agent", side_effect=side_effect):
        result = decompose("do something")
    assert call_count["n"] == 2  # retried with fallback
    assert len(result["subtasks"]) == 1
