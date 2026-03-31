#!/bin/bash
# =============================================================================
# notify-telegram.sh
# Send a Telegram DM to Jordan (or any allowed user in .env)
#
# Usage:
#   ./scripts/notify-telegram.sh "Your message here"
#   echo "Your message" | ./scripts/notify-telegram.sh
#
# Reads credentials from ~/openclaw/.env:
#   TELEGRAM_BOT_TOKEN
#   TELEGRAM_ALLOWED_USERS (first entry used as target chat_id)
# =============================================================================

set -euo pipefail

OPENCLAW_ROOT="${HOME}/openclaw"
ENV_FILE="${OPENCLAW_ROOT}/.env"

# Load .env safely via Python (avoids bash issues with unquoted spaces in values)
if [[ -f "$ENV_FILE" ]]; then
  eval "$(python3 - "$ENV_FILE" <<'PYEOF'
import sys
path = sys.argv[1]
with open(path) as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, _, v = line.partition('=')
        k = k.strip()
        v = v.strip()
        if all(c.isalnum() or c == '_' for c in k):
            print(f"export {k}={v!r}")
PYEOF
  )"
else
  echo "ERROR: .env not found at ${ENV_FILE}" >&2
  exit 1
fi

# Resolve message: arg or stdin
if [[ $# -ge 1 ]]; then
  MESSAGE="$1"
else
  MESSAGE=$(cat)
fi

if [[ -z "${MESSAGE:-}" ]]; then
  echo "ERROR: No message provided" >&2
  exit 1
fi

# Resolve bot token
BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
if [[ -z "$BOT_TOKEN" ]]; then
  echo "ERROR: TELEGRAM_BOT_TOKEN not set in .env" >&2
  exit 1
fi

# Use first user in TELEGRAM_ALLOWED_USERS as target
# Handles both "123" and "[\"123\",\"456\"]" formats
CHAT_ID=$(python3 -c "
import os, json
v = os.environ.get('TELEGRAM_ALLOWED_USERS', '')
try:
    parsed = json.loads(v)
    if isinstance(parsed, list):
        print(parsed[0])
    else:
        print(str(parsed))
except Exception:
    print(v.strip())
")

if [[ -z "$CHAT_ID" ]]; then
  echo "ERROR: TELEGRAM_ALLOWED_USERS not set in .env" >&2
  exit 1
fi

# Send via Bot API
RESPONSE=$(curl -s -X POST \
  "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
  -H "Content-Type: application/json" \
  -d "{\"chat_id\": \"${CHAT_ID}\", \"text\": $(python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))' <<< "$MESSAGE"), \"parse_mode\": \"\"}")

OK=$(python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(d.get('ok', False))" <<< "$RESPONSE")

if [[ "$OK" == "True" ]]; then
  echo "✓ Telegram notification sent to ${CHAT_ID}"
else
  echo "⚠ Telegram send failed: ${RESPONSE}" >&2
  exit 1
fi
