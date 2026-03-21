# ralph-plan-build.lobster
# Autonomous two-phase greenfield build workflow (Ralph Wiggum technique)
# Input: repo path + project goal + specs
# Agent: Claude Code (autonomous loop via ralph-loop.sh)
# Output: working implementation, committed and pushed per iteration

name: ralph-plan-build
description: "Two-phase autonomous build — plan then loop until IMPLEMENTATION_PLAN.md is complete"
trigger: manual

steps:
  - id: validate_repo
    action: shell
    description: "Check that required Ralph files exist in target repo"
    command: |
      REPO="{{input.repo_path}}"
      cd "$REPO"
      MISSING=()
      [[ ! -f "PROMPT_plan.md" ]] && MISSING+=("PROMPT_plan.md")
      [[ ! -f "PROMPT_build.md" ]] && MISSING+=("PROMPT_build.md")
      [[ ! -d "specs" ]] && MISSING+=("specs/")
      if [[ ${#MISSING[@]} -gt 0 ]]; then
        echo "ERROR: Missing Ralph files in $REPO: ${MISSING[*]}"
        echo "Run the ralph-scaffold step first or create these files manually."
        exit 1
      fi
      echo "Ralph files validated in $REPO"
    working_dir: "~/openclaw"

  - id: scaffold_agents_md
    action: shell
    description: "Create AGENTS.md and IMPLEMENTATION_PLAN.md if they don't exist"
    command: |
      cd "{{input.repo_path}}"
      if [[ ! -f "AGENTS.md" ]]; then
        cat > AGENTS.md << 'EOF'
## Build & Run

Succinct rules for how to BUILD the project:

## Validation

Run these after implementing to get immediate feedback:

- Tests: `[test command]`
- Typecheck: `[typecheck command]`
- Lint: `[lint command]`

## Operational Notes

Succinct learnings about how to RUN the project:

### Codebase Patterns

EOF
        echo "Created AGENTS.md"
      fi
      if [[ ! -f "IMPLEMENTATION_PLAN.md" ]]; then
        cat > IMPLEMENTATION_PLAN.md << 'EOF'
# Implementation Plan

> Auto-maintained by Ralph. Update after each iteration. Remove completed items.

## Priority Queue

- [ ] (Ralph will populate this during plan phase)

## Known Issues

## Completed

EOF
        echo "Created IMPLEMENTATION_PLAN.md"
      fi
    working_dir: "~/openclaw"

  - id: create_feature_branch
    action: shell
    description: "Create and checkout a ralph/ feature branch"
    command: |
      cd "{{input.repo_path}}"
      BRANCH="ralph/{{input.slug | default: 'build'}}-$(date +%Y-%m-%d)"
      git checkout -b "$BRANCH" 2>/dev/null || git checkout "$BRANCH"
      git push -u origin "$BRANCH" 2>/dev/null || true
      echo "Branch: $BRANCH"
    working_dir: "~/openclaw"

  - id: run_plan_phase
    action: shell
    description: "Phase 1 — single planning pass to generate IMPLEMENTATION_PLAN.md"
    command: |
      cd "{{input.repo_path}}"
      bash ~/openclaw/scripts/ralph-loop.sh plan
    working_dir: "{{input.repo_path}}"
    timeout_minutes: 30

  - id: notify_plan_complete
    action: shell
    description: "Telegram — notify Jordan that plan is ready for review"
    command: |
      bash ~/openclaw/scripts/notify-telegram.sh \
"Ralph Plan Complete — {{input.slug | default: 'project'}}

Repo: {{input.repo_path}}
IMPLEMENTATION_PLAN.md is ready for review.

Approve to start autonomous build loop:
/ralph-build-{{input.slug | default: 'project'}}

Or review plan first at:
{{input.repo_path}}/IMPLEMENTATION_PLAN.md"
    working_dir: "~/openclaw"

  - id: wait_for_approval
    action: wait_for_signal
    description: "Tier-2 hold — wait for Jordan to approve build phase"
    signal: "ralph-build-{{input.slug | default: 'project'}}"
    timeout_minutes: 1440
    on_timeout: abort

  - id: run_build_loop
    action: shell
    description: "Phase 2 — autonomous build loop (runs until max_iterations or manual kill)"
    command: |
      cd "{{input.repo_path}}"
      bash ~/openclaw/scripts/ralph-loop.sh build {{input.max_iterations | default: 0}}
    working_dir: "{{input.repo_path}}"
    timeout_minutes: "{{input.timeout_minutes | default: 360}}"

  - id: notify_build_complete
    action: shell
    description: "Telegram — notify Jordan that build loop finished"
    command: |
      cd "{{input.repo_path}}"
      ITERATIONS=$(git log --oneline origin/main..HEAD 2>/dev/null | wc -l | tr -d ' ')
      bash ~/openclaw/scripts/notify-telegram.sh \
"Ralph Build Complete — {{input.slug | default: 'project'}}

Iterations: $ITERATIONS commits pushed
Repo: {{input.repo_path}}

Review IMPLEMENTATION_PLAN.md for remaining items.
Open a PR when ready: gh pr create"
    working_dir: "~/openclaw"
