"""
Inspector Gadget -- FastAPI Web Application.

Serves REST API endpoints for the Inspector Gadget trading verification
system and a self-contained HTML UI.

Usage:
    python api.py
    # or: uvicorn inspector.api:app --host 0.0.0.0 --port 7771 --reload
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure the parent of 'inspector/' is on sys.path so the package is importable.
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import BackgroundTasks, FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse

from inspector.dashboard import Dashboard
from inspector.hallucination_detector import HallucinationDetector
from inspector.inspector_db import InspectorDB
from inspector.kalshi_client import KalshiClient
from inspector.logic_analyzer import LogicAnalyzer
from inspector.polymarket_client import PolymarketClient
from inspector.repo_scanner import RepoScanner
from inspector.resolution_auditor import ResolutionAuditor
from inspector.stats_auditor import StatsAuditor
from inspector.verifier import TradeVerifier

# ---------------------------------------------------------------------------
# Import TARGETS from the CLI entry point
# ---------------------------------------------------------------------------

from inspector.run_inspection import TARGETS, _load_env

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Inspector Gadget",
    description="Independent Trading Verification System",
    version="1.0.0",
)

DB_PATH = Path("~/.openclaw/inspector_gadget.db").expanduser()
REPORTS_DIR = Path("~/openclaw/security/inspector/reports").expanduser()
UI_DIR = Path(__file__).parent / "ui"

# ---------------------------------------------------------------------------
# Module-level run tracker
# ---------------------------------------------------------------------------

_run_status: Dict[str, Any] = {
    "running": False,
    "run_type": None,
    "started_at": None,
    "finished_at": None,
    "progress": None,
    "error": None,
    "target": None,
}


def _get_db() -> InspectorDB:
    """Create and initialise an InspectorDB instance."""
    db = InspectorDB()
    db.init()
    return db


def _get_clients(target_key: str = "openclaw"):
    """Return (PolymarketClient, Optional[KalshiClient]) for a target."""
    target = TARGETS.get(target_key, TARGETS["openclaw"])
    env_path = Path(target["env_path"]).expanduser()
    target_env = _load_env(env_path)

    poly = PolymarketClient()

    kalshi_key = target_env.get("KALSHI_API_KEY_ID") or os.environ.get("KALSHI_API_KEY_ID", "")
    kalshi_pk = target_env.get("KALSHI_PRIVATE_KEY_PATH") or os.environ.get("KALSHI_PRIVATE_KEY_PATH", "")
    kalshi_env = target_env.get("KALSHI_API_ENV") or os.environ.get("KALSHI_API_ENV", "demo")

    kalshi: Optional[KalshiClient] = None
    if kalshi_key and kalshi_pk:
        kalshi = KalshiClient(api_key_id=kalshi_key, private_key_path=kalshi_pk, api_env=kalshi_env)

    return poly, kalshi


# ---------------------------------------------------------------------------
# Background task runners
# ---------------------------------------------------------------------------

def _run_full_inspection(target_key: str) -> None:
    """Run the full inspection pipeline (mirrors run_inspection.py --full)."""
    global _run_status
    _run_status.update({
        "running": True,
        "run_type": "full",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "progress": "Initialising...",
        "error": None,
        "target": target_key,
    })

    try:
        target = TARGETS.get(target_key, TARGETS["openclaw"])
        db = _get_db()
        poly, kalshi = _get_clients(target_key)

        target_db = target["db"]
        chat_id = target["chat_id"]
        signals_path = target["signals"]

        # Trade verification
        _run_status["progress"] = "Verifying trades..."
        tv = TradeVerifier(db=db, poly=poly, kalshi=kalshi)
        tv.run(target_db)

        # Resolution audits
        _run_status["progress"] = "Auditing resolutions..."
        ra = ResolutionAuditor(db=db, poly=poly, kalshi=kalshi)
        ra.run(target_db)

        # Stats audit
        _run_status["progress"] = "Running statistical audit..."
        sa = StatsAuditor()
        stats_result = sa.run(target_db, chat_id=chat_id)

        # Persist stats red flags to code_findings
        for flag in stats_result.get("red_flags", []):
            db.insert("code_findings", {
                "file_path": "stats_audit",
                "line_number": None,
                "finding_type": "stats_{}".format(flag.get("check", "unknown")),
                "severity": flag.get("severity", "medium"),
                "description": flag.get("message", ""),
                "snippet": None,
                "found_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            })

        # Hallucination detection
        _run_status["progress"] = "Detecting hallucinations..."
        hd = HallucinationDetector(db=db, poly=poly, kalshi=kalshi)
        if signals_path:
            hd.run_on_signals(signals_path)
        hd.run_on_llm_trades(target_db)

        # Code analysis
        _run_status["progress"] = "Analysing source code..."
        la = LogicAnalyzer(db=db, target_files=target["source_files"])
        la.run()

        # Repo scan
        _run_status["progress"] = "Scanning git history..."
        rs = RepoScanner(db=db, repo_root=target["repo"])
        rs.run()

        # Generate report
        _run_status["progress"] = "Generating report..."
        dash = Dashboard(db=db)
        dash.generate()

        poly.close()
        if kalshi is not None:
            kalshi.close()

        _run_status.update({
            "running": False,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "progress": "Complete",
        })

    except Exception as exc:
        _run_status.update({
            "running": False,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "progress": "Failed",
            "error": str(exc),
        })


def _run_verify_trades(target_key: str) -> None:
    """Run trade verification + resolution + stats + hallucination checks."""
    global _run_status
    _run_status.update({
        "running": True,
        "run_type": "verify",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "progress": "Initialising...",
        "error": None,
        "target": target_key,
    })

    try:
        target = TARGETS.get(target_key, TARGETS["openclaw"])
        db = _get_db()
        poly, kalshi = _get_clients(target_key)

        target_db = target["db"]
        chat_id = target["chat_id"]
        signals_path = target["signals"]

        _run_status["progress"] = "Verifying trades..."
        tv = TradeVerifier(db=db, poly=poly, kalshi=kalshi)
        tv.run(target_db)

        _run_status["progress"] = "Auditing resolutions..."
        ra = ResolutionAuditor(db=db, poly=poly, kalshi=kalshi)
        ra.run(target_db)

        _run_status["progress"] = "Running statistical audit..."
        sa = StatsAuditor()
        stats_result = sa.run(target_db, chat_id=chat_id)

        for flag in stats_result.get("red_flags", []):
            db.insert("code_findings", {
                "file_path": "stats_audit",
                "line_number": None,
                "finding_type": "stats_{}".format(flag.get("check", "unknown")),
                "severity": flag.get("severity", "medium"),
                "description": flag.get("message", ""),
                "snippet": None,
                "found_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            })

        _run_status["progress"] = "Detecting hallucinations..."
        hd = HallucinationDetector(db=db, poly=poly, kalshi=kalshi)
        if signals_path:
            hd.run_on_signals(signals_path)
        hd.run_on_llm_trades(target_db)

        # Generate report
        _run_status["progress"] = "Generating report..."
        dash = Dashboard(db=db)
        dash.generate()

        poly.close()
        if kalshi is not None:
            kalshi.close()

        _run_status.update({
            "running": False,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "progress": "Complete",
        })

    except Exception as exc:
        _run_status.update({
            "running": False,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "progress": "Failed",
            "error": str(exc),
        })


def _run_scan_code(target_key: str) -> None:
    """Run code scan only (logic analyzer + repo scanner)."""
    global _run_status
    _run_status.update({
        "running": True,
        "run_type": "scan",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "progress": "Initialising...",
        "error": None,
        "target": target_key,
    })

    try:
        target = TARGETS.get(target_key, TARGETS["openclaw"])
        db = _get_db()

        _run_status["progress"] = "Analysing source code..."
        la = LogicAnalyzer(db=db, target_files=target["source_files"])
        la.run()

        _run_status["progress"] = "Scanning git history..."
        rs = RepoScanner(db=db, repo_root=target["repo"])
        rs.run()

        _run_status["progress"] = "Generating report..."
        dash = Dashboard(db=db)
        dash.generate()

        _run_status.update({
            "running": False,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "progress": "Complete",
        })

    except Exception as exc:
        _run_status.update({
            "running": False,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "progress": "Failed",
            "error": str(exc),
        })


# ---------------------------------------------------------------------------
# Routes -- UI
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
async def serve_ui():
    """Serve the self-contained HTML UI."""
    index_path = UI_DIR / "index.html"
    if not index_path.exists():
        return JSONResponse(
            status_code=404,
            content={"error": "UI not found. Expected at {}".format(index_path)},
        )
    return FileResponse(str(index_path), media_type="text/html")


# ---------------------------------------------------------------------------
# Routes -- API
# ---------------------------------------------------------------------------

@app.get("/api/status")
async def get_status():
    """Return system status: DB presence, last run, trade counts, run state."""
    db_exists = DB_PATH.exists()

    last_run: Optional[str] = None
    total_trades: int = 0
    trust_score: Optional[int] = None
    report_count: int = 0

    if db_exists:
        try:
            db = _get_db()
            reports = db.fetch_all("audit_reports")
            report_count = len(reports)
            if reports:
                last_report = reports[-1]
                last_run = last_report.get("generated_at")
                total_trades = last_report.get("total_trades_checked", 0) or 0
                scores = json.loads(last_report.get("trust_scores_json", "{}"))
                trust_score = scores.get("overall")
        except Exception:
            pass

    return {
        "db_exists": db_exists,
        "db_path": str(DB_PATH),
        "last_run": last_run,
        "total_trades": total_trades,
        "trust_score": trust_score,
        "report_count": report_count,
        "run_status": dict(_run_status),
    }


@app.post("/api/inspect/full")
async def inspect_full(
    background_tasks: BackgroundTasks,
    target: str = Query(default="openclaw"),
):
    """Trigger a full inspection run as a background task."""
    if _run_status["running"]:
        return JSONResponse(
            status_code=409,
            content={"error": "An inspection is already running", "run_status": dict(_run_status)},
        )
    if target not in TARGETS:
        return JSONResponse(
            status_code=400,
            content={"error": "Unknown target: {}. Available: {}".format(target, list(TARGETS.keys()))},
        )
    background_tasks.add_task(_run_full_inspection, target)
    return {"message": "Full inspection started", "target": target}


@app.post("/api/inspect/verify")
async def inspect_verify(
    background_tasks: BackgroundTasks,
    target: str = Query(default="openclaw"),
):
    """Trigger trade verification only as a background task."""
    if _run_status["running"]:
        return JSONResponse(
            status_code=409,
            content={"error": "An inspection is already running", "run_status": dict(_run_status)},
        )
    if target not in TARGETS:
        return JSONResponse(
            status_code=400,
            content={"error": "Unknown target: {}".format(target)},
        )
    background_tasks.add_task(_run_verify_trades, target)
    return {"message": "Trade verification started", "target": target}


@app.post("/api/inspect/scan")
async def inspect_scan(
    background_tasks: BackgroundTasks,
    target: str = Query(default="openclaw"),
):
    """Trigger code scan only as a background task."""
    if _run_status["running"]:
        return JSONResponse(
            status_code=409,
            content={"error": "An inspection is already running", "run_status": dict(_run_status)},
        )
    if target not in TARGETS:
        return JSONResponse(
            status_code=400,
            content={"error": "Unknown target: {}".format(target)},
        )
    background_tasks.add_task(_run_scan_code, target)
    return {"message": "Code scan started", "target": target}


@app.get("/api/report/latest")
async def get_latest_report():
    """Return the latest audit report as JSON with the markdown body."""
    if not DB_PATH.exists():
        return JSONResponse(status_code=404, content={"error": "No database found"})

    try:
        db = _get_db()
        reports = db.fetch_all("audit_reports")
        if not reports:
            return JSONResponse(status_code=404, content={"error": "No reports generated yet"})

        last = reports[-1]
        report_path = last.get("report_path", "")

        # Read the markdown body if the file exists
        markdown_body: Optional[str] = None
        if report_path:
            rp = Path(report_path)
            if rp.exists():
                markdown_body = rp.read_text(encoding="utf-8")

        return {
            "report_id": last.get("report_id"),
            "generated_at": last.get("generated_at"),
            "summary": last.get("summary"),
            "total_trades_checked": last.get("total_trades_checked"),
            "verified_count": last.get("verified_count"),
            "discrepancy_count": last.get("discrepancy_count"),
            "impossible_count": last.get("impossible_count"),
            "unverifiable_count": last.get("unverifiable_count"),
            "trust_scores": json.loads(last.get("trust_scores_json", "{}")),
            "red_flags": json.loads(last.get("red_flags_json", "[]")),
            "report_path": report_path,
            "markdown_body": markdown_body,
        }

    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.get("/api/findings")
async def get_findings(
    type: Optional[str] = Query(default=None, alias="type"),
    severity: Optional[str] = Query(default=None),
):
    """Return code findings with optional type and severity filters."""
    if not DB_PATH.exists():
        return {"findings": [], "total": 0}

    try:
        db = _get_db()
        clauses: List[str] = []
        params: List[str] = []

        if type is not None:
            clauses.append("finding_type = ?")
            params.append(type)
        if severity is not None:
            clauses.append("severity = ?")
            params.append(severity)

        where = " AND ".join(clauses)
        findings = db.fetch_all("code_findings", where=where, params=tuple(params))

        # Compute severity summary
        severity_counts: Dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for f in findings:
            sev = (f.get("severity") or "low").lower()
            if sev in severity_counts:
                severity_counts[sev] += 1

        return {
            "findings": findings,
            "total": len(findings),
            "severity_counts": severity_counts,
        }

    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.get("/api/trust-score")
async def get_trust_score():
    """Return current trust score and red flags from the latest report."""
    if not DB_PATH.exists():
        return {"trust_score": None, "red_flags": [], "message": "No database found"}

    try:
        db = _get_db()
        reports = db.fetch_all("audit_reports")
        if not reports:
            return {"trust_score": None, "red_flags": [], "message": "No reports generated"}

        last = reports[-1]
        scores = json.loads(last.get("trust_scores_json", "{}"))
        red_flags = json.loads(last.get("red_flags_json", "[]"))

        return {
            "trust_score": scores.get("overall"),
            "trust_scores": scores,
            "red_flags": red_flags,
            "report_id": last.get("report_id"),
            "generated_at": last.get("generated_at"),
        }

    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.get("/api/trades")
async def get_trades():
    """Return verified trades with status counts."""
    if not DB_PATH.exists():
        return {"trades": [], "total": 0, "counts": {}}

    try:
        db = _get_db()
        trades = db.fetch_all("verified_trades")

        counts: Dict[str, int] = {
            "VERIFIED": 0,
            "DISCREPANCY": 0,
            "IMPOSSIBLE": 0,
            "UNVERIFIABLE": 0,
        }
        for t in trades:
            status = t.get("status", "")
            if status in counts:
                counts[status] += 1

        # Resolution audit summary
        resolution_audits = db.fetch_all("resolution_audits")
        resolution_summary = {
            "matched": sum(1 for r in resolution_audits if r.get("match") == 1),
            "mismatched": sum(1 for r in resolution_audits if r.get("match") == 0),
            "unverifiable": sum(1 for r in resolution_audits if r.get("match") == -1),
            "total": len(resolution_audits),
        }

        # Hallucination summary
        hallucination_checks = db.fetch_all("hallucination_checks")
        hallucination_summary: Dict[str, int] = {}
        for h in hallucination_checks:
            result = h.get("verification_result", "UNKNOWN")
            hallucination_summary[result] = hallucination_summary.get(result, 0) + 1

        return {
            "trades": trades,
            "total": len(trades),
            "counts": counts,
            "resolution_summary": resolution_summary,
            "hallucination_summary": hallucination_summary,
        }

    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.get("/api/targets")
async def get_targets():
    """Return available inspection targets."""
    result = {}
    for key, config in TARGETS.items():
        result[key] = {
            "label": config.get("label", key),
            "db": config.get("db", ""),
            "repo": config.get("repo", ""),
            "db_exists": Path(config.get("db", "")).expanduser().exists(),
        }
    return {"targets": result}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7771)
