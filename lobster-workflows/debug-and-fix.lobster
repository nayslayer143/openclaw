# debug-and-fix.lobster
# Input: bug/feature request text
# Agent: Build Agent (Claude Code)
# Output: output contract → build-results/[task-id].json

name: debug-and-fix
description: "Take a bug report or feature request, create task packet, run 4-mode build sequence"
trigger: manual

steps:
  - id: create_task_packet
    action: create_file
    description: "Create task packet from input"
    output: "~/openclaw/repo-queue/task-{{slug}}-{{date}}.json"
    template: |
      {
        "task_id": "build-{{timestamp}}",
        "repo_path": "{{input.repo_path}}",
        "goal": "{{input.goal}}",
        "acceptance_criteria": {{input.acceptance_criteria | default: []}},
        "branch_name": "{{input.type | default: 'feat'}}/{{slug}}",
        "forbidden_operations": ["never touch main branch", "never git push origin main", "never git push --force"],
        "time_budget_minutes": {{input.time_budget | default: 30}},
        "risk_level": "{{input.risk_level | default: 'low'}}",
        "output_location": "~/openclaw/build-results/build-{{timestamp}}/"
      }

  - id: run_build_agent
    action: shell
    description: "Run Claude Code via build-agent-bridge"
    command: "./lobster-workflows/build-agent-bridge.sh ~/openclaw/repo-queue/task-{{slug}}-{{date}}.json"
    working_dir: "~/openclaw"
    timeout_minutes: "{{input.time_budget | default: 30}}"

  - id: check_result
    action: read_json
    description: "Read output contract"
    input: "~/openclaw/build-results/build-{{timestamp}}.json"

  - id: notify
    action: telegram
    description: "Send result to Jordan"
    condition: "always"
    message: |
      {% if result.status == 'success' %}
      ✅ Build complete: {{result.task_id}}
      {{result.summary}}
      Changed: {{result.changed_files | join: ', '}}
      Tests: {{result.tests_passed}}/{{result.tests_run}} passed
      🟡 Tier-2: Reply /approve-{{result.task_id}}
      {% elif result.status == 'blocked' %}
      🔴 Build blocked: {{result.task_id}}
      Reason: {{result.summary}}
      Risks: {{result.unresolved_risks | join: ', '}}
      Suggested: {{result.suggested_next}}
      {% else %}
      🟡 Build partial: {{result.task_id}}
      {{result.summary}}
      Needs human review.
      {% endif %}
    tier: 2
