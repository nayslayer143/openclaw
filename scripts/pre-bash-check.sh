#!/bin/bash
# =============================================================================
# pre-bash-check.sh — Denylist enforcement hook
# Blocks dangerous commands before they run.
# Used as a PreToolUse hook for Bash in .claude/settings.json
#
# Usage: Called automatically by Claude Code hooks system
#   The command to check is passed as $1
# =============================================================================

DENYLIST=(
  "rm -rf"
  "curl | sh"
  "curl |sh"
  "wget | sh"
  "eval("
  "sudo rm"
  "DROP TABLE"
  "DROP DATABASE"
  "TRUNCATE TABLE"
  "> /dev/sda"
  "mkfs."
  ":(){:|:&};:"
)

COMMAND="$1"

for item in "${DENYLIST[@]}"; do
  if echo "$COMMAND" | grep -qF "$item"; then
    echo "BLOCKED: denylist match '$item'"
    echo "Command: $COMMAND"
    echo "This command is on the OpenClaw denylist. Run manually if intentional."
    exit 1
  fi
done

exit 0
