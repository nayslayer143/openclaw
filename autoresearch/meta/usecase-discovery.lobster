# usecase-discovery.lobster — Meta-Research: Discover Novel AutoResearch Use Cases
# Schedule: Weekly (Sundays at 10pm) via cron
# Tier: 1 (auto — research only, no external actions)

name: usecase-discovery
description: >
  Scans trending AI/automation papers, repos, and communities to discover
  novel use cases for the autoresearch system. Scores by feasibility × impact.
  Appends findings to meta/discovery-log.md for Jordan's weekly review.

trigger:
  cron: "0 22 * * 1"  # Monday 10pm local

steps:
  - name: scan-sources
    agent: research
    model: qwen2.5:32b
    action: |
      Search for novel applications of AI-assisted research automation.
      Sources to scan:
        - arXiv: recent papers on "autonomous research", "AI research agents", "automated literature review"
        - GitHub trending: repos tagged research-automation, AI-agents, knowledge-management
        - Reddit: r/MachineLearning, r/artificial, r/LocalLLaMA — posts about research workflows
        - X/Twitter: AI research community discussions
        - Hacker News: threads about AI-powered research tools
      Extract: use case description, implementation complexity (1-10), potential impact (1-10), source URL
    output: raw-discoveries.md
    tier: 1

  - name: score-and-filter
    agent: research
    model: qwen2.5:32b
    action: |
      Read raw-discoveries.md.
      For each discovered use case:
        1. Score feasibility (1-10): can OpenClaw do this with current stack?
        2. Score impact (1-10): how much value would this add to Jordan's businesses?
        3. Composite score = feasibility × impact (max 100)
        4. Drop anything scoring <25
        5. Cross-reference with existing domains — skip if already covered
        6. Check meta/discovery-log.md — skip if previously discovered
      Output: ranked list of novel use cases with scores and one-line descriptions
    input: raw-discoveries.md
    output: scored-discoveries.md
    tier: 1

  - name: update-log
    agent: ops
    model: qwen2.5:7b
    action: |
      Read scored-discoveries.md.
      Append each entry to meta/discovery-log.md in this format:
        ## [date] — [use case name]
        - **Score:** [feasibility] × [impact] = [composite]
        - **Description:** [one line]
        - **Source:** [URL]
        - **Status:** new
      Clean up intermediate files (raw-discoveries.md, scored-discoveries.md).
    input: scored-discoveries.md
    output: meta/discovery-log.md (append)
    tier: 1

  - name: notify-jordan
    agent: orchestrator
    model: qwen2.5:7b
    action: |
      If any new entries were added to discovery-log.md:
        Send Telegram brief: "AutoResearch found [N] new use cases this week. Top: [highest-scored name] ([score]). Review: meta/discovery-log.md"
      If no new entries: skip notification.
    tier: 1

on_failure:
  notify: telegram
  message: "usecase-discovery workflow failed at step: {failed_step}"
  tier: 1
