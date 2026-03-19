# repo-scout.lobster
# Input: GitHub URL
# Agent: Research Agent → Build Agent (if scored ≥7)
# Output: evaluation → repo-queue/evaluated.md

name: repo-scout
description: "Evaluate a GitHub repo for integration potential"
trigger: manual

steps:
  - id: research_score
    action: agent
    agent: research
    model: "qwen2.5:32b"
    description: "Research Agent scores repo relevance 1-10"
    prompt: |
      Evaluate this GitHub repository: {{input.github_url}}

      Score 1-10 on:
      - Relevance to Jordan's web businesses
      - Code quality and maintenance activity
      - Integration complexity (lower score = harder)
      - Community health (stars, issues, PRs, last commit)

      Output format:
      - repo: [name]
      - url: [url]
      - score: [1-10]
      - summary: [2-3 sentences]
      - recommendation: integrate | watch | skip

  - id: complexity_check
    action: agent
    agent: build
    condition: "research_score.score >= 7"
    description: "Build Agent checks install complexity"
    prompt: |
      Check installation complexity for: {{input.github_url}}
      - Can it install on macOS ARM/M2?
      - Dependencies count and size?
      - Any Docker requirements?
      - Estimated setup time?
      Output: complexity rating (low/medium/high) + notes

  - id: save_evaluation
    action: append_file
    description: "Save decision to evaluated.md"
    output: "~/openclaw/repo-queue/evaluated.md"
    template: |
      ## {{research_score.repo}} — {{date}}
      - URL: {{input.github_url}}
      - Score: {{research_score.score}}/10
      - Recommendation: {{research_score.recommendation}}
      - Summary: {{research_score.summary}}
      {% if complexity_check %}
      - Complexity: {{complexity_check.rating}}
      - Notes: {{complexity_check.notes}}
      {% endif %}
      ---

  - id: notify
    action: telegram
    description: "Summary to Jordan"
    message: |
      🔍 Repo Scout: {{research_score.repo}}
      Score: {{research_score.score}}/10 → {{research_score.recommendation}}
      {{research_score.summary}}
    tier: 1
