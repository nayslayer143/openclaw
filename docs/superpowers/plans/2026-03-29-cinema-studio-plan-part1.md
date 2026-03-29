# Cinema Studio — Part 1 of 2: Remotion Scaffold, Templates, Pipeline Core
# Read AFTER: 2026-03-29-cinema-studio-plan.md
# Read BEFORE: 2026-03-29-cinema-studio-plan-part2.md

---

### Task 1: Remotion scaffold

**Files:**
- Create: `cinema-lab/remotion/` (via npx)

- [ ] **Step 1: Scaffold the Remotion project**

```bash
cd ~/openclaw/cinema-lab
npx create-video@latest
```
When prompted:
- Project name: `remotion`
- Template: **Blank**
- Package manager: `npm`

- [ ] **Step 2: Verify it compiled**

```bash
cd ~/openclaw/cinema-lab/remotion
npm run build 2>&1 | tail -5
```
Expected: no errors.

- [ ] **Step 3: Smoke test render**

```bash
cd ~/openclaw/cinema-lab/remotion
npx remotion render src/index.ts MyComposition --output=/tmp/smoke.mp4
```
Expected: `/tmp/smoke.mp4` is created (may take ~30s).

- [ ] **Step 4: Create asset directories**

```bash
mkdir -p ~/openclaw/cinema-lab/assets
mkdir -p ~/openclaw/cinema-lab/renders
touch ~/openclaw/cinema-lab/assets/.gitkeep
touch ~/openclaw/cinema-lab/renders/.gitkeep
echo '{}' > ~/openclaw/cinema-lab/jobs.json
```

- [ ] **Step 5: Commit**

```bash
cd ~/openclaw
git add cinema-lab/remotion cinema-lab/assets/.gitkeep cinema-lab/renders/.gitkeep cinema-lab/jobs.json
git commit -m "feat: scaffold Remotion project in cinema-lab"
```

---

### Task 2: TextReveal + ImageSlideshow templates

**Files:**
- Create: `cinema-lab/remotion/src/templates/TextReveal.tsx`
- Create: `cinema-lab/remotion/src/templates/ImageSlideshow.tsx`
- Create: `cinema-lab/remotion/src/Root.tsx` (replaces scaffold version)
- Modify: `cinema-lab/remotion/src/index.ts` (keep as-is if it just calls registerRoot)

- [ ] **Step 1: Create TextReveal.tsx**

```bash
mkdir -p ~/openclaw/cinema-lab/remotion/src/templates
```

Write `cinema-lab/remotion/src/templates/TextReveal.tsx`:

```tsx
import React from 'react';
import { AbsoluteFill, interpolate, useCurrentFrame, staticFile, Img } from 'remotion';

export type TextRevealProps = {
  text: string;
  accent_color: string;
  bg_asset?: string;
  duration_frames: number;
};

export const TextReveal: React.FC<TextRevealProps> = ({
  text,
  accent_color,
  bg_asset,
  duration_frames,
}) => {
  const frame = useCurrentFrame();
  const words = text.split(' ');
  const framesPerWord = Math.max(8, duration_frames / words.length);

  return (
    <AbsoluteFill
      style={{
        backgroundColor: '#060606',
        justifyContent: 'center',
        alignItems: 'center',
        padding: 60,
      }}
    >
      {bg_asset && (
        <AbsoluteFill>
          <Img
            src={staticFile(bg_asset)}
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'cover',
              filter: 'blur(20px)',
              opacity: 0.3,
            }}
          />
        </AbsoluteFill>
      )}
      <div
        style={{
          textAlign: 'center',
          fontFamily: 'monospace',
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'center',
          gap: 16,
        }}
      >
        {words.map((word, i) => {
          const startFrame = i * framesPerWord;
          const opacity = interpolate(
            frame,
            [startFrame, startFrame + 8],
            [0, 1],
            { extrapolateRight: 'clamp', extrapolateLeft: 'clamp' }
          );
          const y = interpolate(
            frame,
            [startFrame, startFrame + 8],
            [30, 0],
            { extrapolateRight: 'clamp', extrapolateLeft: 'clamp' }
          );
          return (
            <span
              key={i}
              style={{
                color: i % 3 === 0 ? accent_color : '#f0ece4',
                fontSize: 80,
                fontWeight: 700,
                opacity,
                transform: `translateY(${y}px)`,
                letterSpacing: 2,
                display: 'inline-block',
              }}
            >
              {word}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
```

- [ ] **Step 2: Create ImageSlideshow.tsx**

Write `cinema-lab/remotion/src/templates/ImageSlideshow.tsx`:

```tsx
import React from 'react';
import { AbsoluteFill, interpolate, useCurrentFrame, Sequence, Img, staticFile } from 'remotion';

export type ImageSlideshowProps = {
  images: string[];
  captions?: string[];
  duration_frames: number;
};

const SlideFrame: React.FC<{ src: string; caption?: string; totalFrames: number }> = ({
  src,
  caption,
  totalFrames,
}) => {
  const frame = useCurrentFrame();
  const scale = interpolate(frame, [0, totalFrames], [1, 1.08]);
  const opacity = interpolate(
    frame,
    [0, 10, totalFrames - 10, totalFrames],
    [0, 1, 1, 0],
    { extrapolateRight: 'clamp', extrapolateLeft: 'clamp' }
  );

  return (
    <AbsoluteFill style={{ opacity }}>
      <Img
        src={staticFile(src)}
        style={{ width: '100%', height: '100%', objectFit: 'cover', transform: `scale(${scale})` }}
      />
      {caption && (
        <div
          style={{
            position: 'absolute',
            bottom: 80,
            left: 40,
            right: 40,
            color: '#f0ece4',
            fontSize: 40,
            fontFamily: 'monospace',
            textShadow: '0 2px 12px rgba(0,0,0,0.9)',
            letterSpacing: 1,
            lineHeight: 1.4,
          }}
        >
          {caption}
        </div>
      )}
    </AbsoluteFill>
  );
};

export const ImageSlideshow: React.FC<ImageSlideshowProps> = ({
  images,
  captions,
  duration_frames,
}) => {
  if (images.length === 0) return <AbsoluteFill style={{ backgroundColor: '#060606' }} />;
  const framesPerImage = Math.floor(duration_frames / images.length);

  return (
    <AbsoluteFill style={{ backgroundColor: '#060606' }}>
      {images.map((img, i) => (
        <Sequence key={i} from={i * framesPerImage} durationInFrames={framesPerImage}>
          <SlideFrame src={img} caption={captions?.[i]} totalFrames={framesPerImage} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
```

- [ ] **Step 3: Replace Root.tsx with TextReveal + ImageSlideshow registrations**

Write `cinema-lab/remotion/src/Root.tsx`:

```tsx
import React from 'react';
import { Composition } from 'remotion';
import { TextReveal, TextRevealProps } from './templates/TextReveal';
import { ImageSlideshow, ImageSlideshowProps } from './templates/ImageSlideshow';

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="TextReveal"
        component={TextReveal}
        durationInFrames={450}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={{
          text: 'Make it magical',
          accent_color: '#e86800',
          duration_frames: 450,
        }}
        calculateMetadata={async ({ props }: { props: TextRevealProps }) => ({
          durationInFrames: props.duration_frames,
        })}
      />
      <Composition
        id="ImageSlideshow"
        component={ImageSlideshow}
        durationInFrames={450}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={{
          images: [],
          captions: [],
          duration_frames: 450,
        }}
        calculateMetadata={async ({ props }: { props: ImageSlideshowProps }) => ({
          durationInFrames: props.duration_frames,
        })}
      />
    </>
  );
};
```

- [ ] **Step 4: Verify index.ts calls registerRoot**

`cinema-lab/remotion/src/index.ts` should contain exactly:
```ts
import {registerRoot} from 'remotion';
import {RemotionRoot} from './Root';

registerRoot(RemotionRoot);
```
If it differs, replace it with the above.

- [ ] **Step 5: Test render TextReveal**

```bash
cd ~/openclaw/cinema-lab/remotion
npx remotion render src/index.ts TextReveal \
  --props='{"text":"OpenClaw fires today","accent_color":"#e86800","duration_frames":150}' \
  --output=/tmp/test-textreveal.mp4
```
Expected: `/tmp/test-textreveal.mp4` created, ~5s at 150 frames.

- [ ] **Step 6: Test render ImageSlideshow (no images = black frame, acceptable)**

```bash
npx remotion render src/index.ts ImageSlideshow \
  --props='{"images":[],"duration_frames":90}' \
  --output=/tmp/test-slideshow.mp4
```
Expected: MP4 created.

- [ ] **Step 7: Commit**

```bash
cd ~/openclaw
git add cinema-lab/remotion/src/
git commit -m "feat: add TextReveal and ImageSlideshow Remotion templates"
```

---

### Task 3: NarrationReel + TitleCard + finalize Root.tsx

**Files:**
- Create: `cinema-lab/remotion/src/templates/NarrationReel.tsx`
- Create: `cinema-lab/remotion/src/templates/TitleCard.tsx`
- Create: `cinema-lab/remotion/src/custom/.gitkeep`
- Modify: `cinema-lab/remotion/src/Root.tsx` (add NarrationReel + TitleCard)

- [ ] **Step 1: Create NarrationReel.tsx**

Write `cinema-lab/remotion/src/templates/NarrationReel.tsx`:

```tsx
import React from 'react';
import { AbsoluteFill, Audio, interpolate, useCurrentFrame, Sequence, Img, staticFile } from 'remotion';

export type NarrationReelProps = {
  audio: string;
  clips: string[];
  captions: string[];
  duration_frames: number;
};

const ClipFrame: React.FC<{ src: string; caption: string; totalFrames: number }> = ({
  src,
  caption,
  totalFrames,
}) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(
    frame,
    [0, 8, totalFrames - 8, totalFrames],
    [0, 1, 1, 0],
    { extrapolateRight: 'clamp', extrapolateLeft: 'clamp' }
  );
  const captionOpacity = interpolate(frame, [10, 22], [0, 1], { extrapolateRight: 'clamp' });

  return (
    <AbsoluteFill style={{ opacity }}>
      <Img src={staticFile(src)} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
      <div
        style={{
          position: 'absolute',
          bottom: 0,
          left: 0,
          right: 0,
          padding: '80px 40px 60px',
          background: 'linear-gradient(transparent, rgba(0,0,0,0.88))',
        }}
      >
        <div
          style={{
            color: '#f0ece4',
            fontSize: 38,
            fontFamily: 'monospace',
            opacity: captionOpacity,
            letterSpacing: 0.5,
            lineHeight: 1.5,
          }}
        >
          {caption}
        </div>
      </div>
    </AbsoluteFill>
  );
};

export const NarrationReel: React.FC<NarrationReelProps> = ({
  audio,
  clips,
  captions,
  duration_frames,
}) => {
  const framesPerClip = clips.length > 0 ? Math.floor(duration_frames / clips.length) : duration_frames;

  return (
    <AbsoluteFill style={{ backgroundColor: '#060606' }}>
      {audio && <Audio src={staticFile(audio)} />}
      {clips.map((clip, i) => (
        <Sequence key={i} from={i * framesPerClip} durationInFrames={framesPerClip}>
          <ClipFrame src={clip} caption={captions[i] ?? ''} totalFrames={framesPerClip} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
```

- [ ] **Step 2: Create TitleCard.tsx**

Write `cinema-lab/remotion/src/templates/TitleCard.tsx`:

```tsx
import React from 'react';
import { AbsoluteFill, interpolate, useCurrentFrame, spring } from 'remotion';

export type TitleCardProps = {
  title: string;
  subtitle?: string;
  cta?: string;
  bg_color: string;
  duration_frames: number;
};

export const TitleCard: React.FC<TitleCardProps> = ({
  title,
  subtitle,
  cta,
  bg_color,
  duration_frames,
}) => {
  const frame = useCurrentFrame();
  const fps = 30;

  const titleOpacity = spring({ fps, frame, config: { damping: 80 } });
  const titleY = interpolate(frame, [0, 20], [60, 0], { extrapolateRight: 'clamp' });
  const subtitleOpacity = interpolate(frame, [15, 30], [0, 1], { extrapolateRight: 'clamp' });
  const ctaOpacity = interpolate(frame, [30, 45], [0, 1], { extrapolateRight: 'clamp' });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: bg_color,
        justifyContent: 'center',
        alignItems: 'center',
        flexDirection: 'column',
        gap: 32,
        padding: 80,
      }}
    >
      <div
        style={{
          color: '#f0ece4',
          fontSize: 96,
          fontWeight: 700,
          fontFamily: 'monospace',
          textAlign: 'center',
          opacity: titleOpacity,
          transform: `translateY(${titleY}px)`,
          letterSpacing: -2,
          lineHeight: 1.1,
        }}
      >
        {title}
      </div>
      {subtitle && (
        <div
          style={{
            color: '#e86800',
            fontSize: 42,
            fontFamily: 'monospace',
            textAlign: 'center',
            opacity: subtitleOpacity,
            letterSpacing: 3,
          }}
        >
          {subtitle}
        </div>
      )}
      {cta && (
        <div
          style={{
            marginTop: 40,
            padding: '20px 48px',
            border: '2px solid #e86800',
            color: '#e86800',
            fontSize: 32,
            fontFamily: 'monospace',
            letterSpacing: 4,
            opacity: ctaOpacity,
          }}
        >
          {cta}
        </div>
      )}
    </AbsoluteFill>
  );
};
```

- [ ] **Step 3: Add NarrationReel + TitleCard to Root.tsx**

Replace `cinema-lab/remotion/src/Root.tsx` with:

```tsx
import React from 'react';
import { Composition } from 'remotion';
import { TextReveal, TextRevealProps } from './templates/TextReveal';
import { ImageSlideshow, ImageSlideshowProps } from './templates/ImageSlideshow';
import { NarrationReel, NarrationReelProps } from './templates/NarrationReel';
import { TitleCard, TitleCardProps } from './templates/TitleCard';

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="TextReveal"
        component={TextReveal}
        durationInFrames={450}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={{ text: 'Make it magical', accent_color: '#e86800', duration_frames: 450 }}
        calculateMetadata={async ({ props }: { props: TextRevealProps }) => ({
          durationInFrames: props.duration_frames,
        })}
      />
      <Composition
        id="ImageSlideshow"
        component={ImageSlideshow}
        durationInFrames={450}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={{ images: [], captions: [], duration_frames: 450 }}
        calculateMetadata={async ({ props }: { props: ImageSlideshowProps }) => ({
          durationInFrames: props.duration_frames,
        })}
      />
      <Composition
        id="NarrationReel"
        component={NarrationReel}
        durationInFrames={450}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={{ audio: '', clips: [], captions: [], duration_frames: 450 }}
        calculateMetadata={async ({ props }: { props: NarrationReelProps }) => ({
          durationInFrames: props.duration_frames,
        })}
      />
      <Composition
        id="TitleCard"
        component={TitleCard}
        durationInFrames={450}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={{ title: 'OPENCLAW', bg_color: '#060606', duration_frames: 450 }}
        calculateMetadata={async ({ props }: { props: TitleCardProps }) => ({
          durationInFrames: props.duration_frames,
        })}
      />
    </>
  );
};
```

- [ ] **Step 4: Create custom placeholder**

```bash
mkdir -p ~/openclaw/cinema-lab/remotion/src/custom
touch ~/openclaw/cinema-lab/remotion/src/custom/.gitkeep
```

- [ ] **Step 5: Test render NarrationReel**

```bash
cd ~/openclaw/cinema-lab/remotion
npx remotion render src/index.ts NarrationReel \
  --props='{"audio":"","clips":[],"captions":[],"duration_frames":90}' \
  --output=/tmp/test-narration.mp4
```
Expected: MP4 created (black frame, no audio).

- [ ] **Step 6: Test render TitleCard**

```bash
npx remotion render src/index.ts TitleCard \
  --props='{"title":"GONZOCLAW","subtitle":"MAKING MOVES","cta":"FOLLOW NOW","bg_color":"#060606","duration_frames":90}' \
  --output=/tmp/test-titlecard.mp4
```
Expected: MP4 created with animated title.

- [ ] **Step 7: Commit**

```bash
cd ~/openclaw
git add cinema-lab/remotion/src/
git commit -m "feat: add NarrationReel and TitleCard Remotion templates, finalize Root.tsx"
```

---

### Task 4: pipeline.py — manifest + LLM + status

**Files:**
- Create: `cinema-lab/pipeline.py`
- Create: `cinema-lab/tests/__init__.py`
- Create: `cinema-lab/tests/test_pipeline.py`

- [ ] **Step 1: Write failing tests**

Create `cinema-lab/tests/__init__.py` (empty).

Write `cinema-lab/tests/test_pipeline.py`:

```python
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd ~/openclaw
python3 -m pytest cinema-lab/tests/test_pipeline.py -v 2>&1 | head -20
```
Expected: `ModuleNotFoundError` or `ImportError` (pipeline.py doesn't exist yet).

- [ ] **Step 3: Implement pipeline.py (manifest + LLM + status)**

Write `cinema-lab/pipeline.py`:

```python
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
CINEMA_DIR     = Path(__file__).parent
ASSETS_DIR     = CINEMA_DIR / "assets"
RENDERS_DIR    = CINEMA_DIR / "renders"
REMOTION_DIR   = CINEMA_DIR / "remotion"
REMOTION_PUBLIC = REMOTION_DIR / "public"
JOBS_FILE      = CINEMA_DIR / "jobs.json"

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
```

- [ ] **Step 4: Run tests — they should pass now**

```bash
cd ~/openclaw
python3 -m pytest cinema-lab/tests/test_pipeline.py -v
```
Expected: 7 tests passing.

- [ ] **Step 5: Commit**

```bash
cd ~/openclaw
git add cinema-lab/pipeline.py cinema-lab/tests/
git commit -m "feat: pipeline.py manifest builder, LLM compose, status helpers"
```

---

**Continue reading:** `2026-03-29-cinema-studio-plan-part2.md`
