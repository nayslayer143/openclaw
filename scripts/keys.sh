#!/usr/bin/env bash
# keys.sh — dump all stored credentials in one shot
# Usage: bash /Users/nayslayer/openclaw/scripts/keys.sh

set -euo pipefail

BOLD='\033[1m'; TEAL='\033[0;36m'; RESET='\033[0m'; DIM='\033[2m'

echo -e "\n${BOLD}${TEAL}=== OpenClaw Key Vault ===${RESET}\n"

# ── .env file ─────────────────────────────────────────────────────────────────
ENV_FILE="$HOME/openclaw/.env"
if [[ -f "$ENV_FILE" ]]; then
  echo -e "${BOLD}.env (~/openclaw/.env)${RESET}"
  while IFS= read -r line; do
    # Skip blank lines and comments
    [[ -z "$line" || "$line" =~ ^# ]] && continue
    # Mask value after =
    key="${line%%=*}"
    val="${line#*=}"
    if [[ -n "$val" ]]; then
      masked="${val:0:8}...${val: -4}"
      echo -e "  ${key} = ${DIM}${masked}${RESET}"
    fi
  done < "$ENV_FILE"
  echo ""
fi

# ── macOS Keychain ─────────────────────────────────────────────────────────────
echo -e "${BOLD}macOS Keychain${RESET}"

keychain_lookup() {
  local label="$1"
  local service="$2"
  local val
  val=$(security find-generic-password -s "$service" -w 2>/dev/null || echo "")
  if [[ -n "$val" ]]; then
    echo -e "  ${label} = ${DIM}${val:0:12}...${val: -4}${RESET}"
  else
    echo -e "  ${label} = ${DIM}(not set)${RESET}"
  fi
}

keychain_lookup "Anthropic (meOS)"   "com.meos.key.anthropic"
keychain_lookup "OpenAI (meOS)"      "com.meos.key.openai"
keychain_lookup "Gemini (meOS)"      "com.meos.key.gemini"
keychain_lookup "Twitter (meOS)"     "com.meos.key.twitter"
keychain_lookup "Instagram (meOS)"   "com.meos.key.instagram"
keychain_lookup "LinkedIn (meOS)"    "com.meos.key.linkedin"
keychain_lookup "Bluesky (meOS)"     "com.meos.key.bluesky"

# Also check for any anthropic key stored by Claude Code
CLAUDE_ANTHROPIC=$(security find-generic-password -l "Claude API Key" -w 2>/dev/null || echo "")
if [[ -n "$CLAUDE_ANTHROPIC" ]]; then
  echo -e "  Anthropic (Claude Code) = ${DIM}${CLAUDE_ANTHROPIC:0:12}...${CLAUDE_ANTHROPIC: -4}${RESET}"
fi

echo ""

# ── Environment (current shell) ───────────────────────────────────────────────
echo -e "${BOLD}Shell environment${RESET}"
for var in ANTHROPIC_API_KEY OPENAI_API_KEY GEMINI_API_KEY GITHUB_PAT TELEGRAM_BOT_TOKEN ZEP_API_KEY; do
  val="${!var:-}"
  if [[ -n "$val" ]]; then
    echo -e "  ${var} = ${DIM}${val:0:8}...${val: -4}${RESET}"
  else
    echo -e "  ${var} = ${DIM}(not set)${RESET}"
  fi
done

echo ""

# ── Add a new key to meOS Keychain ────────────────────────────────────────────
if [[ "${1:-}" == "--set" && -n "${2:-}" && -n "${3:-}" ]]; then
  SERVICE="com.meos.key.${2,,}"
  security delete-generic-password -s "$SERVICE" 2>/dev/null || true
  security add-generic-password -s "$SERVICE" -a "meOS" -w "$3"
  echo -e "${TEAL}Saved ${2} to Keychain as ${SERVICE}${RESET}"
fi

echo -e "${DIM}To set a key: bash keys.sh --set anthropic sk-ant-...${RESET}\n"
