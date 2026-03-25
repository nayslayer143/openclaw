# GitHub Crawler Enhancement — Design Spec

**Date:** 2026-03-24
**Status:** Approved
**Scope:** Enhance existing `scripts/github_crawler.py` in-place

## Goal

Expand the GitHub intelligence crawler from 6 keyword groups (~30 queries) to 17 groups (~130 queries) with deep quant/trading jargon, plus add graph-based discovery methods (stargazer traversal, dependency graph, trending scrape).

## Changes to github_crawler.py

### 1. Keyword Groups (6 existing + 11 new = 17 total)

**Existing (unchanged):** trading_core, trading_ml, trading_infra, data_pipeline, ai_agents, workflow_tools

**New groups:**
- quant_strategies (9): stat arb, cointegration, Ornstein-Uhlenbeck, factor models, regime detection, Kalman filter, risk parity, Black-Litterman, momentum factor
- execution_microstructure (9): TWAP/VWAP, order book microstructure, Almgren-Chriss, FIX protocol, iceberg detection, matching engine, L2 orderbook
- options_vol (9): implied vol surface, gamma scalping, greeks, vol smile arb, Heston model, SABR, Monte Carlo
- options_futures_trading (14): options trading bot, futures systems, iron condor, spreads, theta decay, calendar spread, straddle screener, VIX, term structure arb
- crypto_defi_mev (9): MEV extraction, sandwich detection, DEX arb, flash loans, funding rate arb, liquidation cascade, whale tracking, AMM IL
- alt_data_signals (9): satellite imagery, 13F parser, congressional STOCK Act, dark pool, unusual options, earnings whisper, insider Form 4, supply chain
- sentiment_nlp (8): finBERT, earnings call NLP, social sentiment, news impact, WSB sentiment, fear/greed, cashtag sentiment, 10-K/10-Q NLP
- prediction_markets (7): prediction market maker, polymarket CLOB, kalshi API, event contract pricing, futarchy, cross-platform arb
- risk_portfolio (8): Kelly criterion, VaR/CVaR, drawdown control, Sharpe optimization, correlation regime, tail risk, rebalancing, all-weather
- infra_plumbing (9): exchange websocket, OHLCV normalization, tick database, event sourcing, position management, PnL attribution, unified API, paper trading
- agent_frameworks (7): autonomous trading agent, multi-agent simulation, MCP financial tools, LLM function calling trading, RL market maker

### 2. Expanded Topic List

Original 10 + new 8: prediction-markets, defi, mev, options-trading, sentiment-analysis, financial-nlp, web3, on-chain-analysis

### 3. Graph Discovery (new functions)

**Stargazer traversal:** For repos with signal_score > 0.6, fetch recent stargazers, then fetch their starred repos. If 3+ stargazers also starred repo X, add it to results. Cap: 20 stargazers per repo, top 10 repos.

**Dependency graph:** Find repos that depend on key libraries: ccxt, py-clob-client, ta-lib, zipline, backtrader, freqtrade, praw. One query per library.

**Trending scrape:** Poll GitHub trending page for Python/Rust/TypeScript. Filter against keyword taxonomy. httpx + basic HTML parse.

All discovery results tagged with `discovery_method` field and fed through existing dedup + rank pipeline.

### 4. CLI Changes

- `--full-scan` — all 17 groups + topics + graph discovery (existing flag, expanded)
- `--trading-only` — original 6 groups (existing, unchanged)
- `--quant-only` — new 11 groups only
- `--discover` — run graph discovery only (stargazers + deps + trending)
- `--trending` — trending scrape only

### 5. Scoring

No changes to signal_score formula. New groups get category_weights:
- quant_strategies: 1.5, execution_microstructure: 1.4, options_vol: 1.4
- options_futures_trading: 1.4, crypto_defi_mev: 1.3, alt_data_signals: 1.3
- sentiment_nlp: 1.2, prediction_markets: 1.5, risk_portfolio: 1.3
- infra_plumbing: 1.2, agent_frameworks: 1.1

### 6. Line Budget

- Keyword expansion: +80 lines
- Graph discovery: +100 lines
- CLI changes: +15 lines
- Total: ~200 lines added to existing ~410 = ~610 lines

## Not In Scope (Phase C — future)

- Cross-crawler correlation (wait until other crawlers produce data)
- Code-level deep analysis (clone + Ollama on source code)
- Copilot integration
- GitHub Actions/releases monitoring
