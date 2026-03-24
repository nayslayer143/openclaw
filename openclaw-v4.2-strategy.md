# OpenClaw v4.2 Strategy

## From Paper Trading System → Self-Improving Alpha Factory

**Author:** OpenClaw
**Owner:** Jordan
**Date:** 2026-03-23
**Phase:** Transition from Phase 4 → Phase 5

---

## 0. Executive Summary

OpenClaw is no longer a theoretical market-intelligence stack. It is already a working paper-trading system with:

- a fast Polymarket scanner
- a deeper multi-strategy trading brain
- five integrated data feeds
- SQLite-backed wallet, PnL, and graduation gates
- multi-agent orchestration and Telegram approval flows

**v4.2 formalizes the next step:**

> Extend the existing system into a cross-venue, execution-aware, agent-coordinated alpha factory.

This is an evolution, not a rebuild.

**v4.2 preserves:**

- `trading-bot.py` as the fast scout / fast-path executor
- MiroFish as the deep analysis + risk-managed executor
- existing four strategies
- five-feed advantage
- graduation gates
- approval tiers
- agent architecture

**v4.2 adds:**

- venue-agnostic `MarketEvent` normalization
- Kalshi integration
- cross-venue matching and arbitrage
- realistic execution simulation
- edge-capture and expected-vs-realized metrics
- strategy tournament + capital allocator
- explicit agent coordination
- Telegram operational surfaces

---

## 1. Current State (Reality Baseline)

### 1.1 What Exists Today

Two active paper-trading systems:

**System A — `trading-bot.py`**

- Fast Polymarket scanner
- Lightweight LLM edge analysis
- JSON-backed paper trading state
- Runs on a lower-latency cadence
- Suitable for obvious opportunities and fast-path execution

**System B — MiroFish Trading Brain**

- Multi-strategy engine
- SQLite-backed wallet
- Kelly sizing, stop-loss, take-profit, graduation gates
- Deeper analysis cadence
- Suitable for validation, sizing, fusion, and tournament logic

### 1.2 Existing Strategy Set

Current active strategies:

- single-venue arbitrage
- price-lag arbitrage
- momentum detection
- LLM analysis

These remain in the system and become entrants in the future tournament layer.

### 1.3 Existing Data Advantage

Five current feeds:

- Polymarket
- Unusual Whales
- Crucix
- spot crypto
- base feed protocol

These are not side information. They are part of the confidence, sizing, and filtering stack.

### 1.4 System Strengths

- Real signals already generated
- Real trades already simulated
- Full PnL tracking
- Graduation gating discipline
- Multi-agent orchestration
- Zero API cost inference
- Persistent memory + workflows

### 1.5 System Limitations

- Single-venue arbitrage only
- No execution realism (perfect fills assumed)
- No cross-strategy competition
- No edge capture measurement
- No persistence-aware filtering
- No cross-venue schema
- No Kalshi integration

---

## 2. Core Shift in v4.2

**From:** Run strategies and track PnL.

**To:** Continuously discover, evaluate, route, rank, and allocate across strategies using execution-aware truth metrics.

**Core principle:**

```
apparent edge ≠ executable edge ≠ realized edge
```

The system must optimize for realized edge, not visible spread or backtest fantasy.

---

## 3. Target Architecture

```
Fast Scout Layer (trading-bot.py)
        ↓
Candidate Opportunity Queue
        ↓
Canonical Market Normalization
        ↓
Cross-Venue Matcher + Existing Strategy Engines
        ↓
Signal Fusion Layer (UW + Crucix + Spot + LLM + Simulation)
        ↓
Execution Scoring Layer
        ↓
Paper Execution Simulator / Live Gate
        ↓
PnL + Truth Metrics Engine
        ↓
Tournament + Capital Allocator
        ↓
OpenClaw Meta-Optimizer
        ↓
Telegram / Human Approval Surface
```

---

## 4. Primary New Capability: Cross-Venue Arbitrage

### 4.1 First Edge

Same underlying event, different executable prices across Polymarket and Kalshi.

### 4.2 Requirements

This requires:

- Kalshi feed
- venue-agnostic normalization
- contract matching
- resolution-text validation
- fee-aware pricing
- persistence and fill-aware scoring

### 4.3 Matching Rule

A cross-venue opportunity is only eligible if all are true:

- same underlying event
- materially compatible settlement criteria
- compatible end time / resolution window
- executable spread after fees
- sufficient depth at target size
- persistence above threshold

If settlement wording differs materially, this is not arbitrage. It is a correlated bet.

---

## 5. Canonical Market Schema

The schema must support:

- binary and bracket contracts
- venue-specific fee schedules
- order-book depth
- resolution-text validation
- sub-second persistence tracking
- matching between venue contracts and research signals

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal, Optional

Venue = Literal["polymarket", "kalshi"]
ContractType = Literal["binary", "bracket", "multi_outcome"]
Side = Literal["yes", "no"]
SignalSource = Literal[
    "polymarket",
    "kalshi",
    "unusual_whales",
    "crucix",
    "spot",
    "llm",
    "simulation",
]

@dataclass(slots=True)
class OrderBookLevel:
    price: float
    size: float

@dataclass(slots=True)
class OutcomeBook:
    outcome: str                 # "YES", "NO", ">$120k", etc.
    bid: float
    ask: float
    last: float
    bid_size: float
    ask_size: float
    bids: list[OrderBookLevel] = field(default_factory=list)
    asks: list[OrderBookLevel] = field(default_factory=list)

@dataclass(slots=True)
class VenueFees:
    taker_bps: float
    maker_bps: float
    settlement_fee_bps: float = 0.0
    withdrawal_fee_fixed: float = 0.0
    notes: str = ""

@dataclass(slots=True)
class ContractSpec:
    contract_type: ContractType
    underlying: str                      # "BTC", "US election", "Fed rate", etc.
    strike: Optional[float] = None       # for threshold/bracket contracts
    lower_bound: Optional[float] = None  # for bracket
    upper_bound: Optional[float] = None  # for bracket
    expiry_ts_ms: int = 0
    timezone: str = "UTC"

@dataclass(slots=True)
class ResolutionSpec:
    resolution_text: str
    source_rules_url: Optional[str] = None
    resolves_yes_if: Optional[str] = None
    resolves_no_if: Optional[str] = None
    ambiguity_flags: list[str] = field(default_factory=list)

@dataclass(slots=True)
class MarketEvent:
    market_id: str
    venue: Venue
    title: str
    question: str
    category: str
    contract: ContractSpec
    resolution: ResolutionSpec
    outcomes: list[OutcomeBook]
    volume_24h: float
    open_interest: float
    fees: VenueFees
    ts_ms: int                          # event timestamp in ms
    observed_at_ms: int                 # ingestion timestamp in ms
    status: Literal["open", "halted", "closed", "resolved"]
    raw_payload_ref: Optional[str] = None
    tags: list[str] = field(default_factory=list)

@dataclass(slots=True)
class MatchedMarketPair:
    pair_id: str
    left: MarketEvent
    right: MarketEvent
    match_confidence: float             # 0-1 semantic + rules-based match
    settlement_compatible: bool
    incompatibility_reasons: list[str] = field(default_factory=list)
    normalized_underlying_key: str = ""

@dataclass(slots=True)
class ExternalSignal:
    signal_id: str
    source: SignalSource
    ts_ms: int
    entity_type: Literal["ticker", "sector", "macro", "event", "theme", "person"]
    entity_key: str                     # "XLE", "defense", "rates", "BTC", etc.
    direction: Literal["bullish", "bearish", "neutral"]
    strength: float                     # normalized 0-1
    confidence: float                   # normalized 0-1
    horizon_hours: float
    half_life_hours: float = 24.0       # fusion layer applies time decay before relevance scoring
    metadata: dict = field(default_factory=dict)
```

### 5.1 Why this schema is enough

It supports:

- depth-aware pricing via full `bids` / `asks`
- fee-aware scoring via `VenueFees`
- resolution checks via `ResolutionSpec`
- brackets / thresholds via `ContractSpec`
- persistence tracking via millisecond timestamps
- feed fusion via `ExternalSignal` with time-decay support
- cross-venue matching via `MatchedMarketPair`

---

## 6. Real vs Fake Arbitrage

A visible spread is only "real" if it survives contact with execution.

### 6.1 Eligibility Gates

A candidate arb must pass:

- settlement compatibility
- executable spread after fees
- minimum persistence
- minimum depth at intended size
- acceptable fill probability
- acceptable latency decay
- no stale feed anomalies

### 6.2 Arb Score

Use a normalized weighted score:

```python
arb_score = (
    w_spread * spread_z
    + w_persistence * persistence_z
    + w_depth * depth_z
    + w_fill * fill_prob_z
    - w_latency * latency_decay_z
    - w_mismatch * mismatch_penalty_z
    - w_staleness * staleness_penalty_z
)
```

All components should be normalized to comparable ranges before weighting.

---

## 7. Arb Score Calibration

The weights need a bootstrap phase, then an adaptive phase.

### 7.1 Bootstrap Phase (low data)

Before real cross-venue fills exist:

- use hand-set priors
- treat settlement compatibility as a hard gate, not a soft weight
- heavily overweight persistence and depth
- heavily penalize latency decay and staleness
- use conservative defaults by venue pair

Initial starting weights:

```python
INITIAL_WEIGHTS = {
    "spread": 0.30,
    "persistence": 0.20,
    "depth": 0.20,
    "fill": 0.15,
    "latency": 0.10,
    "mismatch": 0.03,
    "staleness": 0.02,
}
```

These are not sacred. They are bootstrapping priors.

### 7.2 Bootstrap Method

At the start:

1. collect opportunities without trading all of them
2. log score components for each
3. simulate execution under pessimistic assumptions
4. compare which components predicted retained edge

This creates the first calibration set.

### 7.3 Adaptive Phase (once fills accumulate)

After enough paper trades:

- fit a simple logistic model or gradient-boosted classifier to predict:
  - fill success
  - retained edge after latency
  - profitable completion
- fit per venue-pair and per contract-type where sample size permits
- back off to global weights when sample size is too low

### 7.4 Update Cadence

- daily recalibration for diagnostics only
- weekly weight promotion into active configuration
- no automatic promotion without passing graduation-style checks

### 7.5 Tournament Interaction

The tournament engine does not directly mutate weights every run. It can:

- compare scoring variants
- incubate alternate weight sets
- recommend promotion of new weights
- retire underperforming scoring configs

So: bootstrap manually → adapt statistically → promote conservatively.

---

## 8. Data Fusion Architecture

This is not a vibes layer. It must alter: confidence, sizing, filtering, scenario checks.

### 8.1 Data Flow

```
Feed signal
   ↓
Normalize into ExternalSignal
   ↓
Apply time decay based on half_life_hours
   ↓
Map to entity graph / market ontology
   ↓
Match against open MarketEvents
   ↓
Compute signal-market relevance score
   ↓
Apply impact policy
      - confidence adjustment
      - Kelly multiplier adjustment
      - filter pass/fail
      - hedge recommendation
      - simulation trigger
   ↓
Write fused decision payload
```

Before relevance scoring, all `ExternalSignal` values are time-decayed based on `half_life_hours`, so older signals lose influence unless refreshed or reinforced by new evidence.

### 8.2 Mapping Layer

Build a lightweight ontology:

- ticker → sector → theme → market keywords
- entity → event domain
- macro regime → affected categories

Examples:

- `LMT`, `NOC`, `RTX` → defense sector → military spending / conflict escalation markets
- `XLF`, `KRE`, yield inversion → banking stress / recession / Fed markets
- `BTC`, `ETH` → crypto threshold / bracket markets

### 8.3 Functional Pathways

**Case A: Congressional defense selling + defense-spending market**

1. Unusual Whales emits `ExternalSignal(entity_key="defense", direction="bearish", strength=0.72)`
2. Market matcher finds open Polymarket / Kalshi contracts tagged: defense spending, Pentagon budget, defense contractor performance
3. Relevance scorer computes match confidence
4. Impact policy:
   - if an existing trade thesis already points bearish, increase confidence modestly
   - if current position is bullish, reduce size or require extra confirmation
   - if no trade exists, generate a candidate for LLM + simulation review, not an auto-trade by default

Rule example:

```
aligned external signal → confidence += 0.05 to 0.12
conflicting external signal → Kelly multiplier *= 0.6
high-strength conflicting signal → block new position unless manually reviewed
```

**Case B: VIX spike + yield inversion from Crucix**

1. Crucix emits two macro signals: risk-off volatility spike, recession / tightening stress regime
2. Regime engine marks current regime `macro_risk_off`
3. Impact policy:
   - tighten stops on momentum longs
   - increase hedge preference
   - reduce Kelly multiplier for risk-on contracts
   - raise threshold for new speculative trades
   - prioritize macro and recession-related contracts for scanning

Rule example:

```
if macro_risk_off:
    momentum_kelly *= 0.7
    hedge_budget += 10-20%
    stop_loss_distance *= 0.85
```

**Case C: Dark pool accumulation in a mapped sector**

1. Unusual Whales emits bullish dark-pool accumulation in semis
2. Ticker mapper resolves to sector/theme `semiconductors`, `AI infrastructure`
3. Match against prediction markets containing: NVDA / chip export / AI capex / market-share or index-level outcomes
4. Impact policy:
   - increase confidence if aligned
   - create candidate if combined with spot / price-lag support
   - use as a second-order confirming signal, not primary signal by itself

### 8.4 Impact Types

Each matched signal can do one or more of:

- confidence modifier
- Kelly multiplier modifier
- hard filter
- stop adjustment
- hedge suggestion
- simulation trigger

### 8.5 Fusion Priority

Priority order:

1. hard market structure facts
2. venue-specific executable edge
3. settlement compatibility
4. macro / external signals
5. LLM synthesis

External signals never override a broken executable setup.

---

## 9. MiroFish Simulation + Research Integration

The simulation engine is not a separate vanity system. It becomes a pre-trade and post-trade advantage layer.

### 9.1 When Simulation Runs

Trigger scenario analysis when:

- trade size exceeds threshold
- score is high but external signals conflict
- cross-venue arb match confidence is less than perfect
- macro regime is unstable
- Jordan requests a deeper review

### 9.2 What Simulation Produces

Simulation outputs:

- scenario tree
- thesis stability
- failure modes
- key unknowns
- confidence bands
- recommended action: proceed, reduce size, hedge, watch, reject

### 9.3 Pipeline Position

```
Candidate trade
   ↓
Rules + scoring
   ↓
If high-impact / ambiguous → MiroFish simulation
   ↓
Simulation result modifies confidence / size / hold decision
```

---

## 10. Agent Architecture in v4.2

The 13-agent system must become explicit in the strategy.

### 10.1 Orchestrator

- route tasks between scout, MiroFish, research, memory, security, and build agents
- enforce approval tiers
- manage queue priority under load
- decide when fast-path vs deep-path is appropriate

### 10.2 Research Agent

- gather context on ambiguous or high-conviction opportunities
- request MiroFish scenario runs
- produce event brief when external signals materially affect a trade

### 10.3 Memory Librarian

- record what signal combinations worked
- persist failure modes and parameter lessons
- maintain a strategy changelog
- surface prior similar opportunities to the scorer / tournament engine
- creates candidate parameter updates and warnings (not direct auto-overrides)

### 10.4 Security Auditor

- detect stale feed data
- detect timestamp anomalies
- detect structurally impossible prices
- flag venue/API drift
- quarantine suspicious opportunities before they hit execution

### 10.5 Trader Agent / MiroFish Trader

- run strategies
- compute scores
- size positions
- submit to paper executor
- report metrics

### 10.6 Agent Coordination Sequence for Cross-Venue Arb

```
1.  Scout detects candidate spread
2.  Orchestrator creates opportunity task
3.  Security auditor validates feed freshness / anomaly checks
4.  Matcher validates settlement compatibility
5.  MiroFish trader computes executable edge + score
6.  If threshold exceeded:
      - low ambiguity / obvious → fast path
      - high ambiguity / larger size → research + simulation
7.  Risk checks run
8.  Paper execution or Tier-3 hold for live
9.  Memory librarian stores outcome pattern
10. Tournament engine updates comparative stats
11. Telegram sends alert / digest
```

---

## 11. Two-System Strategy

Do not collapse the two systems.

### 11.1 Long-Term Design

The two-tier architecture is a feature.

**`trading-bot.py`**

- fast scout
- fast-path detector
- can independently execute obvious, rule-clean paper trades

**MiroFish**

- deep evaluator
- fused signal engine
- risk-managed sizing layer
- tournament participant and allocator input

### 11.2 Fast Path vs Deep Path

**Fast path:**

- obvious single-venue arb
- spread above slam-dunk threshold
- low ambiguity
- no conflicting macro/security flags
- can execute without waiting for deep analysis

**Deep path:**

- cross-venue arb
- larger position sizes
- conflicting signals
- ambiguous settlement wording
- regime-sensitive trades
- LLM / simulation-assisted decisions

### 11.3 Relationship

The scanner and MiroFish are: cooperative, partially competitive, intentionally non-unified. This preserves speed tier and depth tier simultaneously.

---

## 12. Risk Management

Existing rules remain:

- 10% max position
- stop-loss -20%
- take-profit +50%
- graduation gates unchanged

### 12.1 New Risk Controls

- settlement mismatch blocker
- stale-feed blocker
- latency-decay blocker
- fill-probability floor
- cross-strategy exposure view
- regime-sensitive Kelly dampening

### 12.2 Capital Reallocation Rules

- small parameter rebalance: Tier 1 if internal and paper-only
- meaningful strategy allocation change: Tier 2 minimum
- any live reallocation >20% of deployable capital: Tier 3

---

## 13. Telegram + Operations Integration

Every major capability needs an operator surface.

### 13.1 Telegram Alerts

- cross-venue arb detected
- fast-path trade executed
- simulation-required candidate
- daily tournament rankings
- strategy promoted / killed
- security anomaly / stale feed block
- graduation-state update

### 13.2 Telegram Commands

- `!scan-crossvenue` — force immediate Polymarket ↔ Kalshi scan
- `!rankings` — show current tournament standings
- `!strategy [name]` — show strategy metrics and recent performance
- `!kill [strategy]` — hold / disable strategy
- `!revive [strategy]` — re-enable strategy
- `!simulate [market-id or thesis]` — run deeper scenario analysis
- `!rebalance` — show suggested capital allocation changes
- `!approve-tier2 [id]`
- `!approve-tier3 [id]`

### 13.3 Human Override

Jordan can:

- override strategy kill decisions
- force watch-only mode
- approve or reject capital allocation changes
- manually trigger scans and simulations

### 13.4 Queue / Backpressure Logic

When 50+ signals arrive at once:

1. hard-filter invalid / stale / low-score candidates
2. prioritize by: executable edge, urgency / persistence decay, capital relevance, strategy novelty
3. route obvious fast-path signals first
4. batch lower-priority items into analysis queue
5. enforce per-cycle processing caps

Priority classes:

- **P0:** active executable arb, decaying fast
- **P1:** high-score non-urgent candidates
- **P2:** simulation / research tasks
- **P3:** logging / memory / summary work

---

## 14. Cost Discipline

The hard system budget remains $10/day.

### 14.1 API Cost Rule

Kalshi integration does not begin until API pricing, access conditions, and expected polling costs are verified to fit within the system's $10/day hard cap or an explicit budget exception is approved.

Any Kalshi integration must be designed with:

- a cached polling layer
- rate-aware scheduling
- incremental refreshes
- cost accounting in daily ops summary

### 14.2 Cost Controls

- prefer polling cadence that matches actual edge half-life
- avoid full refresh when partial market updates suffice
- degrade gracefully under budget pressure
- use scout-layer filtering before expensive deep analysis

---

## 15. Truth Metrics

Track:

- expected PnL
- realized PnL
- edge capture rate
- fill rate
- slippage
- missed opportunity PnL
- opportunity lifetime
- capital efficiency
- drawdown
- per-strategy and per-venue breakdowns

Most important:

```
edge_capture_rate = realized_pnl / expected_pnl
```

This becomes the central optimization target.

---

## 16. Strategy Tournament

The tournament engine compares:

- existing four strategies
- new cross-venue arb strategy
- alternate scoring-weight variants
- alternate execution assumptions
- fast-path vs deep-path variants

It outputs: keep, incubate, scale, kill.

The tournament can suggest capital allocation changes, but human approval still governs live changes.

---

## 17. Implementation Roadmap

### Phase 5A — Foundation

1. **Verify Kalshi API access model, cost model, and rate limits against the $10/day system budget** *(gate — blocks all subsequent Kalshi work)*
2. Implement canonical `MarketEvent` schema
3. Add Kalshi feed
4. Add cross-venue matcher
5. Add resolution compatibility validator

### Phase 5B — Execution Reality

1. Add order-book depth ingestion
2. Add realistic fill simulation
3. Add slippage / latency / partial-fill modeling
4. Add stale-data and anomaly checks
5. **Wire security auditor into pre-execution validation** *(moved from 5D — must be in place before trusting execution sim results)*

### Phase 5C — Truth Layer

1. Expected vs realized PnL
2. Edge capture rate
3. Missed opportunity PnL
4. Persistence / lifetime distributions

### Phase 5D — Signal Fusion + Agents

1. Normalize `ExternalSignal` with time-decay
2. Build entity / market mapping layer
3. Connect research, simulation, memory agents into pipeline
4. Add Telegram surfaces

### Phase 5E — Strategy Competition

1. Tournament engine
2. Scoring-weight experiments
3. Capital allocator with approval gates
4. Per-strategy ranking digests

### Phase 5F — Backtesting + Replay

1. Historical replay engine
2. Scoring calibration loops
3. Scenario archive + similar-case retrieval
4. Promotion rules for new models / weights

---

## 18. What Not To Do

- Do NOT rebuild existing feeds, wallet, dashboard, or approval systems
- Do NOT unify the fast and deep systems into one monolith
- Do NOT trust visible spread without execution realism
- Do NOT let external signals override broken trade structure
- Do NOT scale capital before edge capture is proven
- Do NOT auto-promote new score weights without conservative validation
- Do NOT begin Kalshi integration before verifying API cost model

---

## 19. Success Definition

v4.2 is successful when:

- Polymarket ↔ Kalshi matching is operational
- cross-venue opportunities are scored with executable realism
- edge capture is visible and improving
- the two-tier fast/deep system is preserved
- feed fusion changes confidence and sizing in measurable ways
- agent coordination is explicit and logged
- Telegram becomes a real command-and-control surface
- strategy rankings drive internal selection pressure

---

## 20. Final Truth

The system that wins is not the one with the most strategies.

It is the one that:

- filters reality best
- executes most honestly
- learns from outcomes
- allocates attention and capital intelligently

That is what OpenClaw v4.2 is now for.
