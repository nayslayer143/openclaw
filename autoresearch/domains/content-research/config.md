# Domain Config — Content Research

## Purpose
Research for blogs, video scripts, image concepts, marketing materials, SEO keywords.
Feeds into writing-room (blogs/tutorials) and production (videos/images) and community (social).

## Source Priority
1. Competitor content analysis (what's ranking, what's trending)
2. Web search for topic validation and keyword research
3. Reddit/X for audience pain points and trending discussions
4. YouTube for video format research and gap analysis
5. Internal memory (past content performance, audience profiles)
6. Industry publications and thought leadership blogs

## Output Format
- **Content brief:** topic, angle, target audience, keyword targets, competitor gaps, outline
- **Video concept:** hook, structure, visual notes, estimated length, reference links
- **Image/asset brief:** concept description, style references, dimensions, platform target
- **Trend report:** what's trending in target space, why, shelf life estimate

## Output Location
- Briefs: `autoresearch/outputs/briefs/content-[slug]-[date].md`
- Full research: `autoresearch/outputs/papers/content-[slug]-[date].md`
- Keyword/trend data: `autoresearch/outputs/datasets/content-[slug]-[date].json`

## Handoff
- Blog-worthy research → copy brief to `writing-room/drafts/` as starting point
- Video concepts → copy to `production/workflows/01-briefs/` if approved
- Social angles → copy to `community/content/social/` as draft

## Constraints
- Always validate topic demand before deep research (search volume, Reddit engagement)
- Never plagiarize — research is for ideation, not copying
- Flag if a topic is already saturated (>10 high-quality existing pieces)
- Include differentiation angle: why would Omega MegaCorp's take be unique?

## Quality Override
- Use `core/quality-standards.md` universal standards
- Recency: prefer sources <3 months old for trend research
- Content briefs must include at least one unique angle not found in competitor content
