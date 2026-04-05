#!/bin/bash
# start-lobechat.sh — Start Lobe Chat with OpenClaw keys loaded
# Usage: ./start-lobechat.sh [up|down|restart|logs]

set -e
cd "$(dirname "$0")"

# Load keys from .env
if [ -f .env ]; then
  export $(grep -E "^(ANTHROPIC_API_KEY|OPENAI_API_KEY)" .env | xargs)
fi

ACTION="${1:-up}"

case "$ACTION" in
  up)
    echo "Starting Lobe Chat..."
    docker compose -f docker-compose.lobechat.yml up -d
    echo ""
    echo "Lobe Chat running at: http://localhost:3210"
    echo ""
    echo "Configure your Claws as agents in Settings → Agents → New Agent"
    echo "See ~/openclaw/docs/web-interface-guide.md for system prompts"
    ;;
  down)
    docker compose -f docker-compose.lobechat.yml down
    ;;
  restart)
    docker compose -f docker-compose.lobechat.yml restart
    ;;
  logs)
    docker compose -f docker-compose.lobechat.yml logs -f
    ;;
  *)
    echo "Usage: $0 [up|down|restart|logs]"
    exit 1
    ;;
esac
