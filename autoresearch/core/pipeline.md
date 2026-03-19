# AutoResearch Pipeline — Shared Across All Domains

Every research task follows these 4 stages. No skipping. No reordering.

---

## Stage 1: DISCOVER

**Goal:** Frame the question and identify sources.

- Define the research question in one sentence
- Set scope: what's in, what's out, time horizon
- Identify 3-10 candidate sources (web, papers, repos, databases, internal memory)
- Score sources by expected signal-to-noise ratio (1-10)
- Drop any source scoring <4 unless it's the only source for a critical sub-question

**Output:** `discovery-brief.md` — question, scope, source list with scores

---

## Stage 2: GATHER

**Goal:** Pull data from sources, score relevance, deduplicate.

- Fetch content from top-scored sources (Stage 1)
- Extract key claims, data points, quotes (with source attribution)
- Score each extracted item for relevance to the research question (1-10)
- Deduplicate: if two sources say the same thing, keep the higher-authority one
- Flag contradictions between sources for synthesis stage

**Output:** `gathered-data.md` — structured list of claims/data with source, relevance score, contradictions flagged

---

## Stage 3: SYNTHESIZE

**Goal:** Cross-reference, extract patterns, form conclusions.

- Group related claims/data by theme
- Identify patterns: what do multiple sources agree on?
- Resolve contradictions: which source is more authoritative and why?
- Form conclusions: what does the evidence support?
- Identify gaps: what couldn't be answered with available sources?
- For academic domain: build citation graph

**Output:** `synthesis.md` — themed findings, conclusions, confidence levels, gaps

---

## Stage 4: STORE

**Goal:** Write final output and update system memory.

- Write the deliverable in the correct format for the domain:
  - Brief → `autoresearch/outputs/briefs/[slug]-[date].md`
  - Paper → `autoresearch/outputs/papers/[slug]-[date].md`
  - Dataset → `autoresearch/outputs/datasets/[slug]-[date].json`
- Append 1-line summary to `~/openclaw/memory/MEMORY.md`
- If findings are actionable: create task packet → `repo-queue/pending.md`
- If findings are publishable: flag for Jordan review (Tier-2)
- Clean up intermediate files (discovery-brief, gathered-data) — keep only final output

**Output:** Final deliverable + memory update + optional task packet

---

## Pipeline Rules

- Each stage must complete before the next begins
- If a stage fails (no sources found, contradictory data, etc.), stop and report to Orchestrator
- Intermediate files are working documents — delete after Stage 4
- Never publish or share research outputs without Jordan's Tier-2 approval
- All 4 stages combined should complete in <15 minutes for briefs, <60 minutes for papers
