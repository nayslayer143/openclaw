#!/usr/bin/env python3
"""
OpenClaw Dashboard — FastAPI backend
Real-time task monitor with GitHub OAuth
"""
import os, json, asyncio, secrets, time, hashlib, subprocess, re, uuid, base64, signal, sys
import pty, fcntl, termios, struct, select
from pathlib import Path
from typing import AsyncGenerator, Optional
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Request, Response, HTTPException, Depends, UploadFile, File, Form, WebSocket, Body
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
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


PROJECTS_FILE  = OPENCLAW_ROOT / "projects" / "projects.json"
CHATGPT_REPORTS_DIR = OPENCLAW_ROOT / "outputs" / "chatgpt-reports"
STRATEGY_CATALOG   = Path(__file__).parent / "strategy-catalog.json"
REPO_MAN_API = os.environ.get("REPO_MAN_API", "https://research.asdfghjk.lol")

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
# GZip is set to a very high minimum so it effectively never triggers.
# Starlette's GZipMiddleware buffers the first `minimum_size` bytes of ANY
# response to decide whether to compress, which catastrophically breaks SSE:
# the /api/gonzoclaw/*/stream proxy delivers tokens live but gzip holds them
# in its buffer until the stream ends. Cloudflare's edge handles compression
# for all remote clients anyway (asdfghjk.lol via cloudflared), so local
# gzip is redundant. Raising this threshold keeps the middleware registered
# in case something depends on it, without actually compressing anything.
app.add_middleware(GZipMiddleware, minimum_size=10_000_000)
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

_trading_cache = {"data": None, "ts": 0}

@app.get("/api/trading/dashboard")
async def get_trading_dashboard(user: str = Depends(get_current_user)):
    """Trading dashboard: RivalClaw + QuantumentalClaw. Cached 5s."""
    now = time.time()
    if _trading_cache["data"] and (now - _trading_cache["ts"]) < 5:
        return _trading_cache["data"]

    # RivalClaw state
    rc_state = None
    rivalclaw_positions = []
    try:
        rc_db = Path.home() / "rivalclaw" / "rivalclaw.db"
        if rc_db.exists():
            rc_conn = sqlite3.connect(str(rc_db))
            rc_conn.row_factory = sqlite3.Row
            rc_state = _rivalclaw_state(rc_conn)
            # Also build rivalclaw_positions for unified feed with close_time
            rc_open = rc_conn.execute("""
                SELECT market_id, question, direction, strategy, entry_price, amount_usd,
                       confidence, opened_at, pnl
                FROM paper_trades WHERE status='open' ORDER BY opened_at DESC
            """).fetchall()
            for ro in rc_open:
                rd = dict(ro)
                # Try to get close_time from rivalclaw's own kalshi_markets table
                try:
                    km = rc_conn.execute("SELECT close_time FROM kalshi_markets WHERE ticker=? ORDER BY fetched_at DESC LIMIT 1", (ro["market_id"],)).fetchone()
                    rd["close_time"] = km["close_time"] if km and km["close_time"] else None
                except Exception:
                    rd["close_time"] = None
                rd["current_price"] = ro["entry_price"]
                rivalclaw_positions.append(rd)
            rc_conn.close()
    except Exception:
        pass

    # QuantumentalClaw state
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

    # Aggregated wallet from both systems
    rc_w = rc_state["wallet"] if rc_state else {}
    qc_w = quantclaw_data.get("wallet", {})
    agg_balance = rc_w.get("balance", 0) + qc_w.get("balance", 0)
    agg_starting = rc_w.get("starting_balance", 0) + qc_w.get("starting_balance", 0)
    agg_trades = rc_w.get("total_trades", 0) + qc_w.get("total_trades", 0)
    agg_wins = rc_w.get("wins", 0) + qc_w.get("wins", 0)
    agg_unrealized = rc_w.get("unrealized_pnl", 0) + qc_w.get("unrealized_pnl", 0)
    agg_realized = rc_w.get("total_pnl", 0) + qc_w.get("total_pnl", 0)
    agg_open = rc_w.get("open_positions", 0) + qc_w.get("open_positions", 0)

    pnl_curve = rc_state.get("pnl_curve", []) if rc_state else []

    result = {
        "wallet": {
            "balance": round(agg_balance, 2),
            "starting_balance": round(agg_starting, 2),
            "roi_pct": round(((agg_balance - agg_starting) / agg_starting * 100) if agg_starting > 0 else 0, 2),
            "unrealized_pnl": round(agg_unrealized, 2),
            "realized_pnl": round(agg_realized, 2),
            "total_trades": agg_trades,
            "wins": agg_wins,
            "win_rate": round(agg_wins / agg_trades * 100, 1) if agg_trades > 0 else 0,
            "open_positions": agg_open,
        },
        "pnl_curve": pnl_curve,
        "rivalclaw_positions": rivalclaw_positions,
        "quantclaw": quantclaw_data,
    }
    _trading_cache["data"] = result
    _trading_cache["ts"] = time.time()
    return result


# ── RivalClaw / QuantumentalClaw Experiment ───────────────────────────────────

def _experiment_db(instance):
    """Open SQLite DB for an experiment instance (rivalclaw or quantumentalclaw)."""
    paths = {
        "rivalclaw": Path.home() / "rivalclaw" / "rivalclaw.db",
        "quantumentalclaw": Path.home() / "quantumentalclaw" / "quantumentalclaw.db",
    }
    db_path = paths.get(instance)
    if not db_path or not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


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
    """Read QuantumentalClaw state — protocol events engine (primary) with legacy fallback."""
    starting = 10000.0
    ctx = conn.execute("SELECT value FROM context WHERE key='starting_balance'").fetchone()
    if ctx:
        starting = float(ctx[0])

    closed_pnl = 0.0
    total_closed = 0
    wins = 0
    recent_list = []
    open_list = []
    unrealized = 0.0
    balance = starting
    used_protocol = False

    # Primary: read from protocol_events.db (the live trading engine)
    proto_db = Path.home() / "quantumentalclaw" / "protocol_events.db"
    if proto_db.exists():
        try:
            pconn = sqlite3.connect(str(proto_db))
            pconn.row_factory = sqlite3.Row

            # Check if there are any events at all
            evt_count = pconn.execute("SELECT COUNT(*) FROM protocol_events").fetchone()[0]
            if evt_count > 0:

                # Current balance from latest wallet event
                bal_row = pconn.execute(
                    "SELECT json_extract(payload, '$.balance_after') as bal "
                    "FROM protocol_events WHERE event_type IN ('wallet_credit','wallet_debit') "
                    "ORDER BY timestamp_ms DESC LIMIT 1"
                ).fetchone()

                # Closed trades from trade_close events
                closed_rows = pconn.execute(
                    "SELECT contract_id, "
                    "json_extract(payload, '$.pnl_net') as pnl_net, "
                    "json_extract(payload, '$.pnl_gross') as pnl_gross, "
                    "json_extract(payload, '$.exit_price') as exit_price, "
                    "json_extract(payload, '$.exit_reason') as exit_reason, "
                    "json_extract(payload, '$.fees_exit') as fees_exit, "
                    "timestamp_ms "
                    "FROM protocol_events WHERE event_type='trade_close' "
                    "ORDER BY timestamp_ms DESC"
                ).fetchall()
                total_closed = len(closed_rows)
                closed_pnl = sum(float(r["pnl_net"] or 0) for r in closed_rows)
                wins = sum(1 for r in closed_rows if float(r["pnl_net"] or 0) > 0)

                # Recent closed trades for display
                for r in closed_rows[:20]:
                    # Get matching entry for this contract
                    entry_row = pconn.execute(
                        "SELECT json_extract(payload, '$.entry_price') as entry_price, "
                        "json_extract(payload, '$.venue') as venue "
                        "FROM protocol_events WHERE event_type='trade_entry' AND contract_id=? "
                        "ORDER BY timestamp_ms ASC LIMIT 1",
                        (r["contract_id"],)
                    ).fetchone()
                    pnl_val = float(r["pnl_net"] or 0)
                    status = "closed_win" if pnl_val > 0 else "closed_loss"
                    # Parse ticker from contract_id (e.g. KXBTC-26MAR2921-B66750 -> bitcoin)
                    ticker = r["contract_id"] or ""
                    if "BTC" in ticker:
                        ticker = "bitcoin"
                    elif "ETH" in ticker:
                        ticker = "ethereum"
                    elif "DOGE" in ticker:
                        ticker = "dogecoin"
                    elif "BNB" in ticker:
                        ticker = "binancecoin"
                    recent_list.append({
                        "event_id": r["contract_id"], "venue": entry_row["venue"] if entry_row else "kalshi",
                        "ticker": ticker, "direction": "YES",
                        "entry_price": float(entry_row["entry_price"]) if entry_row else 0,
                        "exit_price": float(r["exit_price"] or 0),
                        "pnl": round(pnl_val, 2), "status": status,
                        "final_score": 0,
                        "opened_at": "", "closed_at": "",
                    })

                # Open positions: position_open not in position_close
                open_rows = pconn.execute("""
                    SELECT po.contract_id,
                        json_extract(po.payload, '$.venue') as venue,
                        json_extract(po.payload, '$.side') as side,
                        json_extract(po.payload, '$.entry_price') as entry_price,
                        json_extract(po.payload, '$.size') as size,
                        po.timestamp_ms
                    FROM protocol_events po
                    WHERE po.event_type='position_open'
                    AND po.contract_id NOT IN (
                        SELECT contract_id FROM protocol_events WHERE event_type='position_close'
                    )
                    GROUP BY po.contract_id
                    ORDER BY po.timestamp_ms DESC
                """).fetchall()
                for op in open_rows:
                    entry_price = float(op["entry_price"] or 0)
                    size = int(op["size"] or 0)
                    amount_usd = round(entry_price * size, 2)
                    ticker = op["contract_id"] or ""
                    if "BTC" in ticker:
                        ticker = "bitcoin"
                    elif "ETH" in ticker:
                        ticker = "ethereum"
                    elif "DOGE" in ticker:
                        ticker = "dogecoin"
                    elif "BNB" in ticker:
                        ticker = "binancecoin"
                    open_list.append({
                        "event_id": op["contract_id"], "venue": op["venue"] or "kalshi",
                        "ticker": ticker, "direction": "YES" if op["side"] == "BUY" else "NO",
                        "entry_price": entry_price, "current_price": entry_price,
                        "amount_usd": amount_usd,
                        "final_score": 0, "confidence": 0,
                        "signal_scores": {},
                        "pnl": 0, "pnl_pct": 0,
                        "reasoning": "",
                        "opened_at": "",
                    })

                # Use wallet balance directly if available, otherwise compute
                if bal_row and bal_row["bal"]:
                    balance = float(bal_row["bal"])
                else:
                    balance = starting + closed_pnl

                used_protocol = True

            pconn.close()
        except Exception:
            pass

    # Fallback: legacy paper_trades if protocol_events unavailable
    if not used_protocol:
        try:
            closed_pnl = conn.execute(
                "SELECT COALESCE(SUM(pnl_usd), 0) FROM paper_trades WHERE status IN ('closed_win','closed_loss','expired')"
            ).fetchone()[0]
            all_closed = conn.execute(
                "SELECT status, pnl_usd FROM paper_trades WHERE status IN ('closed_win','closed_loss','expired')"
            ).fetchall()
            total_closed = len(all_closed)
            wins = sum(1 for t in all_closed if t["status"] == "closed_win")
        except Exception:
            pass

        if total_closed == 0:
            for backup_tbl in ("paper_trades_pre_protocol_20260327", "paper_trades_pre_audit_2026_03_26"):
                try:
                    bc = conn.execute(f'SELECT COUNT(*) FROM "{backup_tbl}" WHERE status IN ("closed_win","closed_loss","expired")').fetchone()[0]
                    if bc > 0:
                        closed_pnl = conn.execute(f'SELECT COALESCE(SUM(pnl_usd), 0) FROM "{backup_tbl}" WHERE status IN ("closed_win","closed_loss","expired")').fetchone()[0]
                        all_closed = conn.execute(f'SELECT status, pnl_usd FROM "{backup_tbl}" WHERE status IN ("closed_win","closed_loss","expired")').fetchall()
                        total_closed = len(all_closed)
                        wins = sum(1 for t in all_closed if t["status"] == "closed_win")
                        break
                except Exception:
                    continue

        balance = starting + closed_pnl + unrealized

    # Recent closed trades from legacy (only if protocol didn't provide them)
    if not recent_list:
        try:
            recent = conn.execute(
                "SELECT pt.*, td.event_id, td.venue, td.ticker, td.direction, td.final_score, td.signal_snapshot "
                "FROM paper_trades pt "
                "JOIN trade_decisions td ON pt.decision_id = td.decision_id "
                "WHERE pt.status IN ('closed_win','closed_loss','expired') "
                "ORDER BY pt.exit_at DESC LIMIT 20"
            ).fetchall()
            for r in recent:
                recent_list.append({
                    "event_id": r["event_id"], "venue": r["venue"],
                    "ticker": r["ticker"], "direction": r["direction"],
                    "entry_price": r["fill_price"], "exit_price": r["exit_price"],
                    "pnl": round(r["pnl_usd"] or 0, 2), "status": r["status"],
                    "final_score": r["final_score"],
                    "opened_at": r["executed_at"], "closed_at": r["exit_at"],
                })
        except Exception:
            pass

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

    # Total decisions (shows engine activity even when paper_trades is empty)
    total_decisions = 0
    try:
        total_decisions = conn.execute("SELECT COUNT(*) FROM trade_decisions").fetchone()[0]
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
            "total_decisions": total_decisions,
        },
        "open_positions": open_list,
        "recent_trades": recent_list,
        "pnl_curve": pnl_curve,
        "weight_history": weight_history,
        "module_accuracy": module_stats,
    }


@app.get("/api/trading/experiment")
async def get_experiment_dashboard(user: str = Depends(get_current_user)):
    """Experiment dashboard: RivalClaw + QuantumentalClaw."""
    result = {"rivalclaw": None, "quantumentalclaw": None}
    for instance in ("rivalclaw", "quantumentalclaw"):
        conn = _experiment_db(instance)
        if not conn:
            continue
        try:
            if instance == "rivalclaw":
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


# ── Claw Terminal Grid (SSE PTY + session management) ─────────────────────────

# PTY sessions: session_name -> {pid, fd}
_pty_sessions: dict = {}

def _ensure_pty(session_name: str) -> dict:
    """Get or create a PTY attached to a tmux session."""
    if session_name in _pty_sessions:
        entry = _pty_sessions[session_name]
        try:
            os.kill(entry["pid"], 0)
            return entry
        except OSError:
            try: os.close(entry["fd"])
            except: pass
            del _pty_sessions[session_name]

    pid, fd = pty.fork()
    if pid == 0:
        os.environ["TERM"] = "xterm-256color"
        os.environ["COLORTERM"] = "truecolor"
        os.environ["LANG"] = "en_US.UTF-8"
        os.execvp("tmux", ["tmux", "attach-session", "-t", session_name])
        os._exit(1)

    os.set_blocking(fd, False)
    entry = {"pid": pid, "fd": fd}
    _pty_sessions[session_name] = entry
    return entry


@app.get("/api/terminal/pty/stream/{session_name}")
async def pty_stream(session_name: str):
    """SSE stream of PTY output from a tmux session."""
    r = subprocess.run(["tmux", "has-session", "-t", session_name], capture_output=True)
    if r.returncode != 0:
        raise HTTPException(404, f"tmux session '{session_name}' not found")

    entry = _ensure_pty(session_name)

    async def generate():
        import base64
        from concurrent.futures import ThreadPoolExecutor
        loop = asyncio.get_event_loop()
        fd = entry["fd"]
        heartbeat = 0
        executor = ThreadPoolExecutor(max_workers=1)

        def _read_pty():
            """Blocking read in thread — waits for data via select."""
            try:
                readable, _, _ = select.select([fd], [], [], 0.5)
                if readable:
                    return os.read(fd, 65536)
            except (ValueError, OSError, BlockingIOError):
                pass
            return None

        while True:
            try:
                data = await loop.run_in_executor(executor, _read_pty)
            except Exception:
                break
            if data:
                encoded = base64.b64encode(data).decode("ascii")
                yield f"data: {json.dumps({'type': 'output', 'data': encoded})}\n\n"
                heartbeat = 0
            else:
                heartbeat += 1
                if heartbeat >= 30:  # ~15 seconds
                    yield ": heartbeat\n\n"
                    heartbeat = 0

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/terminal/pty/input/{session_name}")
async def pty_input(session_name: str, body: dict = Body(...)):
    """Send input to a PTY session."""
    entry = _ensure_pty(session_name)
    data = body.get("data", "")
    if data:
        os.write(entry["fd"], data.encode())
    return {"ok": True}


@app.post("/api/terminal/pty/paste-image/{session_name}")
async def pty_paste_image(session_name: str, body: dict = Body(...)):
    """Save a pasted image to /tmp, write the path into the PTY."""
    b64 = body.get("data", "")
    ext = body.get("ext", "png")
    if not b64:
        raise HTTPException(400, "No image data")
    fname = f"paste-{uuid.uuid4().hex[:8]}.{ext}"
    fpath = f"/tmp/{fname}"
    with open(fpath, "wb") as f:
        f.write(base64.b64decode(b64))
    entry = _ensure_pty(session_name)
    os.write(entry["fd"], fpath.encode())
    return {"ok": True, "path": fpath}


@app.post("/api/terminal/pty/resize/{session_name}")
async def pty_resize(session_name: str, body: dict = Body(...)):
    """Resize a PTY session."""
    if session_name not in _pty_sessions:
        raise HTTPException(404, "PTY session not found")
    entry = _pty_sessions[session_name]
    cols = body.get("cols", 80)
    rows = body.get("rows", 24)
    winsize = struct.pack("HHHH", rows, cols, 0, 0)
    fcntl.ioctl(entry["fd"], termios.TIOCSWINSZ, winsize)
    os.kill(entry["pid"], signal.SIGWINCH)
    return {"ok": True}


@app.get("/api/terminal/claw-status")
async def claw_status():
    state_file = Path.home() / ".openclaw" / "claw-sessions.json"
    health_file = Path.home() / ".openclaw" / "claw-health-log.jsonl"

    DISPLAY_NAMES = {
        "claw-rival": "RIVALCLAW", "rival": "RIVALCLAW",
        "claw-quant": "QUANTCLAW", "quant": "QUANTCLAW",
        "claw-monkey": "CODEMONKEY", "monkey": "CODEMONKEY",
    }

    sessions = {}
    if state_file.exists():
        data = json.loads(state_file.read_text())
        for key, val in data.items():
            session_name = val.get("session", key)
            display = DISPLAY_NAMES.get(session_name, DISPLAY_NAMES.get(key, key.upper()))
            sessions[session_name] = {
                **val,
                "displayName": display,
                "isScratch": "scratch" in key,
            }

    events = []
    if health_file.exists():
        cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()
        for line in health_file.read_text().strip().split("\n"):
            if not line:
                continue
            try:
                ev = json.loads(line)
                ts = ev.get("ts", ev.get("timestamp", ""))
                if ts >= cutoff:
                    events.append(ev)
            except Exception:
                pass

    return {"ok": True, "sessions": sessions, "healthEvents": events}


@app.post("/api/terminal/scratch/create")
async def create_scratch(body: dict = Body(...)):
    name = body.get("name", "")
    if not name.startswith("claw-scratch-"):
        raise HTTPException(400, "name must start with claw-scratch-")
    subprocess.run(["tmux", "new-session", "-d", "-s", name, "-x", "200", "-y", "50"])
    return {"ok": True}


@app.post("/api/terminal/scratch/kill")
async def kill_scratch(body: dict = Body(...)):
    name = body.get("name", "")
    if not name.startswith("claw-scratch-"):
        raise HTTPException(400, "can only kill scratch sessions")
    subprocess.run(["tmux", "kill-session", "-t", name], capture_output=True)
    return {"ok": True}


@app.post("/api/terminal/restart-claude")
async def restart_claude(body: dict = Body(...)):
    session = body.get("session", "")
    if not session:
        raise HTTPException(400, "session required")
    subprocess.run(["tmux", "send-keys", "-t", session, "C-c", ""], capture_output=True)
    subprocess.run(["tmux", "send-keys", "-t", session, "exit", "Enter"], capture_output=True)
    await asyncio.sleep(2)
    subprocess.run(["tmux", "send-keys", "-t", session, "claude", "Enter"], capture_output=True)
    return {"ok": True}


@app.post("/api/terminal/capture")
async def capture_output(body: dict = Body(...)):
    session = body.get("session", "")
    lines = body.get("lines", 50)
    result = subprocess.run(
        ["tmux", "capture-pane", "-t", session, "-p", "-S", f"-{lines}"],
        capture_output=True, text=True
    )
    return {"ok": True, "output": result.stdout}


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
                  rivalclaw_relevance, recency, value_per_complexity
    """
    data = _read_intel_recs()
    recs = data.get("recommendations", [])
    sort_desc = True
    if sort == "composite":
        # Weighted composite: integration_value*3 + signal_score*2 + max_relevance - complexity*0.5
        def composite(r):
            max_rel = r.get("rivalclaw_relevance", 0)
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
    elif sort in ("integration_value", "signal_score", "stars", "rivalclaw_relevance"):
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

    valid_targets = {"clawmpson", "rivalclaw", "quantumentalclaw"}
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


@app.post("/api/intel/push-all-github")
async def intel_push_all_github(request: Request, user: str = Depends(get_current_user)):
    """Push ALL unique GitHub repos from crawl files to Repo Man for analysis."""
    import glob as _glob

    datasets_dir = OPENCLAW_ROOT / "autoresearch" / "outputs" / "datasets"
    crawl_files = sorted(_glob.glob(str(datasets_dir / "crawl_*.json")))

    # Collect unique repos by URL
    seen = {}
    for filepath in crawl_files:
        try:
            items = json.loads(Path(filepath).read_text(encoding="utf-8"))
            if not isinstance(items, list):
                continue
            for item in items:
                url = item.get("url") or item.get("html_url") or ""
                if url and "github.com" in url and url not in seen:
                    seen[url] = {
                        "url": url,
                        "name": item.get("full_name") or item.get("name", ""),
                        "stars": item.get("stars", 0),
                        "description": (item.get("description") or "")[:200],
                        "language": item.get("language", ""),
                        "signal_score": item.get("signal_score", 0),
                        "category": item.get("category", ""),
                    }
        except Exception:
            continue

    if not seen:
        raise HTTPException(400, "No GitHub repos found in crawl data")

    # Check which are already in Repo Man (by querying recommendations.json for pushed URLs)
    already_pushed = set()
    if INTEL_RECS.exists():
        try:
            data = json.loads(INTEL_RECS.read_text(encoding="utf-8"))
            for r in data.get("recommendations", []):
                if r.get("repo_url"):
                    already_pushed.add(r["repo_url"])
        except Exception:
            pass

    # Filter to only new repos
    new_repos = {url: info for url, info in seen.items() if url not in already_pushed}

    if not new_repos:
        return {"ok": True, "queued": 0, "total_unique": len(seen),
                "already_pushed": len(already_pushed),
                "message": "All repos already pushed to Repo Man"}

    # Push to Repo Man via /api/run in batches of 10 (no auth needed, same as manual bucket)
    repoman_url = REPO_MAN_API.rstrip("/")
    total_queued = 0
    errors = []

    batch_size = 10
    repo_list = list(new_repos.values())

    async with httpx.AsyncClient(timeout=60) as client:
        for i in range(0, len(repo_list), batch_size):
            batch = repo_list[i:i + batch_size]
            # /api/run takes newline-separated URLs as "inputs" string
            urls_text = "\n".join(
                f"{repo['url']}  # {repo['name']} | {repo['stars']}★"
                for repo in batch
            )
            try:
                resp = await client.post(
                    f"{repoman_url}/api/run",
                    headers={"Content-Type": "application/json"},
                    json={
                        "inputs": urls_text,
                        "notes": "github-intel-bulk — pushed from Gonzoclaw dashboard",
                    },
                )
                if resp.status_code in (200, 202):
                    data = resp.json()
                    total_queued += data.get("item_count", len(batch))
                else:
                    errors.append(f"Batch {i//batch_size}: {resp.status_code} {resp.text[:200]}")
            except Exception as exc:
                errors.append(f"Batch {i//batch_size}: {exc}")
            # Delay between batches so Repo Man can process
            await asyncio.sleep(2)

    return {
        "ok": total_queued > 0,
        "queued": total_queued,
        "total_unique": len(seen),
        "already_pushed": len(already_pushed),
        "new_repos": len(new_repos),
        "errors": errors[:5] if errors else [],
        "message": f"Pushed {total_queued} of {len(new_repos)} new repos to Repo Man",
    }


@app.get("/api/intel/crawler-health")
async def intel_crawler_health(user: str = Depends(get_current_user)):
    """Check crawler status: is it running, when was last crawl, did it find results?"""
    import glob as _glob

    # Check if continuous crawler PID is alive
    pid_file = LOGS_DIR / "github-intel-continuous.pid"
    crawler_running = False
    crawler_pid = None
    if pid_file.exists():
        try:
            crawler_pid = int(pid_file.read_text().strip())
            os.kill(crawler_pid, 0)  # Signal 0 = check if alive
            crawler_running = True
        except (ValueError, OSError):
            crawler_running = False

    # Find latest crawl file and its results
    datasets_dir = OPENCLAW_ROOT / "autoresearch" / "outputs" / "datasets"
    crawl_files = sorted(_glob.glob(str(datasets_dir / "crawl_*.json")))
    last_crawl_file = crawl_files[-1] if crawl_files else None
    last_crawl_count = 0
    last_crawl_time = None

    if last_crawl_file:
        try:
            last_crawl_count = len(json.loads(Path(last_crawl_file).read_text()))
        except Exception:
            pass
        try:
            last_crawl_time = datetime.fromtimestamp(
                Path(last_crawl_file).stat().st_mtime
            ).isoformat()
        except Exception:
            pass

    # Check last 2 crawls to detect drying up
    recent_counts = []
    for f in crawl_files[-5:]:
        try:
            recent_counts.append(len(json.loads(Path(f).read_text())))
        except Exception:
            recent_counts.append(0)

    # Detect if results are drying up (last crawl found <10 new repos or declining trend)
    drying_up = False
    if recent_counts:
        drying_up = recent_counts[-1] < 10
        if len(recent_counts) >= 3:
            # Check for declining trend
            avg_recent = sum(recent_counts[-2:]) / 2
            avg_earlier = sum(recent_counts[:-2]) / max(len(recent_counts) - 2, 1)
            if avg_earlier > 0 and avg_recent / avg_earlier < 0.3:
                drying_up = True

    return {
        "crawler_running": crawler_running,
        "crawler_pid": crawler_pid,
        "last_crawl_time": last_crawl_time,
        "last_crawl_count": last_crawl_count,
        "recent_counts": recent_counts,
        "total_crawl_files": len(crawl_files),
        "drying_up": drying_up,
    }

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


# ══════════════════════════════════════════════════════════════════
# CHATGPT ANALYSIS — Send research to GPT-4o, get recommendations
# ══════════════════════════════════════════════════════════════════

_CHATGPT_SYSTEM_PROMPT = """You are a strategic advisor for OpenClaw, a web business operating system with three deployed trading instances:

1. **Clawmpson** (clawmpson) — Primary instance. Full business OS with 4 trading strategies, 5 data feeds, graduation engine, 13 agents. Handles trading, software dev, agentic ops, marketing, content, research.
2. **RivalClaw** (rivalclaw) — Lightweight 8-strategy quant engine with hedge engine and self-tuner. Polymarket-centric, mechanical execution.
3. **QuantumentalClaw** (quantumentalclaw) — Signal fusion engine for asymmetric opportunities across equities and prediction markets. 5 independent signal types.

You are analyzing research items that were collected and pre-analyzed by Repo Man (a research ingestion pipeline). Each item includes its original LINK — use these links to inform your analysis and include them in your recommendations so the human operator can verify sources.

For each batch, provide a JSON response with:
1. executive_summary: 2-3 sentence overview of all findings
2. recommendations: array of actionable strategies/integrations/improvements
3. meta_observations: cross-cutting patterns you noticed

Each recommendation MUST include:
- title: concise action title (under 80 chars)
- summary: what this is and why it matters (2-3 sentences)
- category: one of trading_signal, integration, research, infrastructure, content
- confidence: 0.0-1.0 (how confident this is actionable and valuable)
- urgency: immediate, this_week, or backlog
- recommended_target: which instance should handle this (clawmpson, rivalclaw, or quantumentalclaw)
- recommended_target_name: human-readable instance name (Lobster S. Clawmpson, RivalClaw, QuantumentalClaw)
- action_plan: step-by-step markdown plan (concrete enough for an AI coding agent to execute)
- source_items: list of item IDs this recommendation is based on
- source_links: list of original URLs/links for the source items (so operator can verify)
- risk: low, medium, or high
- risk_notes: specific risk concerns (null if low risk)

Respond ONLY with valid JSON. No markdown fences, no commentary outside the JSON."""


@app.post("/api/chatgpt/analyze")
async def chatgpt_analyze(request: Request, user: str = Depends(get_current_user)):
    """Fetch research from Repo Man, send to GPT-4o, save report."""
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if not openai_key:
        raise HTTPException(500, "OPENAI_API_KEY not configured")

    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    item_limit = body.get("item_limit", 20)

    # 1. Fetch completed items from Repo Man
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{REPO_MAN_API}/api/inbox", params={"limit": item_limit})
            resp.raise_for_status()
            inbox = resp.json()
    except Exception as exc:
        raise HTTPException(502, f"Failed to fetch from Repo Man: {exc}")

    items = inbox.get("items", [])
    if not items:
        raise HTTPException(400, "No completed research items to analyze")

    # 2. Predigest: extract essentials, cluster similar items, compress
    def _extract_item(item):
        """Pull only the fields GPT needs, aggressively truncated."""
        analysis = ""
        key_ideas = []
        for key in ("claude_analysis", "openai_analysis", "ollama_analysis"):
            a = item.get(key)
            if a and isinstance(a, dict):
                if not analysis and a.get("summary"):
                    analysis = a["summary"][:250]
                if not key_ideas and a.get("key_ideas"):
                    key_ideas = [str(k)[:60] for k in a["key_ideas"][:3]]
        routing = item.get("openclaw_routing") or {}
        return {
            "id": item.get("id", "unknown"),
            "title": item.get("title", "Untitled")[:100],
            "url": item.get("raw_input", ""),
            "source": item.get("source_type", "unknown"),
            "novelty": round(item.get("novelty_score", 0), 2),
            "action": item.get("action_recommendation", ""),
            "analysis": analysis,
            "ideas": key_ideas,
            "target": routing.get("recommended_instance", ""),
            "route_reason": routing.get("reasoning", "")[:100],
        }

    digested = [_extract_item(i) for i in items]

    # Cluster by source type to reduce redundancy
    clusters = {}
    for d in digested:
        key = d["source"]
        clusters.setdefault(key, []).append(d)

    # Build compressed prompt
    item_blocks = []
    input_items_summary = []
    for source_type, cluster in clusters.items():
        if len(cluster) > 3:
            # Summarize cluster: keep top 3 by novelty, note the rest
            cluster.sort(key=lambda x: x["novelty"], reverse=True)
            top = cluster[:3]
            rest_count = len(cluster) - 3
            for d in top:
                item_blocks.append(
                    f"[{d['id']}] {d['title']} | novelty={d['novelty']} | {d['action']}\n"
                    f"  LINK: {d['url']}\n"
                    f"  {d['analysis']}\n  Ideas: {', '.join(d['ideas'])}\n  → {d['target']} ({d['route_reason']})"
                )
            if rest_count:
                # Still include links for omitted items so GPT can investigate
                rest_links = [f"  - {d['url']}" for d in cluster[3:] if d.get("url")]
                omit_block = f"(+{rest_count} more {source_type} items, lower novelty)"
                if rest_links:
                    omit_block += "\n  Links:\n" + "\n".join(rest_links)
                item_blocks.append(omit_block)
            for d in cluster:
                input_items_summary.append({
                    "id": d["id"], "title": d["title"], "url": d["url"],
                    "source_type": d["source"], "novelty_score": d["novelty"],
                    "action_recommendation": d["action"],
                })
        else:
            for d in cluster:
                item_blocks.append(
                    f"[{d['id']}] {d['title']} | novelty={d['novelty']} | {d['action']}\n"
                    f"  LINK: {d['url']}\n"
                    f"  {d['analysis']}\n  Ideas: {', '.join(d['ideas'])}\n  → {d['target']} ({d['route_reason']})"
                )
                input_items_summary.append({
                    "id": d["id"], "title": d["title"], "url": d["url"],
                    "source_type": d["source"], "novelty_score": d["novelty"],
                    "action_recommendation": d["action"],
                })

    user_message = (
        f"Analyze these {len(items)} research items ({len(clusters)} source types) "
        f"and provide strategic recommendations:\n\n"
        + "\n\n".join(item_blocks)
    )

    # Log prompt size for observability
    prompt_chars = len(_CHATGPT_SYSTEM_PROMPT) + len(user_message)
    est_tokens = prompt_chars // 4
    import logging
    logging.getLogger("dashboard").info(
        f"ChatGPT analyze: {len(items)} items → {len(item_blocks)} blocks, "
        f"~{est_tokens} input tokens, {prompt_chars} chars"
    )

    # 3. Call OpenAI API (with retry for 429 rate limits)
    oai_data = None
    last_err = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                oai_resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {openai_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": os.environ.get("CHATGPT_RESEARCH_MODEL", "gpt-4o"),
                        "max_tokens": int(os.environ.get("CHATGPT_RESEARCH_MAX_TOKENS", "2048")),
                        "temperature": 0.3,
                        "response_format": {"type": "json_object"},
                        "messages": [
                            {"role": "system", "content": _CHATGPT_SYSTEM_PROMPT},
                            {"role": "user", "content": user_message},
                        ],
                    },
                )
                if oai_resp.status_code == 429 and attempt < 2:
                    wait = int(oai_resp.headers.get("retry-after", 20 * (attempt + 1)))
                    await asyncio.sleep(wait)
                    continue
                oai_resp.raise_for_status()
                oai_data = oai_resp.json()
                break
        except Exception as exc:
            last_err = exc
            if attempt < 2:
                await asyncio.sleep(10 * (attempt + 1))
            continue
    if oai_data is None:
        raise HTTPException(502, f"OpenAI API call failed after 3 attempts: {last_err}")

    # 4. Parse response
    tokens_used = oai_data.get("usage", {}).get("total_tokens", 0)
    raw_content = oai_data["choices"][0]["message"]["content"]
    try:
        parsed = json.loads(raw_content)
    except json.JSONDecodeError:
        raise HTTPException(502, "OpenAI returned invalid JSON")

    # 5. Build report
    now = datetime.now()
    report_id = f"rpt-{now.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"

    # Ensure recommendations have all required fields
    recs = parsed.get("recommendations", [])
    for rec in recs:
        rec.setdefault("deployed", False)
        rec.setdefault("deployed_at", None)
        rec.setdefault("task_id", None)
        rec.setdefault("risk_notes", None)

    report = {
        "id": report_id,
        "created_at": now.isoformat(),
        "model": os.environ.get("CHATGPT_RESEARCH_MODEL", "gpt-4o"),
        "tokens_used": tokens_used,
        "item_count": len(items),
        "input_items": input_items_summary,
        "executive_summary": parsed.get("executive_summary", ""),
        "recommendations": recs,
        "meta_observations": parsed.get("meta_observations", ""),
        "status": "complete",
    }

    # 6. Save
    CHATGPT_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_file = CHATGPT_REPORTS_DIR / f"{report_id}.json"
    report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return report


@app.get("/api/chatgpt/reports")
async def chatgpt_list_reports(user: str = Depends(get_current_user)):
    """List all saved ChatGPT analysis reports."""
    CHATGPT_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    reports = []
    for f in sorted(CHATGPT_REPORTS_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            reports.append({
                "id": data["id"],
                "created_at": data["created_at"],
                "item_count": data.get("item_count", 0),
                "recommendation_count": len(data.get("recommendations", [])),
                "status": data.get("status", "complete"),
            })
        except Exception:
            pass
    return {"reports": reports}


@app.get("/api/chatgpt/reports/{report_id}")
async def chatgpt_get_report(report_id: str, user: str = Depends(get_current_user)):
    """Return a full ChatGPT analysis report."""
    report_file = CHATGPT_REPORTS_DIR / f"{report_id}.json"
    if not report_file.exists():
        raise HTTPException(404, "Report not found")
    return json.loads(report_file.read_text(encoding="utf-8"))


@app.post("/api/chatgpt/deploy")
async def chatgpt_deploy(request: Request, user: str = Depends(get_current_user)):
    """Deploy a single ChatGPT recommendation to the task queue."""
    body = await request.json()
    report_id = body.get("report_id", "")
    rec_index = body.get("rec_index", -1)

    report_file = CHATGPT_REPORTS_DIR / f"{report_id}.json"
    if not report_file.exists():
        raise HTTPException(404, "Report not found")

    report = json.loads(report_file.read_text(encoding="utf-8"))
    recs = report.get("recommendations", [])
    if rec_index < 0 or rec_index >= len(recs):
        raise HTTPException(400, "Invalid recommendation index")

    rec = recs[rec_index]
    if rec.get("deployed"):
        raise HTTPException(400, "Already deployed")

    target = rec.get("recommended_target", "clawmpson")
    valid_targets = {"clawmpson", "rivalclaw", "quantumentalclaw"}
    if target not in valid_targets:
        target = "clawmpson"

    task_id = f"chatgpt-{uuid.uuid4().hex[:8]}"
    task = {
        "id": task_id,
        "type": "chatgpt-strategy-deploy",
        "title": f"[ChatGPT] {rec.get('title', 'Untitled')[:80]}",
        "description": rec.get("summary", ""),
        "strategy_details": rec.get("action_plan", ""),
        "confidence": rec.get("confidence", 0),
        "targets": [target],
        "priority": "high" if rec.get("confidence", 0) >= 0.8 else "medium",
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "approved_by": user,
        "source_report": report_id,
        "source_rec_index": rec_index,
    }

    pending = []
    if PENDING_JSON.exists():
        try:
            pending = json.loads(PENDING_JSON.read_text(encoding="utf-8"))
        except Exception:
            pending = []
    pending.append(task)
    PENDING_JSON.write_text(json.dumps(pending, indent=2), encoding="utf-8")

    rec["deployed"] = True
    rec["deployed_at"] = datetime.now().isoformat()
    rec["task_id"] = task_id
    report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return {"ok": True, "task_id": task_id, "targets": [target]}


@app.post("/api/chatgpt/deploy-all")
async def chatgpt_deploy_all(request: Request, user: str = Depends(get_current_user)):
    """Deploy all undeployed recommendations from a report."""
    body = await request.json()
    report_id = body.get("report_id", "")

    report_file = CHATGPT_REPORTS_DIR / f"{report_id}.json"
    if not report_file.exists():
        raise HTTPException(404, "Report not found")

    report = json.loads(report_file.read_text(encoding="utf-8"))

    pending = []
    if PENDING_JSON.exists():
        try:
            pending = json.loads(PENDING_JSON.read_text(encoding="utf-8"))
        except Exception:
            pending = []

    task_ids = []
    for i, rec in enumerate(report.get("recommendations", [])):
        if rec.get("deployed"):
            continue
        target = rec.get("recommended_target", "clawmpson")
        valid_targets = {"clawmpson", "rivalclaw", "quantumentalclaw"}
        if target not in valid_targets:
            target = "clawmpson"

        task_id = f"chatgpt-{uuid.uuid4().hex[:8]}"
        task = {
            "id": task_id,
            "type": "chatgpt-strategy-deploy",
            "title": f"[ChatGPT] {rec.get('title', 'Untitled')[:80]}",
            "description": rec.get("summary", ""),
            "strategy_details": rec.get("action_plan", ""),
            "confidence": rec.get("confidence", 0),
            "targets": [target],
            "priority": "high" if rec.get("confidence", 0) >= 0.8 else "medium",
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "approved_by": user,
            "source_report": report_id,
            "source_rec_index": i,
        }
        pending.append(task)
        task_ids.append(task_id)

        rec["deployed"] = True
        rec["deployed_at"] = datetime.now().isoformat()
        rec["task_id"] = task_id

    PENDING_JSON.write_text(json.dumps(pending, indent=2), encoding="utf-8")
    report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return {"ok": True, "task_ids": task_ids, "deployed_count": len(task_ids)}


# ── Strategy Catalog ───────────────────────────────────────────────────────
_strategy_cache: dict = {}

@app.get("/api/strategies")
async def get_strategies(user: str = Depends(get_current_user)):
    if not STRATEGY_CATALOG.exists():
        return {"strategies": [], "families": [], "strategy_count": 0}
    mtime = STRATEGY_CATALOG.stat().st_mtime
    if _strategy_cache.get("mtime") != mtime:
        data = json.loads(STRATEGY_CATALOG.read_text(encoding="utf-8"))
        _strategy_cache.update(mtime=mtime, data=data)
    return _strategy_cache["data"]


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
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    log_path = LOGS_DIR / f"cinema-{job_id}.log"
    with open(log_path, "w") as log_fh:
        subprocess.Popen(
            [sys.executable, str(CINEMA_DIR / "pipeline.py"), job_id, prompt],
            stdout=log_fh,
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
    fpath = (CINEMA_RENDERS / filename).resolve()
    if not str(fpath).startswith(str(CINEMA_RENDERS.resolve())) or not fpath.exists():
        raise HTTPException(404, "Render not found")
    return FileResponse(
        fpath,
        media_type="video/mp4",
        headers={"Accept-Ranges": "bytes"},
    )


@app.get("/orchestrator-embed")
async def orchestrator_embed(request: Request):
    """Serve the self-contained orchestrator HTML for iframe embedding."""
    token = request.cookies.get("oc_token")
    if not token or not verify_token(token):
        if not is_localhost(request):
            return RedirectResponse(url="/login")
    html = (Path(__file__).parent / "orchestrator-embed.html").read_text()
    return HTMLResponse(content=html, headers={
        "Cache-Control": "no-cache, no-store, must-revalidate",
    })


# ── Gonzoclaw chat dashboard (SPA) ────────────────────────────────────────────
# Built React app from ~/gonzoclaw/frontend/dist. Vite is configured with
# base="/chat-app/" so asset URLs resolve under that prefix. The SPA's API
# calls go to /api/gonzoclaw/* on this same server, which proxies to the
# gonzoclaw FastAPI backend on localhost:18790. Same-origin = no CORS, no
# new auth, the existing oc_token gate covers the chat backend automatically.
GONZOCLAW_DIST = Path.home() / "gonzoclaw" / "frontend" / "dist"
GONZOCLAW_ASSETS = GONZOCLAW_DIST / "assets"
GONZOCLAW_BACKEND = "http://localhost:18790"


@app.get("/chat-app")
@app.get("/chat-app/")
async def chat_app_index(request: Request):
    """Serve the gonzoclaw chat SPA index.html with auth gate."""
    token = request.cookies.get("oc_token")
    if not token or not verify_token(token):
        if not is_localhost(request):
            return RedirectResponse(url="/login")
    index = GONZOCLAW_DIST / "index.html"
    if not index.exists():
        return HTMLResponse(
            content="<h1>chat-app build missing</h1><p>run: cd ~/gonzoclaw/frontend && VITE_BASE_PATH=/chat-app/ VITE_API_PATH=/api/gonzoclaw npm run build</p>",
            status_code=503,
        )
    return HTMLResponse(
        content=index.read_text(),
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


# Static asset bundle (JS/CSS hashed by Vite — safe to cache)
if GONZOCLAW_ASSETS.exists():
    app.mount(
        "/chat-app/assets",
        StaticFiles(directory=str(GONZOCLAW_ASSETS)),
        name="chat_app_assets",
    )


# ── Streaming proxy: /api/gonzoclaw/* → gonzoclaw FastAPI backend ────────────
# Same-origin proxy so the SPA's API calls inherit this dashboard's oc_token
# auth gate (GitHub OAuth) without any extra plumbing. Critical for SSE: we
# stream raw bytes both directions with no buffering.
@app.api_route(
    "/api/gonzoclaw/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
async def gonzoclaw_proxy(path: str, request: Request):
    # Auth gate — same as the rest of the dashboard's protected routes.
    # Return 401 instead of redirecting to /login because EventSource and
    # fetch can't follow auth redirects in any useful way.
    token = request.cookies.get("oc_token")
    if not token or not verify_token(token):
        if not is_localhost(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)

    # Build target URL on the gonzoclaw backend, preserving query string.
    target = f"{GONZOCLAW_BACKEND}/api/{path}"
    if request.url.query:
        target = f"{target}?{request.url.query}"

    # Forward request headers, dropping hop-by-hop and host header so the
    # backend sees its own host.
    drop_req = {"host", "content-length", "connection", "keep-alive",
                "transfer-encoding", "upgrade"}
    fwd_headers = {k: v for k, v in request.headers.items()
                   if k.lower() not in drop_req}

    body = await request.body() if request.method != "GET" else None

    # Stream both directions. timeout=None because SSE can be long-lived.
    client = httpx.AsyncClient(timeout=None)
    upstream_req = client.build_request(
        method=request.method,
        url=target,
        headers=fwd_headers,
        content=body,
    )
    upstream = await client.send(upstream_req, stream=True)

    async def relay():
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    drop_resp = {"content-length", "content-encoding", "transfer-encoding",
                 "connection", "keep-alive"}
    resp_headers = {k: v for k, v in upstream.headers.items()
                    if k.lower() not in drop_resp}

    return StreamingResponse(
        relay(),
        status_code=upstream.status_code,
        headers=resp_headers,
        media_type=upstream.headers.get("content-type"),
    )


# ── CodeMonkeyClaw Work Orders ────────────────────────────────────────────────
_CMC_DB = Path.home() / "codemonkeyclaw" / "codemonkeyclaw.db"

def _cmc_orders(status: str = None):
    """Read work orders from CodeMonkeyClaw SQLite DB."""
    import sqlite3
    if not _CMC_DB.exists():
        return []
    try:
        con = sqlite3.connect(str(_CMC_DB))
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        if status:
            cur.execute("SELECT * FROM work_orders WHERE status=? ORDER BY created_at DESC LIMIT 100", (status,))
        else:
            cur.execute("SELECT * FROM work_orders ORDER BY created_at DESC LIMIT 100")
        rows = [dict(r) for r in cur.fetchall()]
        con.close()
        return rows
    except Exception as e:
        return []

@app.get("/api/codemonkey/orders")
async def cmc_list_orders(status: str = None, user: str = Depends(get_current_user)):
    """List CodeMonkeyClaw work orders, optionally filtered by status."""
    return _cmc_orders(status)

@app.post("/api/codemonkey/orders")
async def cmc_submit_order(request: Request, user: str = Depends(get_current_user)):
    """Submit a new CodeMonkeyClaw work order via the CLI."""
    data = await request.json()
    required = {"description", "target_repo", "type"}
    if not required.issubset(data):
        raise HTTPException(400, f"Missing fields: {required - set(data)}")
    import subprocess, sys
    cmd = [
        sys.executable,
        str(Path.home() / "codemonkeyclaw" / "run.py"),
        "submit",
        "--source", "dashboard",
        "--type", data["type"],
        "--target", data["target_repo"],
        "--path", data.get("target_path", ""),
        "--description", data["description"],
        "--priority", str(data.get("priority", "medium")),
    ]
    if data.get("context"):
        cmd += ["--context-refs", data["context"]]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        wo_id = result.stdout.strip().split()[-1] if result.returncode == 0 else None
        return {"ok": result.returncode == 0, "wo_id": wo_id, "error": result.stderr[:200] if result.returncode != 0 else None}
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "CodeMonkeyClaw submit timed out")

@app.get("/api/codemonkey/orders/{wo_id}")
async def cmc_get_order(wo_id: str, user: str = Depends(get_current_user)):
    """Get a single work order by ID."""
    orders = _cmc_orders()
    for o in orders:
        if o.get("id") == wo_id:
            return o
    raise HTTPException(404, f"Work order {wo_id} not found")

@app.get("/api/codemonkey/stats")
async def cmc_stats(user: str = Depends(get_current_user)):
    """Summary stats for the CodeMonkeyClaw work queue."""
    orders = _cmc_orders()
    from collections import Counter
    counts = Counter(o.get("status", "UNKNOWN") for o in orders)
    return {"total": len(orders), "by_status": dict(counts)}


@app.get("/{path:path}")
async def spa(path: str, request: Request):
    # Let API and WebSocket routes through
    if path.startswith("api/") or path.startswith("auth/") or path.startswith("ws"):
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
    uvicorn.run("server:app", host="0.0.0.0", port=7080, reload=False, workers=1)
