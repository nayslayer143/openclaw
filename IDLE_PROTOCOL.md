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

---

## Cycle 6: Idea Engine (PERPETUAL — highest priority after health)
**Schedule:** Daily at 11:30pm (`30 23 * * *`)
**Agent:** Research Agent (`llama3.3:70b` → fallback `qwen3:32b`)
**Script:** `scripts/cron-idea-engine.sh`

```
1. Pull memory context + past ideas (dedup)
2. Generate 10 SOLID, researched money-making ideas
   Categories: agentic SaaS, bounty gigs, arbitrage, digital products,
               meOS/xyz.cards monetization, AI agent services for SMBs
3. Write to outputs/ideas-{date}.md
4. Telegram Tier-2: numbered list, "Reply with number to approve"
5. Jordan reviews in the morning — replies trigger action plan within 2h
```

## Cycle 7: Bounty & Gig Scan
**Schedule:** Daily at 9pm (`0 21 * * *`)
**Agent:** Research Agent (`qwen3:30b`)
**Script:** `scripts/cron-bounty-scan.sh`

```
1. Scan Gitcoin, Replit Bounties, Contra, Malt, Freelancer, GitHub bounty issues
2. Filter: completable by AI agent, $100-$5000, no hard KYC
3. Write to outputs/bounties-{date}.md
4. If ≥3 actionable gigs: Tier-2 Telegram with summary + numbered list
5. Jordan replies to approve → Clawmpson drafts application within 1h
```

---

## Rules
- Clawmpson is NEVER idle. If no active task exists: run Cycle 6 → Cycle 7 → AutoResearch
- Ideas must be SOLID — researched, specific, realistic. No vague filler ever.
- Jordan wakes up to ≥10 reviewed ideas every morning. Non-negotiable.
- Z-schedule: suppress non-urgent Tier-2 pings Thursday nights and Z-weekends (every other weekend)
- Advanced cycles produce proposals only — never self-applied
- All idle work appends to `memory/IDLE_LOG.md`
- If a cycle fails 3 consecutive times: pause it, Tier-2 Telegram
- Jordan's engagement is the ONLY limiting factor. Clawmpson keeps the engine running.

---

## Cycle 8: OpenBrain (OB1) maintenance

**Stack:** `~/code/claw-core/openclaw/openbrain/` — Postgres + pgvector + Deno MCP server.
**Adapter / CLI:** `python3 -m scripts.openbrain` (capture/search/list/fetch/stats).
**Health:** `bash scripts/openbrain_health.sh`.

### Cron entries to add (DO NOT auto-install — Tier-3 needs Jordan)

```cron
# OB1 nightly backup → ~/.openclaw/backups/, 30-day retention
0  3 * * * bash $HOME/code/claw-core/openclaw/scripts/openbrain_backup.sh

# OB1 health check → syslog (oncall picks it up if "FAIL" appears)
15 3 * * * bash $HOME/code/claw-core/openclaw/scripts/openbrain_health.sh | logger -t openbrain-health
```

Print these with: `tail -8 IDLE_PROTOCOL.md` and add via `crontab -e`.

### Memory consolidation hook (idle-protocol consolidation script)

After any consolidation pass appends to `memory/MEMORY.md`, ALSO capture
the new entry into OB1 so it becomes searchable across sessions:

```python
# in your consolidation script, after MEMORY.md write succeeds:
try:
    from scripts.openbrain import OpenBrain
    with OpenBrain() as ob:
        ob.capture(entry_text, source="idle-protocol", scope="workspace")
except Exception as e:
    print(f"warn: openbrain capture failed: {e}", file=sys.stderr)
    # MEMORY.md write is authoritative; OB1 capture is best-effort secondary.
```

### Post-cycle summary capture (Cycles 1, 4, 6, 7)

Each cycle that produces a deliverable should end with a one-line capture:

```bash
python3 -m scripts.openbrain capture \
  "Cycle <N> ran at <time>: <one-line outcome>. Output: <path>" \
  --source idle-protocol --scope workspace
```

So Jordan's morning review can `python3 -m scripts.openbrain list --source idle-protocol -n 5`
to see what happened overnight without parsing IDLE_LOG.md.
