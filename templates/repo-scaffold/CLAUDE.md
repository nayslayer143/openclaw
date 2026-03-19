# [PROJECT_NAME]

> [One-sentence project description]

## Commands
- **Test:** `./scripts/test.sh`
- **Lint:** `./scripts/lint.sh`
- **Build:** `./scripts/build.sh`
- **Dev server:** `./scripts/dev.sh`
- **Deploy staging:** `[Tier-2 — command here]`
- **Deploy production:** `[Tier-3 only — command + confirmation required]`

## Forbidden
- Never edit main branch directly
- Never rm -rf without explicit approval
- Never deploy production without Tier-3 confirmation

## Context Routing
See `CONTEXT.md` for task routing. See `build/CONTEXT.md` for implementation workflow.

## Structure
```
[PROJECT_NAME]/
├── CLAUDE.md           ← you are here (map only)
├── CONTEXT.md          ← router
├── .claude/
│   ├── settings.json   ← hooks config
│   └── agents/
├── build/
│   └── CONTEXT.md      ← 4-mode implementation workspace
├── scripts/
│   ├── test.sh
│   ├── lint.sh
│   ├── build.sh
│   └── dev.sh
├── src/
├── tests/
└── docs/
```
