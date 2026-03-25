# AutoScholar — Agent Config

## Role
Paper discovery, digestion, and routing agent. Monitors HuggingFace for papers
relevant to active OpenClaw domains and surfaces actionable research to the build
pipeline, bakeoff queue, and Clawmson.

## Entry Points

| Trigger | Function | When |
|---------|----------|------|
| Cron (nightly 2am) | `auto_mode()` | Automated overnight sweep |
| Telegram `/papers [topic]` | `discover()` | On-demand search |
| Telegram `/digest [paper_id]` | `digest_paper()` | On-demand deep dive |
| Telegram `/scholar status` | `get_recent_papers()` | Status check |
| ClawTeam debate | `get_paper_for_debate()` | Debate pattern input |

## Models Used

| Model | Purpose |
|-------|---------|
| `qwen3:30b` | Paper digestion and insight extraction |
| `nomic-embed-text` | Semantic relevance ranking |

## Configuration

| Env var | Default | Purpose |
|---------|---------|---------|
| `SCHOLAR_RELEVANCE_THRESHOLD` | `0.75` | Auto-digest minimum score |
| `SCHOLAR_DIGEST_MODEL` | `qwen3:30b` | Digestion model |
| `SCHOLAR_EMBED_MODEL` | `nomic-embed-text` | Embedding model |

## Output Locations

| Output | Path |
|--------|------|
| Daily digest | `autoresearch/outputs/papers/academic-scholar-digest-[date].md` |
| Improvement proposals | `improvements/scholar-[slug]-[date].md` |
| Bakeoff flags | `benchmark/bakeoff-queue.md` |
| Build context notes | `autoresearch/outputs/papers/academic-[slug]-[date].md` |

## Data

- SQLite: `~/.openclaw/clawmson.db` — tables `papers`, `paper_digests`
- Logs: `logs/cron-scholar.log`

## Cron Schedule

```
0 2 * * *  bash ~/openclaw/scripts/cron-scholar.sh
```

Add to crontab with: `crontab -e`

## Action Routing Rules

| Condition | Output |
|-----------|--------|
| P1 + implementable techniques | `improvements/scholar-*.md` |
| Linked HF models found | `benchmark/bakeoff-queue.md` (append) |
| P1 + non-empty relevance | `autoresearch/outputs/papers/academic-*.md` |

## Domains Monitored (default)

- agent orchestration
- prediction markets
- memory architectures
- local LLM optimization
- multi-agent systems
- RAG retrieval augmented
- tool use LLM
- agentic systems

## Watchlist

Named papers and techniques with explicit monitoring targets.
File: `scripts/autoresearch/watchlist.json`

`auto_mode()` merges all `monitor.search_terms` from watchlist entries into the
overnight domain sweep automatically. To add a new entry: edit `watchlist.json`.

| ID | Name | Priority | Tags |
|----|------|----------|------|
| turboquant | TurboQuant (Google — extreme KV cache compression) | P1 | quantization, KV-cache, inference-optimization, ollama, local-llm |

## Source

`scripts/autoresearch/scholar.py`
