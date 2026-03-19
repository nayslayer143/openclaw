# Domain Config — Market Intel

## Purpose
Investment signals, Polymarket analysis, crypto/equity research, pricing intelligence.
Signal only — never execute trades. Jordan decides all financial actions.

## Source Priority
1. Financial data APIs (when configured): market feeds, price history
2. Polymarket event contracts and resolution data
3. Financial news aggregators (RSS, web search)
4. Reddit: r/wallstreetbets, r/stocks, r/polymarket, r/cryptocurrency
5. X/Twitter: fintwit accounts, breaking news
6. SEC filings, earnings transcripts (for equity research)

## Output Format
- **Daily signal brief:** ≤300 words, top 3 signals, delivered via Telegram
- **Deep dive:** structured report with thesis, evidence, risk factors, confidence level
- **Dataset:** JSON with schema: `{ticker, signal, direction, confidence, sources[], timestamp}`

## Output Location
- Briefs: `autoresearch/outputs/briefs/market-[date].md`
- Deep dives: `autoresearch/outputs/papers/market-[slug]-[date].md`
- Datasets: `autoresearch/outputs/datasets/market-[slug]-[date].json`

## Constraints
- NEVER execute trades, place bets, or move funds — signal only
- NEVER present speculation as investment advice
- All financial conclusions labeled with confidence level
- Recency: prefer sources <7 days old for market signals
- Flag any source with commercial bias (sponsored content, affiliate links)

## Quality Override
- Use `core/quality-standards.md` universal standards
- Additional: every price claim must include timestamp and source
- Polymarket: note contract expiry and current volume alongside probability
