#!/usr/bin/env bash
# openbrain stack health check.
# Use: bash scripts/openbrain_health.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV="$ROOT/.env"

KEY=$(grep ^OPENBRAIN_ACCESS_KEY "$ENV" | cut -d= -f2)
DBPW=$(grep ^OPENBRAIN_DB_PASSWORD "$ENV" | cut -d= -f2)

echo -n "postgres   "
PGPASSWORD="$DBPW" psql -h 127.0.0.1 -p 5433 -U openbrain -d openbrain \
  -tAc "SELECT 1" >/dev/null 2>&1 && echo "OK" || echo "FAIL"

echo -n "mcp        "
curl -fsS -X POST http://127.0.0.1:8765 \
  -H "x-brain-key: $KEY" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' \
  --max-time 5 >/dev/null 2>&1 && echo "OK" || echo "FAIL"

echo -n "ollama     "
curl -fsS http://127.0.0.1:11434/api/tags --max-time 3 >/dev/null 2>&1 \
  && echo "OK" || echo "FAIL"

echo -n "thoughts   "
COUNT=$(PGPASSWORD="$DBPW" psql -h 127.0.0.1 -p 5433 -U openbrain -d openbrain \
  -tAc "SELECT count(*) FROM thoughts" 2>/dev/null || echo "?")
echo "$COUNT row(s)"
