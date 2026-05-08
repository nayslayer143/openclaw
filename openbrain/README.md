# openbrain (OB1) — local stack for OpenClaw

Self-hosted Open Brain by Nate B. Jones, adapted for OpenClaw's local-first
constraints. Runs entirely on the M2 Max — no Supabase, no OpenRouter, no
external API spend. See `SPIKE-NOTES.md` for the path-A scope decisions.

Upstream pin: `UPSTREAM_SHA`.

## Stack

| Service | Bound | Container | What |
|---|---|---|---|
| postgres | `127.0.0.1:5433` | `openclaw-openbrain-pg` | pgvector/pgvector:pg16, dim=768 |
| openbrain-mcp | `127.0.0.1:8765` | `openclaw-openbrain-mcp` | Deno MCP server (capture/search/list/stats/fetch) |

Embeddings + metadata extraction via Ollama (`nomic-embed-text` + `qwen2.5:7b`)
through OpenAI-compat at `http://host.docker.internal:11434/v1`.

## Operate

The compose file lives next to a `.env` symlink → `../.env` so `docker compose`
can resolve `${OPENBRAIN_*}` without sourcing.

```bash
cd ~/code/claw-core/openclaw/openbrain

docker compose up -d        # start
docker compose down         # stop (data persists at ~/.openclaw/openbrain/pgdata/)
docker compose logs -f openbrain-mcp
docker compose ps

bash ../scripts/openbrain_health.sh
```

## Direct postgres

```bash
PGPASSWORD=$(grep ^OPENBRAIN_DB_PASSWORD ../.env | cut -d= -f2) \
  psql -h 127.0.0.1 -p 5433 -U openbrain -d openbrain
```

## Backup / restore

Nightly via `scripts/openbrain_backup.sh`. Files in `~/.openclaw/backups/`.

```bash
gunzip -c ~/.openclaw/backups/openbrain-YYYY-MM-DD.sql.gz | \
  docker compose exec -T postgres psql -U openbrain openbrain
```

## Smoke test the MCP

```bash
KEY=$(grep ^OPENBRAIN_ACCESS_KEY ../.env | cut -d= -f2)
curl -sN -X POST http://127.0.0.1:8765 \
  -H "x-brain-key: $KEY" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | head
```

Expect six tools: `search`, `fetch`, `search_thoughts`, `list_thoughts`,
`thought_stats`, `capture_thought`.

## Reset

```bash
docker compose down
rm -rf ~/.openclaw/openbrain/pgdata
docker compose up -d   # schema-init.sql replays
```
