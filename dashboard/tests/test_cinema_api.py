"""Tests for /api/cinema/* endpoints."""
import io
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("DASHBOARD_PASSWORD", "testpass")

from server import app, get_current_user
from fastapi.testclient import TestClient

app.dependency_overrides[get_current_user] = lambda: "testuser"
client = TestClient(app)


@pytest.fixture(autouse=True)
def patch_cinema_paths(tmp_path, monkeypatch):
    import server
    monkeypatch.setattr(server, "CINEMA_DIR", tmp_path)
    monkeypatch.setattr(server, "CINEMA_ASSETS", tmp_path / "assets")
    monkeypatch.setattr(server, "CINEMA_RENDERS", tmp_path / "renders")
    monkeypatch.setattr(server, "CINEMA_JOBS", tmp_path / "jobs.json")
    (tmp_path / "assets").mkdir()
    (tmp_path / "renders").mkdir()


def test_upload_creates_job_and_saves_files(tmp_path):
    resp = client.post(
        "/api/cinema/upload",
        files=[("files", ("hero.jpg", b"fake image data", "image/jpeg"))],
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "job_id" in data
    job_id = data["job_id"]
    job_dir = tmp_path / "assets" / job_id
    assert job_dir.exists()
    assert (job_dir / "hero.jpg").exists()
    assert data["files"][0]["name"] == "hero.jpg"


def test_render_queues_job(tmp_path):
    job_id = "testjob1"
    (tmp_path / "assets" / job_id).mkdir(parents=True)

    with patch("subprocess.Popen") as mock_popen:
        mock_popen.return_value = MagicMock()
        resp = client.post(
            "/api/cinema/render",
            json={"job_id": job_id, "prompt": "make something cool"},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"
    mock_popen.assert_called_once()


def test_status_returns_job(tmp_path):
    (tmp_path / "jobs.json").write_text(
        '{"job001":{"status":"rendering","template":"TextReveal"}}'
    )
    resp = client.get("/api/cinema/status/job001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "rendering"
    assert data["template"] == "TextReveal"


def test_status_404_for_unknown_job():
    resp = client.get("/api/cinema/status/doesnotexist")
    assert resp.status_code == 404


def test_list_renders(tmp_path):
    (tmp_path / "renders" / "job001.mp4").write_bytes(b"fake mp4")
    (tmp_path / "jobs.json").write_text(
        '{"job001":{"status":"complete","completed_at":"2026-03-29T10:00:00"}}'
    )
    resp = client.get("/api/cinema/renders")
    assert resp.status_code == 200
    renders = resp.json()
    assert any(r["filename"] == "job001.mp4" for r in renders)


def test_serve_render(tmp_path):
    (tmp_path / "renders" / "job001.mp4").write_bytes(b"fake mp4 bytes")
    resp = client.get("/api/cinema/renders/job001.mp4")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "video/mp4"


def test_serve_render_404():
    resp = client.get("/api/cinema/renders/missing.mp4")
    assert resp.status_code == 404
