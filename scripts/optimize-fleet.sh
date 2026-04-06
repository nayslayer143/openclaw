#!/bin/bash
# ==============================================================================
# optimize-fleet.sh — One-shot Mac/Ollama/TurboQuant tuning for the Claw fleet
#
# Run this ONCE after reboot or after pulling fleet changes. Idempotent.
# Requires sudo for sysctl + LaunchDaemon install.
#
# What it does:
#   1. Bumps iogpu.wired_limit_mb to 81920 (80 GB) so the GPU can address
#      more of the 96 GB unified memory — prevents qwen3-coder-next +
#      turboquant from thrashing when both are hot.
#   2. Installs /Library/LaunchDaemons/com.openclaw.iogpu-wired.plist so the
#      sysctl bump survives reboots.
#   3. Writes /tmp/openclaw-ollama-env.sh that you source in ~/.zshrc, and
#      calls `launchctl setenv` so a restarted Ollama.app inherits the vars.
#
# What it does NOT do (intentionally):
#   - Restart Ollama or TurboQuant. Those evict hot models and interrupt
#     live claws. Restart manually when safe.
#
# Usage:
#   sudo bash ~/openclaw/scripts/optimize-fleet.sh
# ==============================================================================

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "ERROR: this script must be run with sudo."
  echo "  sudo bash ~/openclaw/scripts/optimize-fleet.sh"
  exit 1
fi

WIRED_LIMIT_MB=81920
PLIST_PATH="/Library/LaunchDaemons/com.openclaw.iogpu-wired.plist"

echo "==> [1/3] Bumping iogpu.wired_limit_mb to ${WIRED_LIMIT_MB} MB (80 GB)"
CURRENT=$(sysctl -n iogpu.wired_limit_mb 2>/dev/null || echo "0")
echo "    current: ${CURRENT} MB"
sysctl -w iogpu.wired_limit_mb="${WIRED_LIMIT_MB}"
NEW=$(sysctl -n iogpu.wired_limit_mb 2>/dev/null || echo "0")
echo "    new:     ${NEW} MB"

echo ""
echo "==> [2/3] Installing LaunchDaemon so the bump survives reboots"
cat > "${PLIST_PATH}" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.openclaw.iogpu-wired</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/sbin/sysctl</string>
        <string>-w</string>
        <string>iogpu.wired_limit_mb=${WIRED_LIMIT_MB}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardErrorPath</key>
    <string>/var/log/openclaw-iogpu-wired.log</string>
    <key>StandardOutPath</key>
    <string>/var/log/openclaw-iogpu-wired.log</string>
</dict>
</plist>
PLIST
chown root:wheel "${PLIST_PATH}"
chmod 644 "${PLIST_PATH}"
# Reload (idempotent)
launchctl unload "${PLIST_PATH}" 2>/dev/null || true
launchctl load -w "${PLIST_PATH}"
echo "    installed at ${PLIST_PATH}"

echo ""
echo "==> [3/3] Writing Ollama env var bundle"
ENV_FILE="/tmp/openclaw-ollama-env.sh"
cat > "${ENV_FILE}" <<'ENV'
# Ollama tuning for the Claw fleet — source this from ~/.zshrc.
# Also applied to launchctl so the next Ollama.app launch inherits them.
export OLLAMA_FLASH_ATTENTION=1      # Metal flash attention — big decode win
export OLLAMA_KV_CACHE_TYPE=q8_0     # Compressed KV — ~20% VRAM savings
export OLLAMA_KEEP_ALIVE=30m         # Default TTL; dispatchers override per-request
export OLLAMA_MAX_LOADED_MODELS=2    # Allow 2 models co-resident in VRAM
export OLLAMA_NUM_PARALLEL=2         # Two concurrent slots per loaded model
export OLLAMA_LOAD_TIMEOUT=600       # 10-min grace for 80B cold-starts
# NOT set: OLLAMA_GPU_OVERHEAD (default reserves headroom for KV growth — keep it)
ENV
chown nayslayer:staff "${ENV_FILE}"
chmod 644 "${ENV_FILE}"

# launchctl setenv — takes effect only for *future* Ollama.app launches.
# (Running process keeps its original env; restart Ollama to pick up.)
launchctl setenv OLLAMA_FLASH_ATTENTION 1
launchctl setenv OLLAMA_KV_CACHE_TYPE q8_0
launchctl setenv OLLAMA_KEEP_ALIVE 30m
launchctl setenv OLLAMA_MAX_LOADED_MODELS 2
launchctl setenv OLLAMA_NUM_PARALLEL 2
launchctl setenv OLLAMA_LOAD_TIMEOUT 600

echo "    wrote ${ENV_FILE}"
echo "    applied to launchctl (takes effect on next Ollama.app restart)"
echo ""
echo "==> DONE"
echo ""
echo "Next steps (manual):"
echo "  1. Add to ~/.zshrc:  [ -f /tmp/openclaw-ollama-env.sh ] && source /tmp/openclaw-ollama-env.sh"
echo "  2. Restart Ollama.app when safe (quit from menu bar + relaunch)"
echo "  3. Restart TurboQuant when safe:"
echo "       pkill -f 'llama-server.*turboquant' ; ~/llama-cpp-turboquant/start-turboquant.sh &"
echo ""
echo "Verify afterwards:"
echo "  sysctl iogpu.wired_limit_mb           # → ${WIRED_LIMIT_MB}"
echo "  launchctl getenv OLLAMA_FLASH_ATTENTION  # → 1"
echo "  ps aux | grep llama-server | grep mlock  # → flag present"
