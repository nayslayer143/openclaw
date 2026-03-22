# design-intel-scout.lobster
# Schedule: daily at 6am (runs before daily-intel-lite at 7am)
# Agent: Research Agent (qwen3:30b — confirmed fastest for research tasks)
# Output: appends to design-kb-current.json + scout brief for morning pickup

name: design-intel-scout
description: "Daily web search for world-class art-directed websites. Builds design KB for brief injection."
trigger:
  cron: "0 6 * * *"

steps:
  - id: load_existing_kb
    action: read_file
    description: "Load current KB to check for duplicates"
    path: "~/openclaw/autoresearch/outputs/datasets/design-kb-current.json"
    fallback: '{"entries":[]}'

  - id: scout_web
    action: agent
    agent: research
    model: "qwen3:30b"
    description: "Search for today's best art-directed sites across priority sources"
    prompt: |
      Search the web for today's most compelling, boundary-pushing websites and digital experiences.

      Check these sources for new/recent picks (last 48 hours if possible):
      - awwwards.com (Site of the Day, Honorable Mentions)
      - godly.website (new additions)
      - siteinspire.com (recent)
      - cssdesignawards.com (WOTD/WOTW)
      - thefwa.com (recent FWA picks)

      Selection criteria (strict):
      - Art-directed, not just "pretty UI"
      - Something technically or aesthetically unexpected
      - Would make a skilled designer stop scrolling
      - NOT: SaaS dashboards, generic agency sites, Bootstrap templates

      For each candidate, extract ALL of these fields exactly:
      {
        "url": "full URL",
        "name": "site or studio name",
        "discovered": "{{date}}",
        "source": "awwwards|godly|siteinspire|cssawards|fwa|other",
        "what_makes_it_special": "specific technique or decision, not vibe",
        "techniques": ["array", "of", "css/js/visual", "techniques"],
        "aesthetic_tags": ["array", "of", "aesthetic", "descriptors"],
        "intensity": 8,
        "applicable_to": ["landing", "portfolio", "product", "experience", "editorial"],
        "the_unexpected": "the one thing you didn't see coming",
        "brief_injection": "one sentence usable verbatim in a design brief"
      }

      Return 3–5 entries maximum. Quality floor: intensity ≥ 6 or novel technique.
      Return as a valid JSON array only. No prose.

      Already in KB (skip these URLs):
      {{load_existing_kb.entries | map: 'url' | join: '\n'}}

  - id: validate_entries
    action: agent
    agent: research
    model: "qwen2.5:7b"
    description: "Fast validation — confirm URLs are live, brief_injections are specific"
    prompt: |
      Review these design KB entries for quality:
      {{scout_web.output}}

      For each entry, verify:
      1. brief_injection is specific (names a technique or decision, not just "beautiful")
      2. what_makes_it_special names something concrete
      3. intensity score is defensible

      If an entry fails, fix it. If unfixable, drop it.
      Return the cleaned array as valid JSON only. No prose.

  - id: append_to_kb
    action: agent
    agent: orchestrator
    model: "qwen2.5:7b"
    description: "Append validated entries to KB, trim to 90 days / 200 entries max"
    prompt: |
      Merge new entries into the existing design KB.

      Existing KB:
      {{load_existing_kb.output}}

      New entries:
      {{validate_entries.output}}

      Rules:
      1. Deduplicate by URL (new entries take precedence)
      2. Remove entries with discovered date older than 90 days from {{date}}
      3. If total entries > 200, drop lowest intensity entries until ≤ 200
      4. Return the complete merged KB as valid JSON: {"entries": [...]}

    output: "~/openclaw/autoresearch/outputs/datasets/design-kb-current.json"
    write_mode: overwrite

  - id: write_scout_brief
    action: agent
    agent: research
    model: "qwen2.5:7b"
    description: "Write 1-paragraph scout brief for daily-intel-lite morning pickup"
    prompt: |
      Write a brief scout report from today's design intel finds.

      New entries found:
      {{validate_entries.output}}

      Format:
      # design-intel-scout-{{date}}

      **Today's finds:** [N] sites — [1-sentence summary of the aesthetic range found]

      **Standout:** [site name] — [what_makes_it_special for the top entry]

      **Brief injection ready:** "[brief_injection from top entry]"

      **Full KB:** {{append_to_kb.entry_count | default: '?'}} entries across {{append_to_kb.tag_count | default: '?'}} aesthetic tags.

      Keep it under 150 words. Signal only.

    output: "~/openclaw/outputs/design-intel-scout-{{date}}.md"
    write_mode: overwrite

  - id: notify
    action: telegram
    description: "Lightweight Telegram ping — picked up by morning brief"
    condition: "validate_entries.entry_count > 0"
    message: |
      🎨 Design Scout — {{date}}
      {{validate_entries.entry_count}} new sites in KB.
      Top pick: {{validate_entries.entries[0].name}} (intensity {{validate_entries.entries[0].intensity}}/10)
      Brief injection: "{{validate_entries.entries[0].brief_injection}}"
    tier: 1

  - id: log
    action: append_file
    output: "~/openclaw/memory/IDLE_LOG.md"
    template: |
      ### Design Intel Scout — {{date}} 06:00
      - Sites found: {{validate_entries.entry_count | default: 0}}
      - KB total: {{append_to_kb.entry_count | default: '?'}} entries
      - Sources hit: awwwards, godly, siteinspire, cssdesignawards, fwa
