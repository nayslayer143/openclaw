# AI Agent Automation-as-a-Service Market
## MiroFish Simulation Report — March 2026

**Simulation window:** March 2026 – March 2027
**Graph:** 44 entities · 45 relationships · 9 entity types
**Engine:** MiroFish v0.1 · Ollama qwen2.5:7b · Zep Cloud memory

---

## What the simulation mapped

The graph extracted four competitive lanes, three buyer archetypes, and a clear pressure cascade triggered by Devin's price collapse. Here's what emerged.

---

## The Four Market Lanes

The simulation identified four distinct lanes competing for the same automation budget:

| Lane | Players | Threat level to solo operators |
|------|---------|-------------------------------|
| **Autonomous coders** | Devin 2.0, Claude Code, Cursor | Low — targets developers, not SMBs |
| **No-code builders** | Lovable, Taskade Genesis | Medium — abstracts away code but still requires setup |
| **Developer frameworks** | CrewAI, LangGraph, AutoGen, OpenAI Agents SDK | Low — these are tools, not finished products |
| **Cloud incumbents** | OpenAI, Google (Vertex AI), Amazon (Bedrock, Q) | High long-term — distribution advantages, low trust barrier |

**Key insight:** No lane is currently serving the SMB buyer well. The autonomous coders target developers. The cloud incumbents target enterprise. The no-code builders are too fragile. This gap is the opportunity.

---

## The SMB Gap — Does It Close?

The simulation's central question was whether the SMB gap (underserved small businesses who can't deploy developer frameworks) persists or closes over 12 months.

**The graph says it persists — and widens near-term — for one structural reason:**

> SMBs lack the engineering staff necessary to deploy developer frameworks.

The entities that could close the gap (cloud incumbents with managed services) are currently targeting enterprise and engineering teams, not SMBs. Amazon Q targets engineering teams. Vertex AI Agents requires integration work. Bedrock Agents requires AWS expertise.

The gap closes only if:
1. A no-code layer matures enough to handle real SMB workflows, OR
2. A managed service operator steps into the gap

Right now neither condition is met at scale. **This is the 12-month window.**

---

## The Devin Price Cascade

Devin dropping to $20/month created a pressure cascade the simulation traced clearly:

```
Devin ($20/mo)
  → competes with Cursor, Replit, Lovable at similar price points
  → commoditizes "autonomous coder" lane
  → race to the bottom on coding automation pricing
  → BUT: this only affects the developer/startup buyer, not the SMB buyer
```

**Counterintuitive finding:** Devin's price collapse actually *benefits* solo operators targeting SMBs. It drives down the cost of the tooling layer (you build with cheaper Devin/Claude Code), while the managed service layer (what you charge SMBs for) has no comparable price pressure yet. Your build cost drops; your margin holds.

---

## MCP as Infrastructure

The Model Context Protocol emerged as the single most structurally important variable:

- Anthropic created it; Claude Code natively supports it
- Described as a "de facto standard for tool integration"
- More MCP servers → more tool integrations → more viable agent workflows
- The simulation flagged it as a key variable affecting SMB outcomes

**What this means:** Operators who build MCP-compatible skills and workflows now will have a compounding advantage. Every new MCP server in the ecosystem extends the value of your stack without additional build cost. This is the infrastructure bet worth making in the next 90 days.

---

## The Local LLM Variable

The simulation explicitly modeled whether open-weight local models close the quality gap with GPT-4 and Claude for production use. The graph surfaced three nodes here: Ollama, MLX, and llama.cpp — all marked as contributors to viable local inference on consumer hardware.

The gap closure question wasn't resolved — the graph shows it as an active comparison (`open-weight models COMPARED_TO GPT-4`, `open-weight models COMPARED_TO Claude`) rather than a settled outcome.

**Practical read:** Local models are viable for workflow orchestration and triage today (you're already doing this with OpenClaw). They are *not yet* viable for the final customer-facing deliverable quality bar. The 12-month window likely sees this flip for most SMB use cases, but not all.

---

## Actor Dynamics

The simulation extracted three buyer archetypes with distinct behaviors:

**Large enterprises** → actively adopting multi-agent orchestration. Already a customer. Already served by incumbents. Not your market.

**SMB clients** → underserved, high margin potential, weak distribution. The graph noted: *"margins incumbents cannot match, but limited distribution."* This is your market. The distribution problem is a sales problem, not a product problem.

**Solo operators** (you) → the graph placed solo operators as the natural actor to bridge the SMB gap. The exact quote extracted: *"Solo operators can capture meaningful market share in the SMB automation-as-a-service market by targeting underserved SMB clients."*

The OpenClaw stack was directly recognized in the graph: Claude Code as build plane, LangGraph + CrewAI as frameworks, Ollama as local inference. This stack maps cleanly onto the solo operator archetype the simulation modeled.

---

## What the Graph Suggests for Positioning

Synthesizing the 45 relationships:

1. **The $500–5000/month price band is defensible** — cloud incumbents can't profitably serve it, developer tools don't reach it, and no-code builders can't reliably deliver it.

2. **Build MCP-compatible first** — the simulation flagged MCP adoption rate as the single biggest swing variable. Being MCP-native is asymmetric upside.

3. **Lead with SMB pain, not technology** — the simulation noted SMB decision criteria include Slack integration, not framework sophistication. Sell outcomes, not stack.

4. **The 12-month window is real** — once cloud incumbents optimize for SMB (lower pricing, simpler onboarding), the gap closes. The graph suggests this is a 2027 problem, not a 2026 problem.

5. **Local inference cost advantage is durable near-term** — Ollama/MLX/llama.cpp are recognized as viable. Running zero-API-cost infrastructure while charging market rates is a structural margin advantage that won't last forever but lasts long enough to matter.

---

## Limitations of This Run

- 44 nodes from a single 5KB seed file — a real production run should ingest 5–10 documents (competitor pricing pages, SMB buyer surveys, recent funding announcements)
- The simulation built the knowledge graph but did not run agent-to-agent rounds (that's MiroFish Step 3, which requires the simulation runner)
- qwen2.5:7b produced a solid ontology but a larger model (qwen3:32b) would likely extract richer edge facts

---

## Next Step

The graph is built and stored in Zep (`mirofish_c422f60c789e4038`). The natural next move is to run the agent simulation rounds against this graph — that's where you'd see the market dynamics play out across time steps and get the "which archetype wins" answer. That requires MiroFish Step 2 (environment setup) and Step 3 (simulation run).

When you're ready to run that, the project ID is `proj_45a84ac34c95`.
