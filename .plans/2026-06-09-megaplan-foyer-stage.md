# Megaplan — foyer-stage — 2026-06-09

## 0 · TL;DR
Evolve Foyer's live client portal ("the Stage", [clientmcp.asdfghjk.lol/clientmcp/portal.html](https://clientmcp.asdfghjk.lol/clientmcp/portal.html)) from a verified demo into the honest, alive, machine-readable client-relationship surface designed in the 2026-06-09 strategy session. Scope per Jordan: **all identified tracks**, phased; this file is the GitHub reference point — cross tasks off by committing `- [x]` edits to it. Start with **Phase 1** (Phase 0 is infra hygiene; do it first or in parallel).

## 1 · Mission & Vision
- **Mission**: convert client anxiety ("is my money becoming progress?") into anticipation — status without meetings, decisions without email chains, receipts without awkwardness.
- **Vision**: every agency deliverable is a live, versioned, conversational surface; approvals are signed events forming the contract layer; the Stage is readable by humans *and* the client's own agents (it's literally Client MCP).
- **North star**: a client checks in <90s, always finds "what happened / what do you need from me / when's the next good thing", and approval feels like a ribbon-cutting. Demo→pilot signal: an unprompted client question answered by `/qa` with citations.

## 2 · Concept & Key Ideas
- "The Stage" = client-facing **projection** of agency truth; the lens must be *checkable* ("you see everything tagged client-visible"), never hidden curation.
- **The event log is the product** — append-only `{who, what, artifactVersion, ts, channel}`; the portal is a thin renderer over it.
- **Show depth, not delay** (labor paradox): stream the agent's work + rationales + rejected candidates; never fake slowness.
- Delight lives at the edges, never gates function (Knock at the Threshold, approval dust — shipped `8676637`).
- Theme system = secret white-label architecture: CSS vars per client brand.

## 3 · UX — Experience
- **Personas**: client principal (mobile, 11pm, anxious, 90-second visits — *checks*, doesn't *use*); agency operator (fewer status meetings, receipts); silent stakeholders (forwarded link).
- **Core flows**: check-in (open → "since you last looked" diff → review → approve/changes → leave happy) · naming co-authorship (edit brief → generate → star → approve) · ask-anything (`/qa` question → cited answer) · operator (decisions appear in agency feed).
- **IA / surfaces**: entry (threshold) → stage (deliverables · conversation · hill · brand) → review (per-type body + decision rail). Hash routes `#/stage/<id|slug>`, `#/review/<id|slug>/<delivId>`; themes `?v=`.

## 4 · UI — Look & Feel
- **Mood**: confident, slightly literary, threshold & hospitality metaphors; never corporate, never cute.
- **Palette** (Foyer Co seed): gold `#e9c97b` · ink `#1a1815` · cream `#f5f5f1` · bronze `#a17a3a`. Theme tokens in `[data-theme]` blocks, portal.html:19–47.
- **Type**: Atrium display = Cormorant Garamond (literary serif); Nocturne/Doorway display = Inter; kickers/meta = JetBrains Mono 10–11px tracked caps.
- **Motion**: `rise` screen entrances; knock/thud physicality; dust particle grammar (canvas, theme-accent colored); prefers-reduced-motion honored everywhere.
- **Components**: dcard deliverable rows + status tags, hill chart SVG, decision rail, composer thread, ✦ switcher (bottom-right), seam-of-light, Back Room overlay.

## 5 · Inspiration → Styleguide Matrix
| Inspiration source | What we take | Maps to |
|---|---|---|
| Basecamp Shape Up hill chart | status-without-meetings, figure-out vs make-it-happen | Project-status panel (SVG hill) |
| Aryze / SHIFT HAPPENS switcher | ✦/A/B/C theme lock, `?v=` + localStorage | Theme system → white-label tokens |
| Package tracking (the "where's my order" loop) | check-in cadence, diff-since-last-visit | Stage greeting, presence dot |
| Meow Wolf hidden-room culture | discoverable magic, rooms behind walls | Knock at the Threshold / Back Room / attic |
| `c.html` Stage design language | "private projection · live" voice, agent API contracts | Microcopy + `/demo/*` POST shapes |
| Labor-illusion research | perceived value of visible work | Streaming + rationale display (never fake delay) |

## 6 · Architecture & Execution Plan
- **Now**: single-file `dashboard/clientmcp/portal.html` (zero-build, served per-request by FastAPI StaticFiles, `dashboard/server.py:3062`) → Fastify monorepo backend `:4000` (`/Users/nayslayer/code/claw-research/client-mcp`, apps/+packages/, pg `:15432`, redis `:16379`) → Ollama `qwen2.5:7b` (mandatory: `FOYER_USE_OLLAMA=1`; Anthropic key has no credit). Dashboard proxy timeout 90s (`server.py:3041`).
- **Additions by phase**: `POST /demo/decision` + append-only decision store (P1) → SSE for naming + feed (P2) → Web Speech voice answers (P4) → MCP surface exposing stage resources/tools + deliverable-type registry contract + magic-link identity (P5).
- **Decision**: portal stays a thin single-file renderer until P5; truth accretes behind the API, not in the page.

## 7 · Phased Roadmap
Tracking convention: edit this file, flip `- [ ]` → `- [x]`, commit (`megaplan: cross off <task>`).

- **Phase 0 — Solid ground (infra hygiene)**
  - [ ] ~~Cherry-pick onto `main`~~ **AMENDED 2026-06-09:** `main` is 6 weeks stale (`5072d89`, 2026-04-23) — cherry-picking 3 portal commits onto it does NOT make the live tree safe, because the live dashboard can't run old main (missing ohyeah, landings a–e, newer server.py routes). Real fix = a deliberate merge/fast-forward of `feat/foyer-stage-portal` (which contains the ohyeah ancestry) into `main` — Jordan's call. Until then: live checkout stays on `feat/foyer-stage-portal`; do not switch it.
  - [x] `_subdomain_root_router` → pure-ASGI middleware — DONE `aedc495` 2026-06-09. Kickstarted + verified: apex/portal/clientmcp-root/dossier/ohyeah all 200; abort sweep produced no new `RuntimeError` (296 historical in log for contrast). Failure class structurally removed (no response buffering).
  - [ ] GitLab re-auth (`glab auth login`) **as part of rotating all ~25 leaked creds** (memory `project_openclaw_env_bak_leak`); consider un-silencing `pushall`.
  - [x] Backend deep-read — DONE 2026-06-09: Fastify monorepo `apps/server/src/routes/{demo,demo-agents}.ts`, drizzle schema in `packages/db/src/schema/` (audit_log is ADR-009 append-only, monthly-partitioned; inbound_messages needs channelId FK), per-IP limiter + daily budget idioms in demo-agents.ts. Streaming seam for P2 = the Ollama call inside demo-agents.ts naming handler.
- **Phase 1 — The honest core (truth loop)** — ✦ SHIPPED 2026-06-09 (`93e5a6a` client-mcp · `dc3e99f` openclaw)
  - [x] `POST /v1/demo/decision` — append-only audit_log event (client_user/update/stage_deliverable + diff) + stage-platform message into inbound_messages; demo-ID allowlist + 30/5min rate cap; `/v1/demo/feed` returns `decisions[]`. Verified: direct :4000, live proxy path, and UI click all landed events.
  - [x] Decisions render in the agency-side feed — server writes the conversation message ("Approved “Naming shortlist” — …", intent approval/feedback); portal local echo removed.
  - [x] `seedFor()` honest empty state (EMPTY_SEED + guards: empty deliverables card, review fallback, brand placeholder).
  - [x] "demo seed" chip on deliverables + "live" chip on conversation (hidden for non-seeded clients).
  - [x] `relTime` skew fix via feed `generatedAt` → global SKEW.
  - [x] (bonus) `scripts/portal-qa-proxy.py` — isolated portal+API QA loop on :8771 (launch.json `clientmcp-api`); cold-load screenshot shows all three decisions hydrated server-side.
- **Phase 2 — Alive (speed & presence)**
  - [ ] Stream naming candidates (SSE/chunked) — names appear one-by-one with rationales; kill the 15s spinner.
  - [ ] Model warmup noop on portal load (RAM-aware; `pse health --for-model qwen2.5:7b` first).
  - [ ] Live conversation via SSE (the LIVE badge becomes true).
  - [ ] "Since you last looked…" diff greeting (localStorage lastVisit vs event log).
  - [ ] Ambient presence dot ("your studio is here now").
- **Phase 3 — Ceremony & craft (design upscale)**
  - [ ] Approval ceremony v2: receipt moment in rail + soft chime + thread artifact.
  - [ ] Motion grammar pass: staggered dcard entrances, hill chart draw-on.
  - [ ] Time-of-day atmosphere (Atrium morning-cream → dusk-amber by local hour; greeting in voice).
  - [ ] Entry orb → door motif with hover seam (foreshadows the stash).
  - [ ] Self-host the 3 font families (kill FOUT); per-client favicon + OG card.
  - [ ] Mobile + reduced-motion audit (debug-mcp run).
- **Phase 4 — The Stage speaks**
  - [ ] Promote `/qa` to stage-level "Ask your Stage" (not buried in brief review).
  - [ ] Cited answers UI (citations already in contract: `{kind, snippet}`).
  - [ ] Voice reply via Web Speech synthesis — fulfills the Back Room hint ("hear it reply").
- **Phase 5 — Machine-readable & white-label**
  - [ ] Deliverable-type registry contract doc (`naming/brief/brand/generic` formalized; per-type render + decision semantics).
  - [ ] MCP surface: expose stage resources (deliverables, decisions, brand kit) + tools (ask, decide) — client's agent can pre-review.
  - [ ] Per-client theme tokens (client brand = their Stage's skin).
  - [ ] Magic-link identity (the "private" in "private projection" becomes true).
- **Phase 6 — Deeper magic (stash expansion)**
  - [ ] The Attic: find all 3 themes' Back Rooms → origami-fold payout into a hidden microsite (poem becomes navigable).
  - [ ] "open sesame" in composer; project-anniversary poem; seasonal dust (December snow); Coven ritual-variant Back Room ("a little dangerous").
- **Beyond** — foyer-of-foyers (client-side aggregator), decision log as contract layer, client-agent ↔ studio-agent negotiation.

## 8 · Skills & Tools per Phase
- Every phase gate: **verify-before-ping** / **verify** (reproduce → fix → re-verify through the live surface); **ship** to land; **secret-scan** before any push touching config/logs.
- P0: **codex:review** second opinion on the middleware diff (hotspot file, 99.6th %ile churn).
- P2/P4: **get-api-docs** for SSE + Web Speech specifics.
- P3/P6: **cinematic-web** (motion grammar) + **aesthetic-pulse** (the magic/maximal moments); **debug-mcp-audit** for the mobile/regression pass; **Pinterest Style Engine** optional before new visual surfaces.
- Routine build dispatch: **codemonkeyclaw** (local Qwen/DeepSeek); **/justdoit** for hands-free phases.

## 9 · References
- Live portal: [clientmcp.asdfghjk.lol/clientmcp/portal.html](https://clientmcp.asdfghjk.lol/clientmcp/portal.html) (`?v=atrium|nocturne|doorway`)
- Repo: [github.com/nayslayer143/openclaw](https://github.com/nayslayer143/openclaw) · branch `feat/foyer-stage-portal` @ `8676637` (portal `5611cd0`, QA fixes `9189439`, stash `8676637`)
- Portal source: `/Users/nayslayer/code/claw-core/openclaw/dashboard/clientmcp/portal.html` · agent contracts: `dashboard/clientmcp/c.html` `<script>`
- Backend: `/Users/nayslayer/code/claw-research/client-mcp` (restart playbook in repo `.claude/handoff.md` + memory `project_client_mcp`)
- Pre-build docs: `/Users/nayslayer/code/claw-research/client-mcp/docs/` (megaplan, ADR-001…010, naming sprint)
- QA artifacts: `/tmp/p2-*.png`, `/tmp/naming-live-result.json`

## 10 · Open Questions & Risks
- 🔴 Live dashboard serves the **working tree** — until Phase 0 lands the cherry-picks on `main`, switching branches 404s the live portal (parallel sessions have switched branches before).
- 🔴 ~25 leaked creds unrotated; GitLab auth dead (`invalid_grant`) and `pushall` hides its failures.
- 🟡 Middleware flake (intermittent 502/timeout) until P0 fix; never headless-screenshot the live subdomain — use launch.json server `clientmcp` (:8769).
- 🟡 qwen2.5:7b only (qwen3:32b hangs cold; Anthropic key empty); demo budget caps 429/`demo_budget_exhausted_today` are features, not bugs.
- Open: when does single-file portal split (P5 MCP work is the natural seam)? Name "Foyer" still pending TM clearance. Does P1 decision store live in pg or JSONL first (suggest: pg table, it's already running)?

---
## ▶ Start Building — Phase 0
1. Review §1–§5 — confirm mission / styleguide still hold (themes live in portal.html:19–47).
2. Run the Phase 0 checklist in §7 top-to-bottom — the worktree cherry-pick recipe is exact; middleware fix has a prepared spawn-chip (task_45452573) or do it inline per §7.
3. Skills: codex:review on the middleware diff, verify for the abort-test, ship to land, secret-scan before push.
4. Phase 0 done when: `git switch main` on the live checkout leaves [the portal](https://clientmcp.asdfghjk.lol/clientmcp/portal.html) serving 200; abort-test logs no RuntimeError; `git ls-remote gitlab feat/foyer-stage-portal` returns the SHA (auth restored).
