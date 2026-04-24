#!/bin/bash
# Legacy OpenClaw wrapper.
# Daily market intel now routes through CodeMonkeyClaw so workflow execution
# lives under one control plane.

set -euo pipefail

CODEMONKEY_ROOT="${HOME}/code/claw-platform/codemonkeyclaw"
PYTHON="${CODEMONKEY_ROOT}/.venv/bin/python"
RUNPY="${CODEMONKEY_ROOT}/run.py"

exec "${PYTHON}" "${RUNPY}" workflow \
  --chat-id "openclaw-daily-market-intel" \
  --name "daily-market-intel" \
  --params "{}"
