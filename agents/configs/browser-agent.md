# Browser Agent — Eyes & Hands

**Module path:** `scripts/browser/`
**Role:** Gives Claude Code and Clawmson the ability to see, navigate, and interact with websites.

## Capabilities

| Tool | Function | Description |
|------|----------|-------------|
| `browser_open` | `browser_tools.browser_open(url)` | Open URL, extract text/content |
| `browser_screenshot` | `browser_tools.browser_screenshot(url)` | Capture PNG screenshot |
| `browser_click` | `browser_tools.browser_click(url, selector)` | Navigate + click element |
| `browser_fill` | `browser_tools.browser_fill(url, fields)` | Fill form fields |
| `browser_eval` | `browser_tools.browser_eval(url, js)` | Execute JavaScript |
| `browser_login` | `browser_tools.browser_login(url, user, pass)` | Authenticate + save session |

## Telegram Commands

| Command | What it does |
|---------|-------------|
| `/browse <url>` | Opens URL and sends back text summary |
| `/screenshot <url>` | Takes screenshot and sends as photo |
| Natural language: "go to X and check Y" | Routed as `BROWSER_TASK` intent |

## Security Model

- **Credential vault:** `~/.openclaw/browser-vault.enc` (Fernet-encrypted, machine-keyed)
- **Session store:** `~/.openclaw/browser-sessions/<domain>.enc` (encrypted cookies)
- **Audit log:** `~/openclaw/logs/browser/browser-YYYY-MM-DD.jsonl`
- **Domain scope:** configurable allowlist/blocklist in `scripts/browser/config.json`
- **robots.txt:** respected by default; disable per-task only
- **No credentials in logs** — all auth operations redact values

## CAPTCHA Strategy

1. **Tier 1 (always on):** Stealth headers, realistic user-agent, human timing
2. **Tier 2 (API):** 2captcha or AntiCaptcha — requires `CAPTCHA_API_KEY` in `.env`
3. **Tier 3 (human):** Bot pauses, alerts Jordan via Telegram. Reply `/captcha-done` to resume

## ENV Vars

```
CAPTCHA_API_KEY=           # 2captcha or AntiCaptcha
BROWSER_PROXY_URL=         # optional proxy
BROWSER_DEFAULT_TIMEOUT=30000  # ms
```

## File Map

```
scripts/browser/
├── __init__.py            # Public API exports
├── config.json            # Domain lists, rate limits, proxy
├── security.py            # Vault, audit log, domain scope, robots.txt
├── browser_engine.py      # Playwright wrapper (core)
├── eyes.py                # Screenshot + DOM extraction
├── hands.py               # Click, type, scroll, form fill
├── auth_handler.py        # Session persistence, login, OAuth, MFA
├── captcha_handler.py     # 3-tier CAPTCHA
├── browser_tools.py       # Claude Code shim (browser_open etc.)
└── tests/                 # 5 test files, ~33 tests
```

## Web Citizenship Rules

- Always respect `robots.txt` (override requires explicit per-domain flag)
- Default rate limit: 1–3 seconds between requests
- Hard stop on IP block detection — pause + alert, never retry in loop
- Identify as bot in honest mode; stealth mode only for authorized testing
- No data retained beyond current task scope
