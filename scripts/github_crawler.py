#!/usr/bin/env python3
"""
GitHub Repo Intelligence Crawler
Built for: Omega MegaCorp / SHINY LLC Trading Bot Research
Purpose: Surface high-signal repos for algorithmic trading optimization

Usage:
    python github_crawler.py --topic trading-bot --min-stars 500
    python github_crawler.py --keyword "reinforcement learning trading" --sort stars
    python github_crawler.py --full-scan  # runs all keyword categories
"""

import requests
import json
import time
import csv
import os
import sys
import re
import argparse
import math
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import Optional

# ─── CONFIG ────────────────────────────────────────────────────────────────────

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")  # set via: export GITHUB_TOKEN=ghp_xxx
HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"

BASE_URL = "https://api.github.com"

# ─── KEYWORD TAXONOMY ──────────────────────────────────────────────────────────

KEYWORD_GROUPS = {
    # ── Original groups ───────────────────────────────────────────
    "trading_core": [
        "algorithmic trading bot",
        "quantitative trading python",
        "backtesting framework trading",
        "live trading bot crypto",
        "high frequency trading python",
        "market making bot",
    ],
    "trading_ml": [
        "reinforcement learning trading",
        "deep learning stock prediction",
        "LSTM trading strategy",
        "transformer financial time series",
        "RL trading agent gym",
        "AI trading signals",
    ],
    "trading_infra": [
        "trading execution engine",
        "order management system python",
        "portfolio risk management bot",
        "multi-asset trading framework",
        "event-driven trading engine",
        "CCXT trading bot",
    ],
    "data_pipeline": [
        "financial data pipeline",
        "market data websocket",
        "tick data processor",
        "options flow data",
        "crypto orderbook analysis",
    ],
    "ai_agents": [
        "LLM agent autonomous coding",
        "multi-agent orchestration python",
        "AI agent workflow automation",
        "Claude agent MCP tools",
        "autonomous AI pipeline",
    ],
    "workflow_tools": [
        "GitHub Actions automation workflow",
        "developer productivity CLI tool",
        "code review automation",
        "CI/CD pipeline AI",
    ],
    # ── Deep quant groups ─────────────────────────────────────────
    "quant_strategies": [
        "statistical arbitrage pairs trading",
        "mean reversion Ornstein-Uhlenbeck",
        "cointegration trading python",
        "factor model alpha generation",
        "regime detection hidden markov trading",
        "Kalman filter pairs trading",
        "risk parity portfolio python",
        "Black-Litterman portfolio optimization",
        "momentum factor cross-sectional",
    ],
    "execution_microstructure": [
        "TWAP VWAP execution algorithm",
        "order book microstructure python",
        "market impact model Almgren-Chriss",
        "optimal execution slippage",
        "FIX protocol trading python",
        "low latency order routing",
        "iceberg order detection",
        "matching engine implementation",
        "L2 orderbook reconstruction",
    ],
    "options_vol": [
        "implied volatility surface python",
        "gamma scalping delta hedging",
        "options greeks calculator python",
        "volatility smile skew arbitrage",
        "stochastic volatility Heston model",
        "variance swap replication",
        "options market making",
        "SABR model calibration",
        "Monte Carlo option pricing",
    ],
    "options_futures_trading": [
        "options trading bot python",
        "futures trading system automated",
        "iron condor automated strategy",
        "options spread scanner python",
        "futures basis trading bot",
        "options chain data parser",
        "theta decay harvesting bot",
        "calendar spread automation",
        "straddle strangle screener python",
        "futures roll strategy automated",
        "options backtesting framework",
        "commodity futures trading system",
        "VIX trading strategy python",
        "term structure arbitrage futures",
    ],
    "crypto_defi_mev": [
        "MEV extraction flashbots",
        "sandwich attack detection",
        "DEX arbitrage Uniswap",
        "flash loan arbitrage solidity",
        "funding rate arbitrage perpetual",
        "liquidation cascade detector",
        "on-chain whale tracking",
        "AMM impermanent loss calculator",
        "cross-chain bridge arbitrage",
    ],
    "alt_data_signals": [
        "alternative data trading signals",
        "satellite imagery trading",
        "SEC EDGAR 13F filing parser",
        "congressional trading tracker STOCK Act",
        "dark pool print analysis",
        "unusual options activity detector",
        "earnings whisper scraper",
        "insider trading Form 4 parser",
        "supply chain data trading signal",
    ],
    "sentiment_nlp": [
        "finBERT financial sentiment",
        "earnings call transcript NLP",
        "social sentiment trading signal",
        "news event impact quantification",
        "Reddit wallstreetbets sentiment analysis",
        "crypto fear greed index python",
        "Twitter cashtag sentiment",
        "10-K 10-Q filing NLP extraction",
    ],
    "prediction_markets": [
        "prediction market maker bot",
        "polymarket CLOB API python",
        "kalshi API trading bot",
        "event contract pricing model",
        "information aggregation futarchy",
        "binary outcome market scoring",
        "prediction market arbitrage cross-platform",
    ],
    "risk_portfolio": [
        "Kelly criterion position sizing",
        "Value at Risk CVaR portfolio",
        "drawdown control trading system",
        "Sharpe ratio optimization python",
        "correlation regime detection",
        "tail risk hedging strategy",
        "portfolio rebalancing algorithm",
        "risk parity all weather portfolio",
    ],
    "infra_plumbing": [
        "exchange websocket connector python",
        "market data normalization OHLCV",
        "tick database timescale quest",
        "trading system event sourcing",
        "position management system python",
        "PnL attribution trading system",
        "multi-exchange unified API",
        "paper trading simulation engine",
    ],
    "agent_frameworks": [
        "autonomous trading agent LLM",
        "multi-agent market simulation",
        "MCP server financial tools",
        "agent tool use trading execution",
        "LLM function calling trading API",
        "AI agent portfolio management",
        "reinforcement learning market maker",
    ],
}

# Group classifications for CLI shortcuts
ORIGINAL_GROUPS = ["trading_core", "trading_ml", "trading_infra", "data_pipeline", "ai_agents", "workflow_tools"]
QUANT_GROUPS = [g for g in KEYWORD_GROUPS if g not in ORIGINAL_GROUPS]

TOPIC_LIST = [
    "algorithmic-trading",
    "trading-bot",
    "algo-trading",
    "quantitative-finance",
    "backtesting",
    "trading-strategies",
    "reinforcement-learning-trading",
    "fintech",
    "crypto-trading",
    "market-making",
    # New topics
    "prediction-markets",
    "defi",
    "mev",
    "options-trading",
    "sentiment-analysis",
    "financial-nlp",
    "web3",
    "on-chain-analysis",
]

# Libraries to discover dependents of
DEPENDENCY_TARGETS = [
    "ccxt/ccxt", "man-group/arctic", "mhallsmoore/qstrader",
    "freqtrade/freqtrade", "pmorissette/bt", "kernc/backtesting.py",
    "bukosabino/ta", "mrjbq7/ta-lib",
]

# ─── DATA MODEL ────────────────────────────────────────────────────────────────

@dataclass
class RepoResult:
    name: str
    full_name: str
    description: str
    url: str
    stars: int
    forks: int
    language: str
    topics: list
    last_updated: str
    created_at: str
    open_issues: int
    license: str
    score: float
    signal_score: float
    category: str
    readme_snippet: str = ""

# ─── SCORING ENGINE ────────────────────────────────────────────────────────────

def compute_signal_score(repo: dict, category: str) -> float:
    stars = repo.get("stargazers_count", 0)
    forks = repo.get("forks_count", 0)
    open_issues = repo.get("open_issues_count", 0)

    updated = repo.get("updated_at", "")
    if updated:
        try:
            last_update = datetime.fromisoformat(updated.replace("Z", "+00:00"))
            days_since = (datetime.now(last_update.tzinfo) - last_update).days
            recency = max(0, 1 - (days_since / 730))
        except:
            recency = 0
    else:
        recency = 0

    star_score = math.log10(max(stars, 1)) / 5
    fork_ratio = min(forks / max(stars, 1), 1)
    issue_ratio = 1 - min(open_issues / max(stars + 1, 1), 1)
    topics = repo.get("topics", [])
    topic_bonus = min(len(topics) / 10, 1)

    category_weights = {
        "trading_core": 1.5,
        "trading_ml": 1.4,
        "trading_infra": 1.3,
        "data_pipeline": 1.2,
        "ai_agents": 1.1,
        "workflow_tools": 1.0,
        "topic_search": 1.2,
        # Deep quant weights
        "quant_strategies": 1.5,
        "execution_microstructure": 1.4,
        "options_vol": 1.4,
        "options_futures_trading": 1.4,
        "crypto_defi_mev": 1.3,
        "alt_data_signals": 1.3,
        "sentiment_nlp": 1.2,
        "prediction_markets": 1.5,
        "risk_portfolio": 1.3,
        "infra_plumbing": 1.2,
        "agent_frameworks": 1.1,
        # Graph discovery
        "stargazer_discovery": 1.3,
        "dependency_discovery": 1.2,
        "trending_discovery": 1.1,
    }
    weight = category_weights.get(category, 1.0)

    score = (
        star_score * 0.35
        + recency * 0.25
        + fork_ratio * 0.15
        + issue_ratio * 0.15
        + topic_bonus * 0.10
    ) * weight

    return round(score, 4)

# ─── API CALLS ─────────────────────────────────────────────────────────────────

def search_by_keyword(query: str, min_stars: int = 100, max_results: int = 10, category: str = "keyword") -> list[RepoResult]:
    params = {
        "q": f"{query} stars:>={min_stars}",
        "sort": "stars",
        "order": "desc",
        "per_page": min(max_results, 30),
    }

    try:
        resp = requests.get(f"{BASE_URL}/search/repositories", headers=HEADERS, params=params, timeout=10)

        if resp.status_code == 403:
            print(f"  Rate limited. Waiting 60s...")
            time.sleep(60)
            return []

        resp.raise_for_status()
        data = resp.json()

        results = []
        for item in data.get("items", []):
            license_name = ""
            if item.get("license"):
                license_name = item["license"].get("spdx_id", "")

            signal = compute_signal_score(item, category)

            results.append(RepoResult(
                name=item["name"],
                full_name=item["full_name"],
                description=item.get("description") or "",
                url=item["html_url"],
                stars=item["stargazers_count"],
                forks=item["forks_count"],
                language=item.get("language") or "Unknown",
                topics=item.get("topics", []),
                last_updated=item.get("updated_at", "")[:10],
                created_at=item.get("created_at", "")[:10],
                open_issues=item.get("open_issues_count", 0),
                license=license_name,
                score=item.get("score", 0),
                signal_score=signal,
                category=category,
            ))

        return results

    except Exception as e:
        print(f"  Error searching '{query}': {e}")
        return []

def search_by_topic(topic: str, min_stars: int = 200, max_results: int = 10) -> list[RepoResult]:
    return search_by_keyword(f"topic:{topic}", min_stars=min_stars, max_results=max_results, category="topic_search")

def get_readme_snippet(full_name: str, max_chars: int = 300) -> str:
    try:
        resp = requests.get(
            f"{BASE_URL}/repos/{full_name}/readme",
            headers={**HEADERS, "Accept": "application/vnd.github.raw+json"},
            timeout=5
        )
        if resp.status_code == 200:
            text = resp.text.strip()
            text = re.sub(r'#+\s*', '', text)
            text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
            text = re.sub(r'\s+', ' ', text)
            return text[:max_chars].strip()
    except:
        pass
    return ""

# ─── GRAPH DISCOVERY ──────────────────────────────────────────────────────

def discover_via_stargazers(top_repos: list[RepoResult], max_repos: int = 10, max_stargazers: int = 20) -> list[RepoResult]:
    """Find repos starred by people who starred our high-signal repos."""
    if not GITHUB_TOKEN:
        print("  Stargazer discovery requires GITHUB_TOKEN. Skipping.")
        return []
    print(f"\nStargazer discovery (top {max_repos} repos, {max_stargazers} stargazers each)")
    starred_counts = {}  # full_name -> count of shared stargazers
    known = {r.full_name for r in top_repos}

    for repo in top_repos[:max_repos]:
        try:
            resp = requests.get(f"{BASE_URL}/repos/{repo.full_name}/stargazers",
                                headers=HEADERS, params={"per_page": max_stargazers}, timeout=10)
            if resp.status_code != 200:
                continue
            stargazers = resp.json()
            time.sleep(1.0)
            for user in stargazers[:max_stargazers]:
                login = user.get("login", "")
                if not login:
                    continue
                try:
                    uresp = requests.get(f"{BASE_URL}/users/{login}/starred",
                                         headers=HEADERS, params={"per_page": 30, "sort": "created"}, timeout=10)
                    if uresp.status_code != 200:
                        continue
                    for sr in uresp.json():
                        fn = sr.get("full_name", "")
                        if fn and fn not in known:
                            starred_counts[fn] = starred_counts.get(fn, 0) + 1
                    time.sleep(0.8)
                except Exception:
                    continue
        except Exception as e:
            print(f"  Stargazer error for {repo.full_name}: {e}")
            continue

    # Repos starred by 2+ of our high-signal stargazers
    candidates = [(fn, c) for fn, c in starred_counts.items() if c >= 2]
    candidates.sort(key=lambda x: x[1], reverse=True)
    print(f"  Found {len(candidates)} repos with 2+ shared stargazers")

    results = []
    for fn, count in candidates[:30]:
        try:
            resp = requests.get(f"{BASE_URL}/repos/{fn}", headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                continue
            item = resp.json()
            signal = compute_signal_score(item, "stargazer_discovery")
            results.append(RepoResult(
                name=item["name"], full_name=item["full_name"],
                description=item.get("description") or "",
                url=item["html_url"], stars=item["stargazers_count"],
                forks=item["forks_count"], language=item.get("language") or "Unknown",
                topics=item.get("topics", []),
                last_updated=item.get("updated_at", "")[:10],
                created_at=item.get("created_at", "")[:10],
                open_issues=item.get("open_issues_count", 0),
                license=(item.get("license") or {}).get("spdx_id", ""),
                score=item.get("score", 0), signal_score=signal,
                category="stargazer_discovery",
            ))
            time.sleep(0.5)
        except Exception:
            continue
    print(f"  Resolved {len(results)} stargazer-discovered repos")
    return results


def discover_via_trending(languages=None) -> list[RepoResult]:
    """Scrape GitHub trending page for fast-rising repos."""
    languages = languages or ["python", "rust", "typescript"]
    print(f"\nTrending discovery ({', '.join(languages)})")
    results = []
    for lang in languages:
        try:
            resp = requests.get(f"https://github.com/trending/{lang}",
                                params={"since": "daily"}, timeout=10,
                                headers={"User-Agent": "OpenClaw-Crawler/1.0"})
            if resp.status_code != 200:
                continue
            import re
            # Extract repo links from trending page
            matches = re.findall(r'<h2 class="h3[^"]*">\s*<a href="/([^"]+)"', resp.text)
            if not matches:
                matches = re.findall(r'href="/([^/]+/[^/]+)"[^>]*class="[^"]*Link[^"]*"', resp.text)
            for full_name in matches[:25]:
                full_name = full_name.strip().rstrip("/")
                if "/" not in full_name or full_name.count("/") != 1:
                    continue
                try:
                    rresp = requests.get(f"{BASE_URL}/repos/{full_name}", headers=HEADERS, timeout=10)
                    if rresp.status_code != 200:
                        continue
                    item = rresp.json()
                    signal = compute_signal_score(item, "trending_discovery")
                    results.append(RepoResult(
                        name=item["name"], full_name=item["full_name"],
                        description=item.get("description") or "",
                        url=item["html_url"], stars=item["stargazers_count"],
                        forks=item["forks_count"], language=item.get("language") or "Unknown",
                        topics=item.get("topics", []),
                        last_updated=item.get("updated_at", "")[:10],
                        created_at=item.get("created_at", "")[:10],
                        open_issues=item.get("open_issues_count", 0),
                        license=(item.get("license") or {}).get("spdx_id", ""),
                        score=item.get("score", 0), signal_score=signal,
                        category="trending_discovery",
                    ))
                    time.sleep(0.5)
                except Exception:
                    continue
            time.sleep(1.0)
        except Exception as e:
            print(f"  Trending error for {lang}: {e}")
    print(f"  Found {len(results)} trending repos")
    return results


# ─── DEDUP + RANK ──────────────────────────────────────────────────────────────

def deduplicate(results: list[RepoResult]) -> list[RepoResult]:
    seen = set()
    unique = []
    for r in results:
        if r.full_name not in seen:
            seen.add(r.full_name)
            unique.append(r)
    return unique

def rank_results(results: list[RepoResult]) -> list[RepoResult]:
    return sorted(results, key=lambda r: r.signal_score, reverse=True)

# ─── OUTPUT ────────────────────────────────────────────────────────────────────

def save_csv(results: list[RepoResult], filepath: str):
    if not results:
        return
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "signal_score", "name", "stars", "language", "category",
            "description", "url", "last_updated", "topics", "license",
            "forks", "open_issues", "readme_snippet"
        ])
        writer.writeheader()
        for r in results:
            row = asdict(r)
            row["topics"] = ", ".join(r.topics)
            writer.writerow({k: row[k] for k in writer.fieldnames})
    print(f"Saved {len(results)} repos -> {filepath}")

def save_json(results: list[RepoResult], filepath: str):
    data = []
    for r in results:
        d = asdict(r)
        data.append(d)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"Saved JSON -> {filepath}")

def print_report(results: list[RepoResult], top_n: int = 20):
    print(f"\n{'='*70}")
    print(f"  TOP {min(top_n, len(results))} HIGH-SIGNAL REPOS")
    print(f"{'='*70}\n")

    for i, r in enumerate(results[:top_n], 1):
        print(f"  {i:2}. [{r.signal_score:.3f}] *{r.stars:,} | {r.full_name}")
        print(f"      {r.description[:80] if r.description else 'No description'}...")
        print(f"      {r.language} | {r.category} | Updated: {r.last_updated}")
        print(f"      {r.url}")
        if r.topics:
            print(f"      {', '.join(r.topics[:5])}")
        print()

# ─── MAIN RUNNER ───────────────────────────────────────────────────────────────

def run_scan(
    groups=None,
    topics=None,
    keyword=None,
    min_stars: int = 200,
    max_per_query: int = 10,
    fetch_readmes: bool = False,
    output_prefix: str = "github_scan",
    discover: bool = False,
    trending_only: bool = False,
) -> list[RepoResult]:

    all_results = []

    if trending_only:
        all_results.extend(discover_via_trending())
        unique = deduplicate(all_results)
        ranked = rank_results(unique)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        print_report(ranked, top_n=20)
        save_csv(ranked, f"{output_prefix}_{timestamp}.csv")
        save_json(ranked, f"{output_prefix}_{timestamp}.json")
        return ranked

    if keyword:
        print(f"\nCustom keyword: '{keyword}'")
        results = search_by_keyword(keyword, min_stars=min_stars, max_results=max_per_query)
        all_results.extend(results)
        print(f"   Found {len(results)} repos")
        time.sleep(1.5)

    if groups:
        for group_name in groups:
            keywords = KEYWORD_GROUPS.get(group_name, [])
            if not keywords:
                print(f"Unknown group: {group_name}")
                continue
            print(f"\nGroup: {group_name} ({len(keywords)} queries)")
            for kw in keywords:
                print(f"  '{kw}'")
                results = search_by_keyword(kw, min_stars=min_stars, max_results=max_per_query, category=group_name)
                all_results.extend(results)
                print(f"     -> {len(results)} found")
                time.sleep(1.2)

    if topics:
        print(f"\nTopic searches ({len(topics)} topics)")
        for topic in topics:
            print(f"  topic:{topic}")
            results = search_by_topic(topic, min_stars=min_stars, max_results=max_per_query)
            all_results.extend(results)
            print(f"     -> {len(results)} found")
            time.sleep(1.2)

    # Graph discovery
    if discover:
        # Dedup + rank what we have so far to find top repos for stargazer traversal
        interim = rank_results(deduplicate(all_results))
        high_signal = [r for r in interim if r.signal_score > 0.4][:10]
        if high_signal:
            all_results.extend(discover_via_stargazers(high_signal))
        all_results.extend(discover_via_trending())

    print(f"\nProcessing {len(all_results)} raw results...")
    unique = deduplicate(all_results)
    print(f"   After dedup: {len(unique)} unique repos")
    ranked = rank_results(unique)

    if fetch_readmes and ranked:
        print(f"Fetching README snippets for top 20...")
        for r in ranked[:20]:
            r.readme_snippet = get_readme_snippet(r.full_name)
            time.sleep(0.5)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    csv_path = f"{output_prefix}_{timestamp}.csv"
    json_path = f"{output_prefix}_{timestamp}.json"

    print_report(ranked, top_n=20)
    save_csv(ranked, csv_path)
    save_json(ranked, json_path)

    return ranked


# ─── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="GitHub Repo Intelligence Crawler — 17 keyword groups + graph discovery",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--keyword", type=str, help="Single keyword search")
    parser.add_argument("--topic", type=str, help="Single GitHub topic search")
    parser.add_argument("--group", type=str, nargs="+",
                        choices=list(KEYWORD_GROUPS.keys()),
                        help="Run specific keyword groups")
    parser.add_argument("--full-scan", action="store_true",
                        help="Run all 17 keyword groups + all topics + graph discovery")
    parser.add_argument("--trading-only", action="store_true",
                        help="Run original 6 trading-focused groups only")
    parser.add_argument("--quant-only", action="store_true",
                        help="Run new 11 deep quant groups only")
    parser.add_argument("--discover", action="store_true",
                        help="Enable graph discovery (stargazers + trending)")
    parser.add_argument("--trending", action="store_true",
                        help="Run trending scrape only")
    parser.add_argument("--min-stars", type=int, default=200)
    parser.add_argument("--max-per-query", type=int, default=10)
    parser.add_argument("--readmes", action="store_true",
                        help="Fetch README snippets (slower)")
    parser.add_argument("--output", type=str, default="github_scan")

    args = parser.parse_args()

    if not GITHUB_TOKEN:
        print("Warning: No GITHUB_TOKEN set. Rate limited to 10 req/min.")
        print("   Set via: export GITHUB_TOKEN=ghp_your_token_here\n")

    groups_to_run = None
    topics_to_run = None
    do_discover = args.discover

    if args.trending:
        run_scan(output_prefix=args.output, trending_only=True)
        sys.exit(0)
    elif args.full_scan:
        groups_to_run = list(KEYWORD_GROUPS.keys())
        topics_to_run = TOPIC_LIST
        do_discover = True
    elif args.quant_only:
        groups_to_run = QUANT_GROUPS
        topics_to_run = [t for t in TOPIC_LIST if t not in [
            "algorithmic-trading", "trading-bot", "algo-trading", "backtesting",
            "crypto-trading", "quantitative-finance", "reinforcement-learning-trading",
            "fintech", "market-making",
        ]]
    elif args.trading_only:
        groups_to_run = ORIGINAL_GROUPS[:4]
        topics_to_run = ["algorithmic-trading", "trading-bot", "algo-trading", "backtesting", "crypto-trading"]
    elif args.group:
        groups_to_run = args.group
    elif args.topic:
        topics_to_run = [args.topic]
    elif not args.keyword:
        print("No args provided. Running default trading scan...")
        groups_to_run = ["trading_core", "trading_ml"]
        topics_to_run = ["algorithmic-trading", "trading-bot"]

    run_scan(
        groups=groups_to_run,
        topics=topics_to_run,
        keyword=args.keyword,
        min_stars=args.min_stars,
        max_per_query=args.max_per_query,
        fetch_readmes=args.readmes,
        output_prefix=args.output,
        discover=do_discover,
    )
