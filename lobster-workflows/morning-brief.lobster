# morning-brief.lobster
# Schedule: daily at 8am (0 8 * * *)
# Agent: Orchestrator
# Output: morning summary → Telegram

name: morning-brief
description: "Compile overnight results and pending approvals for morning check-in"
trigger:
  cron: "0 8 * * *"

steps:
  - id: read_idle_log
    action: shell
    description: "Get overnight IDLE_LOG entries"
    command: "grep '{{yesterday}}\\|{{today}}' ~/openclaw/memory/IDLE_LOG.md 2>/dev/null || echo 'No overnight entries'"
    timeout_seconds: 5

  - id: read_completed
    action: shell
    description: "Count completed tasks"
    command: "python3 -c \"import json; data=json.load(open('$HOME/openclaw/queue/completed.json')); print(len([t for t in data if t.get('completed_date','').startswith('{{today}}')]))\""
    timeout_seconds: 5

  - id: read_pending
    action: shell
    description: "Count pending tasks"
    command: "python3 -c \"import json; print(len(json.load(open('$HOME/openclaw/queue/pending.json'))))\""
    timeout_seconds: 5

  - id: compile_brief
    action: agent
    agent: orchestrator
    model: "qwen2.5:7b"
    description: "Compile morning brief (use fast model — simple formatting)"
    prompt: |
      Compile a morning brief from this data:
      - Overnight idle log: {{read_idle_log.output}}
      - Completed today: {{read_completed.output}} tasks
      - Pending queue: {{read_pending.output}} tasks

      Format:
      ✅ Completed overnight: [summary]
      🟡 Pending approvals: [list any]
      💡 Opportunities: [from idle log if any]

      Keep it under 10 lines. No filler.

  - id: deliver
    action: telegram
    description: "Send morning brief"
    message: |
      ☀️ Morning Brief — {{today}}
      {{compile_brief.output}}
    tier: 1
