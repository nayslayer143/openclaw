0a. Study `specs/*` with up to 500 parallel Sonnet subagents to learn the application specifications.
0b. Study @IMPLEMENTATION_PLAN.md to understand current priorities.
0c. Study existing source with up to 500 parallel Sonnet subagents to understand what's already built.

1. Your task is to implement functionality per the specifications using parallel subagents. Follow @IMPLEMENTATION_PLAN.md and choose the most important incomplete item. Before making changes, search the codebase (don't assume not implemented) using Sonnet subagents. Use up to 500 parallel Sonnet subagents for searches/reads. Use only 1 Sonnet subagent for build/tests. Use Opus subagents for complex reasoning (debugging, architectural decisions).

2. After implementing, run the tests for the unit of code improved. If functionality is missing, add it per specs. Ultrathink.

3. When you discover issues, immediately update @IMPLEMENTATION_PLAN.md using a subagent. When resolved, remove the item.

4. When tests pass: update @IMPLEMENTATION_PLAN.md, then `git add -A`, then `git commit` with a message describing the changes.

99999. Capture the why in all documentation — tests and implementation notes must explain importance.
999999. Single sources of truth. No migrations or adapters. If unrelated tests fail, resolve them.
9999999. Keep @IMPLEMENTATION_PLAN.md current using a subagent — future loops depend on this.
99999999. Keep @AGENTS.md operational only (build/run/test commands + codebase patterns). No status updates in AGENTS.md — those belong in IMPLEMENTATION_PLAN.md.
999999999. Implement functionality completely. DO NOT IMPLEMENT PLACEHOLDER OR STUB IMPLEMENTATIONS. FULL IMPLEMENTATIONS ONLY.
9999999999. When @IMPLEMENTATION_PLAN.md becomes large, clean completed items using a subagent.
99999999999. If specs are inconsistent, use an Opus subagent to resolve and update the spec.
999999999999. When you learn how to run the application correctly, update @AGENTS.md using a subagent — keep it brief.
9999999999999. For any bugs noticed (even unrelated to current work), resolve them or document in @IMPLEMENTATION_PLAN.md.
