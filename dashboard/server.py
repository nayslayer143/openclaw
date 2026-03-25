#!/usr/bin/env python3
"""
OpenClaw Dashboard — FastAPI backend
Real-time task monitor with GitHub OAuth
"""
import os, json, asyncio, secrets, time, hashlib, subprocess, re, uuid, base64, signal, sys
from pathlib import Path
from typing import AsyncGenerator, Optional
from datetime import datetime, timedelta

from fastapi import FastAPI, Request, Response, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import httpx
from jose import jwt, JWTError

# ── Config ────────────────────────────────────────────────────────────────────
OPENCLAW_ROOT  = Path.home() / "openclaw"
BUILD_RESULTS  = OPENCLAW_ROOT / "build-results"
QUEUE_DIR      = OPENCLAW_ROOT / "repo-queue"
PENDING_JSON   = OPENCLAW_ROOT / "queue" / "pending.json"
LOGS_DIR       = OPENCLAW_ROOT / "logs"
IDEAS_DIR      = OPENCLAW_ROOT / "ideas"
IDEAS_MEDIA    = IDEAS_DIR / "media"
PROJECTS_FILE  = OPENCLAW_ROOT / "projects" / "projects.json"

ENV_FILE = OPENCLAW_ROOT / ".env"
def load_env():
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
load_env()

DASHBOARD_ENV = Path(__file__).parent / ".env"
if DASHBOARD_ENV.exists():
    for line in DASHBOARD_ENV.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()

GITHUB_CLIENT_ID     = os.environ.get("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")
ALLOWED_GITHUB_USERS = set(os.environ.get("ALLOWED_GITHUB_USERS", "nayslayer").split(","))
JWT_SECRET  = os.environ.get("DASHBOARD_JWT_SECRET") or secrets.token_hex(32)
JWT_ALG     = "HS256"
JWT_EXPIRE  = 60 * 24 * 7  # 7 days
PUBLIC_URL  = os.environ.get("DASHBOARD_PUBLIC_URL", "http://localhost:7080")
OAUTH_CALLBACK = f"{PUBLIC_URL}/auth/github/callback"
ACCESS_TOKEN   = os.environ.get("DASHBOARD_ACCESS_TOKEN", "")
DASH_PASSWORD  = os.environ.get("DASHBOARD_PASSWORD", "")

# Terminal Watch
TERMINAL_RELAY = OPENCLAW_ROOT / "scripts" / "terminal-relay.py"
TERMINAL_LOG   = LOGS_DIR / "terminal-watch.jsonl"
TERMINAL_PID   = LOGS_DIR / "terminal-relay.pid"

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="OpenClaw Dashboard")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

# ── Auth ──────────────────────────────────────────────────────────────────────
oauth_states = {}  # state -> expiry

def make_token(username: str) -> str:
    payload = {"sub": username, "exp": datetime.utcnow() + timedelta(minutes=JWT_EXPIRE)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

def verify_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        return payload.get("sub")
    except JWTError:
        return None

def is_localhost(request: Request) -> bool:
    return request.client and request.client.host in ("127.0.0.1", "::1")

def get_current_user(request: Request) -> str:
    token = request.cookies.get("oc_token") or request.headers.get("Authorization", "").removeprefix("Bearer ")
    if not token:
        if is_localhost(request):
            return "nayslayer"
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = verify_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user

@app.get("/auth/token")
async def token_login(t: str, response: Response):
    """Token-based login: /auth/token?t=ACCESS_TOKEN — sets JWT cookie and redirects home."""
    if not ACCESS_TOKEN or t != ACCESS_TOKEN:
        raise HTTPException(403, "Invalid access token")
    jwt_token = make_token("nayslayer")
    response = RedirectResponse("/", status_code=302)
    response.set_cookie("oc_token", jwt_token, max_age=JWT_EXPIRE * 60, httponly=True, samesite="lax")
    return response

@app.post("/auth/password")
async def password_login(request: Request):
    """Password login — checks DASHBOARD_PASSWORD, sets JWT cookie."""
    form = await request.form()
    pw = form.get("password", "")
    if not DASH_PASSWORD or pw != DASH_PASSWORD:
        return RedirectResponse("/login?error=Wrong+password", status_code=302)
    jwt_token = make_token("nayslayer")
    response = RedirectResponse("/", status_code=302)
    response.set_cookie("oc_token", jwt_token, max_age=JWT_EXPIRE * 60, httponly=True, samesite="lax")
    return response

# ── OAuth ─────────────────────────────────────────────────────────────────────
@app.get("/auth/github")
async def github_login():
    if not GITHUB_CLIENT_ID:
        raise HTTPException(400, "GitHub OAuth not configured. Set GITHUB_CLIENT_ID in dashboard/.env")
    state = secrets.token_urlsafe(16)
    oauth_states[state] = time.time() + 300
    url = (f"https://github.com/login/oauth/authorize"
           f"?client_id={GITHUB_CLIENT_ID}&scope=read:user&state={state}"
           f"&redirect_uri={OAUTH_CALLBACK}")
    return RedirectResponse(url)

@app.get("/auth/github/callback")
async def github_callback(code: str, state: str):
    if state not in oauth_states or oauth_states[state] < time.time():
        raise HTTPException(400, "Invalid OAuth state")
    del oauth_states[state]

    async with httpx.AsyncClient() as client:
        r = await client.post("https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={"client_id": GITHUB_CLIENT_ID, "client_secret": GITHUB_CLIENT_SECRET, "code": code})
        access_token = r.json().get("access_token")
        if not access_token:
            raise HTTPException(400, "GitHub OAuth failed")

        r2 = await client.get("https://api.github.com/user",
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"})
        github_user = r2.json().get("login", "")

    if github_user not in ALLOWED_GITHUB_USERS:
        raise HTTPException(403, f"GitHub user '{github_user}' is not allowed.")

    token = make_token(github_user)
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie("oc_token", token, httponly=True, samesite="lax", max_age=JWT_EXPIRE * 60)
    return response

@app.get("/auth/me")
async def me(user: str = Depends(get_current_user)):
    return {"user": user}

@app.post("/auth/logout")
async def logout():
    r = RedirectResponse(url="/login", status_code=302)
    r.delete_cookie("oc_token")
    return r

# ── Data helpers ──────────────────────────────────────────────────────────────
def read_contracts(limit=30):
    results = []
    if not BUILD_RESULTS.exists():
        return results
    for f in sorted(BUILD_RESULTS.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        try:
            d = json.loads(f.read_text())
            d["_file"] = f.name
            d["_mtime"] = f.stat().st_mtime
            results.append(d)
        except Exception:
            pass
    return results

def read_queue():
    items = []

    # Source 1: repo-queue/task-*.json (legacy build tasks)
    if QUEUE_DIR.exists():
        for f in sorted(QUEUE_DIR.glob("task-*.json"), key=lambda p: p.stat().st_mtime):
            try:
                d = json.loads(f.read_text())
                d["_file"] = f.name
                d.setdefault("_source", "build")
                task_id = d.get("task_id", "")
                if (BUILD_RESULTS / f"{task_id}.json").exists():
                    continue
                items.append(d)
            except Exception:
                pass

    # Source 2: queue/pending.json (Clawmpson operational tasks)
    if PENDING_JSON.exists():
        try:
            pending = json.loads(PENDING_JSON.read_text())
            for d in pending:
                d.setdefault("_source", "ops")
                d.setdefault("task_id", d.get("id", "unknown"))
                # Normalise display fields
                if "title" not in d and "goal" not in d:
                    d["goal"] = d.get("description", "")
                items.append(d)
        except Exception:
            pass

    return items

def phase2_progress():
    contracts = read_contracts(200)
    success = [c for c in contracts if c.get("status") == "success"]
    blocked = [c for c in contracts if c.get("status") == "blocked"]
    failed  = [c for c in contracts if c.get("status") == "failed"]
    total   = len(success)
    # Dynamic milestones: 10, 25, 50, 100, 250, 500, 1000...
    milestones = [10, 25, 50, 100, 250, 500, 1000]
    current_target = milestones[0]
    current_phase = 2
    for i, m in enumerate(milestones):
        if total >= m:
            current_phase = i + 3  # Phase 3 after 10, Phase 4 after 25, etc.
            current_target = milestones[i + 1] if i + 1 < len(milestones) else m * 2
        else:
            current_target = m
            break
    pct = min(100, int(total / current_target * 100)) if current_target > 0 else 100
    return {
        "done": total, "target": current_target, "pct": pct,
        "phase": current_phase, "blocked_count": len(blocked), "failed_count": len(failed),
    }

# ── API ───────────────────────────────────────────────────────────────────────
@app.get("/api/builds")
async def get_builds(user: str = Depends(get_current_user)):
    return read_contracts()

@app.get("/api/queue")
async def get_queue(user: str = Depends(get_current_user)):
    return read_queue()

@app.get("/api/progress")
async def get_progress(user: str = Depends(get_current_user)):
    return phase2_progress()

@app.get("/api/summary")
async def get_summary(user: str = Depends(get_current_user)):
    contracts = read_contracts(50)
    return {
        "total": len(contracts),
        "success": len([c for c in contracts if c.get("status") == "success"]),
        "blocked": len([c for c in contracts if c.get("status") == "blocked"]),
        "failed":  len([c for c in contracts if c.get("status") == "failed"]),
        "queue":   len(read_queue()),
        "phase2":  phase2_progress(),
    }

# ── SSE live feed ─────────────────────────────────────────────────────────────
async def event_stream(user: str) -> AsyncGenerator[str, None]:
    last_mtime = -1.0  # force push on first tick
    while True:
        try:
            contracts = read_contracts(30)
            latest = max((c.get("_mtime", 0) for c in contracts), default=0)
            if latest != last_mtime:
                last_mtime = latest
                queue = read_queue()
                payload = json.dumps({
                    "builds": contracts[:20],
                    "queue":  queue,
                    "summary": {
                        "total":   len(contracts),
                        "success": len([c for c in contracts if c.get("status") == "success"]),
                        "blocked": len([c for c in contracts if c.get("status") == "blocked"]),
                        "failed":  len([c for c in contracts if c.get("status") == "failed"]),
                        "queue":   len(queue),
                        "phase2":  phase2_progress(),
                    }
                })
                yield f"data: {payload}\n\n"
            else:
                yield ": heartbeat\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        await asyncio.sleep(3)

@app.get("/api/stream")
async def stream(request: Request):
    # Auth via cookie or query param token (for EventSource which can't set headers)
    token = request.cookies.get("oc_token") or request.query_params.get("token")
    if not token or not verify_token(token):
        if is_localhost(request):
            user = "nayslayer"
        else:
            raise HTTPException(401, "Not authenticated")
    else:
        user = verify_token(token)
    return StreamingResponse(event_stream(user),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

# ── Activity: real-time system introspection for Gunther narration ────────────
def _read_recent_log_events(limit=5):
    """Read most recent build-agent log events."""
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = LOGS_DIR / f"build-agent-{today}.jsonl"
    if not log_file.exists():
        return []
    lines = log_file.read_text().strip().splitlines()
    events = []
    for line in lines[-limit:]:
        try:
            events.append(json.loads(line))
        except Exception:
            pass
    return events

def _get_claude_sessions():
    """Count running Claude Code processes and extract working dirs."""
    try:
        result = subprocess.run(
            ["pgrep", "-afl", "claude.*--output-format"],
            capture_output=True, text=True, timeout=3
        )
        lines = [l for l in result.stdout.strip().splitlines() if l]
        sessions = []
        for line in lines:
            model = "opus" if "opus" in line else "sonnet" if "sonnet" in line else "default"
            sessions.append({"model": model})
        return sessions
    except Exception:
        return []

def _get_running_processes():
    """Check for notable processes (ollama, build agents, crons, etc)."""
    procs = []
    cron_labels = {
        "cron-idea-engine":    "idea engine",
        "cron-gig-scanner":    "gig scanner",
        "cron-bounty-scan":    "bounty scan",
        "cron-skill-upgrade":  "skill upgrade",
        "cron-autoresearch":   "autoresearch",
        "cron-self-improvement": "self-improvement",
        "cron-morning-brief":  "morning brief",
        "cron-nightly":        "nightly summary",
        "cron-intel-scan":     "intel scan",
        "run-daily-market-intel": "market intel",
    }
    try:
        result = subprocess.run(
            ["ps", "aux"], capture_output=True, text=True, timeout=3
        )
        for line in result.stdout.splitlines():
            if "ollama serve" in line:
                procs.append("ollama")
            elif "build-agent" in line or "build_agent" in line:
                procs.append("build-agent")
            elif "mirofish" in line:
                procs.append("mirofish")
            elif "uvicorn" in line and "server:app" in line:
                procs.append("dashboard-server")
            else:
                for script, label in cron_labels.items():
                    if script in line and label not in procs:
                        procs.append(label)
    except Exception:
        pass
    return list(set(procs))

def _get_recent_builds_activity():
    """Get the most recent build result with timing info."""
    if not BUILD_RESULTS.exists():
        return None
    files = sorted(BUILD_RESULTS.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None
    try:
        d = json.loads(files[0].read_text())
        d["_age_seconds"] = int(time.time() - files[0].stat().st_mtime)
        return {
            "task_id": d.get("task_id", files[0].stem),
            "status": d.get("status", "unknown"),
            "tests_passed": d.get("tests_passed"),
            "tests_run": d.get("tests_run"),
            "age_seconds": d["_age_seconds"],
            "changed_files": d.get("changed_files", []),
        }
    except Exception:
        return None

@app.get("/api/activity")
async def get_activity(user: str = Depends(get_current_user)):
    """System activity snapshot for Gunther's narration."""
    log_events = _read_recent_log_events(5)
    claude_sessions = _get_claude_sessions()
    running = _get_running_processes()
    last_build = _get_recent_builds_activity()
    queue = read_queue()

    # Health from ops log
    ops_today = LOGS_DIR / f"ops-{datetime.now().strftime('%Y-%m-%d')}.jsonl"
    health = {}
    if ops_today.exists():
        lines = ops_today.read_text().strip().splitlines()
        if lines:
            try:
                health = json.loads(lines[-1])
            except Exception:
                pass

    # Build rich task list: prefer title > goal > task_id
    def task_label(q):
        return q.get("title") or q.get("goal") or q.get("task_id","?")

    in_progress  = [q for q in queue if q.get("status") == "in_progress"]
    waiting      = [q for q in queue if q.get("status") == "waiting_on_jordan"]
    queued_items = [q for q in queue if q.get("status") not in ("in_progress","waiting_on_jordan")]

    return {
        "claude_sessions":    len(claude_sessions),
        "claude_models":      [s["model"] for s in claude_sessions],
        "processes":          running,
        "last_build":         last_build,
        "queue_depth":        len(queue),
        "pending_tasks":      [q.get("task_id", q.get("_file","?")) for q in queue[:5]],
        "pending_task_titles": [task_label(q) for q in queue[:6]],
        "in_progress_titles": [task_label(q) for q in in_progress[:3]],
        "waiting_titles":     [task_label(q) for q in waiting[:3]],
        "queued_titles":      [task_label(q) for q in queued_items[:3]],
        "in_progress_count":  len(in_progress),
        "waiting_count":      len(waiting),
        "log_events":         log_events,
        "disk_pct":           health.get("disk_pct"),
        "ollama_status":      health.get("ollama", "unknown"),
        "hour":               datetime.now().hour,
        "timestamp":          int(time.time()),
    }

# ── Claude Usage API ──────────────────────────────────────────────────────────
@app.get("/api/claude-usage")
async def get_claude_usage(user: str = Depends(get_current_user)):
    """Return Claude Code token usage for the current billing period."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("tracker",
            OPENCLAW_ROOT / "scripts" / "claude-usage-tracker.py")
        tracker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tracker)
        return tracker.get_usage()
    except Exception as e:
        return {"error": str(e)}

# ── Jordan Tasks API ──────────────────────────────────────────────────────────
def _update_pending_task(task_id: str, updates: dict):
    """Update a task in pending.json by ID."""
    if not PENDING_JSON.exists():
        return False
    pending = json.loads(PENDING_JSON.read_text())
    found = False
    for t in pending:
        if t.get("id") == task_id:
            t.update(updates)
            found = True
            break
    if found:
        PENDING_JSON.write_text(json.dumps(pending, indent=2))
    return found

@app.post("/api/jordan/done")
async def jordan_done(request: Request, user: str = Depends(get_current_user)):
    data = await request.json()
    task_id = data.get("task_id", "")
    if not task_id:
        raise HTTPException(400, "No task_id")
    # Move to completed
    if PENDING_JSON.exists():
        pending = json.loads(PENDING_JSON.read_text())
        task = None
        remaining = []
        for t in pending:
            if t.get("id") == task_id:
                task = t
            else:
                remaining.append(t)
        if task:
            task["status"] = "completed"
            task["completed_at"] = datetime.now().isoformat()
            PENDING_JSON.write_text(json.dumps(remaining, indent=2))
            # Append to completed.json
            completed_file = PENDING_JSON.parent / "completed.json"
            completed = []
            if completed_file.exists():
                try:
                    completed = json.loads(completed_file.read_text())
                except Exception:
                    completed = []
            completed.append(task)
            completed_file.write_text(json.dumps(completed, indent=2))
            return {"done": task_id}
    raise HTTPException(404, "Task not found")

@app.post("/api/jordan/snooze")
async def jordan_snooze(request: Request, user: str = Depends(get_current_user)):
    data = await request.json()
    task_id = data.get("task_id", "")
    if not task_id:
        raise HTTPException(400, "No task_id")
    success = _update_pending_task(task_id, {
        "status": "snoozed",
        "snoozed_at": datetime.now().isoformat(),
        "snooze_until": (datetime.now() + timedelta(hours=12)).isoformat(),
    })
    if success:
        return {"snoozed": task_id}
    raise HTTPException(404, "Task not found")

# ── Ideas API ─────────────────────────────────────────────────────────────────
def _ensure_ideas_dirs():
    IDEAS_DIR.mkdir(parents=True, exist_ok=True)
    IDEAS_MEDIA.mkdir(parents=True, exist_ok=True)

def _read_ideas():
    _ensure_ideas_dirs()
    ideas = []
    for f in sorted(IDEAS_DIR.glob("idea-*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            d = json.loads(f.read_text())
            d["_file"] = f.name
            ideas.append(d)
        except Exception:
            pass
    return ideas

@app.get("/api/ideas")
async def get_ideas(user: str = Depends(get_current_user)):
    return _read_ideas()

@app.post("/api/ideas")
async def create_idea(request: Request, user: str = Depends(get_current_user)):
    _ensure_ideas_dirs()
    data = await request.json()
    idea_id = f"idea-{datetime.now().strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(4)}"
    idea = {
        "id": idea_id,
        "title": data.get("title", "Untitled Idea"),
        "summary": data.get("summary", ""),
        "category": data.get("category", "product"),  # product | arbitrage | research
        "source": data.get("source", "manual"),  # manual | autoresearch | clawmpson
        "status": "pending",  # pending | approved | rejected | in_production
        "notes": [],
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }
    (IDEAS_DIR / f"{idea_id}.json").write_text(json.dumps(idea, indent=2))
    return idea

@app.patch("/api/ideas/{idea_id}")
async def update_idea(idea_id: str, request: Request, user: str = Depends(get_current_user)):
    idea_file = IDEAS_DIR / f"{idea_id}.json"
    if not idea_file.exists():
        raise HTTPException(404, "Idea not found")
    idea = json.loads(idea_file.read_text())
    data = await request.json()
    for key in ["status", "title", "summary", "category"]:
        if key in data:
            idea[key] = data[key]
    idea["updated_at"] = datetime.now().isoformat()
    idea_file.write_text(json.dumps(idea, indent=2))
    return idea

@app.post("/api/ideas/{idea_id}/notes")
async def add_note(idea_id: str, request: Request, user: str = Depends(get_current_user)):
    idea_file = IDEAS_DIR / f"{idea_id}.json"
    if not idea_file.exists():
        raise HTTPException(404, "Idea not found")
    idea = json.loads(idea_file.read_text())
    data = await request.json()
    note = {
        "id": secrets.token_hex(6),
        "text": data.get("text", ""),
        "images": data.get("images", []),  # list of media filenames
        "audio": data.get("audio", ""),     # media filename
        "created_at": datetime.now().isoformat(),
    }
    idea.setdefault("notes", []).append(note)
    idea["updated_at"] = datetime.now().isoformat()
    idea_file.write_text(json.dumps(idea, indent=2))
    return note

@app.post("/api/ideas/media")
async def upload_media(request: Request, user: str = Depends(get_current_user)):
    """Accept base64-encoded media (images, audio) and save to disk."""
    _ensure_ideas_dirs()
    data = await request.json()
    b64 = data.get("data", "")
    ext = data.get("ext", "webm")
    if not b64:
        raise HTTPException(400, "No data provided")
    filename = f"{secrets.token_hex(8)}.{ext}"
    file_bytes = base64.b64decode(b64)
    (IDEAS_MEDIA / filename).write_bytes(file_bytes)
    return {"filename": filename}

@app.get("/api/ideas/media/{filename}")
async def serve_media(filename: str, user: str = Depends(get_current_user)):
    fpath = IDEAS_MEDIA / filename
    if not fpath.exists():
        raise HTTPException(404, "File not found")
    ext = fpath.suffix.lower()
    mime_map = {
        ".webm": "audio/webm", ".ogg": "audio/ogg", ".mp3": "audio/mpeg",
        ".wav": "audio/wav", ".png": "image/png", ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp",
    }
    return FileResponse(fpath, media_type=mime_map.get(ext, "application/octet-stream"))

@app.post("/api/ideas/{idea_id}/push")
async def push_to_production(idea_id: str, request: Request, user: str = Depends(get_current_user)):
    """Approve idea → create project on Projects page → remove from Ideas Lab."""
    idea_file = IDEAS_DIR / f"{idea_id}.json"
    if not idea_file.exists():
        raise HTTPException(404, "Idea not found")
    idea = json.loads(idea_file.read_text())

    # Build notes context for Clawmpson
    notes_ctx = ""
    for n in idea.get("notes", []):
        if n.get("text"):
            notes_ctx += f"\n- {n['text']}"

    # Create project in projects.json
    PROJECTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    projects = []
    if PROJECTS_FILE.exists():
        try:
            projects = json.loads(PROJECTS_FILE.read_text())
        except Exception:
            projects = []

    project_id = idea['title'].lower().replace(' ', '-').replace('*', '')[:40]
    # Avoid duplicate project IDs
    existing_ids = {p.get("id") for p in projects}
    if project_id in existing_ids:
        project_id = f"{project_id}-{secrets.token_hex(3)}"

    project = {
        "id": project_id,
        "name": idea['title'],
        "tagline": (idea.get('summary', '') or '')[:120],
        "stage": "idea",
        "priority": "medium",
        "mrr": 0,
        "mrr_target": 0,
        "next_action": "Clawmpson: research and build action plan",
        "repo": None,
        "tags": [idea.get("category", "product")],
        "notes": notes_ctx.strip() if notes_ctx.strip() else idea.get("summary", ""),
        "source_idea": idea_id,
        "updated_at": datetime.now().strftime("%Y-%m-%d"),
    }
    projects.append(project)
    PROJECTS_FILE.write_text(json.dumps(projects, indent=2))

    # Create task in pending.json for Clawmpson to action
    pending_file = PENDING_JSON
    pending_file.parent.mkdir(parents=True, exist_ok=True)
    pending = []
    if pending_file.exists():
        try:
            pending = json.loads(pending_file.read_text())
        except Exception:
            pending = []

    task = {
        "id": f"idea-prod-{idea_id}",
        "title": f"[IDEA] {idea['title']}",
        "description": idea.get("summary", ""),
        "goal": f"Research and build action plan for: {idea['title']}. {idea.get('summary', '')}",
        "status": "queued",
        "priority": "high",
        "category": idea.get("category", "product"),
        "source_idea": idea_id,
        "agent": "Clawmpson",
        "jordan_notes": notes_ctx.strip() if notes_ctx.strip() else None,
        "added": datetime.now().strftime("%Y-%m-%d"),
        "output": f"outputs/idea-plan-{idea_id}.md",
    }
    pending.append(task)
    pending_file.write_text(json.dumps(pending, indent=2))

    # Remove idea from Ideas Lab — it now lives on the Projects page
    idea_file.unlink()

    return {"task_id": task["id"], "project_id": project_id, "idea_id": idea_id, "status": "pushed"}

@app.delete("/api/ideas/{idea_id}")
async def delete_idea(idea_id: str, user: str = Depends(get_current_user)):
    idea_file = IDEAS_DIR / f"{idea_id}.json"
    if not idea_file.exists():
        raise HTTPException(404, "Idea not found")
    idea_file.unlink()
    return {"deleted": idea_id}

@app.post("/api/ideas/generate")
async def generate_ideas(user: str = Depends(get_current_user)):
    """Trigger the idea engine cron to generate a new batch of ideas."""
    pending = [f for f in IDEAS_DIR.glob("idea-*.json")
               if json.loads(f.read_text()).get("status") == "pending"]
    if len(pending) >= 100:
        return {"status": "at_cap", "active": len(pending), "cap": 100,
                "message": f"{len(pending)} pending ideas — review some first"}
    if len(pending) >= 50:
        return {"status": "throttled", "active": len(pending), "cap": 100,
                "message": f"{len(pending)} pending ideas — Clawmpson is throttled. Review/approve/DQ to open space"}
    script = OPENCLAW_ROOT / "scripts" / "cron-idea-engine.sh"
    if script.exists():
        subprocess.Popen(["bash", str(script)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"status": "generating", "message": "Idea engine started — check back in ~20 min"}
    return {"status": "error", "message": "cron-idea-engine.sh not found"}

# ── Projects API ──────────────────────────────────────────────────────────────
def _read_projects():
    if not PROJECTS_FILE.exists():
        return []
    try:
        projects = json.loads(PROJECTS_FILE.read_text())
    except Exception:
        return []

    # Build a map of latest build result per repo name
    build_map = {}
    if BUILD_RESULTS.exists():
        for f in sorted(BUILD_RESULTS.glob("*.json"), key=lambda p: p.stat().st_mtime):
            try:
                d = json.loads(f.read_text())
                repo = d.get("repo", "")
                if repo:
                    key = Path(repo).name.lower()
                    build_map[key] = {
                        "task_id": d.get("task_id", f.stem),
                        "status": d.get("status", "unknown"),
                        "tests_passed": d.get("tests_passed"),
                        "tests_run": d.get("tests_run"),
                        "age_seconds": int(time.time() - f.stat().st_mtime),
                    }
            except Exception:
                pass

    for p in projects:
        repo = p.get("repo") or ""
        if repo:
            key = Path(repo).name.lower()
            if key in build_map:
                p["last_build"] = build_map[key]

    return projects

@app.get("/api/projects")
async def get_projects(user: str = Depends(get_current_user)):
    return _read_projects()

@app.patch("/api/projects/{project_id}")
async def update_project(project_id: str, request: Request, user: str = Depends(get_current_user)):
    if not PROJECTS_FILE.exists():
        raise HTTPException(404, "Projects file not found")
    projects = json.loads(PROJECTS_FILE.read_text())
    data = await request.json()
    found = False
    for p in projects:
        if p.get("id") == project_id:
            for key in ["name", "tagline", "stage", "mrr", "mrr_target", "priority",
                        "next_action", "notes", "repo", "tags"]:
                if key in data:
                    p[key] = data[key]
            p["updated_at"] = datetime.now().strftime("%Y-%m-%d")
            found = True
            break
    if not found:
        raise HTTPException(404, "Project not found")
    PROJECTS_FILE.write_text(json.dumps(projects, indent=2))
    return {"updated": project_id}

AGENTS_STATE_FILE = OPENCLAW_ROOT / "agents" / "agent-state.json"
AGENT_CONFIGS_DIR = OPENCLAW_ROOT / "agents" / "configs"

AGENT_REGISTRY = [
    {"id": "orchestrator", "codename": "AXIS",  "role": "Chief Orchestrator", "model": "qwen3:32b",        "icon": "⬡"},
    {"id": "research",     "codename": "SCOUT", "role": "Research Agent",      "model": "qwen3:30b",        "icon": "◉"},
    {"id": "build",        "codename": "FORGE", "role": "Build Agent",          "model": "claude-opus-4-6",  "icon": "◈"},
    {"id": "ops",          "codename": "VIGIL", "role": "Ops Agent",            "model": "qwen2.5:7b",       "icon": "◎"},
    {"id": "marketing",    "codename": "WAVE",  "role": "Marketing Agent",      "model": "qwen3:30b",        "icon": "◐"},
    {"id": "support",      "codename": "SHORE", "role": "Support Agent",        "model": "qwen3:30b",        "icon": "◑"},
    {"id": "memory-librarian", "codename": "VAULT", "role": "Memory Librarian", "model": "llama3.3:70b",    "icon": "▣"},
]

def _agent_last_activity(agent_id: str) -> dict:
    """Read last log entry for an agent."""
    log_dir = LOGS_DIR
    today = datetime.now().strftime("%Y-%m-%d")
    pattern = f"{agent_id}-{today}.jsonl"
    log_file = log_dir / pattern
    last_task = None
    last_time = None
    if log_file.exists():
        lines = [l.strip() for l in log_file.read_text().splitlines() if l.strip()]
        if lines:
            try:
                entry = json.loads(lines[-1])
                last_task = entry.get("task") or entry.get("event") or entry.get("summary")
                last_time = entry.get("timestamp") or entry.get("ts")
            except Exception:
                last_task = lines[-1][:80]
    return {"last_task": last_task, "last_seen": last_time}

def _read_agent_state() -> dict:
    if AGENTS_STATE_FILE.exists():
        try:
            return json.loads(AGENTS_STATE_FILE.read_text())
        except Exception:
            pass
    return {}

@app.get("/api/agents")
async def get_agents(user: str = Depends(get_current_user)):
    state = _read_agent_state()
    result = []
    for ag in AGENT_REGISTRY:
        aid = ag["id"]
        activity = _agent_last_activity(aid)
        agent_state = state.get(aid, {})
        result.append({
            **ag,
            "status":      agent_state.get("status", "idle"),
            "current_task": agent_state.get("current_task"),
            "workflow":    agent_state.get("workflow"),
            "progress":    agent_state.get("progress"),
            "last_task":   activity["last_task"],
            "last_seen":   activity["last_seen"],
            "tasks_today": agent_state.get("tasks_today", 0),
            "errors_today": agent_state.get("errors_today", 0),
        })
    return result

@app.patch("/api/agents/{agent_id}")
async def update_agent_state(agent_id: str, request: Request, user: str = Depends(get_current_user)):
    """Let agents report their own status — called by cron scripts."""
    data = await request.json()
    state = _read_agent_state()
    if agent_id not in state:
        state[agent_id] = {}
    state[agent_id].update(data)
    state[agent_id]["updated_at"] = datetime.now().isoformat()
    AGENTS_STATE_FILE.parent.mkdir(exist_ok=True)
    AGENTS_STATE_FILE.write_text(json.dumps(state, indent=2))
    return {"updated": agent_id}

# ── Serve PWA ─────────────────────────────────────────────────────────────────
@app.get("/manifest.json")
async def manifest():
    return Response((Path(__file__).parent / "manifest.json").read_text(), media_type="application/json")

@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return (Path(__file__).parent / "login.html").read_text()

_trading_version = 0  # bumped on each trade change

@app.post("/api/trading/notify")
async def trading_notify():
    """Called by simulator to signal a trade was placed or closed."""
    global _trading_version
    _trading_version += 1
    _trading_cache["data"] = None  # invalidate cache on trade events
    return {"version": _trading_version}

@app.get("/api/trading/stream")
async def trading_stream(request: Request):
    """SSE stream that fires when trades change."""
    last_seen = 0
    async def event_gen():
        nonlocal last_seen
        while True:
            if await request.is_disconnected():
                break
            if _trading_version > last_seen:
                last_seen = _trading_version
                yield f"data: {json.dumps({'version': _trading_version})}\n\n"
            await asyncio.sleep(2)
    return StreamingResponse(event_gen(), media_type="text/event-stream")

@app.get("/api/trading")
async def get_trading(user: str = Depends(get_current_user)):
    """Return trading bot data — signals, positions, P&L."""
    trading_file = OPENCLAW_ROOT / "trading" / "dashboard.json"
    if trading_file.exists():
        try:
            return json.loads(trading_file.read_text())
        except Exception:
            pass
    return {"portfolio": {"open_positions": 0, "total_pnl": 0, "positions": []}, "recent_signals": [], "history": []}


# ── Trading Dashboard (comprehensive) ────────────────────────────────────────
import sqlite3

def _trading_db():
    db_path = Path.home() / ".openclaw" / "clawmson.db"
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn

_trading_cache = {"data": None, "ts": 0}

@app.get("/api/trading/dashboard")
async def get_trading_dashboard(user: str = Depends(get_current_user)):
    """Comprehensive trading dashboard data for the TRADING tab. Cached 5s."""
    now = time.time()
    if _trading_cache["data"] and (now - _trading_cache["ts"]) < 5:
        return _trading_cache["data"]

    conn = _trading_db()
    if not conn:
        return {"error": "Database not found"}
    try:
        # 1. Wallet state
        starting = 1000.0
        ctx = conn.execute("SELECT value FROM context WHERE chat_id='mirofish' AND key='starting_balance'").fetchone()
        if ctx:
            starting = float(ctx[0])

        closed_pnl = conn.execute("SELECT COALESCE(SUM(pnl), 0) as total FROM paper_trades WHERE status IN ('closed_win','closed_loss','expired')").fetchone()[0]
        open_trades = conn.execute("SELECT * FROM paper_trades WHERE status='open' ORDER BY opened_at DESC").fetchall()

        # Mark-to-market open positions
        unrealized = 0.0
        open_list = []
        for t in open_trades:
            latest = conn.execute("SELECT yes_price, no_price FROM market_data WHERE market_id=? ORDER BY fetched_at DESC LIMIT 1", (t["market_id"],)).fetchone()
            current_price = t["entry_price"]
            if latest:
                current_price = latest["yes_price"] if t["direction"] == "YES" else latest["no_price"]
                if current_price is None:
                    current_price = t["entry_price"]
            pnl = t["shares"] * (current_price - t["entry_price"])
            pnl_pct = (pnl / t["amount_usd"] * 100) if t["amount_usd"] > 0 else 0
            unrealized += pnl
            # Look up close_time from kalshi_markets or market_data
            close_time = None
            km = conn.execute("SELECT close_time FROM kalshi_markets WHERE ticker=? ORDER BY fetched_at DESC LIMIT 1", (t["market_id"],)).fetchone()
            if km and km["close_time"]:
                close_time = km["close_time"]
            else:
                md = conn.execute("SELECT end_date FROM market_data WHERE market_id=? ORDER BY fetched_at DESC LIMIT 1", (t["market_id"],)).fetchone()
                if md and md["end_date"]:
                    close_time = md["end_date"]
            open_list.append({
                "id": t["id"], "market_id": t["market_id"],
                "question": t["question"][:80], "direction": t["direction"],
                "strategy": t["strategy"], "entry_price": t["entry_price"],
                "current_price": current_price, "shares": t["shares"],
                "amount_usd": t["amount_usd"], "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 1), "confidence": t["confidence"],
                "opened_at": t["opened_at"], "close_time": close_time,
            })

        balance = starting + closed_pnl + unrealized
        roi_pct = ((balance - starting) / starting * 100) if starting > 0 else 0

        # 2. Closed trades (recent 50)
        recent_closed = conn.execute("""
            SELECT id, market_id, question, direction, strategy, entry_price,
                   exit_price, shares, amount_usd, pnl, status, confidence,
                   opened_at, closed_at
            FROM paper_trades WHERE status IN ('closed_win','closed_loss','expired')
            ORDER BY closed_at DESC LIMIT 50
        """).fetchall()
        closed_list = [dict(r) for r in recent_closed]

        # 3. Daily P&L curve
        daily_pnl = conn.execute("SELECT date, balance, roi_pct, win_rate FROM daily_pnl ORDER BY date ASC").fetchall()
        pnl_curve = [{"date": r["date"], "balance": r["balance"], "roi_pct": r["roi_pct"], "win_rate": r["win_rate"]} for r in daily_pnl]

        # 4. Win/loss stats
        all_closed = conn.execute("SELECT status, strategy, pnl FROM paper_trades WHERE status IN ('closed_win','closed_loss','expired')").fetchall()
        total_closed = len(all_closed)
        wins = sum(1 for t in all_closed if t["status"] == "closed_win")
        win_rate = wins / total_closed if total_closed > 0 else 0

        # Per-strategy breakdown
        strat_map = {}
        for t in all_closed:
            s = t["strategy"]
            if s not in strat_map:
                strat_map[s] = {"wins": 0, "losses": 0, "pnl": 0}
            if t["status"] == "closed_win":
                strat_map[s]["wins"] += 1
            else:
                strat_map[s]["losses"] += 1
            strat_map[s]["pnl"] += t["pnl"] or 0

        strategy_breakdown = [
            {"strategy": k, "wins": v["wins"], "losses": v["losses"],
             "total": v["wins"] + v["losses"], "pnl": round(v["pnl"], 2),
             "win_rate": round(v["wins"] / (v["wins"] + v["losses"]) * 100, 1) if (v["wins"] + v["losses"]) > 0 else 0}
            for k, v in strat_map.items()
        ]
        strategy_breakdown.sort(key=lambda x: x["pnl"], reverse=True)

        # 5. Strategy tournament (from strategy_stats)
        tournament = []
        try:
            strat_stats = conn.execute("""
                SELECT ss.* FROM strategy_stats ss
                INNER JOIN (SELECT strategy, MAX(snapshot_date) as latest FROM strategy_stats GROUP BY strategy) l
                ON ss.strategy = l.strategy AND ss.snapshot_date = l.latest
            """).fetchall()
            tournament = [dict(r) for r in strat_stats]
        except Exception:
            pass

        # 6. Polymarket markets (latest)
        poly_markets = conn.execute("""
            SELECT md.market_id, md.question, md.category, md.yes_price, md.no_price, md.volume
            FROM market_data md
            INNER JOIN (SELECT market_id, MAX(fetched_at) as latest FROM market_data GROUP BY market_id) l
            ON md.market_id = l.market_id AND md.fetched_at = l.latest
            ORDER BY md.volume DESC LIMIT 30
        """).fetchall()
        poly_list = [dict(r) for r in poly_markets]

        # 7. Kalshi markets (latest)
        kalshi_list = []
        try:
            kalshi_markets = conn.execute("""
                SELECT km.ticker, km.title, km.category, km.yes_bid, km.yes_ask,
                       km.no_bid, km.no_ask, km.last_price, km.volume_24h, km.status
                FROM kalshi_markets km
                INNER JOIN (SELECT ticker, MAX(fetched_at) as latest FROM kalshi_markets GROUP BY ticker) l
                ON km.ticker = l.ticker AND km.fetched_at = l.latest
                ORDER BY km.volume_24h DESC LIMIT 30
            """).fetchall()
            kalshi_list = [dict(r) for r in kalshi_markets]
        except Exception:
            pass

        # 8. Cross-venue arb trades
        xv_arb = []
        try:
            xv_rows = conn.execute("SELECT * FROM cross_venue_arb_trades ORDER BY detected_at DESC LIMIT 20").fetchall()
            xv_arb = [dict(r) for r in xv_rows]
        except Exception:
            pass

        # 9. Graduation status
        from statistics import mean, stdev
        grad = {"has_min_history": False, "roi_7d_pass": False, "win_rate_pass": False, "sharpe_pass": False, "drawdown_pass": False, "all_pass": False}
        if len(daily_pnl) >= 7:
            grad["has_min_history"] = True
            last7 = [r["roi_pct"] for r in daily_pnl[-7:] if r["roi_pct"] is not None]
            grad["roi_7d_pass"] = sum(last7) > 0
            grad["win_rate_pass"] = win_rate >= 0.55
            returns = [r["roi_pct"] for r in daily_pnl if r["roi_pct"] is not None]
            if len(returns) >= 7:
                s = stdev(returns)
                sharpe = mean(returns) / s if s > 0 else 0
                grad["sharpe_pass"] = sharpe >= 1.0
            balances = [r["balance"] for r in daily_pnl]
            peak = balances[0]
            max_dd = 0
            for b_val in balances:
                peak = max(peak, b_val)
                dd = (peak - b_val) / peak if peak > 0 else 0
                max_dd = max(max_dd, dd)
            grad["drawdown_pass"] = max_dd < 0.25
            grad["all_pass"] = all([grad["roi_7d_pass"], grad["win_rate_pass"], grad["sharpe_pass"], grad["drawdown_pass"]])

        # 10. PhantomClaw stats (RivalClaw strategy running inside Clawmpson)
        phantom_stats = {"trades": 0, "wins": 0, "losses": 0, "pnl": 0, "open": 0, "positions": []}
        try:
            phantom_closed = conn.execute("""
                SELECT COUNT(*) as n,
                       SUM(CASE WHEN status='closed_win' THEN 1 ELSE 0 END) as w,
                       COALESCE(SUM(pnl), 0) as p
                FROM paper_trades WHERE strategy LIKE 'phantomclaw%' AND status IN ('closed_win','closed_loss','expired')
            """).fetchone()
            phantom_open = conn.execute("""
                SELECT id, market_id, question, direction, entry_price, amount_usd, confidence, opened_at, strategy
                FROM paper_trades WHERE strategy LIKE 'phantomclaw%' AND status='open'
                ORDER BY opened_at DESC
            """).fetchall()
            # Get close_time for each
            phantom_positions = []
            for po in phantom_open:
                pdict = dict(po)
                km = conn.execute("SELECT close_time FROM kalshi_markets WHERE ticker=? ORDER BY fetched_at DESC LIMIT 1", (po["market_id"],)).fetchone()
                pdict["close_time"] = km["close_time"] if km and km["close_time"] else None
                # Mark to market
                latest_k = conn.execute("SELECT yes_bid, no_bid FROM kalshi_markets WHERE ticker=? ORDER BY fetched_at DESC LIMIT 1", (po["market_id"],)).fetchone()
                ep = po["entry_price"] or 0.01
                cp = ep  # default
                if latest_k:
                    raw_cp = latest_k["yes_bid"] if po["direction"] == "YES" else latest_k["no_bid"]
                    if raw_cp is not None:
                        cp = raw_cp / 100.0 if raw_cp > 1 else raw_cp
                pdict["current_price"] = cp
                pdict["pnl"] = round((cp - ep) * (po["amount_usd"] / ep) if ep > 0 else 0, 2)
                amt = po["amount_usd"] or 1
                pdict["pnl_pct"] = round(pdict["pnl"] / amt * 100, 1) if amt > 0 else 0
                phantom_positions.append(pdict)

            pc_n = phantom_closed["n"] or 0
            pc_w = phantom_closed["w"] or 0
            pc_p = phantom_closed["p"] or 0
            phantom_stats = {
                "trades": pc_n,
                "wins": pc_w,
                "losses": pc_n - pc_w,
                "pnl": round(pc_p, 2),
                "open": len(phantom_open),
                "win_rate": round(pc_w / pc_n * 100, 1) if pc_n > 0 else 0,
                "positions": phantom_positions,
            }
        except Exception as phantom_err:
            phantom_stats["error"] = str(phantom_err)

        # 10b. Per-agent stats for CalendarClaw, NewsClaw, SentimentClaw
        agent_stats = {}
        for agent_name in ("calendarclaw", "newsclaw", "sentimentclaw", "dataharvester"):
            try:
                ac = conn.execute("""
                    SELECT COUNT(*) as n,
                           SUM(CASE WHEN status='closed_win' THEN 1 ELSE 0 END) as w,
                           COALESCE(SUM(pnl), 0) as p
                    FROM paper_trades WHERE strategy=? AND status IN ('closed_win','closed_loss','expired')
                """, (agent_name,)).fetchone()
                ao = conn.execute("""
                    SELECT id, market_id, question, direction, entry_price, shares, amount_usd, opened_at
                    FROM paper_trades WHERE strategy=? AND status='open' ORDER BY opened_at DESC
                """, (agent_name,)).fetchall()
                positions = []
                agent_unrealized = 0.0
                for po in ao:
                    pd = dict(po)
                    # Mark-to-market: get current price from kalshi_markets or market_data
                    current_price = po["entry_price"]
                    km = conn.execute("SELECT yes_ask, no_ask, yes_bid, no_bid, close_time FROM kalshi_markets WHERE ticker=? ORDER BY fetched_at DESC LIMIT 1", (po["market_id"],)).fetchone()
                    if km:
                        pd["close_time"] = km["close_time"] if km["close_time"] else None
                        if po["direction"] == "YES":
                            current_price = km["yes_bid"] or km["yes_ask"] or po["entry_price"]
                        else:
                            current_price = km["no_bid"] or km["no_ask"] or po["entry_price"]
                    else:
                        # Try polymarket market_data
                        md = conn.execute("SELECT yes_price, no_price, end_date FROM market_data WHERE market_id=? ORDER BY fetched_at DESC LIMIT 1", (po["market_id"],)).fetchone()
                        if md:
                            pd["close_time"] = md["end_date"] if md["end_date"] else None
                            current_price = md["yes_price"] if po["direction"] == "YES" else md["no_price"]
                        else:
                            pd["close_time"] = None
                    pnl = (po["shares"] or 0) * (current_price - po["entry_price"])
                    pd["pnl"] = round(pnl, 2)
                    pd["current_price"] = current_price
                    agent_unrealized += pnl
                    positions.append(pd)
                n = ac["n"] or 0
                w = ac["w"] or 0
                realized = ac["p"] or 0
                agent_stats[agent_name] = {
                    "trades": n, "wins": w, "losses": n - w,
                    "pnl": round(realized + agent_unrealized, 2),
                    "open": len(ao),
                    "win_rate": round(w / n * 100, 1) if n > 0 else 0,
                    "positions": positions,
                }
            except Exception:
                agent_stats[agent_name] = {"trades": 0, "wins": 0, "losses": 0, "pnl": 0, "open": 0, "win_rate": 0, "positions": []}

        # 10c. RivalClaw open positions (separate DB) for unified feed
        rivalclaw_positions = []
        try:
            rc_db = Path.home() / "rivalclaw" / "rivalclaw.db"
            if rc_db.exists():
                rc_conn = sqlite3.connect(str(rc_db))
                rc_conn.row_factory = sqlite3.Row
                rc_open = rc_conn.execute("""
                    SELECT market_id, question, direction, strategy, entry_price, amount_usd,
                           confidence, opened_at, pnl
                    FROM paper_trades WHERE status='open' ORDER BY opened_at DESC
                """).fetchall()
                for ro in rc_open:
                    rd = dict(ro)
                    # Try to get close_time from rivalclaw's kalshi data or our kalshi_markets
                    km = conn.execute("SELECT close_time FROM kalshi_markets WHERE ticker=? ORDER BY fetched_at DESC LIMIT 1", (ro["market_id"],)).fetchone()
                    rd["close_time"] = km["close_time"] if km and km["close_time"] else None
                    rd["current_price"] = ro["entry_price"]
                    rivalclaw_positions.append(rd)
                rc_conn.close()
        except Exception:
            pass

        # 10d. QuantumentalClaw positions (separate DB)
        quantclaw_data = {"wallet": {}, "positions": []}
        try:
            qc_db = Path.home() / "quantumentalclaw" / "quantumentalclaw.db"
            if qc_db.exists():
                qc_conn = sqlite3.connect(str(qc_db))
                qc_conn.row_factory = sqlite3.Row
                quantclaw_data = _quantumentalclaw_state(qc_conn)
                qc_conn.close()
        except Exception as qe:
            quantclaw_data["error"] = str(qe)

        # 11. Missed opportunities summary
        missed_summary = []
        try:
            missed = conn.execute("""
                SELECT strategy, COUNT(*) as total,
                       SUM(CASE WHEN counterfactual_pnl > 0 THEN 1 ELSE 0 END) as would_win,
                       COALESCE(SUM(counterfactual_pnl), 0) as total_cf_pnl
                FROM missed_opportunities WHERE status='resolved'
                GROUP BY strategy
            """).fetchall()
            missed_summary = [dict(r) for r in missed]
        except Exception:
            pass

        result = {
            "wallet": {
                "balance": round(balance, 2),
                "starting_balance": starting,
                "roi_pct": round(roi_pct, 2),
                "unrealized_pnl": round(unrealized, 2),
                "realized_pnl": round(closed_pnl, 2),
                "total_trades": total_closed,
                "wins": wins,
                "win_rate": round(win_rate * 100, 1),
                "open_positions": len(open_list),
            },
            "graduation": grad,
            "open_positions": open_list,
            "recent_trades": closed_list,
            "pnl_curve": pnl_curve,
            "strategy_breakdown": strategy_breakdown,
            "tournament": tournament,
            "polymarket": poly_list,
            "kalshi": kalshi_list,
            "cross_venue_arb": xv_arb,
            "phantom": phantom_stats,
            "agents": agent_stats,
            "rivalclaw_positions": rivalclaw_positions,
            "quantclaw": quantclaw_data,
            "missed_opportunities": missed_summary,
        }
        _trading_cache["data"] = result
        _trading_cache["ts"] = time.time()
        return result
    finally:
        conn.close()


# ── ArbClaw / RivalClaw Experiment ────────────────────────────────────────────

def _experiment_db(instance):
    """Open SQLite DB for an experiment instance (arbclaw, rivalclaw, or quantumentalclaw)."""
    paths = {
        "arbclaw": Path.home() / "arbclaw" / "arbclaw.db",
        "rivalclaw": Path.home() / "rivalclaw" / "rivalclaw.db",
        "quantumentalclaw": Path.home() / "quantumentalclaw" / "quantumentalclaw.db",
    }
    db_path = paths.get(instance)
    if not db_path or not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _arbclaw_state(conn):
    """Read ArbClaw wallet state (different schema: positions/trades tables)."""
    starting = 1000.0
    total_pnl = conn.execute("SELECT COALESCE(SUM(pnl), 0) FROM trades").fetchone()[0]
    locked = conn.execute("SELECT COALESCE(SUM(amount_usd), 0) FROM positions WHERE status='open'").fetchone()[0]
    balance = starting + total_pnl - locked

    open_pos = conn.execute("SELECT * FROM positions WHERE status='open' ORDER BY opened_at DESC").fetchall()
    open_list = []
    for p in open_pos:
        latest = conn.execute(
            "SELECT yes_price, no_price FROM market_snapshots WHERE market_id=? ORDER BY fetched_at DESC LIMIT 1",
            (p["market_id"],)
        ).fetchone()
        current = p["entry_price"]
        if latest:
            current = latest["yes_price"] if p["direction"] == "YES" else latest["no_price"]
        pnl = (current - p["entry_price"]) * p["shares"] if p["shares"] else 0
        pnl_pct = (pnl / p["amount_usd"] * 100) if p["amount_usd"] and p["amount_usd"] > 0 else 0
        open_list.append({
            "market_id": p["market_id"], "question": (p["question"] or "")[:80],
            "direction": p["direction"], "entry_price": p["entry_price"],
            "current_price": current, "amount_usd": p["amount_usd"],
            "pnl": round(pnl, 2), "pnl_pct": round(pnl_pct, 1),
            "latency_ms": p["signal_to_trade_latency_ms"] or 0,
            "opened_at": p["opened_at"],
        })

    recent = conn.execute(
        "SELECT * FROM trades ORDER BY closed_at DESC LIMIT 20"
    ).fetchall()
    recent_list = [{
        "market_id": r["market_id"], "direction": r["direction"],
        "entry_price": r["entry_price"], "exit_price": r["exit_price"],
        "pnl": round(r["pnl"] or 0, 2),
        "latency_ms": r["signal_to_trade_latency_ms"] or 0,
        "opened_at": r["opened_at"], "closed_at": r["closed_at"],
    } for r in recent]

    total_trades = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    wins = conn.execute("SELECT COUNT(*) FROM trades WHERE pnl > 0").fetchone()[0]
    avg_latency = conn.execute("SELECT AVG(signal_to_trade_latency_ms) FROM trades WHERE signal_to_trade_latency_ms > 0").fetchone()[0]

    # Daily PnL curve
    daily = conn.execute("SELECT date, balance FROM daily_pnl ORDER BY date ASC").fetchall()
    pnl_curve = [{"date": r["date"], "balance": r["balance"]} for r in daily]

    return {
        "instance": "arbclaw",
        "wallet": {
            "balance": round(balance, 2), "starting_balance": starting,
            "total_pnl": round(total_pnl, 2),
            "total_trades": total_trades, "wins": wins,
            "win_rate": round(wins / total_trades * 100, 1) if total_trades > 0 else 0,
            "open_positions": len(open_list),
            "avg_latency_ms": round(avg_latency or 0, 1),
        },
        "open_positions": open_list,
        "recent_trades": recent_list,
        "pnl_curve": pnl_curve,
    }


def _rivalclaw_state(conn):
    """Read RivalClaw wallet state (Mirofish-compatible schema)."""
    starting = 1000.0
    ctx = conn.execute("SELECT value FROM context WHERE chat_id='rivalclaw' AND key='starting_balance'").fetchone()
    if ctx:
        starting = float(ctx[0])

    closed_pnl = conn.execute("SELECT COALESCE(SUM(pnl), 0) FROM paper_trades WHERE status IN ('closed_win','closed_loss','expired')").fetchone()[0]
    open_trades = conn.execute("SELECT * FROM paper_trades WHERE status='open' ORDER BY opened_at DESC").fetchall()

    unrealized = 0.0
    open_list = []
    for t in open_trades:
        latest = conn.execute(
            "SELECT yes_price, no_price FROM market_data WHERE market_id=? ORDER BY fetched_at DESC LIMIT 1",
            (t["market_id"],)
        ).fetchone()
        current = t["entry_price"]
        if latest:
            current = latest["yes_price"] if t["direction"] == "YES" else latest["no_price"]
            if current is None:
                current = t["entry_price"]
        pnl = t["shares"] * (current - t["entry_price"])
        pnl_pct = (pnl / t["amount_usd"] * 100) if t["amount_usd"] > 0 else 0
        unrealized += pnl
        open_list.append({
            "market_id": t["market_id"], "question": (t["question"] or "")[:80],
            "direction": t["direction"], "strategy": t["strategy"],
            "entry_price": t["entry_price"], "current_price": current,
            "amount_usd": t["amount_usd"], "pnl": round(pnl, 2), "pnl_pct": round(pnl_pct, 1),
            "latency_ms": t["signal_to_trade_latency_ms"] or 0,
            "opened_at": t["opened_at"],
        })

    balance = starting + closed_pnl + unrealized

    recent = conn.execute(
        "SELECT * FROM paper_trades WHERE status IN ('closed_win','closed_loss','expired') ORDER BY closed_at DESC LIMIT 20"
    ).fetchall()
    recent_list = [{
        "market_id": r["market_id"], "direction": r["direction"],
        "entry_price": r["entry_price"], "exit_price": r["exit_price"],
        "pnl": round(r["pnl"] or 0, 2), "status": r["status"],
        "latency_ms": r["signal_to_trade_latency_ms"] or 0,
        "opened_at": r["opened_at"], "closed_at": r["closed_at"],
    } for r in recent]

    all_closed = conn.execute("SELECT status, pnl FROM paper_trades WHERE status IN ('closed_win','closed_loss','expired')").fetchall()
    total_closed = len(all_closed)
    wins = sum(1 for t in all_closed if t["status"] == "closed_win")

    avg_latency = conn.execute(
        "SELECT AVG(signal_to_trade_latency_ms) FROM paper_trades WHERE signal_to_trade_latency_ms > 0"
    ).fetchone()[0]

    # Cycle metrics
    cycle_metrics = []
    try:
        rows = conn.execute(
            "SELECT * FROM cycle_metrics ORDER BY id DESC LIMIT 20"
        ).fetchall()
        cycle_metrics = [dict(r) for r in rows]
    except Exception:
        pass

    # Daily PnL curve
    daily = conn.execute("SELECT date, balance, roi_pct FROM daily_pnl ORDER BY date ASC").fetchall()
    pnl_curve = [{"date": r["date"], "balance": r["balance"], "roi_pct": r["roi_pct"]} for r in daily]

    return {
        "instance": "rivalclaw",
        "wallet": {
            "balance": round(balance, 2), "starting_balance": starting,
            "total_pnl": round(closed_pnl, 2),
            "unrealized_pnl": round(unrealized, 2),
            "total_trades": total_closed, "wins": wins,
            "win_rate": round(wins / total_closed * 100, 1) if total_closed > 0 else 0,
            "open_positions": len(open_list),
            "avg_latency_ms": round(avg_latency or 0, 1),
        },
        "open_positions": open_list,
        "recent_trades": recent_list,
        "pnl_curve": pnl_curve,
        "cycle_metrics": cycle_metrics,
    }


def _quantumentalclaw_state(conn):
    """Read QuantumentalClaw state — signal fusion engine with learning loop."""
    starting = 10000.0
    ctx = conn.execute("SELECT value FROM context WHERE key='starting_balance'").fetchone()
    if ctx:
        starting = float(ctx[0])

    # Closed trades PnL
    closed_pnl = 0.0
    try:
        closed_pnl = conn.execute(
            "SELECT COALESCE(SUM(pnl_usd), 0) FROM paper_trades WHERE status IN ('closed_win','closed_loss','expired')"
        ).fetchone()[0]
    except Exception:
        pass

    # Open positions
    open_trades = conn.execute(
        "SELECT pt.*, td.event_id, td.venue, td.ticker, td.direction, td.final_score, "
        "td.confidence, td.amount_usd as decision_amount, td.signal_snapshot, td.reasoning "
        "FROM paper_trades pt "
        "JOIN trade_decisions td ON pt.decision_id = td.decision_id "
        "WHERE pt.status='open' ORDER BY pt.executed_at DESC"
    ).fetchall()

    unrealized = 0.0
    open_list = []
    for t in open_trades:
        entry = t["fill_price"]
        current = entry  # No live price tracking yet; will improve
        pnl = t["fill_shares"] * (current - entry)
        pnl_pct = (pnl / t["fill_amount_usd"] * 100) if t["fill_amount_usd"] > 0 else 0
        unrealized += pnl

        # Parse signal snapshot
        snapshot = {}
        try:
            snapshot = json.loads(t["signal_snapshot"]) if t["signal_snapshot"] else {}
        except Exception:
            pass

        open_list.append({
            "event_id": t["event_id"], "venue": t["venue"],
            "ticker": t["ticker"], "direction": t["direction"],
            "entry_price": entry, "current_price": current,
            "amount_usd": t["fill_amount_usd"],
            "final_score": t["final_score"], "confidence": t["confidence"],
            "signal_scores": snapshot,
            "pnl": round(pnl, 2), "pnl_pct": round(pnl_pct, 1),
            "reasoning": t["reasoning"] or "",
            "opened_at": t["executed_at"],
        })

    balance = starting + closed_pnl + unrealized

    # Recent closed trades
    recent = conn.execute(
        "SELECT pt.*, td.event_id, td.venue, td.ticker, td.direction, td.final_score, td.signal_snapshot "
        "FROM paper_trades pt "
        "JOIN trade_decisions td ON pt.decision_id = td.decision_id "
        "WHERE pt.status IN ('closed_win','closed_loss','expired') "
        "ORDER BY pt.exit_at DESC LIMIT 20"
    ).fetchall()
    recent_list = []
    for r in recent:
        recent_list.append({
            "event_id": r["event_id"], "venue": r["venue"],
            "ticker": r["ticker"], "direction": r["direction"],
            "entry_price": r["fill_price"], "exit_price": r["exit_price"],
            "pnl": round(r["pnl_usd"] or 0, 2), "status": r["status"],
            "final_score": r["final_score"],
            "opened_at": r["executed_at"], "closed_at": r["exit_at"],
        })

    # Stats
    all_closed = conn.execute(
        "SELECT status, pnl_usd FROM paper_trades WHERE status IN ('closed_win','closed_loss','expired')"
    ).fetchall()
    total_closed = len(all_closed)
    wins = sum(1 for t in all_closed if t["status"] == "closed_win")

    # Cycle count
    cycle_count = 0
    try:
        cc = conn.execute("SELECT value FROM context WHERE key='cycle_count'").fetchone()
        if cc:
            cycle_count = int(cc[0])
    except Exception:
        pass

    # Signal weight history (learning evolution)
    weight_history = []
    try:
        rows = conn.execute("SELECT * FROM weight_log ORDER BY logged_at DESC LIMIT 20").fetchall()
        weight_history = [dict(r) for r in rows]
    except Exception:
        pass

    # Module accuracy
    module_stats = []
    try:
        rows = conn.execute(
            "SELECT module, accuracy, total_signals, avg_score FROM module_accuracy "
            "ORDER BY computed_at DESC LIMIT 10"
        ).fetchall()
        module_stats = [dict(r) for r in rows]
    except Exception:
        pass

    # Daily PnL curve
    pnl_curve = []
    try:
        daily = conn.execute("SELECT date, ending_balance, realized_pnl FROM daily_pnl ORDER BY date ASC").fetchall()
        pnl_curve = [{"date": r["date"], "balance": r["ending_balance"], "pnl": r["realized_pnl"]} for r in daily]
    except Exception:
        pass

    return {
        "instance": "quantumentalclaw",
        "wallet": {
            "balance": round(balance, 2), "starting_balance": starting,
            "total_pnl": round(closed_pnl, 2),
            "unrealized_pnl": round(unrealized, 2),
            "total_trades": total_closed, "wins": wins,
            "win_rate": round(wins / total_closed * 100, 1) if total_closed > 0 else 0,
            "open_positions": len(open_list),
            "cycles_completed": cycle_count,
        },
        "open_positions": open_list,
        "recent_trades": recent_list,
        "pnl_curve": pnl_curve,
        "weight_history": weight_history,
        "module_accuracy": module_stats,
    }


@app.get("/api/trading/experiment")
async def get_experiment_dashboard(user: str = Depends(get_current_user)):
    """Four-way experiment dashboard: ArbClaw + RivalClaw + QuantumentalClaw."""
    result = {"arbclaw": None, "rivalclaw": None, "quantumentalclaw": None}
    for instance in ("arbclaw", "rivalclaw", "quantumentalclaw"):
        conn = _experiment_db(instance)
        if not conn:
            continue
        try:
            if instance == "arbclaw":
                result[instance] = _arbclaw_state(conn)
            elif instance == "rivalclaw":
                result[instance] = _rivalclaw_state(conn)
            else:
                result[instance] = _quantumentalclaw_state(conn)
        except Exception as e:
            result[instance] = {"error": str(e)}
        finally:
            conn.close()
    return result


# ── Terminal Watch ────────────────────────────────────────────────────────────

@app.get("/api/terminal/sessions")
async def terminal_sessions(user: str = Depends(get_current_user)):
    """List available tmux sessions and panes."""
    try:
        r = subprocess.run(["tmux", "list-sessions", "-F", "#{session_name}:#{session_windows}"],
                          capture_output=True, text=True, timeout=3)
        if r.returncode != 0:
            return {"sessions": []}
        sessions = []
        for line in r.stdout.strip().splitlines():
            if ":" not in line: continue
            name, windows = line.rsplit(":", 1)
            pr = subprocess.run(["tmux", "list-panes", "-t", name, "-F",
                "#{pane_index}:#{pane_id}:#{pane_current_command}:#{pane_current_path}"],
                capture_output=True, text=True, timeout=3)
            panes = []
            if pr.returncode == 0:
                for pl in pr.stdout.strip().splitlines():
                    parts = pl.split(":", 3)
                    if len(parts) >= 4:
                        panes.append({"index": int(parts[0]), "id": parts[1],
                                      "command": parts[2], "cwd": parts[3]})
            sessions.append({"name": name, "windows": int(windows), "panes": panes})
        return {"sessions": sessions}
    except Exception:
        return {"sessions": []}

@app.post("/api/terminal/start")
async def terminal_start(request: Request, user: str = Depends(get_current_user)):
    """Start relay on a tmux session/pane."""
    data = await request.json()
    session = data.get("session")
    if not session: raise HTTPException(400, "Missing 'session'")
    pane = data.get("pane")
    if TERMINAL_PID.exists():
        try:
            pid = int(TERMINAL_PID.read_text().strip())
            os.kill(pid, 0)
            return {"status": "already_running", "pid": pid}
        except (ProcessLookupError, ValueError):
            TERMINAL_PID.unlink(missing_ok=True)
    cmd = [sys.executable, str(TERMINAL_RELAY), "--session", session]
    if pane is not None: cmd.extend(["--pane", str(pane)])
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(10):
        time.sleep(0.2)
        if TERMINAL_PID.exists():
            return {"status": "started", "pid": int(TERMINAL_PID.read_text().strip()),
                    "session": session, "pane": pane}
    return {"status": "started", "session": session, "pane": pane}

@app.post("/api/terminal/stop")
async def terminal_stop(user: str = Depends(get_current_user)):
    """Stop the relay."""
    if not TERMINAL_PID.exists(): return {"status": "not_running"}
    try:
        pid = int(TERMINAL_PID.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        TERMINAL_PID.unlink(missing_ok=True)
        return {"status": "stopped", "pid": pid}
    except ProcessLookupError:
        TERMINAL_PID.unlink(missing_ok=True)
        return {"status": "not_running", "note": "stale PID cleaned"}

@app.get("/api/terminal/status")
async def terminal_status(user: str = Depends(get_current_user)):
    """Relay status check."""
    running, pid = False, None
    if TERMINAL_PID.exists():
        try:
            pid = int(TERMINAL_PID.read_text().strip())
            os.kill(pid, 0); running = True
        except (ProcessLookupError, ValueError):
            TERMINAL_PID.unlink(missing_ok=True); pid = None
    event_count = sum(1 for _ in open(TERMINAL_LOG)) if TERMINAL_LOG.exists() else 0
    return {"running": running, "pid": pid, "event_count": event_count}

@app.get("/api/terminal/events")
async def terminal_events(n: int = 20, errors_only: bool = False,
                          user: str = Depends(get_current_user)):
    """Last N events from JSONL log."""
    if not TERMINAL_LOG.exists(): return {"events": []}
    events = []
    for line in reversed(TERMINAL_LOG.read_text().strip().splitlines()):
        try:
            ev = json.loads(line)
            if errors_only and ev.get("event_type") not in ("error", "build_failure", "test_failure"):
                continue
            events.append(ev)
            if len(events) >= n: break
        except Exception: pass
    return {"events": events}

@app.get("/api/terminal/stream")
async def terminal_stream(request: Request):
    """SSE stream of new terminal events."""
    token = request.cookies.get("oc_token") or request.query_params.get("token")
    if not token or not verify_token(token):
        if not is_localhost(request): raise HTTPException(401, "Not authenticated")
    async def event_gen():
        last_count = sum(1 for _ in open(TERMINAL_LOG)) if TERMINAL_LOG.exists() else 0
        while True:
            if await request.is_disconnected(): break
            try:
                if TERMINAL_LOG.exists():
                    lines = TERMINAL_LOG.read_text().strip().splitlines()
                    if len(lines) > last_count:
                        new_events = []
                        for line in lines[last_count:]:
                            try: new_events.append(json.loads(line))
                            except Exception: pass
                        if new_events:
                            yield f"data: {json.dumps({'events': new_events})}\n\n"
                        last_count = len(lines)
                    else:
                        yield ": heartbeat\n\n"
                else:
                    yield ": heartbeat\n\n"
            except Exception:
                yield ": heartbeat\n\n"
            await asyncio.sleep(2)
    return StreamingResponse(event_gen(), media_type="text/event-stream",
                            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.post("/api/terminal/snapshot")
async def terminal_snapshot(user: str = Depends(get_current_user)):
    """Trigger manual snapshot."""
    if not TERMINAL_PID.exists(): raise HTTPException(400, "Relay not running")
    try:
        pid = int(TERMINAL_PID.read_text().strip()); os.kill(pid, 0)
    except (ProcessLookupError, ValueError):
        raise HTTPException(400, "Relay not running")
    trigger = LOGS_DIR / "terminal-snapshot-trigger"
    trigger.write_text(datetime.now().isoformat())
    pre_count = sum(1 for _ in open(TERMINAL_LOG)) if TERMINAL_LOG.exists() else 0
    for _ in range(15):
        time.sleep(0.2)
        if TERMINAL_LOG.exists() and sum(1 for _ in open(TERMINAL_LOG)) > pre_count:
            return json.loads(TERMINAL_LOG.read_text().strip().splitlines()[-1])
    return {"status": "snapshot_requested", "note": "check events shortly"}

def _build_packet(event=None):
    cwd = event.get("cwd", str(OPENCLAW_ROOT)) if event else str(OPENCLAW_ROOT)
    recent = []
    if TERMINAL_LOG.exists():
        for line in reversed(TERMINAL_LOG.read_text().strip().splitlines()[-20:]):
            try:
                ev = json.loads(line)
                if ev.get("command"): recent.append(ev["command"])
                if len(recent) >= 5: break
            except Exception: pass
    try:
        br = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                           capture_output=True, text=True, cwd=cwd, timeout=3)
        branch = br.stdout.strip() if br.returncode == 0 else "unknown"
    except Exception: branch = "unknown"
    try:
        dr = subprocess.run(["git", "diff", "--stat"], capture_output=True, text=True, cwd=cwd, timeout=5)
        diff_stat = dr.stdout.strip() if dr.returncode == 0 else ""
    except Exception: diff_stat = ""
    try:
        fr = subprocess.run(["git", "diff", "--name-only"], capture_output=True, text=True, cwd=cwd, timeout=5)
        changed = [f for f in fr.stdout.strip().splitlines() if f] if fr.returncode == 0 else []
    except Exception: changed = []
    return {
        "context": {"repo": Path(cwd).name, "branch": branch, "cwd": cwd,
                    "session": event.get("session", "") if event else "",
                    "recent_commands": recent, "git_diff_stat": diff_stat, "changed_files": changed},
        "event": {"type": event.get("event_type", "") if event else "",
                 "command": event.get("command", "") if event else "",
                 "exit_code": event.get("exit_code") if event else None,
                 "output_tail": event.get("output_tail", []) if event else [],
                 "duration_ms": event.get("duration_ms") if event else None},
        "question": "Explain what failed and suggest a fix."
    }

@app.post("/api/terminal/packet")
async def terminal_packet(request: Request, user: str = Depends(get_current_user)):
    """Build analysis packet from last or specified event."""
    data = await request.json() if request.headers.get("content-type") == "application/json" else {}
    event = None
    if TERMINAL_LOG.exists():
        lines = TERMINAL_LOG.read_text().strip().splitlines()
        event_id = data.get("event_id")
        if event_id:
            for line in reversed(lines):
                try:
                    ev = json.loads(line)
                    if ev.get("timestamp") == event_id: event = ev; break
                except Exception: pass
        elif lines:
            try: event = json.loads(lines[-1])
            except Exception: pass
    if not event: raise HTTPException(404, "No events found")
    return _build_packet(event)

@app.get("/api/terminal/packet/preview")
async def terminal_packet_preview(user: str = Depends(get_current_user)):
    """Preview packet from most recent event."""
    event = None
    if TERMINAL_LOG.exists():
        lines = TERMINAL_LOG.read_text().strip().splitlines()
        if lines:
            try: event = json.loads(lines[-1])
            except Exception: pass
    if not event: return {"packet": None, "note": "No events available"}
    return {"packet": _build_packet(event)}


# ── GitHub Intel ──────────────────────────────────────────────────────────────
INTEL_DIR        = OPENCLAW_ROOT / "autoresearch" / "github-intel"
INTEL_RECS       = INTEL_DIR / "recommendations.json"
INTEL_ARCHIVE    = INTEL_DIR / "archive.json"
INTEL_CRAWL_SCRIPT = OPENCLAW_ROOT / "scripts" / "github-intel-cron.sh"

def _read_intel_recs() -> dict:
    if INTEL_RECS.exists():
        try:
            return json.loads(INTEL_RECS.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"crawl_date": "", "analyzed_at": "", "model": "", "total_analyzed": 0, "recommendations": []}

def _write_intel_recs(data: dict):
    INTEL_DIR.mkdir(parents=True, exist_ok=True)
    INTEL_RECS.write_text(json.dumps(data, indent=2), encoding="utf-8")

def _read_intel_archive() -> list:
    """Read the rejection/review archive. Repos are NEVER deleted — rejected ones live here."""
    if INTEL_ARCHIVE.exists():
        try:
            return json.loads(INTEL_ARCHIVE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []

def _write_intel_archive(archive: list):
    INTEL_DIR.mkdir(parents=True, exist_ok=True)
    INTEL_ARCHIVE.write_text(json.dumps(archive, indent=2), encoding="utf-8")

@app.get("/api/intel")
async def intel_list(sort: str = "composite", user: str = Depends(get_current_user)):
    """Latest recommendations with flexible sorting.
    Sort options: composite, integration_value, signal_score, complexity, stars,
                  clawmpson_relevance, arbclaw_relevance, rivalclaw_relevance, recency, value_per_complexity
    """
    data = _read_intel_recs()
    recs = data.get("recommendations", [])
    sort_desc = True
    if sort == "composite":
        # Weighted composite: integration_value*3 + signal_score*2 + max_relevance - complexity*0.5
        def composite(r):
            max_rel = max(r.get("clawmpson_relevance", 0), r.get("arbclaw_relevance", 0), r.get("rivalclaw_relevance", 0))
            return r.get("integration_value", 0) * 3 + r.get("signal_score", 0) * 2 + max_rel - r.get("complexity", 0) * 0.5
        recs.sort(key=composite, reverse=True)
    elif sort == "value_per_complexity":
        # Best bang for buck: high value, low complexity
        recs.sort(key=lambda r: (r.get("integration_value", 0) / max(r.get("complexity", 1), 1)), reverse=True)
    elif sort == "complexity":
        # Low complexity first (easiest to integrate)
        recs.sort(key=lambda r: r.get("complexity", 10))
        sort_desc = False
    elif sort == "recency":
        recs.sort(key=lambda r: r.get("last_updated", "") or "", reverse=True)
    elif sort in ("integration_value", "signal_score", "stars", "clawmpson_relevance", "arbclaw_relevance", "rivalclaw_relevance"):
        recs.sort(key=lambda r: r.get(sort, 0), reverse=True)
    else:
        recs.sort(key=lambda r: r.get("integration_value", 0), reverse=True)
    return {
        "crawl_date": data.get("crawl_date", ""),
        "analyzed_at": data.get("analyzed_at", ""),
        "model": data.get("model", ""),
        "total_analyzed": data.get("total_analyzed", 0),
        "recommendations": recs,
    }

@app.get("/api/intel/history")
async def intel_history(user: str = Depends(get_current_user)):
    """List past crawl dates from archived files."""
    history = []
    if INTEL_DIR.exists():
        for f in sorted(INTEL_DIR.glob("recommendations*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                history.append({
                    "file": f.name,
                    "crawl_date": d.get("crawl_date", ""),
                    "analyzed_at": d.get("analyzed_at", ""),
                    "count": d.get("total_analyzed", 0),
                })
            except Exception:
                pass
    return history

@app.get("/api/intel/repo/{rec_id}")
async def intel_repo_detail(rec_id: str, user: str = Depends(get_current_user)):
    """Full detail for one recommendation."""
    data = _read_intel_recs()
    for rec in data.get("recommendations", []):
        if rec.get("id") == rec_id:
            return rec
    raise HTTPException(404, "Recommendation not found")

@app.post("/api/intel/approve")
async def intel_approve(request: Request, user: str = Depends(get_current_user)):
    """Approve recommendation and dispatch to queue."""
    body = await request.json()
    rec_id = body.get("id", "")
    targets = body.get("targets", [])
    notes = body.get("notes", "")

    valid_targets = {"clawmpson", "arbclaw", "rivalclaw"}
    targets = [t for t in targets if t in valid_targets]
    if not targets:
        raise HTTPException(400, "At least one target bot required")

    data = _read_intel_recs()
    rec = None
    for r in data.get("recommendations", []):
        if r.get("id") == rec_id:
            rec = r
            break
    if not rec:
        raise HTTPException(404, "Recommendation not found")

    # Update recommendation
    task_id = f"intel-{str(uuid.uuid4())[:8]}"
    rec["status"] = "approved"
    rec["approved_for"] = targets
    rec["approved_at"] = datetime.now().isoformat()
    rec["task_id"] = task_id
    _write_intel_recs(data)

    # Create task in pending.json
    task = {
        "id": task_id,
        "type": "github-intel-integration",
        "title": f"Integrate {rec.get('what_to_take', 'patterns')[:80]} from {rec.get('repo_name', 'unknown')}",
        "description": f"LLM verdict: {rec.get('verdict', 'STUDY')}. {rec.get('what_to_take', '')} Risk: {rec.get('risk', 'none')}. {notes}".strip(),
        "source_repo": rec.get("repo_url", ""),
        "targets": targets,
        "priority": "medium",
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "approved_by": user,
        "recommendation_id": rec_id,
    }

    pending = []
    if PENDING_JSON.exists():
        try:
            pending = json.loads(PENDING_JSON.read_text(encoding="utf-8"))
        except Exception:
            pending = []
    pending.append(task)
    PENDING_JSON.write_text(json.dumps(pending, indent=2), encoding="utf-8")

    return {"ok": True, "task_id": task_id, "targets": targets}

@app.post("/api/intel/reject")
async def intel_reject(request: Request, user: str = Depends(get_current_user)):
    """Reject a recommendation — marks as rejected AND copies to archive. Repos are NEVER deleted."""
    body = await request.json()
    rec_id = body.get("id", "")
    reason = body.get("reason", "")

    data = _read_intel_recs()
    for r in data.get("recommendations", []):
        if r.get("id") == rec_id:
            r["status"] = "rejected"
            r["rejected_at"] = datetime.now().isoformat()
            r["rejected_by"] = user
            if reason:
                r["reject_reason"] = reason
            _write_intel_recs(data)
            # Also copy to archive (repos are NEVER deleted, even on reject)
            archive = _read_intel_archive()
            # Avoid duplicates in archive by ID
            if not any(a.get("id") == rec_id for a in archive):
                archive.append({**r, "archived_at": datetime.now().isoformat()})
            else:
                # Update existing archive entry
                for i, a in enumerate(archive):
                    if a.get("id") == rec_id:
                        archive[i] = {**r, "archived_at": datetime.now().isoformat()}
                        break
            _write_intel_archive(archive)
            return {"ok": True}
    raise HTTPException(404, "Recommendation not found")

@app.get("/api/intel/archive")
async def intel_archive_list(user: str = Depends(get_current_user)):
    """View all archived (rejected) repos — nothing is ever deleted."""
    return _read_intel_archive()

@app.post("/api/intel/bookmark")
async def intel_bookmark(request: Request, user: str = Depends(get_current_user)):
    """Bookmark for later review."""
    body = await request.json()
    rec_id = body.get("id", "")

    data = _read_intel_recs()
    for r in data.get("recommendations", []):
        if r.get("id") == rec_id:
            r["status"] = "bookmarked"
            _write_intel_recs(data)
            return {"ok": True}
    raise HTTPException(404, "Recommendation not found")

@app.post("/api/intel/run-crawl")
async def intel_run_crawl(user: str = Depends(get_current_user)):
    """Trigger crawl + analysis manually (fire-and-forget)."""
    if not INTEL_CRAWL_SCRIPT.exists():
        raise HTTPException(500, "Crawl script not found")
    subprocess.Popen(
        ["/bin/bash", str(INTEL_CRAWL_SCRIPT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return {"ok": True, "message": "Crawl started in background"}

@app.get("/api/intel/stream")
async def intel_stream(request: Request):
    """SSE stream for new recommendations."""
    token = request.cookies.get("oc_token") or request.query_params.get("token")
    if not token or not verify_token(token):
        if not is_localhost(request):
            raise HTTPException(401, "Not authenticated")

    async def event_gen():
        last_mtime = 0.0
        while True:
            try:
                if INTEL_RECS.exists():
                    mtime = INTEL_RECS.stat().st_mtime
                    if mtime != last_mtime:
                        last_mtime = mtime
                        data = _read_intel_recs()
                        payload = json.dumps({
                            "total": data.get("total_analyzed", 0),
                            "pending": len([r for r in data.get("recommendations", []) if r.get("status") == "pending"]),
                            "analyzed_at": data.get("analyzed_at", ""),
                        })
                        yield f"data: {payload}\n\n"
                    else:
                        yield ": heartbeat\n\n"
                else:
                    yield ": heartbeat\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            await asyncio.sleep(5)

    return StreamingResponse(event_gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.get("/api/intel/stats")
async def intel_stats(user: str = Depends(get_current_user)):
    """Aggregate stats."""
    data = _read_intel_recs()
    recs = data.get("recommendations", [])
    archive = _read_intel_archive()
    stats = {"total": len(recs), "total_library": data.get("total_library", len(recs)),
             "pending": 0, "approved": 0, "rejected": 0, "bookmarked": 0,
             "integrate": 0, "study": 0, "skip": 0, "archived": len(archive)}
    for r in recs:
        s = r.get("status", "pending")
        if s in stats:
            stats[s] += 1
        v = r.get("verdict", "").lower()
        if v in stats:
            stats[v] += 1
    stats["crawl_date"] = data.get("crawl_date", "")
    stats["analyzed_at"] = data.get("analyzed_at", "")
    return stats


# ── Crawler Signal Bus ────────────────────────────────────────────────────────
SIGNALS_DIR = OPENCLAW_ROOT / "autoresearch" / "signals"

SIGNAL_PLATFORMS = [
    "github", "polymarket", "kalshi", "reddit", "x", "discord", "telegram",
    "stocktwits", "tradingview", "seekingalpha", "unusualwhales",
    "linkedin", "facebook", "instagram", "tiktok", "moltbook",
]

def _read_signal(platform: str) -> dict:
    f = SIGNALS_DIR / f"{platform}.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"platform": platform, "signals": [], "meta": {"total_signals": 0}}

@app.get("/api/intel/signals")
async def signals_all(user: str = Depends(get_current_user)):
    """All platforms, latest signals combined."""
    combined = []
    for p in SIGNAL_PLATFORMS:
        data = _read_signal(p)
        for s in data.get("signals", []):
            s["_platform"] = p
            combined.append(s)
    combined.sort(key=lambda s: s.get("extracted_at", ""), reverse=True)
    return {"platforms": SIGNAL_PLATFORMS, "signals": combined[:200], "total": len(combined)}

@app.get("/api/intel/signals/{platform}")
async def signals_platform(platform: str, user: str = Depends(get_current_user)):
    """Signals for one platform."""
    if platform not in SIGNAL_PLATFORMS:
        raise HTTPException(404, f"Unknown platform: {platform}")
    return _read_signal(platform)

@app.get("/api/intel/signals/{platform}/history")
async def signals_history(platform: str, user: str = Depends(get_current_user)):
    """Historical signal counts from SQLite if available."""
    # Check crawler's local DB
    crawler_db = OPENCLAW_ROOT / "crawlers" / f"openclaw-{platform}-crawler" / "data" / "signals.db"
    if not crawler_db.exists():
        crawler_db = OPENCLAW_ROOT / "crawlers" / f"openclaw-{platform}-feed" / "data" / "signals.db"
    if not crawler_db.exists():
        return {"platform": platform, "history": [], "total": 0}
    try:
        import sqlite3 as _sql
        conn = _sql.connect(str(crawler_db))
        rows = conn.execute(
            "SELECT date(extracted_at) as d, COUNT(*) as c FROM signals WHERE platform=? GROUP BY d ORDER BY d DESC LIMIT 30",
            (platform,)
        ).fetchall()
        conn.close()
        return {"platform": platform, "history": [{"date": r[0], "count": r[1]} for r in rows], "total": sum(r[1] for r in rows)}
    except Exception:
        return {"platform": platform, "history": [], "total": 0}

@app.get("/api/intel/signals/overview/stats")
async def signals_stats(user: str = Depends(get_current_user)):
    """Cross-platform signal stats."""
    stats = {}
    total = 0
    for p in SIGNAL_PLATFORMS:
        data = _read_signal(p)
        count = len(data.get("signals", []))
        stats[p] = {"count": count, "crawled_at": data.get("crawled_at", "")}
        total += count
    return {"platforms": stats, "total_signals": total, "active_platforms": sum(1 for v in stats.values() if v["count"] > 0)}

@app.get("/api/intel/signals/stream/live")
async def signals_stream(request: Request):
    """SSE for real-time signal updates across all platforms."""
    token = request.cookies.get("oc_token") or request.query_params.get("token")
    if not token or not verify_token(token):
        if not is_localhost(request):
            raise HTTPException(401, "Not authenticated")

    async def event_gen():
        last_mtimes = {}
        while True:
            try:
                changed = []
                for p in SIGNAL_PLATFORMS:
                    f = SIGNALS_DIR / f"{p}.json"
                    if f.exists():
                        mt = f.stat().st_mtime
                        if mt != last_mtimes.get(p, 0):
                            last_mtimes[p] = mt
                            changed.append(p)
                if changed:
                    payload = json.dumps({"updated": changed, "ts": datetime.now().isoformat()})
                    yield f"data: {payload}\n\n"
                else:
                    yield ": heartbeat\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            await asyncio.sleep(5)

    return StreamingResponse(event_gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/{path:path}")
async def spa(path: str, request: Request):
    # Let API routes through
    if path.startswith("api/") or path.startswith("auth/"):
        raise HTTPException(404)
    # Check auth — localhost skips OAuth
    token = request.cookies.get("oc_token")
    if not token or not verify_token(token):
        if not is_localhost(request):
            return RedirectResponse(url="/login")
    html = (Path(__file__).parent / "index.html").read_text()
    return HTMLResponse(content=html, headers={
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=7080, reload=False)
