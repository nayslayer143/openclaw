# Domain Config — Competitive Intelligence

## Purpose
Competitor analysis, market landscape mapping, feature comparisons, pricing intelligence.
Feeds into business strategy decisions. Jordan uses this for positioning.

## Source Priority
1. Competitor websites, product pages, pricing pages
2. Crunchbase, PitchBook, LinkedIn (company profiles)
3. App stores (reviews, ratings, feature lists)
4. Reddit/X (customer complaints about competitors = opportunity signals)
5. Industry analyst reports (Gartner, Forrester — summaries only, respect paywalls)
6. Job postings (reveal strategic direction and tech stack)

## Output Format
- **Competitor profile:** company overview, products, pricing, strengths, weaknesses, recent moves
- **Landscape map:** category overview, key players, positioning matrix, white space
- **Feature comparison:** structured table (feature × competitor), gap analysis
- **Threat/opportunity brief:** specific competitive move and recommended response

## Output Location
- Briefs: `autoresearch/outputs/briefs/competitive-[slug]-[date].md`
- Full reports: `autoresearch/outputs/papers/competitive-[slug]-[date].md`
- Comparison data: `autoresearch/outputs/datasets/competitive-[slug]-[date].json`

## Constraints
- Never access paid/gated content — use publicly available info only
- Never scrape personal data (employee names, emails) — company-level data only
- Flag if intelligence is based on a single source
- Note date of all competitive data — it goes stale fast
- Recency: prefer sources <30 days old

## Quality Override
- Use `core/quality-standards.md` universal standards
- Every claim about a competitor must include source URL and access date
- Pricing data must include date observed — prices change frequently
- Job posting analysis: note posting date and whether position is still open
