#!/usr/bin/env python3
"""
project-launch.py — Clawmpson's Project Launch Engine

Triggered when a new service/product is ready to go to market. Does:
  1. Updates projects.json (status → active)
  2. Competitive research via Serper + Ollama
  3. Generates social media campaign (X threads + LinkedIn post)
  4. Generates Fiverr/Upwork service listing copy
  5. Queues weekly competitive scan
  6. Sends full launch brief to Telegram

Usage:
  python3 project-launch.py <project_name> [description]
  python3 project-launch.py "xyz.cards" "NFC-powered digital business cards"
"""

from __future__ import annotations
import os
import sys
import json
import datetime
import requests
from pathlib import Path
from typing import Optional

OPENCLAW = Path.home() / "openclaw"
PROJECTS_FILE = OPENCLAW / "projects" / "projects.json"
OUTPUTS_DIR = OPENCLAW / "autoresearch" / "outputs" / "briefs"
DATASETS_DIR = OPENCLAW / "autoresearch" / "outputs" / "datasets"


# ── Load env ──────────────────────────────────────────────────────────────────

def _load_env():
    env_file = OPENCLAW / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

_load_env()

OLLAMA_URL   = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
CHAT_MODEL   = os.environ.get("OLLAMA_CHAT_MODEL", "qwen3:32b")
SERPER_KEY   = os.environ.get("SERPER_API_KEY", "")
BOT_TOKEN    = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID      = os.environ.get("TELEGRAM_ALLOWED_USERS", "").strip().strip('"[]').split(",")[0].strip()
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"


# ── Telegram ──────────────────────────────────────────────────────────────────

def tg_send(text: str):
    if not BOT_TOKEN or not CHAT_ID:
        print(f"[launch] Telegram not configured — printing to stdout:\n{text}")
        return
    for i in range(0, len(text), 4000):
        try:
            requests.post(f"{TELEGRAM_API}/sendMessage",
                json={"chat_id": CHAT_ID, "text": text[i:i+4000]}, timeout=10)
        except Exception as e:
            print(f"[launch] Telegram send error: {e}")


# ── LLM call ─────────────────────────────────────────────────────────────────

def llm(prompt: str, system: str = "") -> str:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    try:
        r = requests.post(f"{OLLAMA_URL}/api/chat",
            json={"model": CHAT_MODEL, "messages": messages, "stream": False},
            timeout=300)
        r.raise_for_status()
        return r.json().get("message", {}).get("content", "").strip()
    except Exception as e:
        return f"[LLM error: {e}]"


# ── Serper search ─────────────────────────────────────────────────────────────

def search(query: str, n: int = 5) -> list[dict]:
    if not SERPER_KEY:
        return []
    try:
        r = requests.post("https://google.serper.dev/search",
            headers={"X-API-KEY": SERPER_KEY, "Content-Type": "application/json"},
            json={"q": query, "num": n}, timeout=15)
        results = r.json().get("organic", [])
        return [{"title": x.get("title",""), "snippet": x.get("snippet",""),
                 "link": x.get("link","")} for x in results[:n]]
    except Exception as e:
        print(f"[launch] Serper error: {e}")
        return []


# ── Projects.json ─────────────────────────────────────────────────────────────

def load_projects() -> list:
    if not PROJECTS_FILE.exists():
        return []
    try:
        return json.loads(PROJECTS_FILE.read_text())
    except Exception:
        return []


def save_projects(projects: list):
    PROJECTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROJECTS_FILE.write_text(json.dumps(projects, indent=2))


def upsert_project(name: str, description: str, extra: dict = None) -> dict:
    projects = load_projects()
    today = datetime.date.today().isoformat()

    # Find existing
    existing = next((p for p in projects if p.get("name", "").lower() == name.lower()), None)
    if existing:
        existing["status"] = "active"
        existing["launched_at"] = today
        existing["description"] = description or existing.get("description", "")
        if extra:
            existing.update(extra)
        save_projects(projects)
        return existing
    else:
        project = {
            "name": name,
            "description": description,
            "status": "active",
            "launched_at": today,
            "created_at": today,
            **(extra or {})
        }
        projects.append(project)
        save_projects(projects)
        return project


# ── Research ──────────────────────────────────────────────────────────────────

def competitive_research(project_name: str, description: str) -> dict:
    """Search for competitors and synthesize landscape."""
    print(f"[launch] Running competitive research for: {project_name}")

    queries = [
        f"{project_name} competitors alternatives",
        f"{description} market players pricing",
        f"best {description} service 2025 2026",
    ]

    raw_results = []
    for q in queries:
        results = search(q, n=5)
        raw_results.extend(results)

    # De-duplicate by link
    seen = set()
    unique = []
    for r in raw_results:
        if r["link"] not in seen:
            seen.add(r["link"])
            unique.append(r)

    context = "\n".join(
        f"- {r['title']}: {r['snippet']} ({r['link']})"
        for r in unique[:12]
    )

    analysis = llm(
        f"""You are Clawmpson, analyzing the competitive landscape for a new service.

Project: {project_name}
Description: {description}

Search results about competitors and market:
{context if context else "No search results — analyze based on general knowledge."}

Write a competitive analysis with:
1. TOP 3-5 COMPETITORS (name, URL if known, pricing, weaknesses)
2. MARKET OPPORTUNITY (gaps, underserved segments)
3. OUR DIFFERENTIATION ANGLE (how {project_name} wins)
4. PRICING STRATEGY (what to charge and why)
5. IMMEDIATE THREATS (who will try to copy us)

Be specific and actionable. No vague statements.""",
        system="You are a ruthless competitive intelligence analyst for a bootstrapped startup."
    )

    return {
        "search_results": unique[:12],
        "analysis": analysis,
        "query_count": len(queries),
    }


# ── Social campaign ───────────────────────────────────────────────────────────

def generate_social_campaign(project_name: str, description: str, competitive: dict) -> dict:
    """Generate X threads and LinkedIn post."""
    print(f"[launch] Generating social media campaign...")

    comp_summary = competitive.get("analysis", "")[:1000]

    campaign = llm(
        f"""You are Clawmpson generating a social media launch campaign.

Project: {project_name}
Service: {description}
Competitive edge: {comp_summary}

Generate a COMPLETE social media campaign:

## X (Twitter) — THREAD 1: Problem/Solution (5 tweets)
Tweet each numbered 1/ through 5/. Hook in tweet 1. CTA in tweet 5.

## X (Twitter) — THREAD 2: Behind the scenes / how it works (4 tweets)
More technical, for builders and early adopters.

## LinkedIn Post
Professional, 150-250 words. Lead with insight, end with soft CTA.

## Hashtag Strategy
10 hashtags: mix of niche + broad. Explain which to use on X vs LinkedIn.

## Posting Schedule
When to post each piece for max reach (day of week + time).

Make it real. Specific to {project_name}. No filler. Write like someone who knows the market.""",
        system="You are a growth marketer who has launched 20+ B2B and consumer products. Be direct and specific."
    )

    return {"campaign": campaign}


# ── Fiverr / Upwork listing ───────────────────────────────────────────────────

def generate_gig_listing(project_name: str, description: str) -> dict:
    """Generate Fiverr/Upwork service listing copy."""
    print(f"[launch] Generating gig listing copy...")

    listing = llm(
        f"""You are Clawmpson writing a service listing for Fiverr and Upwork.

Service: {project_name}
What it does: {description}

Write TWO listings:

## FIVERR GIG
Title (max 80 chars):
Category suggestion:
Pricing: Basic / Standard / Premium (what's included, price points)
Description (250-300 words, keyword-rich, starts with benefit):
Tags (5, comma separated):
FAQ (3 questions buyers always ask):

## UPWORK PROFILE SECTION
Headline (max 120 chars):
Overview (400-500 words, positions Adam Maximus as expert, specific results):
Specialized Profile Title:

Use real pricing that reflects the market. Don't undercharge.""",
        system="You are a 6-figure Fiverr/Upwork seller who knows exactly what converts."
    )

    return {"listing": listing}


# ── Main launch orchestration ─────────────────────────────────────────────────

def launch_project(project_name: str, description: str = ""):
    today = datetime.date.today().isoformat()
    now = datetime.datetime.now().strftime("%H:%M")
    print(f"\n[launch] *** LAUNCHING PROJECT: {project_name} ***\n")

    # 1. Update projects.json
    project = upsert_project(project_name, description)
    print(f"[launch] Updated projects.json → status=active")

    # 2. Competitive research
    competitive = competitive_research(project_name, description)

    # 3. Social campaign
    social = generate_social_campaign(project_name, description, competitive)

    # 4. Gig listing
    gig = generate_gig_listing(project_name, description)

    # 5. Write outputs
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    DATASETS_DIR.mkdir(parents=True, exist_ok=True)

    slug = project_name.lower().replace(" ", "-").replace("/", "-")
    brief_path = OUTPUTS_DIR / f"launch-{slug}-{today}.md"
    dataset_path = DATASETS_DIR / f"competitive-{slug}-{today}.json"

    brief_path.write_text(f"""# Launch Brief: {project_name}
> Generated by Clawmpson at {now} on {today}

---

## COMPETITIVE ANALYSIS
{competitive['analysis']}

---

## SOCIAL MEDIA CAMPAIGN
{social['campaign']}

---

## FIVERR / UPWORK LISTINGS
{gig['listing']}

---

*Generated by project-launch.py. Review and approve via Telegram.*
""")

    dataset_path.write_text(json.dumps({
        "project": project_name,
        "description": description,
        "launched_at": today,
        "competitive": competitive,
        "outputs": {
            "brief": str(brief_path),
            "dataset": str(dataset_path),
        }
    }, indent=2))

    print(f"[launch] Wrote brief → {brief_path}")
    print(f"[launch] Wrote dataset → {dataset_path}")

    # 6. Schedule weekly competitive scan
    _schedule_weekly_scan(project_name, slug)

    # 7. Telegram notification
    comp_short = competitive["analysis"][:600] + "..." if len(competitive["analysis"]) > 600 else competitive["analysis"]
    campaign_short = social["campaign"][:800] + "..." if len(social["campaign"]) > 800 else social["campaign"]

    message = f"""PROJECT LAUNCHED: {project_name}

{description}

COMPETITIVE LANDSCAPE:
{comp_short}

SOCIAL CAMPAIGN (preview):
{campaign_short}

FULL BRIEF: autoresearch/outputs/briefs/launch-{slug}-{today}.md
GIG LISTINGS: included in brief

NEXT: Reply with any of these to act:
  /post-x — queue X threads for posting
  /post-linkedin — queue LinkedIn post
  /list-gig — list on Fiverr/Upwork now
  /research-more [competitor] — deep dive on a specific competitor"""

    tg_send(message)
    print(f"[launch] Telegram notified.")

    return brief_path


def _schedule_weekly_scan(project_name: str, slug: str):
    """Append project to the weekly competitive scan list."""
    scan_list = OPENCLAW / "memory" / "competitive-scan-list.json"
    existing = []
    if scan_list.exists():
        try:
            existing = json.loads(scan_list.read_text())
        except Exception:
            pass
    # Add if not already there
    names = [p.get("name","") for p in existing]
    if project_name not in names:
        existing.append({
            "name": project_name,
            "slug": slug,
            "added_at": datetime.date.today().isoformat(),
            "scan_frequency": "weekly",
        })
        scan_list.parent.mkdir(parents=True, exist_ok=True)
        scan_list.write_text(json.dumps(existing, indent=2))
    print(f"[launch] Scheduled weekly competitive scan for: {project_name}")


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 project-launch.py <project_name> [description]")
        sys.exit(1)

    name = sys.argv[1]
    desc = sys.argv[2] if len(sys.argv) > 2 else ""
    launch_project(name, desc)
