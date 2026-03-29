# Cinema Studio — Design Spec
**Date:** 2026-03-29
**Status:** Approved
**Location:** Gonzoclaw dashboard (`localhost:7080`) — new `✦ CINEMA` tab
**Output:** 9:16 vertical MP4s (1080×1920, 30fps) for social media

---

## 1. Architecture

Three layers wired together. No new processes — everything runs inside the existing gonzoclaw/OpenClaw stack.

```
gonzoclaw UI (index.html)
    ↕  REST (fetch)
FastAPI server (dashboard/server.py) — 5 new endpoints
    ↕  subprocess
Render pipeline (cinema-lab/pipeline.py)
    ↕  Ollama API       ↕  npx remotion render
qwen3:30b               cinema-lab/remotion/
```

### File Layout

```
cinema-lab/
├── remotion/                ← Remotion project (npx create-video@latest)
│   └── src/
│       ├── templates/       ← TextReveal.tsx, ImageSlideshow.tsx,
│       │                       NarrationReel.tsx, TitleCard.tsx
│       ├── custom/          ← LLM-generated JSX (ephemeral, gitignored)
│       └── index.ts         ← registers all compositions
├── assets/
│   └── {job_id}/            ← uploaded files scoped per job
├── renders/                 ← output MP4s, served by FastAPI
├── jobs.json                ← job queue + status log
└── pipeline.py              ← render orchestrator
```

---

## 2. Remotion Templates

All compositions: 1080×1920, 30fps, accept a typed `SceneProps` JSON object.

### `TextReveal`
Words slam in one-by-one over a solid color or blurred asset background.
```ts
type TextRevealProps = {
  text: string;           // full text, split into words by template
  accent_color: string;   // hex — defaults to #e86800 (gonzoclaw orange)
  bg_asset?: string;      // optional image/video path (blurred behind text)
  duration_frames: number;
}
```
Use: quotes, hooks, punchy openers.

### `ImageSlideshow`
Sequence of images with Ken Burns zoom + crossfade transitions. Optional per-image caption.
```ts
type ImageSlideshowProps = {
  images: string[];       // asset paths
  captions?: string[];    // one per image, optional
  duration_frames: number;
}
```
Use: photo essays, product showcases, travel content.

### `NarrationReel`
Audio-driven timeline. Clips cut on beat markers. Text captions sync to narration.
```ts
type NarrationReelProps = {
  audio: string;          // asset path (.mp3 / .wav)
  clips: string[];        // image or video asset paths
  captions: string[];     // one per clip
  duration_frames: number;
}
```
Use: storytelling, explainers, narrated social content.

### `TitleCard`
Single-impact frame sequence: title → subtitle fade → CTA.
```ts
type TitleCardProps = {
  title: string;
  subtitle?: string;
  cta?: string;
  bg_color: string;       // hex
  duration_frames: number;
}
```
Use: intros, outros, brand idents, chapter cards.

---

## 3. Render Pipeline

**File:** `cinema-lab/pipeline.py`

### Step-by-step

```
1. BUILD MANIFEST
   Scan assets/{job_id}/ → list of {filename, type, path}
   Types inferred from extension: audio, video, image, text

2. LLM COMPOSE  (Ollama → qwen3:30b)
   Input:  user prompt + asset manifest (JSON)
   Output: scene plan JSON:
   {
     "template": "NarrationReel",   // or "TextReveal" / "ImageSlideshow" / "TitleCard" / "custom"
     "composition_id": "job_{id}",
     "scenes": { ...template-specific fields... },
     "duration_frames": 450         // 15s @ 30fps; LLM sets based on content
   }
   System prompt instructs LLM on template schemas + 9:16 constraints.

3a. TEMPLATE PATH (happy path)
    Write scene plan as props to remotion/src/custom/{job_id}.tsx
    Import correct template, pass props
    Run: npx remotion render src/index.ts {composition_id} \
           --output=../../renders/{job_id}.mp4 \
           --width=1080 --height=1920

3b. CUSTOM PATH (escape hatch)
    LLM writes full JSX Remotion component
    Validate: node --check remotion/src/custom/{job_id}.tsx
    If invalid → log warning, fall back to TextReveal with user prompt as text
    If valid → render same as template path

4. STATUS UPDATES
   pipeline.py writes to jobs.json at each step:
   status: "queued" | "composing" | "rendering" | "complete" | "failed"
   On complete: output_path = "renders/{job_id}.mp4"
   On failed:   error message stored
```

### Render time estimate
~2–4 min for a 15–30s clip on M2 Max (Remotion is CPU-bound, headless Chrome).

---

## 4. FastAPI Endpoints (server.py additions)

```
POST   /api/cinema/upload              → multipart upload, saves to assets/{job_id}/
                                         returns {job_id, files: [{name, type}]}

POST   /api/cinema/render              → {job_id, prompt}
                                         spawns pipeline.py as background subprocess
                                         returns {job_id, status: "queued"}

GET    /api/cinema/status/{job_id}     → {status, template?, error?, output_path?}

GET    /api/cinema/renders             → [{job_id, filename, created_at, duration_s?}]

GET    /api/cinema/renders/{filename}  → serves MP4 (video/mp4, range-request support)
```

---

## 5. UI — Cinema Page (`pageCinema` in `index.html`)

### Nav tab
```html
<button class="nav-tab" id="tabCinema" onclick="showPage('cinema')">✦ CINEMA</button>
```

### Page layout (vertical, gonzoclaw aesthetic)

```
◈ CINEMA STUDIO                          ← .page-title orange letter-spaced
MAKE VIDEOS. TELL STORIES.               ← .page-subtitle grey2

──────────────────────────────────────

STEP 1 — DROP YOUR ASSETS                ← .section-label (0.52rem, grey2, 2.5px spacing)

┌────────────────────────────────────┐
│  drag files here · or click        │   dashed 1px border var(--orange-dim)
│  audio · video · images · text     │   hover: border var(--orange), bg glow
└────────────────────────────────────┘
[AUDIO] job_narration.mp3  ×            ← file chips, orange badge per type
[IMG]   hero_frame.jpg     ×
[TEXT]  script.txt         ×

──────────────────────────────────────

STEP 2 — DESCRIBE YOUR VISION

┌────────────────────────────────────┐
│  what story do you want to tell?   │   monospace textarea, 6 rows
│                                    │   focus: border var(--orange), 0 0 8px glow
└────────────────────────────────────┘

──────────────────────────────────────

STEP 3 — RENDER

╔════════════════════════════════════╗
║  ✦  MAKE IT MAGICAL  ✦             ║   large button, bg var(--orange)
╚════════════════════════════════════╝   pulsing box-shadow glow animation
                                         disabled + spinner while job running

──────────────────────────────────────

STEP 4 — STATUS                          hidden until first job submitted

▸ QUEUED  →  COMPOSING  →  RENDERING  →  ✓ DONE
  [template name shown when composing starts]
  [error message in neon-red on failure]

──────────────────────────────────────

STEP 5 — YOUR VIDEOS                     hidden until first render complete

┌─────────┐  ┌─────────┐  ┌─────────┐
│  9:16   │  │  9:16   │  │  9:16   │  video cards, 3-per-row on desktop
│ <video> │  │ <video> │  │ <video> │  click → fullscreen modal player
│ job id  │  │ job id  │  │ job id  │  date + duration badge
└─────────┘  └─────────┘  └─────────┘
```

### Key CSS rules
- Button pulse: `@keyframes magic-pulse` — alternating `box-shadow` on `--orange` and `--orange-hi`
- File drop hover: border → `var(--orange)` + subtle orange bg glow
- Status steps: inactive = `var(--grey2)`, active = `var(--orange-hi)`, done = `var(--neon-green)`
- Video cards: `border: 1px solid var(--grey3)`, hover `border-color: var(--orange)`

---

## 6. LLM System Prompt (pipeline.py)

```
You are a Remotion video composition engine for 9:16 vertical social media videos (1080x1920, 30fps).

Given a user prompt and an asset manifest, output a JSON scene plan.

Available templates and their required fields:
- TextReveal: {text, accent_color, bg_asset?, duration_frames}
- ImageSlideshow: {images[], captions[]?, duration_frames}
- NarrationReel: {audio, clips[], captions[], duration_frames}
- TitleCard: {title, subtitle?, cta?, bg_color, duration_frames}
- custom: write a full Remotion JSX component (only if none of the above fit)

Rules:
- duration_frames = seconds × 30. Target 15–60s (450–1800 frames).
- Only reference assets from the provided manifest by their exact filename.
- For custom mode, write complete valid TSX with all imports from remotion package.
- Output ONLY valid JSON. No markdown, no explanation.
```

---

## 7. Out of Scope

- Audio generation / TTS (assets must be pre-recorded)
- Horizontal (16:9) output — added in a future iteration
- Videos longer than 60s — templates support it but UI caps at 60s for now
- Batch rendering multiple jobs simultaneously
- Direct social media posting
