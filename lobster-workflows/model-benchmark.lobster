# model-benchmark.lobster
# Schedule: monthly on 1st at 10pm (0 22 1 * *)
# Agent: Orchestrator → benchmark tests → results
# Output: bakeoff results → benchmark/bakeoff-{date}.md
# Phase 4 — monthly model evaluation

name: model-benchmark
description: "Monthly model bakeoff — test current models against challengers"
trigger:
  cron: "0 22 1 * *"

steps:
  - id: check_challengers
    action: agent
    agent: research
    model: "qwen2.5:7b"
    description: "Check if any new model releases warrant benchmarking"
    prompt: |
      Check the Ollama model library for any new releases in the last 30 days
      that could challenge our current model assignments:
      - Agent work (currently qwen2.5:32b): any new 30B+ dense models?
      - Coding (currently deepseek-coder:33b): any new code-specialized models?
      - Fast triage (currently qwen2.5:7b): any new 7-14B models with better tool-calling?

      Output: list of challenger models worth benchmarking, or "no challengers" if none.

  - id: pull_challengers
    action: shell
    condition: "check_challengers.output != 'no challengers'"
    description: "Pull challenger models"
    command: "{{check_challengers.pull_commands}}"
    timeout_minutes: 60

  - id: run_bakeoff
    action: agent
    agent: orchestrator
    model: "qwen2.5:32b"
    description: "Run structured bakeoff protocol"
    prompt: |
      Run the bakeoff protocol from ~/openclaw/openclaw-v4.1-strategy.md Model Policy section.

      Current champions:
      - Agent: qwen2.5:32b
      - Code: deepseek-coder:33b
      - Fast: qwen2.5:7b

      Challengers: {{check_challengers.output}}

      For each matchup:
      1. 10 chained tool-call tasks — record format errors, retries, completion rate
      2. 10 code-analysis tasks — record latency, accuracy
      3. 5 long-context summarizations (8K+) — record quality, truncation

      Save results to ~/openclaw/benchmark/bakeoff-{{date}}.md
      Include clear winner per role with evidence.

  - id: notify
    action: telegram
    description: "Report bakeoff results"
    message: |
      🏆 Monthly Model Bakeoff — {{date}}

      {{run_bakeoff.summary}}

      Full results: ~/openclaw/benchmark/bakeoff-{{date}}.md

      {% if run_bakeoff.changes_recommended %}
      🟡 Tier-2: Model assignment changes recommended.
      Reply /approve-bakeoff-{{date}} to update CONSTRAINTS.md
      {% else %}
      ✅ Current assignments confirmed. No changes needed.
      {% endif %}
    tier: "{% if run_bakeoff.changes_recommended %}2{% else %}1{% endif %}"

  - id: log
    action: append_file
    output: "~/openclaw/memory/IDLE_LOG.md"
    template: |
      ### Monthly Bakeoff — {{date}}
      - Challengers tested: {{check_challengers.challenger_count | default: 0}}
      - Changes recommended: {{run_bakeoff.changes_recommended | default: false}}
      - Results: benchmark/bakeoff-{{date}}.md
