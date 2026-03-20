#!/usr/bin/env bash
# Clawmson env additions — run once to append to ~/openclaw/.env
# Usage: bash ~/openclaw/scripts/clawmson-env-additions.sh

ENV_FILE="$HOME/openclaw/.env"

cat >> "$ENV_FILE" << 'EOF'

# ── Clawmson (added by clawmson-env-additions.sh) ─────────────────────────
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_CHAT_MODEL=qwen3:32b
OLLAMA_VISION_MODEL=qwen3-vl:32b
CLAWMSON_DB_PATH=~/.openclaw/clawmson.db
CLAWMSON_MEDIA_PATH=~/.openclaw/media/
EOF

echo "Done. New vars appended to $ENV_FILE"
