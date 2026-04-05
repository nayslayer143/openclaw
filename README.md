---
project: openclaw
type: trading-agent
stack: [python, sqlite, bash, yaml]
status: active
github: https://github.com/nayslayer143/openclaw
gitlab: https://gitlab.com/jordan291/openclaw
instance: Clawmpson
parent: none
children: [arbclaw, rivalclaw, quantumentalclaw]
---

# OpenClaw

AI operating system for web-based businesses — agent orchestration, trading, research, content, and automation on a single M2 Max.

## What This Is

OpenClaw is the central nervous system that runs a fleet of AI agents. Trading bots, research engines, content pipelines, and build systems all route through here. Claude Code is the build plane, local Ollama models handle inference at zero API cost, and deterministic Lobster workflows handle scheduling and approval gates.

## Architecture

- **Agent orchestration** — 13+ specialized agents each own a domain
- **Trading stack** — paper trading across Polymarket and equities with multiple parallel strategies
- **Research engine** — automated multi-domain research (market intel, content, academic, competitive)
- **Lobster workflows** — YAML-based deterministic pipelines with schedule and approval gates
- **Memory layer** — learns from past runs, surfaces patterns over time

## Key Files

| File/Dir | Purpose |
|----------|---------|
| `CLAUDE.md` | Agent instructions and workspace map |
| `CONTEXT.md` | Task router — start here |
| `CONSTRAINTS.md` | Non-negotiable rules |
| `openclaw-v4.1-strategy.md` | Full strategy document |
| `agents/configs/` | 13 agent configuration files |
| `scripts/mirofish/` | Advanced trading brain (10 modules) |
| `dashboard/` | Next.js monitoring dashboard |

## Quick Start

```bash
git clone https://github.com/nayslayer143/openclaw.git
cd openclaw
cat CONTEXT.md  # Route to the right workspace
```

## Related Projects

| Project | Relationship | Repo |
|---------|-------------|------|
| ArbClaw | Child — minimal arb bot | [GitHub](https://github.com/nayslayer143/arbclaw) |
| RivalClaw | Child — arb architecture comparison | [GitHub](https://github.com/nayslayer143/rivalclaw) |
| QuantumentalClaw | Child — signal fusion engine | [GitHub](https://github.com/nayslayer143/quantumentalclaw) |
| CodeMonkeyClaw | Sibling — engineering agent | [GitHub](https://github.com/nayslayer143/codemonkeyclaw) |

## License

Private project.
