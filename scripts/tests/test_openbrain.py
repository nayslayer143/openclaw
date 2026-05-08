"""Tests for scripts/openbrain.py.

Two layers:
  * Unit tests (always run) — patch httpx + psycopg.
  * Smoke tests (auto-skipped if stack down) — real capture/search/stats.
"""
from __future__ import annotations
import json
import socket
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from scripts.openbrain import OpenBrain, OpenBrainError


# ----------------------------------------------------------------------
# Unit tests
# ----------------------------------------------------------------------

@pytest.fixture
def ob(monkeypatch):
    monkeypatch.setenv("OPENBRAIN_ACCESS_KEY", "testkey")
    monkeypatch.setenv("OPENBRAIN_DB_PASSWORD", "x")
    instance = OpenBrain.__new__(OpenBrain)
    instance.mcp_url = "http://127.0.0.1:8765"
    instance.access_key = "testkey"
    instance.embedding_api_base = "http://127.0.0.1:11434/v1"
    instance.embedding_model = "nomic-embed-text"
    instance.embedding_api_key = "ollama"
    instance.db_dsn = "irrelevant — patched"
    instance._client = MagicMock()
    instance._db = None
    yield instance


def _sse_response(envelope: dict) -> MagicMock:
    body = f"event: message\ndata: {json.dumps(envelope)}\n"
    m = MagicMock()
    m.text = body
    m.raise_for_status = MagicMock()
    return m


def test_mcp_call_parses_sse_envelope(ob):
    ob._client.post.return_value = _sse_response({
        "jsonrpc": "2.0", "id": 1,
        "result": {"content": [{"type": "text", "text": "Captured as observation -- a, b"}]},
    })
    out = ob._mcp_call("capture_thought", {"content": "hi"})
    assert out == "Captured as observation -- a, b"
    sent = json.loads(ob._client.post.call_args.kwargs["content"])
    assert sent["params"]["name"] == "capture_thought"
    assert sent["params"]["arguments"] == {"content": "hi"}
    assert ob._client.post.call_args.kwargs["headers"]["x-brain-key"] == "testkey"


def test_mcp_call_raises_on_error_envelope(ob):
    ob._client.post.return_value = _sse_response({
        "jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": "boom"},
    })
    with pytest.raises(OpenBrainError):
        ob._mcp_call("capture_thought", {"content": "hi"})


def test_capture_prepends_source_and_scope_tags(ob):
    ob._client.post.return_value = _sse_response({
        "jsonrpc": "2.0", "id": 1,
        "result": {"content": [{"type": "text", "text": "ok"}]},
    })
    fake_cur = MagicMock()
    fake_cur.fetchone.return_value = {"id": 42}
    fake_cur.__enter__ = MagicMock(return_value=fake_cur)
    fake_cur.__exit__ = MagicMock(return_value=False)
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur
    fake_conn.closed = False
    ob._db = fake_conn

    tid = ob.capture("hello world", source="idle-protocol", scope="workspace")
    assert tid == 42
    sent_content = json.loads(ob._client.post.call_args.kwargs["content"])["params"]["arguments"]["content"]
    assert sent_content.startswith("[source: idle-protocol | scope: workspace]\n")
    assert sent_content.endswith("hello world")


def test_capture_without_tags_passes_content_unchanged(ob):
    ob._client.post.return_value = _sse_response({
        "jsonrpc": "2.0", "id": 1,
        "result": {"content": [{"type": "text", "text": "ok"}]},
    })
    fake_cur = MagicMock()
    fake_cur.fetchone.return_value = {"id": 7}
    fake_cur.__enter__ = MagicMock(return_value=fake_cur)
    fake_cur.__exit__ = MagicMock(return_value=False)
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur
    fake_conn.closed = False
    ob._db = fake_conn

    ob.capture("plain content")
    sent_content = json.loads(ob._client.post.call_args.kwargs["content"])["params"]["arguments"]["content"]
    assert sent_content == "plain content"


def test_recall_writeback_usage_report_raise_not_implemented(ob):
    with pytest.raises(NotImplementedError, match="agent-memory-api"):
        ob.recall(task="x", scope="y")
    with pytest.raises(NotImplementedError, match="agent-memory-api"):
        ob.writeback(content="x", kind="lesson", provenance={})
    with pytest.raises(NotImplementedError, match="agent-memory-api"):
        ob.usage_report(recall_id="r", used_memory_ids=[], outcome="x")


def test_embed_uses_openai_compat_shape(ob):
    fake_resp = MagicMock()
    fake_resp.raise_for_status = MagicMock()
    fake_resp.json.return_value = {"data": [{"embedding": [0.1, 0.2, 0.3]}], "model": "nomic-embed-text"}
    ob._client.post.return_value = fake_resp
    out = ob._embed("hello")
    assert out == [0.1, 0.2, 0.3]
    args, kwargs = ob._client.post.call_args
    assert args[0] == "http://127.0.0.1:11434/v1/embeddings"
    sent = json.loads(kwargs["content"])
    assert sent == {"model": "nomic-embed-text", "input": "hello"}
    assert kwargs["headers"]["Authorization"] == "Bearer ollama"


# ----------------------------------------------------------------------
# Smoke tests — require live stack
# ----------------------------------------------------------------------

def _stack_up() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 8765), timeout=0.5):
            pass
        with socket.create_connection(("127.0.0.1", 5433), timeout=0.5):
            pass
        return True
    except OSError:
        return False


pytestmark_smoke = pytest.mark.skipif(not _stack_up(), reason="openbrain stack not running")


@pytestmark_smoke
def test_smoke_capture_search_roundtrip():
    marker = f"smoke-{int(time.time())}"
    with OpenBrain() as ob:
        tid = ob.capture(
            f"openclaw smoke test marker={marker} — verifying end-to-end pipeline",
            source="pytest-smoke",
        )
        assert isinstance(tid, int) and tid > 0
        # Loose check: search by the marker should retrieve this thought.
        results = ob.search(f"smoke test {marker}", k=5)
        ids = [t.id for t in results]
        assert tid in ids, f"expected {tid} in {ids}"


@pytestmark_smoke
def test_smoke_stats_reflects_capture():
    with OpenBrain() as ob:
        s = ob.stats()
    assert isinstance(s, dict)
    assert s.get("count", 0) >= 1


@pytestmark_smoke
def test_smoke_list_recent_filters_by_source():
    with OpenBrain() as ob:
        ob.capture("smoke source filter check", source="filter-test")
        recent = ob.list_recent(n=5, source="filter-test")
    assert recent, "expected at least one result for source=filter-test"
    assert all(t.content.startswith("[source: filter-test") for t in recent)


@pytestmark_smoke
def test_smoke_fetch_by_id():
    with OpenBrain() as ob:
        tid = ob.capture("fetch-by-id check", source="fetch-test")
        got = ob.fetch(tid)
    assert got is not None
    assert got.id == tid
