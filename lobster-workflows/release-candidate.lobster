# release-candidate.lobster
# Input: approved branch name + repo path
# Agent: Build Agent (tests/lint) → Ops Agent (staging health) → Telegram approval chain
# Output: staging deploy or rejection

name: release-candidate
description: "Validate a branch for release: tests, lint, diff summary, staging deploy"
trigger: manual

steps:
  - id: validate_input
    action: validate
    description: "Ensure branch and repo are provided"
    required:
      - input.branch_name
      - input.repo_path

  - id: run_tests
    action: shell
    description: "Run full test suite — fail hard if any test fails"
    command: "cd {{input.repo_path}} && git checkout {{input.branch_name}} && ./scripts/test.sh"
    working_dir: "{{input.repo_path}}"
    timeout_minutes: 15
    fail_on_error: true

  - id: run_lint
    action: shell
    description: "Run linter — fail hard if any error"
    command: "cd {{input.repo_path}} && ./scripts/lint.sh"
    working_dir: "{{input.repo_path}}"
    timeout_minutes: 5
    fail_on_error: true

  - id: generate_diff
    action: shell
    description: "Generate diff summary for review"
    command: "cd {{input.repo_path}} && git diff main...{{input.branch_name}} --stat"
    working_dir: "{{input.repo_path}}"
    timeout_minutes: 2

  - id: verify_staging
    action: agent
    agent: ops
    model: "qwen2.5:7b"
    description: "Ops Agent verifies staging environment is healthy"
    prompt: |
      Run a quick health check on the staging environment for {{input.repo_path}}.
      Check: service is reachable, no active incidents, disk/memory ok.
      Output: healthy (yes/no) + any warnings.

  - id: request_staging_deploy
    action: telegram
    description: "Tier-2: request approval for staging deploy"
    message: |
      🟡 Tier-2: Release candidate ready for staging

      Branch: {{input.branch_name}}
      Repo: {{input.repo_path}}

      Tests: ✅ All passed
      Lint: ✅ Clean
      Staging: {{verify_staging.healthy}}

      Diff summary:
      {{generate_diff.output}}

      Reply /approve-rc-{{input.branch_name}} to deploy to staging
      Reply /deny-rc-{{input.branch_name}} to reject
    tier: 2
    wait_for_reply: true

  - id: deploy_staging
    action: shell
    condition: "request_staging_deploy.approved == true"
    description: "Deploy to staging"
    command: "cd {{input.repo_path}} && ./scripts/deploy-staging.sh {{input.branch_name}}"
    working_dir: "{{input.repo_path}}"
    timeout_minutes: 10

  - id: smoke_test
    action: shell
    condition: "deploy_staging.success == true"
    description: "Run smoke tests against staging URL"
    command: "cd {{input.repo_path}} && ./scripts/smoke-test.sh"
    working_dir: "{{input.repo_path}}"
    timeout_minutes: 5

  - id: staging_result
    action: telegram
    condition: "deploy_staging.success == true"
    description: "Report staging result + rollback command"
    message: |
      {% if smoke_test.success %}
      ✅ Staging deploy successful

      Branch: {{input.branch_name}}
      Smoke tests: ✅ Passed
      Rollback: `git checkout main -- . && ./scripts/deploy-staging.sh main`

      🔴 Tier-3: Reply 'yes rc-{{input.branch_name}}' to promote to production
      {% else %}
      ⚠️ Staging deploy — smoke tests FAILED

      Branch: {{input.branch_name}}
      Smoke tests: ❌ Failed
      Auto-rolling back staging...

      Review needed before retry.
      {% endif %}
    tier: 3

  - id: rollback_on_failure
    action: shell
    condition: "smoke_test.success == false"
    description: "Auto-rollback staging on smoke test failure"
    command: "cd {{input.repo_path}} && git checkout main -- . && ./scripts/deploy-staging.sh main"
    working_dir: "{{input.repo_path}}"
