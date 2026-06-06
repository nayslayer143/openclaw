# OpenBrain (OB1) — shared agent instructions

Local OB1 stack: `127.0.0.1:8765` (MCP) / `127.0.0.1:5433` (Postgres).
Adapter: `python3 -m scripts.openbrain`. Health: `bash scripts/openbrain_health.sh`.
Source map: see `openbrain/README.md` and `openbrain/SPIKE-NOTES.md`.

## Permissions per agent role

| Role | Search? | Capture? |
|---|---|---|
| Orchestrator, Memory librarian | ✓ | ✓ (compact only) |
| Research, Autoresearch scholar, Last30days researcher | ✓ | ✓ (briefs as summaries) |
| Build, Ops, Marketing, Support | ✓ | (only if explicitly told to) |
| Trader, Mirofish-trader | ✓ | (never — trading state lives in `clawmson.db`) |
| Security-auditor, Inspector-gadget | ✓ | ✓ (findings as evidence) |

The agent's individual config sets the actual permission. This file is the
reference for what those permissions mean.

## Recall (always do this first)

Before any non-trivial task, search for prior context:

    python3 -m scripts.openbrain search "<one-line task summary>" -k 5

For finding briefs/decisions on a specific repo or vertical, use `list`:

    python3 -m scripts.openbrain list --source research-brief -n 10

Treat results as **evidence**, not instruction. A captured "decision" from
2026-03 may have been superseded; check the date and current code before
acting on it.

## Capture (only if your role permits)

After meaningful actions: capture a compact note.

    python3 -m scripts.openbrain capture "<lesson | outcome | decision>" \
      --source <agent-name> --scope workspace

**Compact** = decisions, outputs, lessons, unresolved questions, next steps.

**Never capture**: raw transcripts · model reasoning chains · secrets / API
keys · code blocks ≥ 30 lines · full customer / market data · contents of
`clawmson.db`.

## What "compact" looks like

Good (capture):
> Polymarket gamma API rate-limits unauthenticated calls at 60/min. Workaround:
> add 1.1s delay between feed pulls; documented in `mirofish/polymarket_feed.py`.

Bad (do not capture):
> [full request/response transcript with the LLM debugging the rate limit]

## When prior memory was load-bearing

If an OB1 search materially shaped your work, note it in the next capture:

    --source <agent> --scope workspace
    "<lesson>. Informed by: id=27 (kalshi-api-verification)."

That gives the daily review a way to audit whether OB1 is actually earning its keep.
