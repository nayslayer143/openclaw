# daily-intel-lite.lobster
# Schedule: daily at 7am (0 7 * * *)
# Agent: Research Agent
# Output: morning intel brief → Telegram

name: daily-intel-lite
description: "Extract highest-signal items from scout reports for morning brief"
trigger:
  cron: "0 7 * * *"

steps:
  - id: scan_outputs
    action: glob
    description: "Find unprocessed scout reports"
    pattern: "~/openclaw/outputs/*-scout-*.md"
    filter: "modified_after: {{yesterday}}"

  - id: extract_intel
    action: agent
    agent: research
    model: "qwen2.5:32b"
    condition: "scan_outputs.files | length > 0"
    description: "Research Agent extracts 1-3 highest-signal items"
    prompt: |
      Review these scout reports from the last 24 hours:
      {{scan_outputs.files | join: '\n'}}

      Extract the 1-3 highest-signal items. For each:
      - What it is (1 sentence)
      - Why it matters to Jordan's businesses (1 sentence)
      - Recommended action: investigate | watch | ignore

      No simulation. No speculation. Signal only.

  - id: format_brief
    action: template
    description: "Format morning brief"
    template: |
      ☀️ Morning Intel Brief — {{date}}

      {{extract_intel.output}}

      Scout reports processed: {{scan_outputs.files | length}}

  - id: deliver
    action: telegram
    description: "Send morning brief"
    message: "{{format_brief.output}}"
    tier: 1

  - id: log
    action: append_file
    output: "~/openclaw/memory/IDLE_LOG.md"
    template: |
      ### Intel Scan — {{date}} {{time}}
      - Reports scanned: {{scan_outputs.files | length}}
      - Items surfaced: {{extract_intel.item_count | default: 0}}
