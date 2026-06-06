# OB1 Spike Notes — 2026-05-07

Pinned upstream: `openbrain/UPSTREAM_SHA` = `151a8d1c922ffadad08399508efe46b207a5894e`.

## MCP server (`integrations/kubernetes-deployment/`)

- Runtime: **Deno 2.3.3** (not Node)
- Port: **8000** (env: `PORT`)
- Source: `index.ts` (single file, ~580 lines)
- Dockerfile: `FROM denoland/deno:2.3.3` · `CMD ["deno","run","--allow-net","--allow-env","--allow-read","index.ts"]`
- Connects directly to Postgres (Velo's adaptation already in upstream main)

### Env vars (exact names)

| Var | Required | Default |
|---|---|---|
| `DB_HOST` | yes | 127.0.0.1 |
| `DB_PORT` | yes | 5432 |
| `DB_NAME` | yes | openbrain |
| `DB_USER` | yes | postgres |
| `DB_PASSWORD` | **yes** | — |
| `EMBEDDING_API_BASE` | yes | https://openrouter.ai/api/v1 |
| `EMBEDDING_API_KEY` | yes | — |
| `EMBEDDING_MODEL` | yes | openai/text-embedding-3-small |
| `CHAT_API_BASE` | no | falls back to EMBEDDING_API_BASE |
| `CHAT_API_KEY` | no | falls back to EMBEDDING_API_KEY |
| `CHAT_MODEL` | yes | openai/gpt-4o-mini |
| `MCP_ACCESS_KEY` | **yes** | — |
| `OPEN_BRAIN_CITATION_BASE_URL` | no | https://openbrain.local/thoughts |
| `PORT` | no | 8000 |

> Note: there is **no** `EMBEDDING_DIMENSIONS` env var. Dim is purely schema-driven.

### Embedding wire shape (line 86)

```ts
fetch(`${EMBEDDING_API_BASE}/embeddings`, {
  method: "POST",
  headers: { Authorization: `Bearer ${EMBEDDING_API_KEY}`, "Content-Type": "application/json" },
  body: JSON.stringify({ model: EMBEDDING_MODEL, input: text }),
});
// Reads: data[0].embedding
```

**Standard OpenAI shape.** Ollama's `/v1/embeddings` matches exactly.

Smoke test: `curl http://127.0.0.1:11434/v1/embeddings -d '{"model":"nomic-embed-text","input":"hi"}'` returns `{data:[{embedding:[…768 floats…]}], model:"nomic-embed-text"}`.

**Result: A — Compatible. Task 1.5 proxy NOT needed.** Task 1.5 is skipped.

### Schema (`integrations/kubernetes-deployment/k8s/openbrain.yml`)

Hardcodes `vector(1536)` in two places — `CREATE TABLE thoughts` column and the `match_thoughts(query_embedding vector(1536), …)` function signature. Both need patching to `vector(768)` for `nomic-embed-text`.

## Schema — base thoughts

Embedded in `k8s/openbrain.yml` as a ConfigMap. Need to extract and inline it into `openbrain/schema-init.sql` so the postgres init container can pick it up.

## Schema — agent-memory sidecars (`schemas/agent-memory/schema.sql`)

Standalone .sql file. Idempotent (`IF NOT EXISTS`, BEGIN/COMMIT). Safe to apply alongside the base thoughts schema.

## agent-memory-api (`integrations/agent-memory-api/`)

**Not deployable as-is on self-hosted Postgres.**

- Hardcoded to Supabase: `createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)` (line 13)
- Uses Supabase query builders (`supabase.from('agent_memories').select(...)`) throughout — ~30 call sites
- Velo's K8s deployment did NOT port this service — only the MCP server
- Routes: `POST /recall`, `POST /writeback`, `POST /recall/:id/usage`, `GET /memories`, `GET /memories/review`, `GET /memories/:id`, `GET /recall-traces/:id`, `GET /health`

**Decision (2026-05-07):** Defer. Plan executed as **Path A — MCP-only**. Sidecar schema still applied (cheap, future-ready). Recall/writeback methods on `OpenBrain` adapter raise `NotImplementedError` referencing a follow-up spec. To re-enable: write `docs/superpowers/specs/YYYY-MM-DD-agent-memory-api-port-design.md` and a corresponding plan.

## Decision summary

| Plan task | Effect |
|---|---|
| Task 1 | Done. Submodule pinned at `151a8d1`. |
| Task 1.5 | **Skipped** — Ollama wire-compatible. |
| Task 2 | Schema-init.sql includes both base thoughts (dim 1536→768) AND sidecars. |
| Task 3 | MCP image — Deno-based Dockerfile (NOT Node as the plan template suggested). |
| Task 4 | **Skipped** — agent-memory-api requires Supabase. |
| Task 5 | docker-compose has 2 services: postgres + openbrain-mcp. |
| Task 6 | Adapter: capture/search/list/stats — full implementation. |
| Task 7 | Adapter: recall/writeback/usage_report — `NotImplementedError` with TODO. Tests assert the error type. |
| Task 8 | Smoke tests cover only base 4 tools. |
| Task 9 | Backfill unchanged. |
| Task 10–11 | Pilot + fleet wire-up: agents call `search`/`capture` directly via the adapter; recall semantics deferred. |
| Task 12 | Backup unchanged. Idle-protocol cron uses `capture`. |
| Task 13 | PreCompact hook calls `capture` with `metadata.kind="handoff", metadata.use_policy="evidence"` instead of `writeback`. |
| Task 14 | Skills install unchanged. |
| Task 15 | Acceptance — drop agent-memory-api checks, drop recall_trace count check. |
