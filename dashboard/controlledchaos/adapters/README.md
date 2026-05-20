# Style-Guide Adapters

Style guides describe a vibe. Controlled Chaos renders it. The bridge is `style.json`.

This folder is the *contract layer*:

| File | Purpose |
|---|---|
| `style-schema.json` | Machine-readable JSON Schema. SSG/PSE exporters target this. |
| `from-style-json.md` | Agent-readable workflow. Read this when consuming a `style.json`. |
| `examples/minimal.json` | Bare minimum that validates (name + palette only). |
| `examples/dusk.json` | Rich example: editorial warmth, full palette + typography + forces. |
| `examples/signal.json` | Rich example: neon kinetic, motion-heavy, grain texture. |

## Direction

One-way: external tools emit `style.json`; this skill consumes it. SSG-side and
PSE-side exporters live in their own repos and target `style-schema.json` as the
spec.

## Image policy

Style guides describe a vibe — they do not supply page imagery. The schema
deliberately omits image fields. Source-board images are reference-only.
