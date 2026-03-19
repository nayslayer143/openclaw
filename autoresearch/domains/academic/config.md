# Domain Config — Academic Research

## Purpose
PhD-level research papers, literature reviews, technical deep dives, patent research.
Highest rigor tier. Every claim cited. Opposing viewpoints required.

## Source Priority
1. Peer-reviewed journals and conference proceedings
2. arXiv / SSRN / bioRxiv preprints (flag as non-peer-reviewed)
3. University and research institution publications
4. Patent databases (Google Patents, USPTO)
5. Technical books and reference materials
6. High-quality technical blogs (as supporting evidence only, never primary)

## Output Format
- **Literature review:** structured survey of existing work on a topic
- **Research paper:** Abstract, Introduction, Related Work, Methodology, Findings, Discussion, Conclusion, References
- **Technical brief:** compressed format for internal use — key findings + full citation list
- **Patent landscape:** structured analysis of relevant patents, claims, and white space

## Output Location
- Papers: `autoresearch/outputs/papers/academic-[slug]-[date].md`
- Briefs: `autoresearch/outputs/briefs/academic-[slug]-[date].md`
- Datasets: `autoresearch/outputs/datasets/academic-[slug]-[date].json`

## Constraints
- **Strict mode MANDATORY** — see `core/quality-standards.md`
- Zero tolerance for unsourced factual claims
- Every direct quote: quotation marks + full bibliographic citation
- Opposing viewpoints must be addressed, not ignored
- If insufficient sources exist: state the gap explicitly, do not fill with speculation
- Methodology section required for any original analysis
- Time limit: 60 minutes for a paper, 30 minutes for a brief

## Quality Override
- Strict mode from `core/quality-standards.md` — non-negotiable
- No recency bias — the best source may be decades old
- Prefer peer-reviewed over preprints, but include both when relevant
- Self-citation from past OpenClaw research: allowed but flagged as internal source
