# ChatGPT GitHub Connector Setup

## Connect GitHub to ChatGPT Plus

1. Open ChatGPT -> Settings -> Connected apps (or "Apps & Connectors")
2. Find the GitHub integration and click Connect
3. Authenticate with GitHub as **nayslayer143**
4. Grant access to repos: `openclaw` at minimum, or all repos
5. Verify: ask Chad "Using the GitHub connector, show me the file tree of nayslayer143/openclaw"

## If GitHub Connector Is Not Available

The connector may be under a different name or behind a feature flag. Alternatives:

**Option A — Upload context file (recommended)**
Run `chad-context` in terminal, then upload `~/openclaw/outputs/CHAD-CONTEXT.md` to your ChatGPT Project as a pinned file (Plus supports up to 20 files).

**Option B — API bridge**
Use the existing `~/openclaw/chatgpt-mcp/` integration for programmatic access.

**Option C — Manual paste**
Copy the contents of `CHAD-CONTEXT.md` into the start of each conversation.

## Keeping Context Fresh

The `chad-context` alias regenerates the file on demand. A cron job runs it daily at 6am. Re-upload to ChatGPT after significant changes.
