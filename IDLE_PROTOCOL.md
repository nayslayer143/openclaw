# IDLE_PROTOCOL.md — OpenClaw Idle-Time Cron Schedule

> When no active task exists, agents run these cycles.
> All idle work logged to `memory/IDLE_LOG.md`.
> Lite tier launches in Phase 1. Advanced tier is Phase 4 only.

---

## Lite Tier — 4 Deterministic Lobster Cron Workflows

### Cycle 1: Health Watchdog
**Schedule:** Every 2 hours (`0 */2 * * *`)
**Agent:** Ops Agent (`qwen2.5:7b`)
**Workflow:** `lobster-workflows/system-health.lobster`

```
1. ollama list — models responding?
2. disk usage — alert Tier-2 if >80%
3. scan today's agent logs for FATAL/ERROR entries
4. pending queue depth — alert Tier-2 if >20 items
5. append status to logs/ops-{date}.jsonl
```

### Cycle 2: Intel Scan
**Schedule:** Every 4 hours, 8am–10pm only (`0 8,12,16,20 * * *`)
**Agent:** Research Agent (`qwen2.5:32b`)
**Workflow:** `lobster-workflows/daily-intel-lite.lobster`

```
1. check outputs/ for unprocessed bookmark-scout-*.md
2. check outputs/ for unprocessed reddit-scout-*.md
3. for any unprocessed report: extract repos scored ≥7/10 → repo-queue/pending.md
4. flag CROSS-REF items (appear in both sources) as high-priority
5. append scan summary to memory/IDLE_LOG.md
```

### Cycle 3: Content Pipeline Check
**Schedule:** Every 6 hours (`0 9,15,21 * * *`)
**Agent:** Marketing Agent [Phase 3+] (`qwen2.5:32b`)

```
1. check Marketing Agent content queue (Phase 3+)
2. if any item due in next 24h: draft → Tier-2 Telegram → hold
3. if nothing due: log "Content pipeline clear" and exit
```

### Cycle 4: Daily Memory Consolidation
**Schedule:** Daily at 11pm (`0 23 * * *`)
**Agent:** Orchestrator (`qwen2.5:32b`) → [Phase 4] Memory Librarian (`qwen2.5:32b`)

```
1. read all today's agent logs
2. extract: completed tasks, errors, patterns, durations
3. append structured summary (not raw transcripts) to memory/MEMORY.md
4. compress logs older than 7 days → logs/archive/
5. send Tier-1 Telegram: "Nightly check ✓ | Tasks: N complete, N failed"
```

---

## Advanced Tier — Phase 4 Only

> Do not activate until 4 weeks of boring lite-tier logs.

### Cycle 5: Self-Improvement Loop
**Schedule:** Every 48 hours (`0 22 */2 * *`)
**Agent:** Memory Librarian (`qwen2.5:32b`)

```
1. review MEMORY.md for recurring failure patterns
2. draft improvement proposals for AGENT_CONFIG.md or Lobster workflows
3. send Tier-2 Telegram with top 3 proposals — hold for approval
4. if approved: git branch → apply change → commit → notify Jordan
5. never apply unapproved changes
```

---

## Rules
- Lite cycles are deterministic — no creative interpretation, no speculative work
- Advanced cycles produce proposals only — never self-applied
- All idle work appends to `memory/IDLE_LOG.md`
- If a cycle fails 3 consecutive times: pause it, Tier-2 Telegram
