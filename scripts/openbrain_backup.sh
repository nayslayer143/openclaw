#!/usr/bin/env bash
# Nightly OB1 backup.
# Use: bash scripts/openbrain_backup.sh
# Cron: see suggested entries at the bottom of IDLE_PROTOCOL.md.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${HOME}/.openclaw/backups"
COMPOSE="$ROOT/openbrain/docker-compose.yml"
DATE=$(date +%F)
OUT="$DEST/openbrain-$DATE.sql.gz"

mkdir -p "$DEST"

docker compose -f "$COMPOSE" exec -T postgres \
  pg_dump -U openbrain -d openbrain --no-owner --clean | gzip > "$OUT"

# 30-day retention
find "$DEST" -name 'openbrain-*.sql.gz' -mtime +30 -delete

SIZE=$(du -h "$OUT" | cut -f1)
echo "backup: $OUT ($SIZE)"
