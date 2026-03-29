#!/usr/bin/env python3
"""
Inspector Gadget -- MCP Server (stdio transport).

Implements the Model Context Protocol over JSON-RPC 2.0 / stdio so that
Claude Code (and any other MCP client) can call Inspector Gadget as a tool.

Works on Python 3.9+ without the `mcp` SDK by speaking the wire protocol
directly: newline-delimited JSON-RPC messages on stdin/stdout.

Tools exposed:
  inspector_run_full          -- Trigger a full audit
  inspector_run_verify        -- Trade verification only
  inspector_get_latest_report -- Get the latest audit report (markdown)
  inspector_get_findings      -- Query findings by severity / type
  inspector_get_trust_score   -- Current trust score + red flags

Usage (Claude Code settings.json):
  {
    "mcpServers": {
      "inspector-gadget": {
        "command": "python3",
        "args": ["/Users/nayslayer/openclaw/scripts/inspector/mcp_server.py"]
      }
    }
  }
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Ensure inspector package is importable
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent          # .../inspector/
_SCRIPTS_DIR = _SCRIPT_DIR.parent                      # .../scripts/
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from inspector.inspector_db import InspectorDB
from inspector.dashboard import Dashboard
from inspector.polymarket_client import PolymarketClient
from inspector.verifier import TradeVerifier
from inspector.resolution_auditor import ResolutionAuditor
from inspector.stats_auditor import StatsAuditor
from inspector.hallucination_detector import HallucinationDetector
from inspector.logic_analyzer import LogicAnalyzer
from inspector.repo_scanner import RepoScanner
from inspector.run_inspection import TARGETS, _load_env

# Optional: Kalshi may fail to import if deps missing -- degrade gracefully
try:
    from inspector.kalshi_client import KalshiClient
except ImportError:
    KalshiClient = None  # type: ignore[assignment,misc]

# ---------------------------------------------------------------------------
# Reports directory
# ---------------------------------------------------------------------------
REPORTS_DIR = Path("~/openclaw/security/inspector/reports").expanduser()

# ---------------------------------------------------------------------------
# MCP protocol constants
# ---------------------------------------------------------------------------
PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "inspector-gadget"
SERVER_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Tool definitions (MCP schema)
# ---------------------------------------------------------------------------
TOOLS: List[Dict[str, Any]] = [
    {
        "name": "inspector_run_full",
        "description": (
            "Trigger a full Inspector Gadget audit: trade verification, "
            "resolution audits, stats checks, hallucination detection, "
            "code analysis, and repo scanning. Returns a summary of results."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Which bot to audit. Options: openclaw, rivalclaw.",
                    "default": "openclaw",
                },
            },
        },
    },
    {
        "name": "inspector_run_verify",
        "description": (
            "Run trade verification only: verify trades, resolution audits, "
            "stats checks, and hallucination detection. No code scanning."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Which bot to audit. Options: openclaw, rivalclaw.",
                    "default": "openclaw",
                },
            },
        },
    },
    {
        "name": "inspector_get_latest_report",
        "description": (
            "Get the most recent Inspector Gadget audit report as markdown."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "inspector_get_findings",
        "description": (
            "Query code findings from the inspector database, optionally "
            "filtered by severity and/or finding type."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "severity": {
                    "type": "string",
                    "description": "Filter by severity: critical, high, medium, low.",
                },
                "finding_type": {
                    "type": "string",
                    "description": "Filter by finding type string.",
                },
            },
        },
    },
    {
        "name": "inspector_get_trust_score",
        "description": (
            "Get the current trust score and red flags summary from the "
            "latest audit report."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _get_target_config(target_name: str) -> Dict[str, Any]:
    """Resolve a target name to its config dict."""
    name = (target_name or "openclaw").lower().strip()
    if name not in TARGETS:
        raise ValueError(
            f"Unknown target '{name}'. Valid targets: {', '.join(TARGETS.keys())}"
        )
    return TARGETS[name]


def _init_kalshi(target_cfg: Dict[str, Any]) -> Optional[Any]:
    """Try to initialise a KalshiClient for the given target."""
    if KalshiClient is None:
        return None
    env_path = Path(target_cfg["env_path"]).expanduser()
    target_env = _load_env(env_path)
    kalshi_key = target_env.get("KALSHI_API_KEY_ID") or os.environ.get("KALSHI_API_KEY_ID", "")
    kalshi_pk = target_env.get("KALSHI_PRIVATE_KEY_PATH") or os.environ.get("KALSHI_PRIVATE_KEY_PATH", "")
    kalshi_env = target_env.get("KALSHI_API_ENV") or os.environ.get("KALSHI_API_ENV", "demo")
    if kalshi_key and kalshi_pk:
        return KalshiClient(api_key_id=kalshi_key, private_key_path=kalshi_pk, api_env=kalshi_env)
    return None


def tool_run_full(arguments: Dict[str, Any]) -> str:
    """Execute a full audit and return a summary."""
    target_name = arguments.get("target", "openclaw")
    target_cfg = _get_target_config(target_name)
    target_db = target_cfg["db"]
    chat_id = target_cfg["chat_id"]
    label = target_cfg["label"]

    db = InspectorDB()
    db.init()
    poly = PolymarketClient()
    kalshi = _init_kalshi(target_cfg)

    results = {}
    start = datetime.now(timezone.utc)

    # -- Trade verification --
    tv = TradeVerifier(db=db, poly=poly, kalshi=kalshi)
    results["verify"] = tv.run(target_db)

    # -- Resolution audit --
    ra = ResolutionAuditor(db=db, poly=poly, kalshi=kalshi)
    results["resolution"] = ra.run(target_db)

    # -- Stats audit --
    sa = StatsAuditor()
    results["stats"] = sa.run(target_db, chat_id=chat_id)

    # Persist stats red flags
    for flag in results["stats"].get("red_flags", []):
        db.insert("code_findings", {
            "file_path": "stats_audit",
            "line_number": None,
            "finding_type": "stats_%s" % flag.get("check", "unknown"),
            "severity": flag.get("severity", "medium"),
            "description": flag.get("message", ""),
            "snippet": None,
            "found_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })

    # -- Hallucination detection --
    signals_path = target_cfg["signals"]
    hd = HallucinationDetector(db=db, poly=poly, kalshi=kalshi)
    if signals_path:
        results["hallucination"] = hd.run_on_signals(signals_path)
    else:
        results["hallucination"] = {"checked": 0, "skipped": "no signals file"}
    results["hallucination_trades"] = hd.run_on_llm_trades(target_db)

    # -- Code analysis --
    la = LogicAnalyzer(db=db, target_files=target_cfg["source_files"])
    results["code"] = la.run()

    # -- Repo scanner --
    rs = RepoScanner(db=db, repo_root=target_cfg["repo"])
    results["repo"] = rs.run()

    # -- Generate report --
    dash = Dashboard(db=db)
    report_path = dash.generate()

    elapsed = (datetime.now(timezone.utc) - start).seconds

    # Build summary
    last_reports = db.fetch_all("audit_reports")
    last = last_reports[-1] if last_reports else {}
    trust = json.loads(last.get("trust_scores_json", "{}")).get("overall", "?")

    poly.close()
    if kalshi is not None:
        kalshi.close()

    summary = (
        "Inspector Gadget Full Audit -- %s\n"
        "Trust Score: %s/100\n"
        "Trades checked: %s\n"
        "Verified: %s | Discrepancies: %s | Impossible: %s\n"
        "Code findings: %s\n"
        "Hallucination results: %s\n"
        "Report saved: %s\n"
        "Elapsed: %ds"
    ) % (
        label,
        trust,
        last.get("total_trades_checked", "?"),
        last.get("verified_count", "?"),
        last.get("discrepancy_count", 0),
        last.get("impossible_count", 0),
        results.get("code", {}),
        results.get("hallucination", {}),
        report_path,
        elapsed,
    )
    return summary


def tool_run_verify(arguments: Dict[str, Any]) -> str:
    """Execute trade verification checks only."""
    target_name = arguments.get("target", "openclaw")
    target_cfg = _get_target_config(target_name)
    target_db = target_cfg["db"]
    chat_id = target_cfg["chat_id"]
    label = target_cfg["label"]

    db = InspectorDB()
    db.init()
    poly = PolymarketClient()
    kalshi = _init_kalshi(target_cfg)

    results = {}
    start = datetime.now(timezone.utc)

    # -- Trade verification --
    tv = TradeVerifier(db=db, poly=poly, kalshi=kalshi)
    results["verify"] = tv.run(target_db)

    # -- Resolution audit --
    ra = ResolutionAuditor(db=db, poly=poly, kalshi=kalshi)
    results["resolution"] = ra.run(target_db)

    # -- Stats audit --
    sa = StatsAuditor()
    results["stats"] = sa.run(target_db, chat_id=chat_id)

    for flag in results["stats"].get("red_flags", []):
        db.insert("code_findings", {
            "file_path": "stats_audit",
            "line_number": None,
            "finding_type": "stats_%s" % flag.get("check", "unknown"),
            "severity": flag.get("severity", "medium"),
            "description": flag.get("message", ""),
            "snippet": None,
            "found_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })

    # -- Hallucination detection --
    signals_path = target_cfg["signals"]
    hd = HallucinationDetector(db=db, poly=poly, kalshi=kalshi)
    if signals_path:
        results["hallucination"] = hd.run_on_signals(signals_path)
    else:
        results["hallucination"] = {"checked": 0, "skipped": "no signals file"}
    results["hallucination_trades"] = hd.run_on_llm_trades(target_db)

    # -- Generate report --
    dash = Dashboard(db=db)
    report_path = dash.generate()

    elapsed = (datetime.now(timezone.utc) - start).seconds

    last_reports = db.fetch_all("audit_reports")
    last = last_reports[-1] if last_reports else {}
    trust = json.loads(last.get("trust_scores_json", "{}")).get("overall", "?")

    poly.close()
    if kalshi is not None:
        kalshi.close()

    summary = (
        "Inspector Gadget Verify -- %s\n"
        "Trust Score: %s/100\n"
        "Trades checked: %s\n"
        "Verified: %s | Discrepancies: %s | Impossible: %s\n"
        "Stats red flags: %d\n"
        "Report saved: %s\n"
        "Elapsed: %ds"
    ) % (
        label,
        trust,
        last.get("total_trades_checked", "?"),
        last.get("verified_count", "?"),
        last.get("discrepancy_count", 0),
        last.get("impossible_count", 0),
        len(results["stats"].get("red_flags", [])),
        report_path,
        elapsed,
    )
    return summary


def tool_get_latest_report(arguments: Dict[str, Any]) -> str:
    """Return the text of the most recent audit report."""
    if not REPORTS_DIR.exists():
        return "No reports directory found at %s" % REPORTS_DIR

    reports = sorted(REPORTS_DIR.glob("audit-*.md"))
    if not reports:
        return "No audit reports found. Run inspector_run_full first."

    latest = reports[-1]
    text = latest.read_text(encoding="utf-8")
    return "# Latest Report: %s\n\n%s" % (latest.name, text)


def tool_get_findings(arguments: Dict[str, Any]) -> str:
    """Query code_findings with optional severity/type filters."""
    db = InspectorDB()
    db.init()

    where_parts: List[str] = []
    params: List[str] = []

    severity = arguments.get("severity")
    if severity:
        where_parts.append("severity = ?")
        params.append(severity.lower().strip())

    finding_type = arguments.get("finding_type")
    if finding_type:
        where_parts.append("finding_type LIKE ?")
        params.append("%%%s%%" % finding_type)

    where = " AND ".join(where_parts) if where_parts else ""
    findings = db.fetch_all("code_findings", where=where, params=tuple(params))

    if not findings:
        filters = []
        if severity:
            filters.append("severity=%s" % severity)
        if finding_type:
            filters.append("type=%s" % finding_type)
        filter_str = ", ".join(filters) if filters else "none"
        return "No findings found (filters: %s)." % filter_str

    lines = ["# Code Findings (%d results)\n" % len(findings)]
    for f in findings:
        sev = (f.get("severity") or "?").upper()
        fp = f.get("file_path") or "?"
        ln = f.get("line_number")
        loc = "%s:%s" % (fp, ln) if ln else fp
        ftype = f.get("finding_type") or "?"
        desc = f.get("description") or ""
        lines.append("- [%s] %s (%s) -- %s" % (sev, loc, ftype, desc))

    return "\n".join(lines)


def tool_get_trust_score(arguments: Dict[str, Any]) -> str:
    """Return the trust score and red flags from the latest audit_reports row."""
    db = InspectorDB()
    db.init()

    reports = db.fetch_all("audit_reports")
    if not reports:
        return "No audit reports in the database. Run inspector_run_full first."

    latest = reports[-1]
    trust_json = json.loads(latest.get("trust_scores_json", "{}"))
    red_flags_json = json.loads(latest.get("red_flags_json", "[]"))
    overall = trust_json.get("overall", "?")

    lines = [
        "Trust Score: %s/100" % overall,
        "Report: %s" % latest.get("report_id", "?"),
        "Generated: %s" % latest.get("generated_at", "?"),
        "Trades checked: %s" % latest.get("total_trades_checked", "?"),
        "Verified: %s" % latest.get("verified_count", "?"),
        "Discrepancies: %s" % latest.get("discrepancy_count", 0),
        "Impossible: %s" % latest.get("impossible_count", 0),
        "",
    ]

    if red_flags_json:
        lines.append("Red flags:")
        for flag in red_flags_json:
            if isinstance(flag, str):
                lines.append("  - %s" % flag)
            elif isinstance(flag, dict):
                lines.append("  - [%s] %s" % (flag.get("severity", "?"), flag.get("message", str(flag))))
    else:
        lines.append("No red flags.")

    return "\n".join(lines)


# Tool dispatch table
TOOL_HANDLERS = {
    "inspector_run_full": tool_run_full,
    "inspector_run_verify": tool_run_verify,
    "inspector_get_latest_report": tool_get_latest_report,
    "inspector_get_findings": tool_get_findings,
    "inspector_get_trust_score": tool_get_trust_score,
}


# ---------------------------------------------------------------------------
# JSON-RPC / MCP wire protocol
# ---------------------------------------------------------------------------

def _write_message(msg: Dict[str, Any]) -> None:
    """Write a JSON-RPC message to stdout."""
    raw = json.dumps(msg)
    sys.stdout.write(raw + "\n")
    sys.stdout.flush()


def _make_response(request_id: Any, result: Any) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _make_error(request_id: Any, code: int, message: str, data: Any = None) -> Dict[str, Any]:
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": err}


def handle_initialize(request_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    """Respond to the MCP initialize handshake."""
    return _make_response(request_id, {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {
            "tools": {},
        },
        "serverInfo": {
            "name": SERVER_NAME,
            "version": SERVER_VERSION,
        },
    })


def handle_tools_list(request_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    """Return the list of available tools."""
    return _make_response(request_id, {"tools": TOOLS})


def handle_tools_call(request_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a tool and return the result."""
    tool_name = params.get("name", "")
    arguments = params.get("arguments", {})

    handler = TOOL_HANDLERS.get(tool_name)
    if handler is None:
        return _make_error(request_id, -32602, "Unknown tool: %s" % tool_name)

    try:
        result_text = handler(arguments)
        return _make_response(request_id, {
            "content": [
                {"type": "text", "text": result_text},
            ],
        })
    except Exception as exc:
        tb = traceback.format_exc()
        return _make_response(request_id, {
            "content": [
                {"type": "text", "text": "Error running %s: %s\n\n%s" % (tool_name, exc, tb)},
            ],
            "isError": True,
        })


# Method dispatch
METHOD_HANDLERS = {
    "initialize": handle_initialize,
    "tools/list": handle_tools_list,
    "tools/call": handle_tools_call,
}

# Notifications we silently acknowledge (no response needed per JSON-RPC)
NOTIFICATION_METHODS = frozenset({
    "notifications/initialized",
    "notifications/cancelled",
})


def main_loop() -> None:
    """Read JSON-RPC messages from stdin, dispatch, write responses to stdout."""
    # Redirect stderr so inspector modules' prints don't corrupt the JSON stream.
    # We keep a reference to real stderr for our own debug logging.
    _real_stderr = sys.stderr
    log_path = Path("~/.openclaw/inspector_mcp.log").expanduser()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(str(log_path), "a", encoding="utf-8")

    # Redirect stdout prints from inspector modules to stderr/log
    # We'll capture stdout for JSON-RPC and use _write_message for output.
    import io
    _real_stdout = sys.stdout
    sys.stderr = log_file

    # Replace stdout with a buffer so inspector print() calls don't pollute JSON-RPC
    _capture = io.StringIO()

    for raw_line in sys.stdin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue

        try:
            msg = json.loads(raw_line)
        except json.JSONDecodeError:
            # Not valid JSON -- skip
            continue

        method = msg.get("method", "")
        request_id = msg.get("id")
        params = msg.get("params", {})

        # Notifications have no id -- don't send a response
        if request_id is None and method in NOTIFICATION_METHODS:
            continue

        handler = METHOD_HANDLERS.get(method)
        if handler is None:
            if request_id is not None:
                resp = _make_error(request_id, -32601, "Method not found: %s" % method)
                _real_stdout.write(json.dumps(resp) + "\n")
                _real_stdout.flush()
            continue

        # Temporarily swap stdout so inspector print() output goes to capture
        sys.stdout = _capture
        try:
            resp = handler(request_id, params)
        finally:
            sys.stdout = _real_stdout
            # Discard captured prints (they're inspector status messages)
            _capture.truncate(0)
            _capture.seek(0)

        _real_stdout.write(json.dumps(resp) + "\n")
        _real_stdout.flush()

    log_file.close()


if __name__ == "__main__":
    main_loop()
