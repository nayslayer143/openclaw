# scripts/security/auditor.py
#!/usr/bin/env python3
"""
Orchestrator for the skill/MCP security audit pipeline.
Wires scanner → scorer → debate → registry → reporter → notify.
"""
from __future__ import annotations
import json
import os
import datetime
import logging
from dataclasses import dataclass
from pathlib import Path

from security import scanner, scorer, registry, debate, reporter

LOG_FILE = Path.home() / "openclaw" / "logs" / "security-auditor.jsonl"
SKILLS_INCOMING = Path.home() / "openclaw" / "skills" / "incoming"
SKILLS_ACTIVE   = Path.home() / "openclaw" / "skills" / "active"
SKILLS_REJECTED = Path.home() / "openclaw" / "skills" / "rejected"


def _log(event: str, data: dict):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = json.dumps({"ts": datetime.datetime.utcnow().isoformat(),
                        "event": event, **data})
    with open(LOG_FILE, "a") as f:
        f.write(entry + "\n")


@dataclass
class AuditResult:
    skill_name:  str
    score:       int
    category:    str
    findings:    list
    mismatch:    bool
    debate:      dict | None
    report_path: Path | None
    notification: str


def audit_skill(
    source_path: str,
    skill_name: str | None = None,
    source_url: str | None = None,
    notify_fn=None,
) -> AuditResult:
    """
    Full audit pipeline for a skill file or directory.
    notify_fn: optional callable(message: str) for Telegram DM.
    """
    path = Path(source_path)
    if skill_name is None:
        skill_name = path.stem

    # 1. Scan all .py files
    all_findings = []
    if path.is_file():
        all_findings = scanner.scan(source_path)
    elif path.is_dir():
        for py_file in sorted(path.rglob("*.py")):
            all_findings.extend(scanner.scan(str(py_file)))

    # 2. SKILL.md capability check
    skill_md = path.parent / "SKILL.md" if path.is_file() else path / "SKILL.md"
    caps     = scanner.scan_skill_md_capabilities(str(skill_md))

    # 3. Score
    score_result = scorer.score(all_findings, skill_md_caps=caps, source_url=source_url)
    trust_score  = score_result["score"]
    category     = score_result["category"]
    mismatch     = score_result["mismatch"]

    # 4. Debate (REVIEW only, and only if we have a local file to read)
    debate_result = None
    if category == scorer.REVIEW:
        try:
            code = path.read_text(encoding="utf-8", errors="replace") if path.is_file() \
                   else "\n".join(
                       p.read_text(encoding="utf-8", errors="replace")
                       for p in sorted(path.rglob("*.py"))
                   )
            debate_result = debate.run_debate(code[:6000], all_findings, trust_score)
            if not debate_result["parse_failed"]:
                trust_score = debate_result["adjusted_score"]
                if trust_score >= 80:
                    category = scorer.TRUSTED
                elif trust_score >= 50:
                    category = scorer.REVIEW
                else:
                    category = scorer.BLOCKED
        except Exception as e:
            _log("debate_error", {"skill": skill_name, "error": str(e)})

    # 5. Register
    registry.register(
        skill_name, source_path, trust_score, category,
        all_findings, source_url=source_url,
    )

    # 6. Move file based on category (only for skills in incoming/)
    try:
        if path.exists() and path.is_relative_to(SKILLS_INCOMING):
            if category == scorer.TRUSTED:
                SKILLS_ACTIVE.mkdir(parents=True, exist_ok=True)
                path.rename(SKILLS_ACTIVE / path.name)
            elif category == scorer.BLOCKED:
                SKILLS_REJECTED.mkdir(parents=True, exist_ok=True)
                path.rename(SKILLS_REJECTED / path.name)
            # REVIEW: stays in incoming/
    except Exception as e:
        _log("move_error", {"skill": skill_name, "error": str(e)})

    # 7. Write report
    report_content = reporter.build_report(
        skill_name, trust_score, category, all_findings,
        mismatch, debate_result.get("transcript") if debate_result else None,
        approved_by=None, source_url=source_url,
    )
    report_path = None
    try:
        report_path = reporter.write_report(skill_name, report_content)
    except Exception as e:
        _log("report_error", {"skill": skill_name, "error": str(e)})

    # 8. Build notification
    if category == scorer.TRUSTED:
        msg = f"✅ Skill TRUSTED: {skill_name} (score: {trust_score}/100)"
    elif category == scorer.REVIEW:
        parse_note = " ⚠ debate failed — manual review" if (debate_result and debate_result["parse_failed"]) else ""
        msg = (f"🟡 Skill needs review: {skill_name} (score: {trust_score}/100){parse_note}\n"
               f"Reply /approve {skill_name} or /block {skill_name}")
    else:
        top = all_findings[0].snippet[:60] if all_findings else "multiple issues"
        msg = f"🔴 Skill BLOCKED: {skill_name} (score: {trust_score}/100) — {top}"

    if notify_fn:
        notify_fn(msg)

    _log("audit_complete", {"skill": skill_name, "score": trust_score, "category": category})
    return AuditResult(skill_name, trust_score, category, all_findings,
                       mismatch, debate_result, report_path, msg)


def handle_approval(skill_name: str, notify_fn=None) -> str:
    """
    Jordan approves a REVIEW-held skill.
    Re-verifies SHA256 before moving to active/. set_approved() is a pure DB update
    and is only called AFTER the hash check passes.
    """
    row = registry.get(skill_name)
    if not row:
        return f"Unknown skill: {skill_name}"

    if row["category"] == scorer.BLOCKED:
        return f"{skill_name} is BLOCKED — cannot approve."

    # Re-verify hash before approving
    source_path = row["source_path"]
    live_hash   = registry.compute_hash(source_path)
    if live_hash != row["hash_sha256"]:
        msg = (f"⚠ {skill_name}: file changed since audit. "
               f"Re-run /audit {skill_name} before approving.")
        if notify_fn:
            notify_fn(msg)
        return msg

    # Hash matches — approve and move
    registry.set_approved(skill_name, "jordan")

    src = Path(source_path)
    if src.exists():
        try:
            if src.is_relative_to(SKILLS_INCOMING):
                SKILLS_ACTIVE.mkdir(parents=True, exist_ok=True)
                src.rename(SKILLS_ACTIVE / src.name)
        except Exception as e:
            _log("approval_move_error", {"skill": skill_name, "error": str(e)})

    msg = f"✅ {skill_name} approved by Jordan and moved to active/"
    if notify_fn:
        notify_fn(msg)
    return msg


def handle_block(skill_name: str, notify_fn=None) -> str:
    """Jordan manually blocks a skill."""
    row = registry.get(skill_name)
    if not row:
        return f"Unknown skill: {skill_name}"

    registry.set_blocked(skill_name)

    src = Path(row["source_path"])
    if src.exists():
        SKILLS_REJECTED.mkdir(parents=True, exist_ok=True)
        try:
            src.rename(SKILLS_REJECTED / src.name)
        except Exception as exc:
            _log("block_move_error", {"skill_name": skill_name, "error": str(exc)})

    msg = f"🔴 {skill_name} blocked by Jordan."
    if notify_fn:
        notify_fn(msg)
    return msg


def scan_incoming(notify_fn=None) -> list[AuditResult]:
    """Scan ~/openclaw/skills/incoming/ for new unregistered files. Called by cron."""
    SKILLS_INCOMING.mkdir(parents=True, exist_ok=True)
    results = []
    for path in sorted(SKILLS_INCOMING.iterdir()):
        if path.suffix not in (".py",) and not path.is_dir():
            continue
        skill_name = path.stem
        if registry.get(skill_name):
            continue  # already registered
        if notify_fn:
            notify_fn(f"🟡 New skill pending audit: {skill_name}")
        result = audit_skill(str(path), skill_name=skill_name, notify_fn=notify_fn)
        results.append(result)
    return results


def verify_all_skills(notify_fn=None) -> list[tuple[str, str]]:
    """Hash-check all registered skills. DM Jordan if any changed."""
    results = registry.verify_all()
    for skill_name, status in results:
        if status in ("changed", "missing"):
            label = "hash changed" if status == "changed" else "file missing"
            msg = f"🔴 Skill {label}: {skill_name} — re-auditing now"
            if notify_fn:
                notify_fn(msg)
            row = registry.get(skill_name)
            if row and status == "changed":
                audit_skill(row["source_path"], skill_name=skill_name,
                            source_url=row.get("source_url"), notify_fn=notify_fn)
    return results


def audit_mcp(notify_fn=None) -> list[AuditResult]:
    """
    Scan Claude MCP configurations in ~/.claude/settings.json and
    project-level .claude/settings.json.
    """
    settings_paths = [
        Path.home() / ".claude" / "settings.json",
        Path.cwd() / ".claude" / "settings.json",
    ]
    results = []
    for settings_path in settings_paths:
        if not settings_path.exists():
            continue
        try:
            data = json.loads(settings_path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            _log("audit_mcp_error", {"path": str(settings_path), "error": str(e)})
            continue  # Graceful — no crash, no notification

        mcp_servers = data.get("mcpServers", {})
        for server_name, config in mcp_servers.items():
            skill_name = f"mcp:{server_name}"
            command    = config.get("command", "")
            source_url = config.get("url")

            # Remote MCP (npm or remote URL) — no source to scan
            is_remote = (
                command in ("npx", "uvx", "npm") or
                (source_url and not source_url.startswith("file://"))
            )
            if is_remote:
                if registry.get(skill_name):
                    continue  # already registered — skip to avoid repeat DMs
                registry.register(
                    skill_name, str(settings_path), score=55,
                    category=scorer.REVIEW, findings=[], source_url=source_url,
                )
                msg = (f"🟡 Remote MCP: {server_name} — manual review required. "
                       f"No local source to scan.")
                if notify_fn:
                    notify_fn(msg)
                continue

            # Local MCP — find the script and scan it
            local_path = Path(command) if command else None
            if local_path and local_path.exists():
                result = audit_skill(str(local_path), skill_name=skill_name,
                                     source_url=source_url, notify_fn=notify_fn)
                results.append(result)

    return results
