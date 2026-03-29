# Cinema Studio — Part 2 of 2: Render Paths, FastAPI Endpoints, UI
# Read AFTER: 2026-03-29-cinema-studio-plan-part1.md

---

### Task 5: pipeline.py — render paths

**Files:**
- Modify: `cinema-lab/pipeline.py` (add `_render_template`, `_render_custom`, `run_pipeline`, `__main__`)
- Modify: `cinema-lab/tests/test_pipeline.py` (add render tests)

- [ ] **Step 1: Add render tests to test_pipeline.py**

Append to `cinema-lab/tests/test_pipeline.py`:

```python
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
```

- [ ] **Step 2: Run tests — confirm new ones fail**

```bash
cd ~/openclaw
python3 -m pytest cinema-lab/tests/test_pipeline.py -v 2>&1 | grep -E "PASS|FAIL|ERROR"
```
Expected: 3 new tests fail (`_render_template`, `_render_custom`, `run_pipeline` not defined yet).

- [ ] **Step 3: Add render paths to pipeline.py**

Append to `cinema-lab/pipeline.py` (after `_llm_compose`):

```python
def _render_template(job_id: str, template: str, scenes: dict, duration_frames: int) -> str:
    """Invoke npx remotion render for a named template with scene props."""
    props = dict(scenes)
    props["duration_frames"] = duration_frames

    output = RENDERS_DIR / f"{job_id}.mp4"
    RENDERS_DIR.mkdir(exist_ok=True)

    result = subprocess.run(
        [
            "npx", "remotion", "render", "src/index.ts", template,
            "--output", str(output),
            "--props", json.dumps(props),
        ],
        cwd=str(REMOTION_DIR),
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Remotion render failed:\n{result.stderr[-600:]}")
    return str(output)


def _render_custom(job_id: str, jsx_code: str, duration_frames: int) -> str:
    """Write LLM JSX, validate with node --check, fallback to TextReveal on failure."""
    custom_dir = REMOTION_DIR / "src" / "custom"
    custom_dir.mkdir(parents=True, exist_ok=True)
    comp_file = custom_dir / f"{job_id}.tsx"
    comp_file.write_text(jsx_code)

    check = subprocess.run(
        ["node", "--check", str(comp_file)],
        capture_output=True,
        text=True,
    )
    if check.returncode != 0:
        _update_status(job_id, warning="Custom JSX invalid, falling back to TextReveal")
        return _render_template(
            job_id, "TextReveal",
            {"text": "Custom render failed", "accent_color": "#e86800"},
            duration_frames,
        )

    output = RENDERS_DIR / f"{job_id}.mp4"
    result = subprocess.run(
        [
            "npx", "remotion", "render", str(comp_file), "DynamicComp",
            "--output", str(output),
        ],
        cwd=str(REMOTION_DIR),
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode != 0:
        _update_status(job_id, warning="Custom render failed, falling back to TextReveal")
        return _render_template(
            job_id, "TextReveal",
            {"text": "Custom render failed", "accent_color": "#e86800"},
            duration_frames,
        )
    return str(output)


def run_pipeline(job_id: str, prompt: str) -> None:
    """Main entry point. Orchestrates manifest → LLM → render → status."""
    try:
        _update_status(job_id, status="composing")
        manifest = _build_manifest(job_id)
        scene_plan = _llm_compose(prompt, manifest)

        template       = scene_plan.get("template", "TextReveal")
        duration_frames = int(scene_plan.get("duration_frames", 450))
        scenes         = scene_plan.get("scenes", {})

        _update_status(job_id, status="rendering", template=template)

        if template == "custom":
            output = _render_custom(job_id, scene_plan.get("jsx_code", ""), duration_frames)
        else:
            output = _render_template(job_id, template, scenes, duration_frames)

        _update_status(
            job_id,
            status="complete",
            output_path=f"renders/{job_id}.mp4",
            completed_at=datetime.datetime.utcnow().isoformat(),
        )

    except Exception as exc:
        _update_status(job_id, status="failed", error=str(exc)[:500])


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: pipeline.py <job_id> <prompt>")
        sys.exit(1)
    run_pipeline(sys.argv[1], sys.argv[2])
```

- [ ] **Step 4: Run all pipeline tests**

```bash
cd ~/openclaw
python3 -m pytest cinema-lab/tests/test_pipeline.py -v
```
Expected: 10 tests passing.

- [ ] **Step 5: Commit**

```bash
cd ~/openclaw
git add cinema-lab/pipeline.py cinema-lab/tests/test_pipeline.py
git commit -m "feat: pipeline.py render paths, run_pipeline entry point"
```

---

### Task 6: FastAPI cinema endpoints

**Files:**
- Modify: `dashboard/server.py` (add cinema helpers + 5 endpoints before line 2647)
- Create: `dashboard/tests/__init__.py`
- Create: `dashboard/tests/test_cinema_api.py`

- [ ] **Step 1: Write failing tests**

Create `dashboard/tests/__init__.py` (empty).

Write `dashboard/tests/test_cinema_api.py`:

```python
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
    # Pre-create a job directory
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
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
cd ~/openclaw
python3 -m pytest dashboard/tests/test_cinema_api.py -v 2>&1 | head -20
```
Expected: failures because cinema endpoints don't exist yet.

- [ ] **Step 3: Add cinema constants + helpers to server.py**

Insert after the existing path constants block (after line ~30, near `STRATEGY_CATALOG`):

```python
# ── Cinema Studio ─────────────────────────────────────────────────────────────
CINEMA_DIR     = OPENCLAW_ROOT / "cinema-lab"
CINEMA_ASSETS  = CINEMA_DIR / "assets"
CINEMA_RENDERS = CINEMA_DIR / "renders"
CINEMA_JOBS    = CINEMA_DIR / "jobs.json"


def _load_cinema_jobs() -> dict:
    if not CINEMA_JOBS.exists():
        return {}
    try:
        return json.loads(CINEMA_JOBS.read_text())
    except Exception:
        return {}


def _update_cinema_job(job_id: str, **kwargs) -> None:
    jobs = _load_cinema_jobs()
    if job_id not in jobs:
        jobs[job_id] = {}
    jobs[job_id].update(kwargs)
    CINEMA_JOBS.write_text(json.dumps(jobs, indent=2))
```

- [ ] **Step 4: Add 5 cinema endpoints to server.py**

Insert the following block **immediately before** `@app.get("/{path:path}")` (line 2658):

```python
# ── Cinema Studio endpoints ───────────────────────────────────────────────────

@app.post("/api/cinema/upload")
async def cinema_upload(request: Request, user: str = Depends(get_current_user)):
    """Accept multipart file upload. Creates job_id, saves to cinema-lab/assets/{job_id}/."""
    form = await request.form()
    job_id = uuid.uuid4().hex[:8]
    job_dir = CINEMA_ASSETS / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    files_info = []
    for _key, value in form.multi_items():
        if hasattr(value, "filename") and value.filename:
            content = await value.read()
            (job_dir / value.filename).write_bytes(content)
            files_info.append({"name": value.filename, "size": len(content)})

    return {"job_id": job_id, "files": files_info}


@app.post("/api/cinema/render")
async def cinema_render(request: Request, user: str = Depends(get_current_user)):
    """Queue a render job. Spawns pipeline.py as non-blocking subprocess."""
    data = await request.json()
    job_id = data["job_id"]
    prompt = data.get("prompt", "")

    _update_cinema_job(
        job_id,
        status="queued",
        prompt=prompt,
        created_at=datetime.utcnow().isoformat(),
    )

    log_path = LOGS_DIR / f"cinema-{job_id}.log"
    subprocess.Popen(
        [sys.executable, str(CINEMA_DIR / "pipeline.py"), job_id, prompt],
        stdout=open(log_path, "w"),
        stderr=subprocess.STDOUT,
    )

    return {"job_id": job_id, "status": "queued"}


@app.get("/api/cinema/status/{job_id}")
async def cinema_status(job_id: str, user: str = Depends(get_current_user)):
    """Return current status of a render job."""
    jobs = _load_cinema_jobs()
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    return jobs[job_id]


@app.get("/api/cinema/renders")
async def cinema_list_renders(user: str = Depends(get_current_user)):
    """List all completed render MP4s with metadata."""
    jobs = _load_cinema_jobs()
    renders = []
    if CINEMA_RENDERS.exists():
        for f in sorted(CINEMA_RENDERS.glob("*.mp4"), key=lambda x: x.stat().st_mtime, reverse=True):
            job_id = f.stem
            meta = jobs.get(job_id, {})
            renders.append({
                "job_id": job_id,
                "filename": f.name,
                "size_bytes": f.stat().st_size,
                "created_at": meta.get("completed_at"),
                "template": meta.get("template"),
            })
    return renders


@app.get("/api/cinema/renders/{filename}")
async def cinema_serve_render(filename: str, user: str = Depends(get_current_user)):
    """Serve an MP4 file with range request support for video playback."""
    fpath = CINEMA_RENDERS / filename
    if not fpath.exists():
        raise HTTPException(404, "Render not found")
    return FileResponse(
        fpath,
        media_type="video/mp4",
        headers={"Accept-Ranges": "bytes"},
    )
```

- [ ] **Step 5: Run tests**

```bash
cd ~/openclaw
python3 -m pytest dashboard/tests/test_cinema_api.py -v
```
Expected: 7 tests passing.

- [ ] **Step 6: Commit**

```bash
cd ~/openclaw
git add dashboard/server.py dashboard/tests/
git commit -m "feat: add 5 cinema FastAPI endpoints to gonzoclaw server"
```

---

### Task 7: UI — HTML structure + CSS

**Files:**
- Modify: `dashboard/index.html`

Add the nav tab, CSS, and HTML skeleton for `pageCinema`. JS comes in Task 8.

- [ ] **Step 1: Add nav tab**

In `dashboard/index.html`, find:
```html
<button class="nav-tab" id="tabStrategies" onclick="showPage('strategies')">◇ STRATEGIES</button>
```
Add immediately after it:
```html
<button class="nav-tab" id="tabCinema" onclick="showPage('cinema')">✦ CINEMA</button>
```

- [ ] **Step 2: Register cinema in showPage()**

In `index.html`, find the `showPage` function. It has a `validPages` array or similar. Find:
```javascript
const validPages = [...
```
or wherever page names are listed, and add `'cinema'` to the list. Also find all references like:
```javascript
document.getElementById('tabDashboard')
```
and add the cinema tab case. The pattern in the existing code maps page name → tab ID. Add:
```javascript
if (page === 'cinema') document.getElementById('tabCinema').classList.add('active');
```

- [ ] **Step 3: Add CSS**

Find the closing `</style>` tag and insert before it:

```css
/* ── Cinema Studio ────────────────────────────────────────────────── */
.cinema-header { margin-bottom: 32px; }
.cinema-title {
  font-size: 1.1rem; letter-spacing: 4px; color: var(--orange-hi);
  font-weight: 700; margin-bottom: 4px;
}
.cinema-subtitle { font-size: 0.58rem; color: var(--grey2); letter-spacing: 2px; }

.cinema-step-label {
  font-size: 0.52rem; color: var(--grey2); letter-spacing: 2.5px;
  margin-bottom: 10px; margin-top: 28px;
}

.cinema-dropzone {
  border: 1px dashed rgba(232,104,0,0.25);
  border-radius: 2px;
  padding: 36px 24px;
  text-align: center;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
  background: var(--surface);
  color: var(--grey2);
  font-size: 0.62rem;
  letter-spacing: 1.5px;
}
.cinema-dropzone:hover,
.cinema-dropzone.drag-over {
  border-color: var(--orange);
  background: rgba(232,104,0,0.06);
  color: var(--offwhite);
}

.cinema-chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; min-height: 10px; }
.cinema-chip {
  display: flex; align-items: center; gap: 6px;
  background: var(--surface2); border: 1px solid var(--grey3);
  padding: 4px 10px; border-radius: 1px;
  font-size: 0.55rem; color: var(--offwhite);
}
.cinema-chip-badge {
  background: var(--orange-dim); color: var(--orange-hi);
  padding: 1px 5px; font-size: 0.48rem; letter-spacing: 1px;
}
.cinema-chip button {
  background: none; border: none; color: var(--grey2);
  cursor: pointer; padding: 0 2px; font-size: 0.7rem; line-height: 1;
}
.cinema-chip button:hover { color: var(--neon-red); }

.cinema-prompt {
  width: 100%; background: var(--surface);
  border: 1px solid var(--grey3); color: var(--offwhite);
  font-family: inherit; font-size: 0.68rem; padding: 14px;
  resize: vertical; min-height: 100px; outline: none;
  transition: border-color 0.2s, box-shadow 0.2s;
  box-sizing: border-box;
}
.cinema-prompt:focus {
  border-color: var(--orange);
  box-shadow: 0 0 0 1px rgba(232,104,0,0.3);
}

@keyframes magic-pulse {
  0%,100% { box-shadow: 0 0 18px rgba(232,104,0,0.45), 0 0 36px rgba(232,104,0,0.18); }
  50%      { box-shadow: 0 0 28px rgba(255,124,26,0.75), 0 0 56px rgba(255,124,26,0.30), 0 0 80px rgba(232,104,0,0.12); }
}
.cinema-magic-btn {
  width: 100%; padding: 18px;
  background: var(--orange); color: #000;
  border: none; font-family: inherit; font-size: 0.85rem;
  font-weight: 700; letter-spacing: 5px; cursor: pointer;
  animation: magic-pulse 2s ease-in-out infinite;
  transition: opacity 0.2s;
}
.cinema-magic-btn:disabled {
  animation: none; opacity: 0.45; cursor: not-allowed;
}
.cinema-magic-btn:not(:disabled):hover { background: var(--orange-hi); }

.cinema-status-row {
  display: flex; align-items: center; gap: 10px;
  flex-wrap: wrap; font-size: 0.55rem; letter-spacing: 1.5px;
}
.cinema-status-step { color: var(--grey3); }
.cinema-status-step.active { color: var(--orange-hi); }
.cinema-status-step.done { color: var(--neon-green); }
.cinema-status-sep { color: var(--grey3); }
.cinema-status-tmpl { color: var(--grey2); font-size: 0.50rem; }
.cinema-status-error {
  color: var(--neon-red); font-size: 0.58rem;
  margin-top: 6px; display: none;
}

.cinema-gallery {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 12px; margin-top: 12px;
}
.cinema-video-card {
  border: 1px solid var(--grey3); background: var(--surface);
  cursor: pointer; transition: border-color 0.2s;
  overflow: hidden;
}
.cinema-video-card:hover { border-color: var(--orange); }
.cinema-video-card video {
  width: 100%; display: block; aspect-ratio: 9/16; object-fit: cover;
}
.cinema-video-label {
  padding: 6px 8px; font-size: 0.50rem;
  color: var(--grey1); letter-spacing: 1px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.cinema-video-date { padding: 0 8px 6px; font-size: 0.46rem; color: var(--grey2); }

.cinema-player-modal {
  display: none; position: fixed; inset: 0; z-index: 9000;
  background: rgba(0,0,0,0.92); justify-content: center; align-items: center;
}
.cinema-player-modal video {
  max-height: 90vh; max-width: 90vw; aspect-ratio: 9/16;
}
.cinema-player-close {
  position: absolute; top: 20px; right: 24px;
  background: none; border: none; color: var(--grey1);
  font-size: 1.4rem; cursor: pointer; letter-spacing: 1px;
}
.cinema-player-close:hover { color: var(--offwhite); }
```

- [ ] **Step 4: Add pageCinema HTML**

Find `<div class="page" id="pageStrategies">` and after its closing `</div>` add:

```html
<div class="page" id="pageCinema">
  <div style="max-width:680px;margin:0 auto;padding:24px 16px 80px;">

    <div class="cinema-header">
      <div class="cinema-title">◈ CINEMA STUDIO</div>
      <div class="cinema-subtitle">MAKE VIDEOS. TELL STORIES.</div>
    </div>

    <!-- Step 1: Assets -->
    <div class="cinema-step-label">STEP 1 — DROP YOUR ASSETS</div>
    <div class="cinema-dropzone" id="cinema-dropzone">
      drag files here · or click to browse<br>
      <span style="font-size:0.50rem;color:var(--grey3);margin-top:6px;display:block;">
        audio · video · images · text
      </span>
    </div>
    <input type="file" id="cinema-file-input" multiple style="display:none;">
    <div class="cinema-chips" id="cinema-file-chips"></div>

    <!-- Step 2: Prompt -->
    <div class="cinema-step-label">STEP 2 — DESCRIBE YOUR VISION</div>
    <textarea
      class="cinema-prompt"
      id="cinema-prompt"
      placeholder="what story do you want to tell?"
      rows="5"
    ></textarea>

    <!-- Step 3: Render -->
    <div class="cinema-step-label">STEP 3 — RENDER</div>
    <button class="cinema-magic-btn" id="cinema-magic-btn" onclick="makeMagical()">
      ✦&nbsp;&nbsp;MAKE IT MAGICAL&nbsp;&nbsp;✦
    </button>

    <!-- Step 4: Status (hidden until first job) -->
    <div id="cinema-status-section" style="display:none;">
      <div class="cinema-step-label">STEP 4 — STATUS</div>
      <div class="cinema-status-row">
        <span class="cinema-status-step" id="cinema-step-uploading">UPLOADING</span>
        <span class="cinema-status-sep">→</span>
        <span class="cinema-status-step" id="cinema-step-queued">QUEUED</span>
        <span class="cinema-status-sep">→</span>
        <span class="cinema-status-step" id="cinema-step-composing">COMPOSING</span>
        <span class="cinema-status-sep">→</span>
        <span class="cinema-status-step" id="cinema-step-rendering">RENDERING</span>
        <span class="cinema-status-sep">→</span>
        <span class="cinema-status-step" id="cinema-step-complete">✓ DONE</span>
        <span class="cinema-status-tmpl" id="cinema-step-template"></span>
      </div>
      <div class="cinema-status-error" id="cinema-status-error"></div>
    </div>

    <!-- Step 5: Video gallery (hidden until first render) -->
    <div id="cinema-renders-section" style="display:none;">
      <div class="cinema-step-label">STEP 5 — YOUR VIDEOS</div>
      <div class="cinema-gallery" id="cinema-gallery"></div>
    </div>

  </div>

  <!-- Fullscreen player modal -->
  <div class="cinema-player-modal" id="cinema-player-modal">
    <button class="cinema-player-close" onclick="closeCinemaPlayer()">✕ CLOSE</button>
    <video id="cinema-player-video" controls></video>
  </div>
</div>
```

- [ ] **Step 5: Manual test — page renders**

Restart gonzoclaw:
```bash
pkill -f 'python3 server.py' 2>/dev/null; cd ~/openclaw/dashboard && PYTHONUNBUFFERED=1 python3 server.py &
```
Open `http://localhost:7080`, click `✦ CINEMA`. Verify:
- Page loads, no JS errors in console
- Drop zone visible with dashed orange border
- Prompt textarea visible
- MAKE IT MAGICAL button visible and pulsing

- [ ] **Step 6: Commit**

```bash
cd ~/openclaw
git add dashboard/index.html
git commit -m "feat: cinema studio UI - nav tab, HTML structure, CSS"
```

---

### Task 8: UI — JavaScript

**Files:**
- Modify: `dashboard/index.html` (add cinema JS block)

- [ ] **Step 1: Add cinema JS**

Find the closing `</script>` tag (near the end of index.html). Insert this block before it:

```javascript
// ── Cinema Studio ─────────────────────────────────────────────────────────

let _cinemaFiles = [];
let _cinemaPollInterval = null;

(function initCinema() {
  const dropzone  = document.getElementById('cinema-dropzone');
  const fileInput = document.getElementById('cinema-file-input');
  if (!dropzone) return;

  dropzone.addEventListener('click', () => fileInput.click());
  dropzone.addEventListener('dragover', e => {
    e.preventDefault(); dropzone.classList.add('drag-over');
  });
  dropzone.addEventListener('dragleave', () => dropzone.classList.remove('drag-over'));
  dropzone.addEventListener('drop', e => {
    e.preventDefault(); dropzone.classList.remove('drag-over');
    _cinemaAddFiles(Array.from(e.dataTransfer.files));
  });
  fileInput.addEventListener('change', () => {
    _cinemaAddFiles(Array.from(fileInput.files));
    fileInput.value = '';
  });

  // Load existing renders when page is activated
  document.getElementById('tabCinema')?.addEventListener('click', loadCinemaRenders);
})();

const _CINEMA_EXT_TYPE = {
  mp3:'AUDIO', wav:'AUDIO', m4a:'AUDIO', ogg:'AUDIO',
  mp4:'VIDEO', mov:'VIDEO', webm:'VIDEO',
  jpg:'IMG', jpeg:'IMG', png:'IMG', gif:'IMG', webp:'IMG',
  txt:'TXT', md:'TXT',
};

function _cinemaAddFiles(files) {
  _cinemaFiles = [..._cinemaFiles, ...files];
  _cinemaRenderChips();
}

function _cinemaRemoveFile(i) {
  _cinemaFiles.splice(i, 1);
  _cinemaRenderChips();
}

function _cinemaRenderChips() {
  const container = document.getElementById('cinema-file-chips');
  if (!container) return;
  container.innerHTML = _cinemaFiles.map((f, i) => {
    const ext = f.name.split('.').pop().toLowerCase();
    const type = _CINEMA_EXT_TYPE[ext] || 'FILE';
    return `<span class="cinema-chip">
      <span class="cinema-chip-badge">${type}</span>
      ${f.name}
      <button onclick="_cinemaRemoveFile(${i})">×</button>
    </span>`;
  }).join('');
}

async function makeMagical() {
  const prompt = (document.getElementById('cinema-prompt')?.value || '').trim();
  if (!prompt && _cinemaFiles.length === 0) return;

  const btn = document.getElementById('cinema-magic-btn');
  btn.disabled = true;

  _cinemaSetStatus('uploading');

  try {
    // 1. Upload files
    const fd = new FormData();
    _cinemaFiles.forEach(f => fd.append('files', f));
    const upResp = await fetch('/api/cinema/upload', { method: 'POST', body: fd });
    if (!upResp.ok) throw new Error(`Upload failed: ${upResp.status}`);
    const { job_id } = await upResp.json();

    // 2. Submit render
    const renderResp = await fetch('/api/cinema/render', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id, prompt }),
    });
    if (!renderResp.ok) throw new Error(`Render submit failed: ${renderResp.status}`);

    _cinemaSetStatus('queued');

    // 3. Poll status every 3s
    if (_cinemaPollInterval) clearInterval(_cinemaPollInterval);
    _cinemaPollInterval = setInterval(() => _cinemaPoll(job_id), 3000);

  } catch (err) {
    _cinemaSetStatus('failed', err.message);
    btn.disabled = false;
  }
}

async function _cinemaPoll(jobId) {
  try {
    const r = await fetch(`/api/cinema/status/${jobId}`);
    if (!r.ok) return;
    const data = await r.json();
    _cinemaSetStatus(data.status, data.error, data.template);

    if (data.status === 'complete') {
      clearInterval(_cinemaPollInterval);
      document.getElementById('cinema-magic-btn').disabled = false;
      loadCinemaRenders();
    } else if (data.status === 'failed') {
      clearInterval(_cinemaPollInterval);
      document.getElementById('cinema-magic-btn').disabled = false;
    }
  } catch (_) {}
}

function _cinemaSetStatus(status, error, template) {
  const section = document.getElementById('cinema-status-section');
  if (!section) return;
  section.style.display = 'block';

  const steps = ['uploading', 'queued', 'composing', 'rendering', 'complete'];
  const idx   = steps.indexOf(status);

  steps.forEach((s, i) => {
    const el = document.getElementById(`cinema-step-${s}`);
    if (!el) return;
    el.className = 'cinema-status-step' +
      (i < idx ? ' done' : i === idx ? ' active' : '');
  });

  const tmplEl = document.getElementById('cinema-step-template');
  if (tmplEl) tmplEl.textContent = template ? `[${template}]` : '';

  const errEl = document.getElementById('cinema-status-error');
  if (errEl) {
    errEl.style.display = error ? 'block' : 'none';
    if (error) errEl.textContent = `✕ ${error}`;
  }
}

async function loadCinemaRenders() {
  try {
    const r = await fetch('/api/cinema/renders');
    if (!r.ok) return;
    const renders = await r.json();

    const section = document.getElementById('cinema-renders-section');
    const gallery = document.getElementById('cinema-gallery');
    if (!section || !gallery) return;

    if (renders.length === 0) { section.style.display = 'none'; return; }

    section.style.display = 'block';
    gallery.innerHTML = renders.map(render => `
      <div class="cinema-video-card" onclick="openCinemaPlayer('${render.filename}')">
        <video src="/api/cinema/renders/${render.filename}"
               muted preload="metadata" playsinline></video>
        <div class="cinema-video-label">${render.job_id}</div>
        <div class="cinema-video-date">${(render.created_at || '').slice(0, 10)}</div>
      </div>
    `).join('');
  } catch (_) {}
}

function openCinemaPlayer(filename) {
  const modal = document.getElementById('cinema-player-modal');
  const video = document.getElementById('cinema-player-video');
  if (!modal || !video) return;
  video.src = `/api/cinema/renders/${filename}`;
  modal.style.display = 'flex';
  video.play().catch(() => {});
}

function closeCinemaPlayer() {
  const modal = document.getElementById('cinema-player-modal');
  const video = document.getElementById('cinema-player-video');
  if (!modal || !video) return;
  video.pause();
  video.src = '';
  modal.style.display = 'none';
}
```

- [ ] **Step 2: Verify `showPage('cinema')` is wired**

Find the `showPage` function and check it handles `'cinema'`. The existing pattern activates the tab and shows the page div. If the function uses a generic approach (iterates all `.nav-tab` + `.page`), it already works — no change needed. If it uses explicit `if/else` cases, add:
```javascript
if (page === 'cinema') { document.getElementById('tabCinema').classList.add('active'); }
```

- [ ] **Step 3: Manual test — full flow**

1. Restart gonzoclaw if needed: `pkill -f 'python3 server.py'; cd ~/openclaw/dashboard && PYTHONUNBUFFERED=1 python3 server.py &`
2. Open `http://localhost:7080/cinema`
3. Drop an image file onto the drop zone → chip appears
4. Type a prompt: `"A dramatic title card for OpenClaw"`
5. Click MAKE IT MAGICAL
6. Watch status ticker advance: UPLOADING → QUEUED → COMPOSING → RENDERING → ✓ DONE
7. Video appears in gallery → click to open fullscreen player

Check render log if something fails: `tail -50 ~/openclaw/logs/cinema-<job_id>.log`

- [ ] **Step 4: Commit**

```bash
cd ~/openclaw
git add dashboard/index.html
git commit -m "feat: cinema studio UI - JavaScript upload, render, polling, gallery, player"
```

---

**All tasks complete.** Proceed to `superpowers:finishing-a-development-branch`.
