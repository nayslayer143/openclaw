# Role-Specialist Bakeoff — 2026-03-19

**Models tested:** qwen3:30b, qwen2.5:7b, qwen3:32b, llama3.3:70b, qwen3-coder-next, devstral-small-2
**Run completed:** 20:47

## Master Decision Sheet

| Role | Model | Tasks Passed | Avg Latency | Format Errors |
|------|-------|-------------|-------------|---------------|
| coding | qwen3:32b | 10/10 | 5.4s | 0 |
| coding | qwen3-coder-next | 10/10 | 6.2s | 0 |
| coding | devstral-small-2 | 10/10 | 6.5s | 0 |
| research | qwen3:32b | 2/3 | 149.3s | 0 |
| research | qwen3:30b | 3/3 | 80.2s | 0 |
| ops | qwen3:32b | 3/3 | 83.6s | 0 |
| ops | qwen2.5:7b | 3/3 | 18.6s | 0 |
| business | qwen3:32b | 6/6 | 45.7s | 0 |
| business | qwen3:30b | 6/6 | 19.9s | 0 |
| memory | qwen3:32b | 2/2 | 102.8s | 0 |
| memory | llama3.3:70b | 2/2 | 265.4s | 0 |

## Role: Coding

### qwen3:32b — 10/10 passed, avg 5.4s

| Task | Status | Latency | Detail |
|------|--------|---------|--------|
| C1a: tool chain - read file | PASS | 12.3s | ok |
| C1b: tool chain - create branch | PASS | 3.5s | ok |
| C1c: tool chain - run bash | PASS | 2.8s | ok |
| C1d: tool chain - write result | PASS | 3.9s | ok |
| C1e: tool chain - telegram | PASS | 3.5s | ok |
| C1f: chained - read then branch | PASS | 5.8s | ok |
| C1g: chained - test then notify | PASS | 3.1s | ok |
| C1h: chained - branch and test | PASS | 5.6s | ok |
| C1i: chained - read and write | PASS | 3.4s | ok |
| C1j: chained - full loop | PASS | 9.7s | ok |

### qwen3-coder-next — 10/10 passed, avg 6.2s

| Task | Status | Latency | Detail |
|------|--------|---------|--------|
| C1a: tool chain - read file | PASS | 34.7s | ok |
| C1b: tool chain - create branch | PASS | 2.6s | ok |
| C1c: tool chain - run bash | PASS | 2.1s | ok |
| C1d: tool chain - write result | PASS | 2.8s | ok |
| C1e: tool chain - telegram | PASS | 2.5s | ok |
| C1f: chained - read then branch | PASS | 3.9s | ok |
| C1g: chained - test then notify | PASS | 2.2s | ok |
| C1h: chained - branch and test | PASS | 2.6s | ok |
| C1i: chained - read and write | PASS | 2.3s | ok |
| C1j: chained - full loop | PASS | 6.7s | ok |

### devstral-small-2 — 10/10 passed, avg 6.5s

| Task | Status | Latency | Detail |
|------|--------|---------|--------|
| C1a: tool chain - read file | PASS | 18.8s | ok |
| C1b: tool chain - create branch | PASS | 4.9s | ok |
| C1c: tool chain - run bash | PASS | 3.5s | ok |
| C1d: tool chain - write result | PASS | 5.7s | ok |
| C1e: tool chain - telegram | PASS | 5.3s | ok |
| C1f: chained - read then branch | PASS | 4.4s | ok |
| C1g: chained - test then notify | PASS | 4.7s | ok |
| C1h: chained - branch and test | PASS | 6.5s | ok |
| C1i: chained - read and write | PASS | 5.8s | ok |
| C1j: chained - full loop | PASS | 4.9s | ok |

## Role: Research

### qwen3:32b — 2/3 passed, avg 149.3s

| Task | Status | Latency | Detail |
|------|--------|---------|--------|
| R1: repo scout - EmergentWebActions | PASS | 44.7s | - Relevance score: 6/10   - Evidence: (1) The repo contains  |
| R2: competitor gap analysis | PASS | 103.2s | **Competitor 1: Iridescent Inc**   *Characterization:* DTC b |
| R3: 30-day launch plan | TIMEOUT | 300.0s | timed out |

### qwen3:30b — 3/3 passed, avg 80.2s

| Task | Status | Latency | Detail |
|------|--------|---------|--------|
| R1: repo scout - EmergentWebActions | PASS | 129.7s | We are given a GitHub repo URL: https://github.com/nayslayer |
| R2: competitor gap analysis | PASS | 31.4s | Okay, the user wants me to act as a Research Agent analyzing |
| R3: 30-day launch plan | PASS | 79.5s | Okay, the user is asking me to act as a Research Agent and P |

## Role: Ops

### qwen3:32b — 3/3 passed, avg 83.6s

| Task | Status | Latency | Detail |
|------|--------|---------|--------|
| O1: tier classification - 10 items | PASS | 63.1s | 1. **Item 1**: Tier 1 — [Checking loaded models is a read-on |
| O2: log triage | PASS | 150.3s | Here's a triage of the three log files, categorizing the ale |
| O3: task packet formatting | PASS | 37.4s | ```json {   "task_id": "build-1717000000",   "repo_path": "p |

### qwen2.5:7b — 3/3 passed, avg 18.6s

| Task | Status | Latency | Detail |
|------|--------|---------|--------|
| O1: tier classification - 10 items | PASS | 21.0s | 1. Run ollama list to check which models are loaded: Tier 1  |
| O2: log triage | PASS | 27.2s | ### Triage Summary  #### `ops-agent-2026-03-19.jsonl` - **FA |
| O3: task packet formatting | PASS | 7.7s | ```json {   "task_id": "build-202310171430",   "repo_path":  |

## Role: Business

### qwen3:32b — 6/6 passed, avg 45.7s

| Task | Status | Latency | Detail |
|------|--------|---------|--------|
| B1: market intel report - lenticular fashion | PASS | 139.9s | **Market Intelligence Report: North American Holographic Len |
| B2a: product copy - InformationCube | PASS | 30.3s | **Headline:**   The Information Cube: Where Thought Meets Pl |
| B2b: product copy - pfpcards | PASS | 24.4s | **Headline:**   Elevate Your Network with Laser-Etched Brass |
| B4a: support draft - shipping delay | PASS | 27.5s | Thank you for reaching out, and I'm truly sorry for the dela |
| B4b: support draft - NFC compatibility | PASS | 25.8s | Thank you for reaching out! Your pfpCard should work on all  |
| B4c: support draft - purchase inquiry | PASS | 26.3s | Hi there! Thanks for reaching out — we totally get the excit |

### qwen3:30b — 6/6 passed, avg 19.9s

| Task | Status | Latency | Detail |
|------|--------|---------|--------|
| B1: market intel report - lenticular fashion | PASS | 57.0s | Okay, the user wants me to create a market intelligence repo |
| B2a: product copy - InformationCube | PASS | 14.8s | Okay, the user wants me to act as a Business Agent and creat |
| B2b: product copy - pfpcards | PASS | 17.4s | Okay, the user wants me to write product page copy for pfpca |
| B4a: support draft - shipping delay | PASS | 11.7s | Okay, the user is a customer support agent needing to draft  |
| B4b: support draft - NFC compatibility | PASS | 10.6s | Okay, the user is reporting that their new pfpcard didn't wo |
| B4c: support draft - purchase inquiry | PASS | 7.9s | Okay, the user is asking about buying a holographic jacket t |

## Role: Memory

### qwen3:32b — 2/2 passed, avg 102.8s

| Task | Status | Latency | Detail |
|------|--------|---------|--------|
| M1: log synthesis - structured MEMORY.md append | PASS | 60.7s | ## 2026-03-19  **Completed:** - NFC write error task failed  |
| M2: failure pattern extraction | PASS | 145.0s | ### **Recurring Failure Pattern 1**   **Pattern Name:** Neo4 |

### llama3.3:70b — 2/2 passed, avg 265.4s

| Task | Status | Latency | Detail |
|------|--------|---------|--------|
| M1: log synthesis - structured MEMORY.md append | PASS | 239.3s | ## 2026-03-19 **Completed:**  - Health checks (morning and a |
| M2: failure pattern extraction | PASS | 291.5s | After analyzing the logs, I've identified two recurring fail |


*Generated by run-role-bakeoff.py — OpenClaw v4.2*