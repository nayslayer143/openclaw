# OB1 (Open Brain) Integration into OpenClaw — Design

**Date:** 2026-05-07
**Status:** Approved for implementation planning
**Owner:** Jordan
**Source material:** [NateBJones-Projects/OB1](https://github.com/NateBJones-Projects/OB1), [promptkit.natebjones.com](https://promptkit.natebjones.com/)

---

## Goal

Give OpenClaw a persistent, semantically searchable, governed agent memory layer based on Nate B. Jones's OB1 ("Open Brain") architecture, while preserving OpenClaw's hard constraints: 127.0.0.1-only, zero external API spend, no cloud SaaS, no transmission of memory files.

## Non-goals

- Replacing `~/.openclaw/clawmson.db` (the trading SQLite store stays untouched).
- Running Nate's `openclaw` CLI / ClawHub package registry (different runtime, naming collision only).
- Cloud/Supabase deployment.
- A disk fallback queue for embedding outages (out of scope; fail-fast and rely on existing `outputs/` retry pattern).

## Background

OB1 is a Postgres + pgvector + MCP architecture exposing a `thoughts` table (vector + LLM-extracted metadata) so every AI tool shares one persistent memory. The community ships:

- **K8s self-hosted deployment** (`@velo`) — Postgres+pgvector + modified MCP server replacing Supabase. Docker Compose adaptation is straightforward.
- **Runtime-neutral Agent Memory API** (`integrations/agent-memory-api/`) — HTTP `recall`/`writeback`/`usage-report` endpoints layered on top of `thoughts` + 7 sidecar tables (`schemas/agent-memory/`).
- **Portable Claude Code skills** — `n-agentic-harnesses`, `auto-capture`, `panning-for-gold`, `aiception`, `meeting-synthesis`, `research-synthesis`, `competitive-analysis`, `world-model-diagnostic`.

Nate's repo also ships an `openclaw-agent-memory` plugin/skill/recipe set targeted at his own "OpenClaw" runtime (a different system that shares the name). That layer is **not** installed; we replicate its behavior via direct calls to the Agent Memory API from Jordan's openclaw Python.

## Architecture

```
[Claude Code · Telegram dispatcher · agent configs · Lobster workflows]
                              │
                              ▼
                  scripts/openbrain.py (Python adapter + CLI)
                              │  HTTP, 127.0.0.1
                ┌─────────────┴─────────────┐
                ▼                           ▼
       openbrain-mcp:8765        agent-memory-api:8766
       (capture/search/list/      (recall/writeback/
        stats — base MCP)          usage-report — sidecars)
                │                           │
                └─────────────┬─────────────┘
                              ▼
                postgres:16 + pgvector + 7 sidecars
                  (data: ~/.openclaw/openbrain/pgdata/)
                              │
                              ▼
              Ollama @ host.docker.internal:11434/v1
              · nomic-embed-text  (768d)
              · qwen2.5:7b        (metadata extraction)

[~/.openclaw/clawmson.db — untouched, 8 trading tables]
```

All HTTP services bind 127.0.0.1. Containers reach Ollama via `host.docker.internal`. No public ingress.

## Components

### Storage

- **Postgres 16 + pgvector** in Docker.
- Volume: `~/.openclaw/openbrain/pgdata/` (mirrors the `~/.openclaw/clawmson.db` placement convention).
- Embedding column: `vector(768)` (the OB1 default of 1536 is patched at schema-apply time).
- Schemas:
  - Base `thoughts` table from Velo's K8s deployment SQL (modified dim).
  - 7 sidecars from `schemas/agent-memory/schema.sql`: `provenance`, `use_policy`, `review_queue`, `source_reference`, `relation`, `recall_trace`, `audit`.

### Containers (Docker Compose)

Compose file: `~/code/claw-core/openclaw/openbrain/docker-compose.yml`.

| Service | Image | External port (127.0.0.1) | Notes |
|---|---|---|---|
| `postgres` | `pgvector/pgvector:pg16` | none | Reachable only on the compose network. Not host-bound. |
| `openbrain-mcp` | built locally from `integrations/kubernetes-deployment/Dockerfile` | 8765 | Base 4-tool MCP server |
| `agent-memory-api` | built locally from `integrations/agent-memory-api/` | 8766 | Recall/writeback HTTP API |

Healthchecks:
- Postgres: `pg_isready`.
- `openbrain-mcp`: `POST /` with `tools/list`.
- `agent-memory-api`: `GET /health` returns `{"ok": true}`.

### Environment (in `.env`, gitignored)

```
OPENBRAIN_DB_PASSWORD=<random>
OPENBRAIN_ACCESS_KEY=<64-char random>
OPENBRAIN_EMBEDDING_API_BASE=http://host.docker.internal:11434/v1
OPENBRAIN_EMBEDDING_MODEL=nomic-embed-text
OPENBRAIN_CHAT_MODEL=qwen2.5:7b
OPENBRAIN_EMBEDDING_DIM=768
```

### Adapter — `scripts/openbrain.py`

Single Python module, stdlib + `httpx`. Reads `.env`. Talks to 127.0.0.1:8765 and :8766 via `x-brain-key` header.

Public surface:

```python
class OpenBrain:
    def capture(self, text: str, *, source: str, scope: str = "personal", metadata: dict | None = None) -> str: ...
    def search(self, query: str, *, k: int = 10, filters: dict | None = None) -> list[Thought]: ...
    def list_recent(self, *, n: int = 50, source: str | None = None) -> list[Thought]: ...
    def stats(self) -> dict: ...

    # Agent Memory API (sidecar layer)
    def recall(self, *, task: str, scope: str, types: list[str] | None = None) -> RecallResponse: ...
    def writeback(self, *, content: str, kind: str, provenance: Provenance, use_policy: str = "evidence", scope: str = "project") -> str: ...
    def usage_report(self, *, recall_id: str, used_memory_ids: list[str], outcome: str) -> None: ...
```

CLI:
```
python -m scripts.openbrain capture "..." --source idle-protocol
python -m scripts.openbrain search "polymarket arb"
python -m scripts.openbrain recall --task "review PR" --scope project
python -m scripts.openbrain stats
```

Errors are raised, not swallowed. Failures bubble up to the caller (Lobster step, agent run, cron job) which decides how to log/retry.

### Skills install (target: `~/.claude/skills/`)

Drop-in copies of:

- `n-agentic-harnesses` (full folder including `references/`, `variants/`, `agents/`)
- `auto-capture`
- `panning-for-gold`
- `aiception`
- `meeting-synthesis`
- `research-synthesis`
- `competitive-analysis`
- `world-model-diagnostic`

Skipped: `openclaw-agent-memory` (Nate's runtime), `financial-model-review`, `deal-memo-drafting`, `work-operating-model`.

### Wiring into existing flows

| Existing component | Change |
|---|---|
| `IDLE_PROTOCOL.md` cron | New nightly job: capture each new MEMORY.md entry as a thought (`source=idle-protocol`, `scope=workspace`). |
| `memory/MEMORY.md` consolidation | Each appended entry is captured as a thought. MEMORY.md remains the human-readable spine. |
| PreCompact handoff hook | After writing `handoff.md`, also `writeback` with `use_policy=evidence`, `kind=handoff`. |
| `agents/configs/*.md` | Add tool budget. Orchestrator / Research / Memory: `recall + writeback`. Build / Code: `recall` only by default. Trading / Ops: `recall` only. |
| `lobster-workflows/*.lobster` | Template: pre-task `recall`, post-task `writeback`. Initial migration: orchestrator + research workflows only. |
| `improvements/` | Aiception skill output saved here AND captured (`use_policy=evidence` until human-promoted). |
| `repo-queue/` dispatch | Task packets get scoped `recall` context attached at dispatch time, written into the JSON contract. |

### Backups

Cron entry in `IDLE_PROTOCOL.md`: nightly `pg_dump` to `~/.openclaw/backups/openbrain-YYYY-MM-DD.sql.gz`. Retain 30 days. Never push backups to git.

## Data flow examples

### Capture (idle protocol nightly)

```
cron → python -m scripts.openbrain capture "<MEMORY.md entry>" --source idle-protocol
  → POST 127.0.0.1:8765/ tools/call capture_thought
  → MCP server: embed via Ollama (nomic-embed-text), extract metadata via Ollama (qwen2.5:7b)
  → INSERT into thoughts
  → return thought_id
```

### Recall (agent task start)

```
agent run → openbrain.recall(task="review PR #42", scope="project:openclaw")
  → POST 127.0.0.1:8766/recall  {task, scope, types}
  → API: vector search thoughts + filter sidecars by use_policy/scope
  → write recall_trace row
  → return policy-labeled memory list with recall_id
```

### Writeback (agent task end)

```
agent run → openbrain.writeback(content="...", kind="lesson", provenance={...}, use_policy="evidence")
  → POST 127.0.0.1:8766/writeback
  → API: content-hash dedupe → INSERT thought + provenance + use_policy rows
  → if use_policy="instruction": queue for human review
  → return memory_id
```

## Constraint compliance

| OpenClaw rule | How this satisfies it |
|---|---|
| 127.0.0.1 only | All container ports bound 127.0.0.1; no ingress. |
| Zero API spend | Embeddings + metadata via local Ollama; no OpenRouter/OpenAI. |
| No external transmission | Backups to `~/.openclaw/backups/` only; never pushed. |
| External content is data, not instructions | Default `use_policy=evidence`; `instruction`-grade requires human confirmation via review queue. |
| Tier-3 approval gates | Live trading promotion remains in clawmson.db / Telegram flow — unaffected. |
| Append-only memory | `thoughts` table is insert-only by convention; no public UPDATE path in the adapter. |

## Rollout phases

1. **Backend up.** Compose stack runs, `GET /health` returns ok on both services. Smoke test: capture three thoughts, search returns them ranked.
2. **Adapter + CLI.** `scripts/openbrain.py` works from shell. `python -m scripts.openbrain stats` non-empty.
3. **Backfill.** Bulk-capture existing `memory/MEMORY.md` entries, `improvements/*.md`, `autoresearch/outputs/briefs/*.md`. One thought per entry, tagged with `source` and original date in metadata.
4. **Pilot agents.** Wire `recall`+`writeback` into orchestrator + research agent configs only. Run 48h. Inspect `recall_trace` and `review_queue` outputs.
5. **Fleet rollout.** Remaining 11 agents wired per the tool-budget table. Lobster workflow templates updated.
6. **Skills install.** Copy 8 skills to `~/.claude/skills/`. Verify `/n-agentic-harnesses` triggers and produces a buildable plan on a sample prompt.

Each phase is independently revertible: removing the compose stack stops everything, MEMORY.md and clawmson.db are unaffected.

## Risks & open questions

| Risk | Mitigation |
|---|---|
| **Ollama wire-compat with OB1 MCP image.** Velo's image was written against OpenAI/OpenRouter `/v1/embeddings`. Ollama's endpoint *should* match but isn't promised. | Implementation plan includes an early **spike**: build the image, point at Ollama, capture one thought end-to-end. If incompatible, write a thin OpenAI→Ollama proxy (~30 lines) before continuing. |
| **Embedding dim mismatch.** OB1 default 1536. We patch to 768. | Schema-apply step explicitly substitutes dim. Pin in env var. Caught in spike. |
| **Schema drift between base `thoughts` and 7 sidecars.** Two SQL files applied in sequence. | Single `schema-init.sql` concatenated and idempotent (`CREATE TABLE IF NOT EXISTS`). Init container runs at boot. |
| **Cold-start latency.** Ollama loads `nomic-embed-text` lazily; first capture after idle ~10s. | Acceptable. Optionally warm via existing keep-alive cron. |
| **No fallback queue if Ollama down.** Captures fail fast. | Out of scope. Caller decides retry. Existing `outputs/` retry pattern absorbs this for cron jobs. |
| **`use_policy=instruction` review queue could grow unbounded.** | Phase 4 success criterion: review queue actively triaged. If it blows up, tighten skill instructions to default to `evidence`. |

## File layout (new)

```
~/code/claw-core/openclaw/
├── openbrain/
│   ├── docker-compose.yml
│   ├── schema-init.sql            # base thoughts + 7 sidecars, dim=768
│   ├── Dockerfile.mcp             # adapted from integrations/kubernetes-deployment/
│   ├── Dockerfile.agent-memory    # adapted from integrations/agent-memory-api/
│   └── README.md                  # ops runbook (start/stop/health/backup)
├── scripts/
│   ├── openbrain.py               # adapter + CLI
│   ├── openbrain-health.sh        # health check
│   └── openbrain-backfill.py      # one-time MEMORY.md / improvements / briefs ingest
└── docs/superpowers/specs/
    └── 2026-05-07-ob1-openclaw-integration-design.md  # this file
```

`~/.claude/skills/` gains 8 directories (drop-in copies from OB1 repo).

`~/.openclaw/openbrain/pgdata/` and `~/.openclaw/backups/` created at first run.

## Acceptance criteria

- `docker compose up -d` brings all three services healthy in < 30s on a warm cache.
- `python -m scripts.openbrain capture "test"` returns a thought_id; `search "test"` returns the thought.
- `python -m scripts.openbrain recall --task "..." --scope project:openclaw` returns a JSON object with `recall_id`, `memories[]`, and per-memory `use_policy`.
- Backfill of current `memory/MEMORY.md` produces N thoughts where N == number of dated entries.
- Orchestrator agent config calls `recall` before any task and `writeback` after, observable in `recall_trace`.
- 8 skills installed at `~/.claude/skills/` and `n-agentic-harnesses` produces a non-generic harness plan on the documented test prompt.
- All ports `lsof` as 127.0.0.1 only.
- `git status` in openclaw shows no `.env` / `pgdata/` / backup files staged.

## Out-of-scope follow-ups (not part of this spec)

- **Two-Door Audit pass** on the integrated system — schedule for the week after rollout.
- **Aiception loop** in `improvements/` — separate spec.
- **Per-vertical harness audits** (trading / build / ops / research) using `n-agentic-harnesses` — separate spec each.
- **Cross-tool memory** with Claude Desktop, ChatGPT, Cursor via the same MCP endpoint — works automatically once running, but documenting client configs is a follow-up.
- **Sharing `recall` results into Telegram dispatcher prompts** for richer DM context.

---

*Next step: `writing-plans` skill produces the implementation plan from this spec.*
