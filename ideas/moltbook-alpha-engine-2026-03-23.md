# Moltbook Alpha Engine — Parked Idea

**Status:** PARKED — revisit when Moltbook has real content
**Date:** 2026-03-23
**Source:** ChatGPT strategy session
**Claude assessment:** Concept interesting, timing premature, better fit as distribution channel than signal source

---

## What is Moltbook?

A social network for AI agents. Agents post, discuss, upvote. Humans observe. Think Reddit for agents.
URL: https://www.moltbook.com/
As of 2026-03-23: 0 verified agents, 0 posts, 0 comments. Platform is pre-launch.

---

## ChatGPT's Proposal: 4-Layer Alpha Engine

### Layer 1: Scout Agent (Ingestion)
- Passively ingest Moltbook data
- Extract raw observations WITHOUT interpretation
- Output: structured JSON (entities, actions, problems, claims)
- Rules: no interpretation, no scoring, preserve raw signal integrity

### Layer 2: Signal Engine (Interpretation)
- Convert raw observations into scored signals
- Signal types: problem, opportunity, trend, arbitrage
- Scoring: confidence (0-1), novelty (0-1), actionability (0-1)
- Time sensitivity: low/medium/high
- Classification: first_order, second_order, third_order
- Rules: prefer first-order signals, penalize consensus, detect contradictions

### Layer 3: Opportunity Engine (Execution)
- Convert signals into executable opportunities
- Opportunity types: build, trade, arbitrage, content, network
- Output: execution plan, required resources, estimated time, expected value
- Repeatability and automation potential scored
- Rules: must be concrete, executable, prefer repeatable systems

### Layer 4: Execution Interface
- Prepare opportunities for downstream systems (ArbClaw, builders)
- Output: priority_queue, quick_wins, long_term_bets
- Clean task packets, API-ready structure

### Layer 5: Learning Loop
- Track outcomes and improve scoring
- Compare predicted vs actual outcomes
- Adjust scoring weights over time
- Identify repeatable edges

---

## Claude's Assessment

### Why not now:
- Moltbook has zero content — nothing to ingest
- Public agent chatter is consensus by definition, not alpha
- Building a pipeline for a data source that doesn't produce data is premature
- Our existing five feeds (Polymarket, UW, Crucix, spot, base) provide proprietary signal — Moltbook would be public

### Where Moltbook fits better:
- **Distribution channel** for OpenClaw's content vertical
- Post MiroFish simulation reports, market analysis, research outputs TO Moltbook
- Build agent reputation, attract collaborators/clients
- Marketing/content play, not trading/alpha play

### If revisiting as a signal source:
- Check if Moltbook has meaningful content volume
- Assess whether agent posts contain information NOT already in our five feeds
- If yes, wire into existing ExternalSignal schema (v4.2) rather than building parallel system
- Use entity_type: "theme" or "event", source: "moltbook"
- Do NOT build the 4-layer architecture — integrate into existing MiroFish fusion layer

### Integration path (if/when ready):
```
Moltbook API → moltbook_feed.py (new, follows base_feed.py protocol)
   → ExternalSignal normalization
   → existing data fusion pipeline (v4.2 section 8)
   → confidence/sizing modifiers on existing strategies
```
NOT a separate system. A new feed into the existing architecture.

---

## Revisit Trigger

Check back when ANY of these are true:
- Moltbook has 100+ active agents posting daily
- Moltbook has a public API with documented endpoints
- A competitor or collaborator is visibly extracting value from Moltbook data
- Jordan says so

---

## Original ChatGPT Prompt (Preserved)

The full "OPENCLAW MOLTBOOK ALPHA ENGINE — PHASE 1 BUILD" prompt is preserved below for future reference.

### System Rules from ChatGPT's proposal:
1. NEVER allow raw Moltbook data directly into execution
2. ALWAYS pass through scoring and filtering
3. MAINTAIN separation between ingestion and decision-making
4. OPTIMIZE for SPEED + ACCURACY
5. LOG EVERYTHING for learning loop

### Phase 2 hooks (design only, don't build):
- Multi-agent coordination layer
- External data fusion (trading, social, internal data)
- Automated execution pipelines
- Feedback-driven model tuning
