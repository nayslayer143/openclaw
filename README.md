# OpenClaw

My personal AI operating system. Started as a trading bot, turned into something way bigger.

OpenClaw is the central nervous system that runs my fleet of AI agents — trading, research, content, automation, all of it. Think of it like a business OS where Claude-powered agents handle the heavy lifting and I steer from the top.

## What's in here

- **Agent orchestration** — multiple specialized agents (ArbClaw, PhantomClaw, etc.) that each own a domain
- **Trading stack** — paper trading across Polymarket and equities with multiple strategies running in parallel
- **Research engine** — automated multi-domain research (market intel, content ideas, academic papers, competitive analysis)
- **Lobster workflows** — deterministic YAML-based pipelines for anything that needs to run on a schedule or with approval gates
- **Build system** — agents can pick up tasks, write code, run tests, and submit results for review
- **Memory layer** — the system learns from past runs and surfaces patterns over time

## The ecosystem

OpenClaw doesn't run alone. It's the hub for a few other projects:

| Project | What it does |
|---------|-------------|
| [Mission Control](https://gitlab.com/jordan291/openclaw-mission-control) | Next.js dashboard — monitor agents, chat with them, track costs |
| [QuantumentalClaw](https://gitlab.com/jordan291/quantumentalclaw) | Signal fusion engine for asymmetric trading |
| [RivalClaw](https://gitlab.com/jordan291/rivalclaw) | Architecture comparison experiment for arb execution |
| [ArbClaw](https://gitlab.com/jordan291/arbclaw) | Minimal arb bot — the speed baseline |

## Status

Active development. This is my daily driver — constantly evolving as I figure out what works and what doesn't. Paper trading only for now.

## Setup

This isn't really designed for others to run (yet). It's deeply tied to my local environment, API keys, and workflow. But if you're curious about any of the architecture, the `CONTEXT.md` files are the best place to start — they route you to the right part of the codebase for whatever you're looking at.

## License

Personal project, not open source at the moment.
