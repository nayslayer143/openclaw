# daily-market-intel.lobster
# Schedule: daily at 6:30am (0 6 * * *)
# Agent: Research Agent → MiroFish → Telegram approval
# Output: market intel report → outputs/market-intel-{date}.md
# Phase 3 — requires MiroFish validation (SCORING_RUBRIC.md ≥3.5 average)

name: daily-market-intel
description: "Produce daily market intelligence report using scout data + MiroFish simulation"
trigger:
  cron: "0 6 * * *"

steps:
  - id: check_scouts
    action: shell
    description: "Find today's scout reports"
    command: "ls ~/openclaw/outputs/bookmark-scout-$(date +%Y-%m-%d)*.md ~/openclaw/outputs/reddit-scout-$(date +%Y-%m-%d)*.md 2>/dev/null || echo 'none'"
    timeout_seconds: 5

  - id: skip_if_empty
    action: validate
    condition: "check_scouts.output != 'none'"
    description: "Skip if no scout reports today"
    on_fail: "log_skip"

  - id: extract_items
    action: agent
    agent: research
    model: "qwen2.5:32b"
    description: "Extract 2-3 market-relevant items from scout reports"
    prompt: |
      Review today's scout reports:
      {{check_scouts.output}}

      Extract 2-3 items most relevant to market intelligence (finance, tech, business trends).
      For each item:
      - Topic (1 sentence)
      - Source and credibility assessment
      - Why it matters for Jordan's businesses
      - Seed text for MiroFish simulation (500 words max)

  - id: run_mirofish
    action: shell
    description: "Run MiroFish simulation per extracted item"
    condition: "extract_items.items | length > 0"
    command: |
      cd ~/openclaw/mirofish && python3 run_simulation.py \
        --agents 100 \
        --rounds 20 \
        --seed "{{extract_items.items[0].seed_text}}" \
        --model qwen2.5:32b \
        --output ~/openclaw/outputs/market-intel-$(date +%Y-%m-%d).md
    timeout_minutes: 30

  - id: compile_report
    action: agent
    agent: research
    model: "qwen2.5:32b"
    description: "Compile final market intel report"
    prompt: |
      Compile a market intelligence report from:
      - Extracted items: {{extract_items.output}}
      - MiroFish simulation results: {{run_mirofish.output}}

      Format as a clean, professional report with:
      - Executive summary (3 sentences max)
      - Per-item analysis with MiroFish insights
      - Recommended actions (prioritized)
      - Confidence level per recommendation

      Save to: ~/openclaw/outputs/market-intel-$(date +%Y-%m-%d).md

  - id: request_approval
    action: telegram
    description: "Tier-2: approve market intel for delivery"
    message: |
      📊 Market Intel Ready — {{today}}

      {{compile_report.executive_summary}}

      Items analyzed: {{extract_items.items | length}}
      MiroFish: 100 agents, 20 rounds

      Report: ~/openclaw/outputs/market-intel-{{today}}.md

      Reply /approve-intel-{{today}} to mark as deliverable
      Reply /deny-intel-{{today}} to reject
    tier: 2

  - id: log_skip
    action: append_file
    condition: "check_scouts.output == 'none'"
    output: "~/openclaw/memory/IDLE_LOG.md"
    template: |
      ### Market Intel Skip — {{today}}
      - No scout reports found for today. Skipped.
