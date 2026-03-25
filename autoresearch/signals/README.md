# OpenClaw Signal Bus

Shared directory where all crawlers write their latest signals.
Trading bots and the Gonzoclaw Intel page read from here.

## Files

Each platform writes:
- `{platform}.json` — latest signal snapshot (bots read this)

## Schema

See `~/openclaw/autoresearch/CRAWLER-FLEET-SPEC.md` for the shared signal format.
