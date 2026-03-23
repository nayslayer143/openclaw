"""Tests for runner.py — single Ollama /api/chat call."""
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def _mock_streaming_response(content: str):
    """Build a mock requests streaming response that yields one chunk then done."""
    chunk1 = json.dumps({"message": {"content": content}, "done": False}).encode()
    chunk2 = json.dumps({"message": {"content": ""}, "done": True}).encode()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.iter_lines.return_value = [chunk1, chunk2]
    return mock_resp


def test_run_returns_content():
    from clawteam.runner import run_agent
    mock_resp = _mock_streaming_response("The answer is 42.")
    with patch("clawteam.runner.requests.post", return_value=mock_resp):
        result = run_agent("SCOUT", "qwen3:30b", "What is the answer?")
    assert result == "The answer is 42."


def test_run_uses_correct_model():
    from clawteam.runner import run_agent
    mock_resp = _mock_streaming_response("ok")
    with patch("clawteam.runner.requests.post", return_value=mock_resp) as mock_post:
        run_agent("FORGE", "qwen3-coder-next", "write code")
    call_kwargs = mock_post.call_args
    payload = call_kwargs[1]["json"] if call_kwargs[1] else call_kwargs[0][1]
    assert payload["model"] == "qwen3-coder-next"


def test_run_timeout_is_300():
    from clawteam.runner import run_agent
    mock_resp = _mock_streaming_response("ok")
    with patch("clawteam.runner.requests.post", return_value=mock_resp) as mock_post:
        run_agent("AXIS", "qwen3:32b", "do something")
    assert mock_post.call_args.kwargs["timeout"] == 300


def test_run_returns_error_string_on_connection_error():
    from clawteam.runner import run_agent
    import requests as req
    with patch("clawteam.runner.requests.post", side_effect=req.exceptions.ConnectionError):
        result = run_agent("SCOUT", "qwen3:30b", "do research")
    assert "ollama" in result.lower() or "error" in result.lower()


def test_run_returns_error_string_on_timeout():
    from clawteam.runner import run_agent
    import requests as req
    with patch("clawteam.runner.requests.post", side_effect=req.exceptions.Timeout):
        result = run_agent("SCOUT", "qwen3:30b", "do research")
    assert "timeout" in result.lower() or "error" in result.lower()


def test_run_includes_system_prompt():
    from clawteam.runner import run_agent
    mock_resp = _mock_streaming_response("done")
    with patch("clawteam.runner.requests.post", return_value=mock_resp) as mock_post:
        run_agent("AXIS", "qwen3:32b", "synthesize this")
    payload = mock_post.call_args[1]["json"]
    messages = payload["messages"]
    assert messages[0]["role"] == "system"
    assert messages[-1]["role"] == "user"
    assert "synthesize this" in messages[-1]["content"]


def test_forge_prepends_chub_context():
    """FORGE codename: chub context is prepended with double-newline separator."""
    from clawteam.runner import run_agent
    chub_ctx = "[API DOCS: requests]\nSample docs."
    prompt = "write a GET request"
    mock_resp = _mock_streaming_response("done")
    # Patch the name as bound in runner's namespace (from clawteam.chub import fetch_chub_context)
    with patch("clawteam.runner.requests.post", return_value=mock_resp) as mock_post, \
         patch("clawteam.runner.fetch_chub_context", return_value=chub_ctx):
        run_agent("FORGE", "qwen3-coder-next", prompt)
    payload = mock_post.call_args[1]["json"]
    user_content = payload["messages"][-1]["content"]
    assert user_content == f"{chub_ctx}\n\n{prompt}"


def test_non_forge_skips_chub():
    """Non-FORGE codenames never call fetch_chub_context."""
    from clawteam.runner import run_agent
    mock_resp = _mock_streaming_response("done")
    # Patch the name as bound in runner's namespace
    with patch("clawteam.runner.requests.post", return_value=mock_resp), \
         patch("clawteam.runner.fetch_chub_context") as mock_fetch:
        run_agent("SCOUT", "qwen3:30b", "do research")
    assert mock_fetch.call_count == 0
