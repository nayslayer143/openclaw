#!/usr/bin/env python3
"""
idea-ingest.py — Parse ideas markdown files and deposit into Ideas Lab.
Run after cron-idea-engine.sh, or standalone to ingest any ideas-*.md file.

Usage:
  python3 idea-ingest.py                    # ingest today's ideas
  python3 idea-ingest.py 2026-03-20         # ingest specific date
  python3 idea-ingest.py --all              # ingest all unprocessed ideas files
"""
import json, re, sys, secrets
from pathlib import Path
from datetime import datetime

OPENCLAW_ROOT = Path.home() / "openclaw"
OUTPUTS_DIR = OPENCLAW_ROOT / "outputs"
IDEAS_DIR = OPENCLAW_ROOT / "ideas"

def parse_ideas_md(filepath):
    """Parse ideas markdown into structured idea objects."""
    text = filepath.read_text()
    ideas = []

    # Split on ## headings (each idea starts with ##)
    sections = re.split(r'\n##\s+', text)

    for section in sections[1:]:  # skip header before first ##
        lines = section.strip().split('\n')
        if not lines:
            continue

        title = lines[0].strip().rstrip('#').strip()
        if not title or len(title) < 3:
            continue

        body = '\n'.join(lines[1:]).strip()

        # Extract structured fields
        summary_parts = []
        category = 'product'

        # Try to extract "What it is" field
        what_match = re.search(r'\*\*What it is\*\*[:\s]*(.*?)(?=\n\*\*|\Z)', body, re.DOTALL)
        if what_match:
            summary_parts.append(what_match.group(1).strip())

        # Try to extract "Revenue model"
        rev_match = re.search(r'\*\*Revenue model\*\*[:\s]*(.*?)(?=\n\*\*|\Z)', body, re.DOTALL)
        if rev_match:
            summary_parts.append(f"Revenue: {rev_match.group(1).strip()}")

        # Try to extract "Time to first dollar"
        time_match = re.search(r'\*\*Time to first dollar\*\*[:\s]*(.*?)(?=\n\*\*|\Z)', body, re.DOTALL)
        if time_match:
            summary_parts.append(f"Time to $: {time_match.group(1).strip()}")

        # Try to extract "First action"
        action_match = re.search(r'\*\*First action\*\*[:\s]*(.*?)(?=\n\*\*|\Z)', body, re.DOTALL)
        if action_match:
            summary_parts.append(f"Next step: {action_match.group(1).strip()}")

        # Try to extract "Risk/blocker"
        risk_match = re.search(r'\*\*Risk/blocker\*\*[:\s]*(.*?)(?=\n\*\*|\Z)', body, re.DOTALL)
        if risk_match:
            summary_parts.append(f"Risk: {risk_match.group(1).strip()}")

        summary = '\n'.join(summary_parts) if summary_parts else body[:500]

        # Categorize based on content
        title_lower = title.lower() + ' ' + body.lower()
        if any(w in title_lower for w in ['arbitrage', 'polymarket', 'kalshi', 'trading', 'dex', 'cex']):
            category = 'arbitrage'
        elif any(w in title_lower for w in ['research', 'study', 'analysis', 'report']):
            category = 'research'
        else:
            category = 'product'

        ideas.append({
            'title': title,
            'summary': summary,
            'category': category,
        })

    return ideas


def ingest_ideas(ideas, source='clawmpson'):
    """Write ideas to the Ideas Lab directory."""
    IDEAS_DIR.mkdir(parents=True, exist_ok=True)

    created = []
    for idea_data in ideas:
        idea_id = f"idea-{datetime.now().strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(4)}"
        idea = {
            "id": idea_id,
            "title": idea_data['title'],
            "summary": idea_data['summary'],
            "category": idea_data['category'],
            "source": source,
            "status": "pending",
            "notes": [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        (IDEAS_DIR / f"{idea_id}.json").write_text(json.dumps(idea, indent=2))
        created.append(idea_id)
        # Small delay to ensure unique timestamps in IDs
        import time
        time.sleep(0.05)

    return created


def main():
    args = sys.argv[1:]

    if '--all' in args:
        # Ingest all unprocessed ideas files
        files = sorted(OUTPUTS_DIR.glob("ideas-*.md"))
    elif args and args[0] != '--all':
        # Specific date
        date_str = args[0]
        filepath = OUTPUTS_DIR / f"ideas-{date_str}.md"
        if not filepath.exists():
            print(f"No ideas file for {date_str}")
            sys.exit(1)
        files = [filepath]
    else:
        # Today
        today = datetime.now().strftime('%Y-%m-%d')
        filepath = OUTPUTS_DIR / f"ideas-{today}.md"
        if not filepath.exists():
            print(f"No ideas file for today ({today})")
            sys.exit(0)
        files = [filepath]

    # Track which files have been ingested
    ingest_marker = IDEAS_DIR / ".ingested"
    ingested = set()
    if ingest_marker.exists():
        ingested = set(ingest_marker.read_text().strip().splitlines())

    total = 0
    for f in files:
        if f.name in ingested:
            print(f"  skip {f.name} (already ingested)")
            continue

        ideas = parse_ideas_md(f)
        if not ideas:
            print(f"  skip {f.name} (no ideas parsed)")
            continue

        created = ingest_ideas(ideas, source='clawmpson')
        print(f"  {f.name}: ingested {len(created)} ideas")
        total += len(created)

        # Mark as ingested
        ingested.add(f.name)

    # Save ingest markers
    IDEAS_DIR.mkdir(parents=True, exist_ok=True)
    ingest_marker.write_text('\n'.join(sorted(ingested)) + '\n')

    print(f"\nTotal: {total} ideas ingested into Ideas Lab")


if __name__ == '__main__':
    main()
