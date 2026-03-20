#!/usr/bin/env python3
"""
OpenClaw Dashboard — FastAPI backend
Real-time task monitor with GitHub OAuth
"""
import os, json, asyncio, secrets, time, hashlib
from pathlib import Path
from typing import AsyncGenerator, Optional
from datetime import datetime, timedelta

from fastapi import FastAPI, Request, Response, HTTPException, Depends
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import httpx
from jose import jwt, JWTError

# ── Config ────────────────────────────────────────────────────────────────────
OPENCLAW_ROOT = Path.home() / "openclaw"
BUILD_RESULTS = OPENCLAW_ROOT / "build-results"
QUEUE_DIR     = OPENCLAW_ROOT / "repo-queue"
LOGS_DIR      = OPENCLAW_ROOT / "logs"

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
    if not QUEUE_DIR.exists():
        return []
    items = []
    for f in sorted(QUEUE_DIR.glob("task-*.json"), key=lambda p: p.stat().st_mtime):
        try:
            d = json.loads(f.read_text())
            d["_file"] = f.name
            items.append(d)
        except Exception:
            pass
    return items

def phase2_progress():
    contracts = read_contracts(50)
    success = [c for c in contracts if c.get("status") == "success"]
    return {"done": len(success), "target": 10, "pct": min(100, int(len(success) / 10 * 100))}

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

# ── Serve PWA ─────────────────────────────────────────────────────────────────
@app.get("/manifest.json")
async def manifest():
    return Response((Path(__file__).parent / "manifest.json").read_text(), media_type="application/json")

@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return (Path(__file__).parent / "login.html").read_text()

@app.get("/{path:path}", response_class=HTMLResponse)
async def spa(path: str, request: Request):
    # Let API routes through
    if path.startswith("api/") or path.startswith("auth/"):
        raise HTTPException(404)
    # Check auth — localhost skips OAuth
    token = request.cookies.get("oc_token")
    if not token or not verify_token(token):
        if is_localhost(request):
            return (Path(__file__).parent / "index.html").read_text()
        return RedirectResponse(url="/login")
    return (Path(__file__).parent / "index.html").read_text()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=7080, reload=False)
