0a. Study `specs/*` with up to 250 parallel Sonnet subagents to learn the application specifications.
0b. Study @IMPLEMENTATION_PLAN.md (if present) to understand the plan so far.
0c. Study `src/` or existing source with up to 250 parallel Sonnet subagents to understand what already exists.

1. Use up to 500 Sonnet subagents to compare existing source against `specs/*`. Use an Opus subagent to analyze findings, prioritize tasks, and create/update @IMPLEMENTATION_PLAN.md as a bullet point list sorted by priority of items yet to be implemented. Ultrathink. Search for TODOs, minimal implementations, placeholders, skipped/flaky tests, and inconsistent patterns.

IMPORTANT: Plan only. Do NOT implement anything. Do NOT assume functionality is missing — confirm with code search first.

ULTIMATE GOAL: We want to achieve a complete, production-ready implementation per specs/*. If a spec is missing for something clearly needed, author it at `specs/FILENAME.md` and document the plan in @IMPLEMENTATION_PLAN.md using a subagent.
