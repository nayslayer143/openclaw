# Task: PWA Dashboard with GitHub OAuth

**Status:** Paused — needs GitHub OAuth credentials
**Parked:** 2026-03-20
**Resume:** Drop GitHub Client ID + Secret into `dashboard/.env`, restart dashboard, done.

---

## What's built

- `~/openclaw/dashboard/server.py` — FastAPI backend, port 7080, runs as launchd agent `com.openclaw.dashboard`
- `~/openclaw/dashboard/index.html` — PWA frontend, dark terminal UI, live SSE updates every 3s
- `~/openclaw/dashboard/login.html` — GitHub OAuth login page
- `~/openclaw/dashboard/manifest.json` — PWA manifest (installable on mobile/desktop)
- `~/openclaw/dashboard/.env` — config file, JWT secret already written, OAuth fields empty

## What it shows

- Live build history (success/blocked/failed) with test counts
- Task queue (pending packets)
- Phase 2 progress bar (X/10 builds)
- SSE real-time updates, no polling on frontend

## What's missing

GitHub OAuth credentials. The dashboard works locally without them but auth fails for external access.

## Steps to resume (10 min)

1. **Create GitHub OAuth app**
   - Go to github.com/settings/developers → OAuth Apps → New OAuth App
   - Name: OpenClaw Dashboard
   - Homepage: `https://your-tunnel.trycloudflare.com` (or stable Render URL)
   - Callback: `https://your-tunnel.trycloudflare.com/auth/github/callback`

2. **Start Cloudflare tunnel** to get public URL:
   ```bash
   cloudflared tunnel --url http://localhost:7080 --no-autoupdate &
   # URL appears in: grep trycloudflare /tmp/cloudflared.log
   ```

3. **Update `~/openclaw/dashboard/.env`**:
   ```
   GITHUB_CLIENT_ID=<from step 1>
   GITHUB_CLIENT_SECRET=<from step 1>
   DASHBOARD_PUBLIC_URL=https://<tunnel-url>
   ```

4. **Restart dashboard**:
   ```bash
   launchctl stop com.openclaw.dashboard && launchctl start com.openclaw.dashboard
   ```

5. Open tunnel URL in browser → GitHub login → dashboard loads

## Stable URL option (better long-term)

Deploy `dashboard/` to Render as a Python web service. Set env vars in Render dashboard. GitHub OAuth callback becomes `https://openclaw-dashboard.onrender.com/auth/github/callback`. No tunnel needed, always-on.

## Notes

- Tunnel URL changes on restart — use Render or a paid Cloudflare tunnel for stability
- JWT secret already set in `.env` — don't regenerate or existing sessions will break
- `ALLOWED_GITHUB_USERS=nayslayer` — add more users as comma-separated list if needed
