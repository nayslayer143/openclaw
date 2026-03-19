# CONTEXT.md — [PROJECT_NAME] Router

Route your task through this file before loading anything else.

---

## Task Routing

| If the task is... | Start here | You'll also need | Skip initially |
|-------------------|-----------|------------------|-----------------------|
| Implement a feature or fix | `build/CONTEXT.md` | Task packet, relevant source files | docs/, marketing |
| Review or audit code | `build/CONTEXT.md` | Diff or PR, test results | unrelated source |
| Update documentation | `docs/` | Related source code for accuracy | test files, build scripts |
| Configure CI/CD or scripts | `scripts/` | Current deploy config | source code |
| Understand the codebase | `CLAUDE.md` → `build/CONTEXT.md` (EXPLORE mode) | — | everything else |

---

## Handoffs

- **Receives from:** `~/openclaw/repo-queue/` (task packets)
- **Hands off to:** `~/openclaw/build-results/` (output contracts), `~/openclaw/memory/` (summaries)
