#!/usr/bin/env python3
"""
ClawTeam CLI entry point.
Usage: python clawteam.py --task "..." [--pattern sequential|parallel|debate|hierarchy]
       python clawteam.py --resume swarm-id
       python clawteam.py --list
       python clawteam.py --task "..." --dry-run
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

# Add scripts/ dir so `clawteam` package is importable
_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from clawteam import bus
from clawteam.orchestrator import run_swarm, resume_swarm
from clawteam.decomposer import decompose

_VALID_PATTERNS = {"sequential", "parallel", "debate", "hierarchy"}


def _sanitize(raw: str) -> str:
    """Strip control chars, cap at 500 chars."""
    return re.sub(r'[\x00-\x1f\x7f]', '', raw)[:500]


def cmd_run(args):
    task = _sanitize(args.task)
    if not task:
        print("[ERROR] Empty task after sanitization.", file=sys.stderr)
        sys.exit(1)

    pattern = args.pattern
    if pattern and pattern not in _VALID_PATTERNS:
        print(f"[ERROR] Unknown pattern {pattern!r}. Choose: {', '.join(_VALID_PATTERNS)}", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        cmd_dry_run(task, pattern)
        return

    print(f"Starting swarm: {task[:60]}...")
    swarm_id = run_swarm(task, pattern=pattern, notify=args.notify)
    swarm = bus.get_swarm(swarm_id)
    print(f"\nSwarm {swarm_id} → {swarm['status']}")
    if swarm.get("result"):
        print("\n" + swarm["result"][:500])


def cmd_dry_run(task: str, pattern):
    print(f"Swarm: {task}")
    decomp = decompose(task)
    effective_pattern = pattern or decomp["pattern"]
    print(f"Pattern: {effective_pattern}" + (" (auto-selected)" if not pattern else ""))
    print("Subtasks:")
    for idx, sub in enumerate(decomp["subtasks"]):
        print(f"  {idx}. [{sub['agent']}] {sub['prompt']}")


def cmd_resume(args):
    swarm_id = args.resume
    print(f"Resuming swarm: {swarm_id}")
    resume_swarm(swarm_id, notify=args.notify)
    swarm = bus.get_swarm(swarm_id)
    print(f"Swarm {swarm_id} → {swarm['status']}")


def cmd_list(args):
    rows = bus.list_swarms(limit=10)
    if not rows:
        print("No swarms found.")
        return
    print(f"{'ID':<35} {'PATTERN':<12} {'STATUS':<10} {'CREATED'}")
    print("-" * 80)
    for r in rows:
        slug = r["id"][len("swarm-"):][:28]
        print(f"{slug:<35} {r['pattern']:<12} {r['status']:<10} {r['created_at'][:19]}")


def main():
    parser = argparse.ArgumentParser(description="ClawTeam — multi-agent swarm orchestration")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--task",   help="Task description to decompose and run")
    group.add_argument("--resume", help="Swarm ID to resume")
    group.add_argument("--list",   action="store_true", help="List recent swarms")
    parser.add_argument("--pattern", choices=list(_VALID_PATTERNS),
                        help="Execution pattern (default: auto-selected)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show decomposition without executing")
    parser.add_argument("--notify", action="store_true",
                        help="Send Telegram message on completion")
    args = parser.parse_args()

    if args.task:
        cmd_run(args)
    elif args.resume:
        cmd_resume(args)
    elif args.list:
        cmd_list(args)


if __name__ == "__main__":
    main()
