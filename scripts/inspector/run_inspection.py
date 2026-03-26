#!/usr/bin/env python3
"""
Inspector Gadget — CLI entry point (Task 10).

Orchestrates all inspector modules and sends Telegram notifications.

Usage:
  python run_inspection.py --full           # run all checks
  python run_inspection.py --verify-trades  # trade + resolution + stats + hallucination only
  python run_inspection.py --scan-code      # logic analyzer + repo scanner only
  python run_inspection.py --report         # generate report from existing data (no API calls)
"""

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Ensure the parent of 'inspector/' is on sys.path so the package is importable.
sys.path.insert(0, str(Path(__file__).parent.parent))

from inspector.dashboard import Dashboard
from inspector.hallucination_detector import HallucinationDetector
from inspector.inspector_db import InspectorDB
from inspector.logic_analyzer import LogicAnalyzer
from inspector.polymarket_client import PolymarketClient
from inspector.repo_scanner import RepoScanner
from inspector.resolution_auditor import ResolutionAuditor
from inspector.stats_auditor import StatsAuditor
from inspector.verifier import TradeVerifier

# ---------------------------------------------------------------------------
# Key paths
# ---------------------------------------------------------------------------

CLAWMSON_DB  = "~/.openclaw/clawmson.db"
SIGNALS_JSON = "~/openclaw/trading/signals.json"
ENV_PATH     = Path("~/.openclaw/.env").expanduser()


# ---------------------------------------------------------------------------
# Env / Telegram helpers
# ---------------------------------------------------------------------------

def _load_env() -> dict:
    """Read ~/.openclaw/.env, parse KEY=VALUE lines (skip # lines), return dict."""
    env: dict = {}
    if not ENV_PATH.exists():
        return env
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def notify_telegram(msg: str) -> None:
    env = _load_env()
    token   = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_ALLOWED_USERS", "").strip().strip('"[]').split(",")[0].strip()
    if not token or not chat_id:
        print("[Telegram] No credentials — skipping")
        return
    try:
        data = json.dumps({"chat_id": chat_id, "text": msg[:4000]}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
        print("[Telegram] Sent.")
    except Exception as e:
        print(f"[Telegram] Failed: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Inspector Gadget — trading audit system")
    parser.add_argument("--full",          action="store_true", help="Run all checks")
    parser.add_argument("--verify-trades", dest="verify_trades", action="store_true",
                        help="Trade + resolution + stats + hallucination checks only")
    parser.add_argument("--scan-code",     dest="scan_code",    action="store_true",
                        help="Logic analyzer + repo scanner only")
    parser.add_argument("--report",        action="store_true",
                        help="Generate report from existing data (no API calls)")
    args = parser.parse_args()

    if not any(vars(args).values()):
        parser.print_help()
        return

    db   = InspectorDB(); db.init()
    poly = PolymarketClient()
    results: dict = {}
    start = datetime.now(timezone.utc)

    if args.full or args.verify_trades:
        print("🔍 Verifying trades...")
        tv = TradeVerifier(db=db, poly=poly)
        results["verify"] = tv.run(CLAWMSON_DB)
        print(f"   → {results['verify']}")

        print("📋 Auditing resolutions...")
        ra = ResolutionAuditor(db=db, poly=poly)
        results["resolution"] = ra.run(CLAWMSON_DB)
        print(f"   → {results['resolution']}")

        print("📊 Statistical audit...")
        sa = StatsAuditor()
        results["stats"] = sa.run(CLAWMSON_DB)
        print(f"   → trust={results['stats'].get('trust_score', '?')}, "
              f"flags={len(results['stats'].get('red_flags', []))}")

        # Persist stats red flags to code_findings so they appear in the report
        for flag in results["stats"].get("red_flags", []):
            db.insert("code_findings", {
                "file_path": "stats_audit",
                "line_number": None,
                "finding_type": f"stats_{flag.get('check', 'unknown')}",
                "severity": flag.get("severity", "medium"),
                "description": flag.get("message", ""),
                "snippet": None,
                "found_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            })

        print("🧠 Hallucination detection...")
        hd = HallucinationDetector(db=db, poly=poly)
        results["hallucination"]        = hd.run_on_signals(SIGNALS_JSON)
        results["hallucination_trades"] = hd.run_on_llm_trades(CLAWMSON_DB)
        print(f"   → {results['hallucination']}")

    if args.full or args.scan_code:
        print("🔬 Analyzing source code...")
        la = LogicAnalyzer(db=db)
        results["code"] = la.run()
        print(f"   → {results['code']}")

        print("📜 Scanning git history...")
        rs = RepoScanner(db=db)
        results["repo"] = rs.run()
        print(f"   → {results['repo']}")

    print("📄 Generating report...")
    dash = Dashboard(db=db)
    report_path = dash.generate()
    print(f"   → {report_path}")

    elapsed = (datetime.now(timezone.utc) - start).seconds
    last_reports = db.fetch_all("audit_reports")
    last = last_reports[-1] if last_reports else {}
    trust = json.loads(last.get("trust_scores_json", "{}")).get("overall", "?")
    impossible   = last.get("impossible_count",   0) or 0
    discrepancy  = last.get("discrepancy_count",  0) or 0

    # Check for HALLUCINATED findings to trigger alert
    hallucinated = sum(
        1 for h in db.fetch_all("hallucination_checks")
        if h.get("verification_result") == "HALLUCINATED"
    )

    # Check for CRITICAL code findings (includes stats red flags persisted above)
    critical_findings = sum(1 for f in db.fetch_all("code_findings")
                            if f.get("severity") == "critical")

    summary = (
        f"🔍 Inspector Gadget Report ({datetime.now(timezone.utc).strftime('%Y-%m-%d')})\n"
        f"Trust Score: {trust}/100\n"
        f"Trades checked: {last.get('total_trades_checked', '?')}\n"
        f"✅ Verified: {last.get('verified_count', '?')}\n"
        f"⚠️ Discrepancies: {discrepancy}\n"
        f"🚨 Impossible: {impossible}\n"
        f"Code findings: {results.get('code', {}).get('total_findings', 'N/A')}\n"
        f"Report: {report_path}\n"
        f"Elapsed: {elapsed}s"
    )
    print("\n" + summary)

    alert_needed = (impossible > 0) or (discrepancy > 5) or (hallucinated > 0) or (critical_findings > 0)
    if alert_needed:
        reasons = []
        if impossible > 0: reasons.append(f"🚨 {impossible} IMPOSSIBLE trade(s)")
        if discrepancy > 5: reasons.append(f"⚠️ {discrepancy} discrepancies")
        if hallucinated > 0: reasons.append(f"🧠 {hallucinated} HALLUCINATED claim(s)")
        if critical_findings > 0: reasons.append(f"🔴 {critical_findings} CRITICAL code finding(s)")
        notify_telegram(f"🚨 INSPECTOR GADGET ALERT\n{chr(10).join(reasons)}\n\n{summary}")
    else:
        notify_telegram(summary)


if __name__ == "__main__":
    main()
