# Web Interface Guide — OpenClaw Ecosystem

## What's Already Running

**OpenClaw Dashboard** — `http://localhost:7080`
- FastAPI backend: `~/openclaw/dashboard/server.py`
- Start: `cd ~/openclaw/dashboard && python3 server.py`
- Auth: GitHub OAuth (or localhost skips auth)

### New endpoints (added 2026-04-05):
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/codemonkey/orders` | GET | List all work orders (optional `?status=QUEUED`) |
| `/api/codemonkey/orders` | POST | Submit a new work order |
| `/api/codemonkey/orders/{id}` | GET | Get single work order |
| `/api/codemonkey/stats` | GET | Queue summary stats |

**Submit a work order via dashboard API:**
```bash
curl -X POST http://localhost:7080/api/codemonkey/orders \
  -H "Content-Type: application/json" \
  -d '{"type":"fix","target_repo":"nayslayer143/myclaw","description":"Fix the timeout bug","priority":"high"}'
```

---

## Recommended Full Web UI: Lobe Chat

Lobe Chat is the best self-hosted multi-agent chat UI. Stars: 50k+. Stack: Next.js. Deploy in minutes.

### Why Lobe Chat for OpenClaw
- Multi-model: Claude, OpenAI, Ollama (all your models in one place)
- Plugin system: add OpenClaw as a "plugin" (API endpoint)
- Multi-agent: configure Clawmpson, RivalClaw, QuantumentalClaw as separate "personas"
- Self-hostable: runs on localhost:3210

### Quick Install
```bash
# Option 1: Docker (fastest)
docker run -d -p 3210:3210 \
  -e OPENAI_API_KEY=your_key \
  -e ANTHROPIC_API_KEY=your_key \
  --name lobechat \
  lobehub/lobe-chat

# Option 2: npm
npx @lobehub/chat
```

### Configure Your Claws as Agents

In Lobe Chat Settings → Agents → New Agent:

**Clawmpson (Primary Orchestrator):**
```
Name: Clawmpson
System Prompt: You are Lobster S. Clawmpson, Jordan's primary AI business orchestrator.
  You manage ArbClaw, PhantomClaw, and other sub-agents. You're based at ~/openclaw/.
  When Jordan gives you a task, route it to the right sub-agent or handle it directly.
Model: claude-sonnet-4-6
```

**RivalClaw (Trading):**
```
Name: RivalClaw
System Prompt: You are RivalClaw, Jordan's trading arbitrage agent. You're laser-focused
  on finding and executing trading opportunities across markets and prediction platforms.
  Based at ~/rivalclaw/. Report P&L, positions, and signals concisely.
Model: claude-sonnet-4-6
```

**QuantumentalClaw (Signals):**
```
Name: QuantumentalClaw
System Prompt: You are QuantumentalClaw, Jordan's signal fusion engine. You analyze
  asymmetric opportunities across equities and prediction markets using a 5-module
  pipeline: asymmetry, narrative, event, edgar, quant signals. Based at ~/quantumentalclaw/.
Model: claude-opus-4-6 (use Opus for deep signal analysis)
```

**CodeMonkeyClaw (Engineering):**
```
Name: CodeMonkeyClaw
System Prompt: You are CodeMonkeyClaw, Head of Engineering. You receive work orders and
  dispatch them to open models (Qwen/DeepSeek). Submit orders via:
  python3 ~/codemonkeyclaw/run.py submit --type fix --target REPO --description "..."
  Based at ~/codemonkeyclaw/.
Model: claude-haiku-4-5 (cheap; real work goes to open models)
```

### Add OpenClaw Dashboard as a Plugin

In Lobe Chat → Settings → Plugins → Custom Plugin:
```json
{
  "identifier": "openclaw-dashboard",
  "meta": {
    "title": "OpenClaw Dashboard",
    "description": "Query agent status, submit work orders, check activity"
  },
  "api": [
    {"path": "/api/agents", "method": "GET", "description": "List all agents and status"},
    {"path": "/api/codemonkey/stats", "method": "GET", "description": "Work order queue stats"},
    {"path": "/api/codemonkey/orders", "method": "POST", "description": "Submit work order"}
  ],
  "server": {"url": "http://localhost:7080"}
}
```

---

## Alternative: Agent Chat UI (LangChain)

For a cleaner, more minimal agent-chat experience:
```bash
git clone https://github.com/langchain-ai/agent-chat-ui
cd agent-chat-ui && npm install && npm run dev
```
Point it at your OpenClaw gateway API. Best if you want to build a custom LangGraph agent graph around the Claws.

---

## Architecture Decision

| Option | Pros | Cons | Best for |
|--------|------|------|---------|
| Lobe Chat | Polished, multi-model, extensible | Docker/npm dep | Daily chat with all Claws |
| Agent Chat UI | Minimal, hackable | Requires LangGraph backend | Custom agent orchestration |
| OpenClaw Dashboard | Already running, auth included | No chat UI | Ops monitoring |

**Recommendation:** Run all three:
- Dashboard on :7080 — ops/monitoring
- Lobe Chat on :3210 — daily agent chat
- Agent Chat UI on :3000 — if you build LangGraph routing later
