# system-health.lobster
# Schedule: every 30 minutes (*/30 * * * *)
# Agent: Ops Agent
# Output: health log → logs/ops-{date}.jsonl

name: system-health
description: "Check stack health: Ollama, disk, logs, queue depth"
trigger:
  cron: "*/30 * * * *"

steps:
  - id: check_ollama
    action: shell
    description: "Verify Ollama is responding"
    command: "ollama list > /dev/null 2>&1 && echo 'ok' || echo 'fail'"
    timeout_seconds: 10

  - id: restart_ollama
    action: shell
    condition: "check_ollama.output == 'fail'"
    description: "Safe-listed restart: ollama serve"
    command: "ollama serve > /tmp/ollama.log 2>&1 &"
    retry: 1

  - id: check_disk
    action: shell
    description: "Check disk usage percentage"
    command: "df -h / | tail -1 | awk '{print $5}' | tr -d '%'"
    timeout_seconds: 5

  - id: check_queue
    action: shell
    description: "Count pending queue items"
    command: "python3 -c \"import json; print(len(json.load(open('$HOME/openclaw/queue/pending.json'))))\""
    timeout_seconds: 5

  - id: check_logs
    action: shell
    description: "Scan today's logs for FATAL/ERROR"
    command: "grep -c 'FATAL\\|ERROR' ~/openclaw/logs/*-$(date +%Y-%m-%d).jsonl 2>/dev/null || echo '0'"
    timeout_seconds: 5

  - id: log_status
    action: shell
    description: "Append health check to ops log"
    command: |
      echo '{"timestamp":'$(date +%s)',"check":"health","ollama":"{{check_ollama.output}}","disk_pct":{{check_disk.output | default: 0}},"queue_depth":{{check_queue.output | default: 0}},"error_count":{{check_logs.output | default: 0}}}' >> ~/openclaw/logs/ops-$(date +%Y-%m-%d).jsonl

  - id: alert_disk
    action: telegram
    condition: "check_disk.output | int > 80"
    description: "Disk critical alert"
    message: "⚠️ Disk usage at {{check_disk.output}}% — needs cleanup"
    tier: 2

  - id: alert_queue
    action: telegram
    condition: "check_queue.output | int > 20"
    description: "Queue depth alert"
    message: "⚠️ Queue depth at {{check_queue.output}} items — needs triage"
    tier: 2

  - id: alert_errors
    action: telegram
    condition: "check_logs.output | int > 5"
    description: "Error spike alert"
    message: "⚠️ {{check_logs.output}} FATAL/ERROR entries in today's logs — review needed"
    tier: 2
