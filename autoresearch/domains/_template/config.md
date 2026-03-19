# Domain Config — [DOMAIN NAME]

> Clone this file to create a new research domain.
> 1. Copy `_template/` to `domains/[your-domain-name]/`
> 2. Fill in every section below
> 3. Add a row to `autoresearch/CONTEXT.md` → Domains table
> 4. Add a row to `autoresearch/CONTEXT.md` → Task Routing table

## Purpose
[One-line description of what this domain researches.]

## Source Priority
1. [Highest-priority source type]
2. [Second priority]
3. [Third priority]
4. [Add more as needed]

## Output Format
- **Brief:** [describe the short-form output]
- **Full report:** [describe the long-form output]
- **Dataset:** [describe structured data output, if applicable]

## Output Location
- Briefs: `autoresearch/outputs/briefs/[domain]-[slug]-[date].md`
- Reports: `autoresearch/outputs/papers/[domain]-[slug]-[date].md`
- Datasets: `autoresearch/outputs/datasets/[domain]-[slug]-[date].json`

## Constraints
- [Domain-specific rules]
- [Safety constraints]
- [Time limits]

## Quality Override
- Use `core/quality-standards.md` universal standards
- [Any domain-specific quality additions]
