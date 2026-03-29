"""Tests for cinema-lab/pipeline.py — manifest, LLM compose, status helpers."""
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Load pipeline module from hyphenated directory
_spec = importlib.util.spec_from_file_location(
    "pipeline",
    Path(__file__).parent.parent / "pipeline.py",
)
_pipeline = importlib.util.module_from_spec(_spec)


def _load():
    _spec.loader.exec_module(_pipeline)
    return _pipeline


@pytest.fixture(autouse=True)
def pipeline(tmp_path, monkeypatch):
    p = _load()
    monkeypatch.setattr(p, "CINEMA_DIR", tmp_path)
    monkeypatch.setattr(p, "ASSETS_DIR", tmp_path / "assets")
    monkeypatch.setattr(p, "RENDERS_DIR", tmp_path / "renders")
    monkeypatch.setattr(p, "REMOTION_DIR", tmp_path / "remotion")
    monkeypatch.setattr(p, "REMOTION_PUBLIC", tmp_path / "remotion" / "public")
    monkeypatch.setattr(p, "JOBS_FILE", tmp_path / "jobs.json")
    return p


@pytest.fixture
def job_assets(tmp_path):
    job_dir = tmp_path / "assets" / "job001"
    job_dir.mkdir(parents=True)
    (job_dir / "hero.jpg").write_bytes(b"fake")
    (job_dir / "narration.mp3").write_bytes(b"fake")
    (job_dir / "script.txt").write_text("hello world")
    (tmp_path / "remotion" / "public").mkdir(parents=True, exist_ok=True)
    (tmp_path / "renders").mkdir(exist_ok=True)
    return tmp_path


def test_build_manifest_classifies_files(pipeline, job_assets):
    manifest = pipeline._build_manifest("job001")
    types = {m["filename"]: m["type"] for m in manifest}
    assert types["hero.jpg"] == "image"
    assert types["narration.mp3"] == "audio"
    assert types["script.txt"] == "text"


def test_build_manifest_copies_to_public(pipeline, job_assets):
    pipeline._build_manifest("job001")
    public = job_assets / "remotion" / "public" / "job001"
    assert (public / "hero.jpg").exists()
    assert (public / "narration.mp3").exists()


def test_build_manifest_relative_paths(pipeline, job_assets):
    manifest = pipeline._build_manifest("job001")
    for m in manifest:
        assert m["relative_path"] == f"job001/{m['filename']}"


def test_llm_compose_parses_json(pipeline):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "response": '{"template":"TextReveal","scenes":{"text":"hi","accent_color":"#e86800"},"duration_frames":150}'
    }
    mock_resp.raise_for_status = MagicMock()
    with patch.object(pipeline.requests, "post", return_value=mock_resp):
        result = pipeline._llm_compose("make a video", [])
    assert result["template"] == "TextReveal"
    assert result["duration_frames"] == 150


def test_llm_compose_strips_markdown_fences(pipeline):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "response": "```json\n{\"template\":\"TitleCard\",\"scenes\":{\"title\":\"Hi\",\"bg_color\":\"#060606\"},\"duration_frames\":90}\n```"
    }
    mock_resp.raise_for_status = MagicMock()
    with patch.object(pipeline.requests, "post", return_value=mock_resp):
        result = pipeline._llm_compose("title card", [])
    assert result["template"] == "TitleCard"


def test_update_status_creates_entry(pipeline, tmp_path):
    pipeline._update_status("job001", status="queued", prompt="test")
    data = json.loads((tmp_path / "jobs.json").read_text())
    assert data["job001"]["status"] == "queued"
    assert data["job001"]["prompt"] == "test"


def test_update_status_merges(pipeline, tmp_path):
    (tmp_path / "jobs.json").write_text('{"job001":{"status":"queued"}}')
    pipeline._update_status("job001", status="rendering", template="TextReveal")
    data = json.loads((tmp_path / "jobs.json").read_text())
    assert data["job001"]["status"] == "rendering"
    assert data["job001"]["template"] == "TextReveal"


# ── Render tests ──────────────────────────────────────────────────────────────

def test_render_template_calls_npx_remotion(pipeline, tmp_path):
    (tmp_path / "remotion" / "src" / "custom").mkdir(parents=True, exist_ok=True)
    (tmp_path / "renders").mkdir(exist_ok=True)

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        output = pipeline._render_template(
            "job001", "TextReveal",
            {"text": "hello", "accent_color": "#e86800"}, 150
        )

    assert "job001.mp4" in output
    cmd = mock_run.call_args[0][0]
    assert "npx" in cmd
    assert "remotion" in cmd
    assert "TextReveal" in cmd


def test_render_custom_falls_back_on_invalid_jsx(pipeline, tmp_path):
    (tmp_path / "remotion" / "src" / "custom").mkdir(parents=True, exist_ok=True)
    (tmp_path / "renders").mkdir(exist_ok=True)

    check_fail = MagicMock()
    check_fail.returncode = 1
    check_fail.stderr = "SyntaxError"

    fallback_output = str(tmp_path / "renders" / "job001.mp4")

    with patch("subprocess.run", return_value=check_fail):
        with patch.object(pipeline, "_render_template", return_value=fallback_output) as mock_tmpl:
            out = pipeline._render_custom("job001", "bad jsx !!!", 150)

    mock_tmpl.assert_called_once_with(
        "job001", "TextReveal",
        {"text": "Custom render failed", "accent_color": "#e86800"}, 150
    )
    assert out == fallback_output


def test_run_pipeline_updates_status_on_failure(pipeline, tmp_path):
    (tmp_path / "assets" / "job001").mkdir(parents=True)
    (tmp_path / "remotion" / "public").mkdir(parents=True)
    (tmp_path / "renders").mkdir()

    with patch.object(pipeline, "_llm_compose", side_effect=RuntimeError("Ollama down")):
        pipeline.run_pipeline("job001", "make a video")

    data = json.loads((tmp_path / "jobs.json").read_text())
    assert data["job001"]["status"] == "failed"
    assert "Ollama down" in data["job001"]["error"]
