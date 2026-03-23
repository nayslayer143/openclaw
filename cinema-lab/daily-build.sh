#!/bin/bash
# Cinema Lab — Daily 5-build pipeline
CINEMA_DIR="$HOME/openclaw/cinema-lab"
LOG="$CINEMA_DIR/logs/build-$(date +%Y%m%d-%H%M%S).log"

echo "◆ Cinema Lab daily build — $(date)" | tee "$LOG"

claude -p "You are running the Cinema Lab daily build.

1. Read the cinematic-web skill at ~/.claude/skills/cinematic-web/SKILL.md and its reference files
2. Read ~/openclaw/cinema-lab/index.json to get the current tier level
3. Read ~/openclaw/cinema-lab/prompt-bank.json for the prompt bank
4. Pick 5 random prompts from the current tier (or below)
5. For each prompt, build a SINGLE self-contained HTML file:
   - All CSS and JS inline
   - Use CDN links for GSAP, Lenis, Three.js as needed
   - Google Fonts via @import
   - Must work when opened via file:// protocol
   - Follow the cinematic-web skill to make it PHENOMENAL
6. Save each HTML file to ~/openclaw/cinema-lab/builds/{id}.html
   - ID format: cine-YYYYMMDD-HHMMSS-{6 random hex chars}
7. Update ~/openclaw/cinema-lab/index.json — prepend the new builds to the builds array with this shape:
   {\"id\": \"the-id\", \"name\": \"descriptive name\", \"prompt\": \"the prompt\", \"tier\": N, \"score\": 0, \"notes\": \"\", \"created_at\": \"ISO timestamp\", \"graded_at\": null, \"file\": \"{id}.html\"}

Build all 5. Make each one jaw-dropping." 2>&1 | tee -a "$LOG"

echo "◆ Build complete — $(date)" | tee -a "$LOG"
