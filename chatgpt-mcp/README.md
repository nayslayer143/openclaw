# OpenClaw ChatGPT MCP Server

Bridges Claude Code → ChatGPT for deep research and terminal insights.

## Setup

### 1. Install dependencies

```bash
cd ~/openclaw/chatgpt-mcp
npm install
```

### 2. Add your OpenAI API key to `~/openclaw/.env`

```bash
echo 'OPENAI_API_KEY=sk-your-key-here' >> ~/openclaw/.env
```

### 3. Register with Claude Code

Run this once from anywhere:

```bash
claude mcp add chatgpt \
  --scope project \
  --env OPENAI_API_KEY=sk-your-key-here \
  -- node ~/openclaw/chatgpt-mcp/server.js
```

Or add it globally (available in all projects):

```bash
claude mcp add chatgpt \
  --scope user \
  --env OPENAI_API_KEY=sk-your-key-here \
  -- node ~/openclaw/chatgpt-mcp/server.js
```

### 4. Verify it works

Start Claude Code and run:
```
/mcp
```
You should see `chatgpt` listed with two tools: `deep_research` and `terminal_insights`.

## Tools

### `deep_research`
- **Model:** GPT-4o (configurable)
- **Use for:** Market research, competitive analysis, technical deep-dives
- **Formats:** brief, detailed, bullet_points
- **Cost:** ~$0.01-0.05 per call

### `terminal_insights`
- **Model:** GPT-4o-mini (configurable)
- **Use for:** Error diagnosis, build output, log analysis, test results
- **Cost:** ~$0.001-0.005 per call

## Terminal Watcher (Optional)

For passive terminal monitoring:

```bash
# Source it in your shell to watch continuously
source ~/openclaw/chatgpt-mcp/terminal-watcher.sh

# Or pipe a specific command
npm run build 2>&1 | ~/openclaw/chatgpt-mcp/terminal-watcher.sh --analyze

# Read latest insights
cat ~/openclaw/chatgpt-mcp/.terminal-insights.md
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | (required) | Your OpenAI API key |
| `CHATGPT_RESEARCH_MODEL` | `gpt-4o` | Model for deep_research |
| `CHATGPT_TERMINAL_MODEL` | `gpt-4o-mini` | Model for terminal_insights |
| `CHATGPT_RESEARCH_MAX_TOKENS` | `4096` | Max response tokens for research |
| `CHATGPT_TERMINAL_MAX_TOKENS` | `1024` | Max response tokens for terminal |
| `TERMINAL_WATCH_INTERVAL` | `60` | Seconds between watcher analyses |

## Cost Control

- Terminal insights use gpt-4o-mini (~$0.15/1M input tokens)
- Research uses gpt-4o (~$2.50/1M input tokens)
- Long terminal outputs are auto-truncated to ~12k chars
- Session token usage is logged to stderr
- Fits within OpenClaw's $10/day budget alongside Ollama
