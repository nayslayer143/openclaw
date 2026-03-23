#!/bin/bash
# claude-session.sh — attach or create persistent Claude Code tmux session
# Run this after SSH-ing in from iPhone

SESSION="claude"

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "Attaching to existing Claude session..."
  tmux attach-session -t "$SESSION"
else
  echo "Starting new Claude session..."
  tmux new-session -s "$SESSION" -d
  tmux send-keys -t "$SESSION" "cd ~/openclaw && claude" Enter
  tmux attach-session -t "$SESSION"
fi
