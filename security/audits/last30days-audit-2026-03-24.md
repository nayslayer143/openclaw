# Security Audit: last30days-skill
**Date:** 2026-03-24
**Auditor:** Claude Code (automated + manual review)
**Source:** https://github.com/mvanhorn/last30days-skill
**Version audited:** 2.9.5
**Verdict:** PASS — install approved with notes

---

## 1. Repository Overview

| Field | Value |
|-------|-------|
| Author | Matt Van Horn (mvanhorn@gmail.com) |
| License | MIT |
| Language | Python + JavaScript (Node.js 22+) |
| Install path | `~/.claude/skills/last30days` |
| DB path | `~/.local/share/last30days/research.db` |

---

## 2. Audit Checklist

### 2.1 Outbound Network Calls

All outbound calls confirmed against documented platforms only:

| Domain | Purpose | Key Required |
|--------|---------|-------------|
| `api.scrapecreators.com` | Reddit, X, TikTok, Instagram search | SCRAPECREATORS_API_KEY |
| `api.x.ai` | X/Twitter search via xAI Grok | XAI_API_KEY |
| `twitter.com` / `x.com` GraphQL | X search via vendored bird-search (Node.js) | AUTH_TOKEN + CT0 |
| `bsky.social` | Bluesky search | BSKY_HANDLE + BSKY_APP_PASSWORD |
| `gamma-api.polymarket.com` | Polymarket market data | None (free) |
| `hn.algolia.com` | Hacker News search | None (free) |
| `www.reddit.com` | Reddit public JSON fallback | None (free) |
| `api.openai.com` | Reddit search via Responses API (fallback) | OPENAI_API_KEY |
| `api.search.brave.com` | Web search | BRAVE_API_KEY |
| `openrouter.ai` | Web search via Sonar Pro | OPENROUTER_API_KEY |
| YouTube via yt-dlp | YouTube search/metadata | None (yt-dlp required) |
| `host.docker.internal:18060` | Xiaohongshu (configurable, off by default) | None |

**No unexpected outbound calls found.** No calls to any analytics, telemetry, or data-collection endpoints.

### 2.2 Credential Handling

- All credentials read from `os.environ` or `~/.config/last30days/.env` or `.claude/last30days.env`
- No credentials logged or written to disk beyond the user's own config file
- JWT decode is local-only (for Codex token expiry check)
- `env.py` reads: SCRAPECREATORS_API_KEY, AUTH_TOKEN, CT0, BSKY_HANDLE, BSKY_APP_PASSWORD, XAI_API_KEY, OPENAI_API_KEY, BRAVE_API_KEY, OPENROUTER_API_KEY, APIFY_API_TOKEN, TRUTHSOCIAL_TOKEN, XIAOHONGSHU_API_BASE
- Each credential is sent **only** to its documented service — no cross-API key sharing
- Warns on stderr if config files have permissions wider than 600

### 2.3 Browser Cookie Access (Notable Item)

**Component:** `@steipete/sweet-cookie` (vendored in `scripts/lib/vendor/bird-search/`)
**Purpose:** Reads Twitter `auth_token` + `ct0` cookies from Safari/Chrome/Firefox
**Risk level:** LOW (see mitigations)

**Mitigations already in place:**
1. `bird_x.py:set_credentials()` — when AUTH_TOKEN+CT0 are provided via .env, it calls `env.setdefault("BIRD_DISABLE_BROWSER_COOKIES", "1")` before any Node subprocess is spawned. Browser cookie extraction never runs.
2. Cookies are used only for Twitter GraphQL API calls — not transmitted anywhere else
3. Only `auth_token` and `ct0` for `x.com`/`twitter.com` origins are extracted; no other cookies
4. The `@steipete/bird` library (MIT) is well-known in the developer community

**Recommendation:** Add `AUTH_TOKEN` and `CT0` to `.env` (see Step 4 below). This permanently disables browser cookie access.

### 2.4 Code Execution Patterns

| Pattern | Found | Notes |
|---------|-------|-------|
| `eval()` / `exec()` | No | Not in any Python file |
| `os.system()` | No | |
| `subprocess.call()` | No | |
| `subprocess.Popen/run` | Yes | Used only to invoke `node bird-search.mjs` with controlled args |
| `__import__` | No | |
| `pickle.load` | No | |
| Base64 decode + exec | No | |
| Obfuscated strings | No | |
| `regex.exec()` in JS | Yes | Standard JS regex method — not dangerous eval |

### 2.5 File System Access

| Path | Operation | Expected |
|------|-----------|---------|
| `~/.config/last30days/.env` | Read | Config file |
| `.claude/last30days.env` | Read | Per-project config |
| `~/.codex/auth.json` | Read | Codex token (if using Codex auth) |
| `~/.local/share/last30days/research.db` | Read/Write | SQLite findings database |
| `~/.local/share/last30days/` | mkdir | DB directory creation only |

No access to OpenClaw system paths, `.env` main file, agent configs, or other system files.

### 2.6 Hooks

**File:** `hooks/hooks.json`
**Hook:** `SessionStart` → `bash check-config.sh`
**What it does:** Checks if config files exist and warns about insecure permissions (chmod 600)
**Network calls:** None
**Verdict:** Safe

### 2.7 Dependencies

**Python:** stdlib only (`json`, `sqlite3`, `subprocess`, `urllib`, `pathlib`, etc.) + optional `requests` (already in OpenClaw env)
**Node.js:** `@steipete/sweet-cookie` (vendored in repo, MIT license) — used only for browser cookie extraction when env vars not set
**No pip install required.**

### 2.8 Plugin Metadata

```json
{
  "name": "last30days",
  "version": "2.9.5",
  "author": {"name": "Matt Van Horn", "email": "mvanhorn@gmail.com"},
  "license": "MIT",
  "skills": ["./"],
  "hooks": {}
}
```

Metadata is honest and matches actual capabilities.

---

## 3. API Keys Required

| Key | Service | Used For |
|-----|---------|---------|
| `SCRAPECREATORS_API_KEY` | ScrapeCreators | Reddit, X, TikTok, Instagram (one key covers all) |
| `XAI_API_KEY` | xAI | X/Twitter search via Grok |
| `AUTH_TOKEN` | Twitter session cookie | X search via bird-search (free, no API key) |
| `CT0` | Twitter CSRF token | X search via bird-search (pair with AUTH_TOKEN) |
| `BSKY_HANDLE` | Bluesky | Bluesky search (e.g. `you.bsky.social`) |
| `BSKY_APP_PASSWORD` | Bluesky | Bluesky app password (create at bsky.app/settings) |

**Optional:** OPENAI_API_KEY (Reddit fallback), BRAVE_API_KEY, OPENROUTER_API_KEY, APIFY_API_TOKEN (legacy TikTok)

**Minimum viable:** SCRAPECREATORS_API_KEY alone covers Reddit + X + TikTok + Instagram.

---

## 4. Installation Notes

- Installed to: `~/.claude/skills/last30days/`
- Config location: `~/.config/last30days/.env` (global) or `.claude/last30days.env` (per-project)
- SQLite DB: `~/.local/share/last30days/research.db`
- BIRD_DISABLE_BROWSER_COOKIES is automatically set when AUTH_TOKEN+CT0 are in env

---

## 5. Verdict

**APPROVED for installation.** No red flags found. All network calls match documented behavior. The browser cookie reader is present but rendered inactive by providing AUTH_TOKEN+CT0 via env vars. Code is clean, well-structured, and uses only stdlib + one optional well-known dependency.

**Register in skill registry:** Run `python3 ~/openclaw/scripts/skill_auditor.py audit ~/.claude/skills/last30days` to register.
