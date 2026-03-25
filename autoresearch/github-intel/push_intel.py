#!/usr/bin/env python3
"""Push pending github-intel recommendations to Repo Man.

Run manually:       python push_intel.py
Preview only:       python push_intel.py --dry-run
Force all:          python push_intel.py --force

Designed to be called after each github-intel crawl cycle.
"""
import asyncio
import json
import sys
from pathlib import Path

# Import from repo-man scripts (works as long as ~/repo-man exists)
REPO_MAN_SCRIPTS = Path.home() / "repo-man" / "scripts"
if not REPO_MAN_SCRIPTS.exists():
    print(f"[push_intel] ERROR: {REPO_MAN_SCRIPTS} not found. Is Repo Man installed?")
    sys.exit(1)

sys.path.insert(0, str(REPO_MAN_SCRIPTS))

from push_to_repoman import push_items, PushItem  # type: ignore  # noqa: E402

RECS_FILE = Path(__file__).parent / "recommendations.json"
PUSHED_STATUS = "pushed_to_repoman"


async def main(dry_run: bool = False, force: bool = False) -> None:
    if not RECS_FILE.exists():
        print(f"[push_intel] {RECS_FILE} not found — run github-intel crawler first")
        return

    data = json.loads(RECS_FILE.read_text())
    recs = data.get("recommendations", [])

    if force:
        pending = recs
        print(f"[push_intel] --force mode: pushing all {len(pending)} recommendations")
    else:
        pending = [r for r in recs if r.get("status") == "pending"]
        print(f"[push_intel] {len(recs)} total, {len(pending)} pending")

    if not pending:
        print("[push_intel] nothing to push")
        return

    items = [PushItem.from_github_intel(r) for r in pending]

    if dry_run:
        print("[push_intel] DRY RUN — would push:")
        for it in items:
            print(f"  {it.raw_input}")
            print(f"    {it.note[:100]}")
        return

    try:
        result = await push_items(items)
        print(f"[push_intel] queued {result['queued']} items in Repo Man")

        # Mark as pushed so we don't double-push
        for r in pending:
            r["status"] = PUSHED_STATUS
        RECS_FILE.write_text(json.dumps(data, indent=2))
        print(f"[push_intel] marked {len(pending)} items as '{PUSHED_STATUS}'")

    except Exception as exc:
        print(f"[push_intel] ERROR: {exc}")
        print("[push_intel] Is Repo Man running at localhost:8765?")
        sys.exit(1)


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    force = "--force" in sys.argv
    asyncio.run(main(dry_run=dry_run, force=force))
