#!/usr/bin/env python3
"""Cinema Studio render pipeline. Called by FastAPI as a subprocess."""
import datetime
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import requests

# ── Paths ─────────────────────────────────────────────────────────────────────
CINEMA_DIR      = Path(__file__).parent
ASSETS_DIR      = CINEMA_DIR / "assets"
RENDERS_DIR     = CINEMA_DIR / "renders"
REMOTION_DIR    = CINEMA_DIR / "remotion"
REMOTION_PUBLIC = REMOTION_DIR / "public"
JOBS_FILE       = CINEMA_DIR / "jobs.json"

OLLAMA_URL  = "http://127.0.0.1:11434/api/generate"
LLM_MODEL   = "qwen3:30b"

_EXT_TYPE = {
    ".mp3": "audio", ".wav": "audio", ".m4a": "audio", ".ogg": "audio",
    ".mp4": "video", ".mov": "video", ".webm": "video",
    ".jpg": "image", ".jpeg": "image", ".png": "image",
    ".gif": "image", ".webp": "image",
    ".txt": "text", ".md": "text",
}

_SYSTEM_PROMPT = """You are a Remotion video composition engine for 9:16 vertical social media videos (1080x1920, 30fps).

Given a user prompt and an asset manifest, output a JSON scene plan.

Available templates and their required fields:
- TextReveal:     {"text": str, "accent_color": str, "bg_asset": str|null, "duration_frames": int}
- ImageSlideshow: {"images": [str], "captions": [str]|null, "duration_frames": int}
- NarrationReel:  {"audio": str, "clips": [str], "captions": [str], "duration_frames": int}
- TitleCard:      {"title": str, "subtitle": str|null, "cta": str|null, "bg_color": str, "duration_frames": int}
- custom:         write full Remotion TSX with registerRoot (only if none of the above fit)

Rules:
- duration_frames = seconds × 30. Target 15-60s (450-1800 frames).
- Reference assets only by their exact relative_path from the manifest.
- For custom mode, include "jsx_code" with complete TSX including all imports and registerRoot().
- Output ONLY valid JSON. No markdown fences. No explanation.

Output format:
{"template": "TemplateName", "scenes": {...}, "duration_frames": 450}
OR for custom:
{"template": "custom", "jsx_code": "...", "duration_frames": 450}
"""


def _load_jobs() -> dict:
    if not JOBS_FILE.exists():
        return {}
    try:
        return json.loads(JOBS_FILE.read_text())
    except Exception:
        return {}


def _update_status(job_id: str, **kwargs) -> None:
    jobs = _load_jobs()
    if job_id not in jobs:
        jobs[job_id] = {}
    jobs[job_id].update(kwargs)
    JOBS_FILE.write_text(json.dumps(jobs, indent=2))


def _build_manifest(job_id: str) -> list:
    """Copy assets to remotion/public/{job_id}/ and return manifest list."""
    src = ASSETS_DIR / job_id
    dst = REMOTION_PUBLIC / job_id
    dst.mkdir(parents=True, exist_ok=True)

    manifest = []
    for f in src.iterdir():
        if not f.is_file():
            continue
        shutil.copy2(f, dst / f.name)
        file_type = _EXT_TYPE.get(f.suffix.lower(), "other")
        manifest.append({
            "filename": f.name,
            "type": file_type,
            "relative_path": f"{job_id}/{f.name}",
        })
    return manifest


def _llm_compose(prompt: str, manifest: list) -> dict:
    """Ask Ollama to generate a scene plan. Returns parsed dict."""
    user_msg = f"Prompt: {prompt}\n\nAssets:\n{json.dumps(manifest, indent=2)}"
    resp = requests.post(
        OLLAMA_URL,
        json={
            "model": LLM_MODEL,
            "prompt": user_msg,
            "system": _SYSTEM_PROMPT,
            "stream": False,
            "options": {"temperature": 0.7},
        },
        timeout=120,
    )
    resp.raise_for_status()
    raw = resp.json()["response"].strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())
