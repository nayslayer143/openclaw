# Kalshi API Verification Gate -- Phase 5A Step 1

**Date:** 2026-03-23
**Gate:** Phase 5A Step 1 -- Verify Kalshi API access model, cost model, and rate limits
**Researcher:** Claude Code (automated)
**Sources:** docs.kalshi.com, Kalshi OpenAPI spec, pykalshi/kalshi-rs GitHub repos, Benzinga review

---

## GATE VERDICT: CONDITIONAL PASS

Kalshi's API is free to access, has a full demo/sandbox environment with mock funds, and
the Basic tier rate limits (20 read/s, 10 write/s) are more than sufficient for our use case.
However, conditions must be met before proceeding to live trading.

### Conditions for Full PASS

1. **Create a demo account** at https://demo.kalshi.co/ and confirm API key generation works
2. **Verify demo API returns market data** (prices, orderbooks) without a funded account
3. **Before any live trading:** Jordan must explicitly approve funding a Kalshi account (Tier-3 approval per CONSTRAINTS.md)
4. **Fee impact must be modeled** against $10/day budget before any real trades

---

## 1. API Access Model

| Question | Answer |
|----------|--------|
| Cost to get API access | **Free.** No signup costs, membership fees, or processing fees. |
| Account requirement | Free account creation required. No minimum balance for API access. |
| Funded account needed? | **No** for market data. **Yes** for live trading (minimum deposit $1). |
| Sandbox/paper trading? | **Yes.** Full demo environment available. |
| Developer agreement? | Yes -- must agree to Kalshi Developer Agreement. |

### Demo Environment

| Detail | Value |
|--------|-------|
| Web interface | https://demo.kalshi.co/ |
| API root | `https://demo-api.kalshi.co/trade-api/v2` |
| Credentials | Separate from production (not shared) |
| Funds | Mock funds provided for testing |
| Setup | Tutorial available via Kalshi docs |

### Production Environment

| Detail | Value |
|--------|-------|
| API root | `https://api.elections.kalshi.com/trade-api/v2` |
| Protocol | REST + WebSocket + FIX (institutional) |
| SDK support | Python (kalshi_python_sync / kalshi_python_async), TypeScript |
| Community SDKs | pykalshi (Python), kalshi-rs (Rust), pmxt (multi-exchange), Go client |

---

## 2. Cost Model

### API Usage Costs

**There are zero per-request API fees.** Kalshi does not charge for API calls, market data
retrieval, or WebSocket connections. Cost is incurred only when executing trades.

### Trading Fees

| Component | Details |
|-----------|---------|
| Fee model | **Taker pays, maker is free** |
| Fee formula | Max potential earnings x implied probability of realizing those earnings |
| Contract price range | $0.01 to $0.99 per contract |
| Maker fee | **$0.00** (placing limit orders that add liquidity) |
| Taker fee | Variable, based on contract price and potential earnings |
| Settlement fee | None documented |
| Deposit fee (ACH) | **$0.00** |
| Deposit fee (wire) | Variable (bank-dependent) |
| Withdrawal fee | **$2.00 flat** per withdrawal |
| Monthly/annual fee | **$0.00** |

### Fee Example

For a contract priced at $0.50 (50% implied probability):
- Cost to buy 1 contract: $0.50
- Max potential earnings: $0.50 (pays $1.00 if correct)
- Taker fee: ~$0.50 x 0.50 = ~$0.25 (illustrative; actual varies by market)
- If you place a limit order (maker): fee = $0.00

### $10/Day Budget Analysis

| Scenario | Feasibility |
|----------|-------------|
| **Data-only (no trading)** | Fully within budget. $0/day API cost. |
| **Paper trading on demo** | Fully within budget. $0/day (mock funds). |
| **Small live trades (1-10 contracts/day)** | Within budget. Contracts cost $0.01-$0.99 each plus taker fees. |
| **Signal generation + occasional trades** | Within budget. Market data free; selective trades under $10. |
| **High-frequency trading** | NOT within budget. Volume would exceed $10/day. |

**Verdict:** A data-harvesting + selective-signal approach operates comfortably within $10/day.
Pure market data consumption is $0/day. Demo/paper trading is $0/day.

---

## 3. Rate Limits

### Tier Structure

| Tier | Read (req/s) | Write (req/s) | Qualification |
|------|-------------|---------------|---------------|
| **Basic** | 20 | 10 | Complete signup (free) |
| Advanced | 30 | 30 | Submit form at kalshi.typeform.com/advanced-api |
| Premier | 100 | 100 | 3.75% of exchange volume/month + technical review |
| Prime | 400 | 400 | 7.5% of exchange volume/month + technical review |

### Write-Limited Endpoints

These count toward write limits:
- CreateOrder, CancelOrder, AmendOrder, DecreaseOrder
- BatchCreateOrders (each item = 1 transaction)
- BatchCancelOrders (each cancel = 0.2 transactions)

### Additional Limits

| Limit | Value |
|-------|-------|
| Max open orders | 200,000 per user |
| Max batch size | 20 orders per batch |
| Max open RFQs | 100 |
| Multivariate market creation | 5,000/week |

### Assessment for Our Use Case

At Basic tier (20 read/s):
- Polling 100 markets every 5 seconds = 20 req/5s = 4 req/s (well under limit)
- WebSocket for real-time data avoids REST polling entirely
- 10 write/s is far more than needed for signal-based selective trading

**Basic tier is sufficient.** No need to apply for Advanced/Premier.

---

## 4. API Capabilities

### Authentication

| Component | Details |
|-----------|---------|
| Method | RSA key-pair signature (not simple API key) |
| Key generation | Dashboard at kalshi.com/account/api (or demo equivalent) |
| Required headers | KALSHI-ACCESS-KEY, KALSHI-ACCESS-TIMESTAMP, KALSHI-ACCESS-SIGNATURE |
| Key format | RSA private key (PEM format) |
| Env vars (community convention) | KALSHI_API_KEY_ID, KALSHI_PRIVATE_KEY_PATH |
| Signing note | Sign the path WITHOUT query parameters |

### Market Data Endpoints

| Capability | Available? | Endpoint |
|------------|-----------|----------|
| Fetch active markets with prices | Yes | GET /markets, GET /series/.../markets/{ticker} |
| Get order book depth | Yes | GET /markets/{ticker}/orderbook |
| Get historical trades | Yes | GET /markets/trades |
| Get candlestick (OHLC) data | Yes | GET /events/{ticker}/candlesticks |
| Get event/series data | Yes | GET /events, GET /series |
| Search/filter markets | Yes | GET /markets with query params |
| Archived/historical data | Yes | Dedicated archive endpoints |

### Trading Endpoints

| Capability | Available? | Endpoint |
|------------|-----------|----------|
| Place orders | Yes | POST /portfolio/orders |
| Cancel orders | Yes | DELETE /portfolio/orders/{id} |
| Amend orders | Yes | PATCH /portfolio/orders/{id} |
| Batch create orders | Yes | POST /portfolio/orders/batched |
| Batch cancel orders | Yes | DELETE /portfolio/orders/batched |
| Get positions | Yes | GET /portfolio/positions |
| Get balance | Yes | GET /portfolio/balance |
| Get fills | Yes | GET /portfolio/fills |
| Get settlements | Yes | GET /portfolio/settlements |

### Real-Time Data (WebSocket)

| Feature | Available? |
|---------|-----------|
| WebSocket support | Yes |
| Market ticker stream | Yes |
| Orderbook snapshot stream | Yes |
| User order updates | Yes |
| Trade stream | Yes |
| AsyncAPI spec available | Yes (docs.kalshi.com/asyncapi.yaml) |

### Paper Trading via API

| Feature | Details |
|---------|---------|
| Demo API endpoint | `https://demo-api.kalshi.co/trade-api/v2` |
| Same endpoints as production | Yes (identical API surface) |
| Mock funds | Yes, provided automatically |
| Separate credentials | Yes (demo keys != production keys) |

---

## 5. Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Kalshi rate-limits our IP | Low | Basic tier 20/s is generous; use WebSocket for real-time |
| Trading fees eat into $10 budget | Medium | Use maker orders (free); start with data-only mode |
| RSA signing adds complexity | Low | Well-documented; community SDKs handle it |
| Demo environment differs from prod | Low | Same API surface; separate credentials only |
| Regulatory changes (CFTC) | Medium | Kalshi is CFTC-regulated; monitor for changes |
| Account funding required for live | Low | $1 minimum deposit; defer until strategy proven on demo |

---

## 6. Recommendation

**PROCEED with Kalshi integration.**

### Recommended Approach (Phased)

**Phase 5A-1 (now, $0 cost):**
- Create demo account at demo.kalshi.co
- Generate API keys
- Build data fetcher against demo API
- Validate market data retrieval (prices, orderbooks)
- Build signal generation pipeline using free market data

**Phase 5A-2 (after demo validation, $0 cost):**
- Implement paper trading via demo API
- Test order placement, cancellation, position tracking
- Build performance tracking against mock portfolio
- Validate signal quality over 1-2 weeks

**Phase 5A-3 (requires Tier-3 Jordan approval, ~$1-10 cost):**
- Fund production account with minimum viable amount ($5-$20)
- Execute small live trades to validate end-to-end
- Monitor actual fees vs. modeled fees
- Scale only if ROI positive

### Key Advantages for OpenClaw

1. **Zero cost for data** -- all market data is free via API
2. **Full sandbox** -- can develop and test everything without spending a cent
3. **Maker orders are free** -- limit orders incur no fees
4. **WebSocket support** -- real-time data without polling overhead
5. **Low minimums** -- $1 deposit minimum, $0.01 contract minimum
6. **Well-documented** -- OpenAPI spec, AsyncAPI spec, multiple SDKs
7. **Basic tier is sufficient** -- 20 read/s handles our volume easily

---

## Sources

- Kalshi Official API Docs: https://docs.kalshi.com
- Kalshi OpenAPI Spec: https://docs.kalshi.com/openapi.yaml
- Kalshi AsyncAPI Spec: https://docs.kalshi.com/asyncapi.yaml
- Kalshi Demo Environment: https://docs.kalshi.com/getting_started/demo_env
- Kalshi Rate Limits: https://docs.kalshi.com/getting_started/rate_limits
- Kalshi API Keys: https://docs.kalshi.com/getting_started/api_keys
- pykalshi (Python SDK): https://github.com/arshka/pykalshi
- kalshi-rs (Rust SDK): https://github.com/arvchahal/kalshi-rs
- pmxt (multi-exchange): https://github.com/pmxt-dev/pmxt
- Benzinga Kalshi Review (fee details): https://www.benzinga.com/money/kalshi-review
