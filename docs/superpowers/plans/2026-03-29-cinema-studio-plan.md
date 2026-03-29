# Cinema Studio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `✦ CINEMA` tab to the gonzoclaw dashboard with drag-drop asset upload, LLM-powered Remotion video composition (qwen3:30b), and an in-browser viewer for rendered 9:16 social media videos.

**Architecture:** Remotion (TypeScript/React) hosts 4 template compositions. A Python pipeline orchestrates LLM scene planning via Ollama and calls `npx remotion render`. FastAPI adds 5 `/api/cinema/` endpoints to the existing `server.py`. `index.html` gets a new `pageCinema` with a vertical step-by-step UI in the gonzoclaw dark-orange aesthetic.

**Tech Stack:** Remotion v4, React 18, TypeScript, Python 3.9, FastAPI (existing), Ollama `qwen3:30b`

---

## Read Order (split plan — read in this order)

| File | Contents |
|------|----------|
| `2026-03-29-cinema-studio-plan.md` | **This file** — entry point, file map, key rules, task index |
| `2026-03-29-cinema-studio-plan-part1.md` | Tasks 1–4: Remotion scaffold, 4 templates, pipeline.py core |
| `2026-03-29-cinema-studio-plan-part2.md` | Tasks 5–8: pipeline render paths, FastAPI endpoints, UI HTML/CSS/JS |

---

## File Map

**Create:**
```
cinema-lab/remotion/                         Task 1  (scaffolded by npx create-video@latest)
cinema-lab/remotion/src/templates/TextReveal.tsx      Task 2
cinema-lab/remotion/src/templates/ImageSlideshow.tsx  Task 2
cinema-lab/remotion/src/Root.tsx             Task 2  (replaces scaffold version)
cinema-lab/remotion/src/templates/NarrationReel.tsx   Task 3
cinema-lab/remotion/src/templates/TitleCard.tsx       Task 3
cinema-lab/remotion/src/custom/.gitkeep     Task 3
cinema-lab/pipeline.py                       Tasks 4–5
cinema-lab/assets/.gitkeep                  Task 4
cinema-lab/renders/.gitkeep                 Task 4
cinema-lab/jobs.json                         Task 4  (initialized as {})
cinema-lab/tests/__init__.py                Task 4
cinema-lab/tests/test_pipeline.py           Tasks 4–5
dashboard/tests/__init__.py                 Task 6
dashboard/tests/test_cinema_api.py          Task 6
```

**Modify:**
```
dashboard/server.py        Task 6  (add 5 cinema endpoints + 4 helpers before line 2647)
dashboard/index.html       Tasks 7–8  (nav tab + pageCinema + CSS + JS)
```

---

## Key Rules

1. **Run Python tests** from `~/openclaw/`:
   `python3 -m pytest cinema-lab/tests/ -v`
   `python3 -m pytest dashboard/tests/test_cinema_api.py -v`

2. **Run Remotion renders** from `~/openclaw/cinema-lab/remotion/`:
   `npx remotion render src/index.ts <CompositionId> --props='<JSON>' --output=/tmp/test.mp4`

3. **Asset paths in props** are relative to `cinema-lab/remotion/public/`
   (e.g., `"job123/image.jpg"` → pipeline copies to `remotion/public/job123/image.jpg`)

4. **Restart gonzoclaw** to pick up `server.py` changes:
   `pkill -f 'server.py' && cd ~/openclaw/dashboard && python3 server.py &`
   Or find PID: `lsof -i :7080`

5. **Verify Ollama** has qwen3:30b before testing pipeline:
   `ollama list | grep qwen3:30b`
   If missing: `ollama pull qwen3:30b`

6. **`cinema-lab` has a hyphen** — not a Python package. Tests import pipeline with importlib (see Task 4).

7. The **new cinema endpoints** must be inserted **before** the catch-all `@app.get("/{path:path}")` at line 2658 of `server.py`.

---

## Task Index

| # | Task | Files | Test method |
|---|------|-------|-------------|
| 1 | Remotion scaffold | `cinema-lab/remotion/` | `npx remotion render` smoke test |
| 2 | TextReveal + ImageSlideshow templates | `templates/`, `Root.tsx` | `npx remotion render` each |
| 3 | NarrationReel + TitleCard templates | `templates/`, `Root.tsx` | `npx remotion render` each |
| 4 | pipeline.py — manifest + LLM + status | `pipeline.py`, `test_pipeline.py` | pytest |
| 5 | pipeline.py — render paths | `pipeline.py`, `test_pipeline.py` | pytest |
| 6 | FastAPI cinema endpoints | `server.py`, `test_cinema_api.py` | pytest |
| 7 | UI HTML + CSS | `index.html` | manual |
| 8 | UI JavaScript | `index.html` | manual |

---

**Continue reading:** `2026-03-29-cinema-studio-plan-part1.md`
