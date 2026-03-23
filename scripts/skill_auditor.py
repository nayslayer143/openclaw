#!/usr/bin/env python3
"""
Skill/MCP Security Auditor — CLI entry point.

Usage:
  python3 skill_auditor.py audit <path_or_name>
  python3 skill_auditor.py verify
  python3 skill_auditor.py list
  python3 skill_auditor.py summary
  python3 skill_auditor.py mcp
"""
from __future__ import annotations
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from security import auditor, registry, reporter


def _print(msg: str):
    """Pass-through notify_fn for CLI — prints to stdout."""
    print(msg)


def cmd_audit(args: list[str]):
    if not args:
        print("Usage: skill_auditor.py audit <path_or_skill_name>")
        sys.exit(1)
    target = args[0]
    path   = Path(target)
    if not path.exists():
        # Try incoming dir
        path = Path.home() / "openclaw" / "skills" / "incoming" / target
    result = auditor.audit_skill(str(path), notify_fn=_print)
    print(f"\nAudit complete: {result.skill_name} — {result.category} ({result.score}/100)")
    if result.report_path:
        print(f"Report: {result.report_path}")


def cmd_verify():
    results = auditor.verify_all_skills(notify_fn=_print)
    changed = [r for r in results if r[1] == "changed"]
    ok      = [r for r in results if r[1] == "ok"]
    print(f"\nVerified {len(results)} skills: {len(ok)} ok, {len(changed)} changed")


def cmd_list():
    rows = registry.get_all()
    if not rows:
        print("No skills registered.")
        return
    print(f"{'Skill':<30} {'Score':>5}  {'Category':<10}  {'Approved By':<12}  Last Verified")
    print("-" * 85)
    for r in rows:
        print(f"{r['skill_name']:<30} {r['trust_score']:>5}  {r['category']:<10}  "
              f"{r.get('approved_by') or '—':<12}  {r.get('last_verified') or '—'}")


def cmd_summary():
    rows      = registry.get_all()
    out_path  = reporter.write_summary(rows)
    print(f"Summary written to {out_path}")


def cmd_mcp():
    results = auditor.audit_mcp(notify_fn=_print)
    print(f"\nMCP audit complete: {len(results)} local MCPs scanned.")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd  = sys.argv[1]
    args = sys.argv[2:]

    dispatch = {
        "audit":   lambda: cmd_audit(args),
        "verify":  cmd_verify,
        "list":    cmd_list,
        "summary": cmd_summary,
        "mcp":     cmd_mcp,
    }

    fn = dispatch.get(cmd)
    if not fn:
        print(f"Unknown command: {cmd}")
        print("Commands: audit, verify, list, summary, mcp")
        sys.exit(1)
    fn()


if __name__ == "__main__":
    main()
