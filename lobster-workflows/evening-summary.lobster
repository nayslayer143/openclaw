# evening-summary.lobster
# Schedule: daily at 6pm (0 18 * * *)
# Agent: Orchestrator
# Output: day summary → Telegram, triggers nightly consolidation

name: evening-summary
description: "Compile day's work, list tomorrow's schedule, trigger nightly consolidation"
trigger:
  cron: "0 18 * * *"

steps:
  - id: read_day_logs
    action: shell
    description: "Gather today's agent log summaries"
    command: "wc -l ~/openclaw/logs/*-$(date +%Y-%m-%d).jsonl 2>/dev/null || echo '0 total'"
    timeout_seconds: 5

  - id: read_completed
    action: shell
    description: "Count today's completed tasks"
    command: "python3 -c \"import json; data=json.load(open('$HOME/openclaw/queue/completed.json')); print(len([t for t in data if t.get('completed_date','').startswith('{{today}}')]))\""
    timeout_seconds: 5

  - id: read_pending
    action: shell
    description: "Count remaining pending tasks"
    command: "python3 -c \"import json; print(len(json.load(open('$HOME/openclaw/queue/pending.json'))))\""
    timeout_seconds: 5

  - id: list_tomorrow_crons
    action: template
    description: "List scheduled Lobster crons for tomorrow"
    template: |
      Scheduled for tomorrow:
      - 07:00 daily-intel-lite (Intel Scan)
      - 08:00 morning-brief (Morning Brief)
      - */30  system-health (Health Checks)
      - 18:00 evening-summary (This workflow)
      - 23:00 nightly consolidation (Memory)

  - id: compile_summary
    action: agent
    agent: orchestrator
    model: "qwen2.5:7b"
    description: "Compile evening summary"
    prompt: |
      Compile an evening summary:
      - Log activity: {{read_day_logs.output}}
      - Tasks completed today: {{read_completed.output}}
      - Tasks still pending: {{read_pending.output}}
      - Tomorrow's schedule: {{list_tomorrow_crons.output}}

      Format:
      📊 Day Summary:
      - Completed: [count + brief]
      - Pending: [count]
      - Issues: [any from logs, or "None"]

      📅 Tomorrow: [scheduled items]

      Keep it under 10 lines.

  - id: deliver
    action: telegram
    description: "Send evening summary"
    message: |
      🌙 Evening Summary — {{today}}
      {{compile_summary.output}}
    tier: 1

  - id: log
    action: append_file
    output: "~/openclaw/memory/IDLE_LOG.md"
    template: |
      ### Evening Summary — {{today}} 18:00
      - Tasks completed: {{read_completed.output}}
      - Tasks pending: {{read_pending.output}}
      - Nightly consolidation: scheduled for 23:00
