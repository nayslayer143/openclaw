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
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Ensure the parent of 'inspector/' is on sys.path so the package is importable.
sys.path.insert(0, str(Path(__file__).parent.parent))

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
# Target configs
# ---------------------------------------------------------------------------

TARGETS = {
    "openclaw": {
        "db": "~/.openclaw/clawmson.db",
        "signals": "~/openclaw/trading/signals.json",
        "repo": "~/openclaw",
        "source_files": [
            "~/openclaw/scripts/mirofish/trading_brain.py",
            "~/openclaw/scripts/mirofish/paper_wallet.py",
            "~/openclaw/scripts/mirofish/polymarket_feed.py",
            "~/openclaw/scripts/trading-bot.py",
        ],
        "chat_id": "mirofish",
        "env_path": "~/.openclaw/.env",
        "label": "OpenClaw (Clawmpson)",
    },
    "rivalclaw": {
        "db": "~/rivalclaw/rivalclaw.db",
        "signals": None,
        "repo": "~/rivalclaw",
        "source_files": [
            "~/rivalclaw/trading_brain.py",
            "~/rivalclaw/paper_wallet.py",
            "~/rivalclaw/polymarket_feed.py",
            "~/rivalclaw/kalshi_feed.py",
        ],
        "chat_id": "rivalclaw",
        "env_path": "~/rivalclaw/.env",
        "label": "RivalClaw",
    },
}

ENV_PATH = Path("~/.openclaw/.env").expanduser()


# ---------------------------------------------------------------------------
# Env / Telegram helpers
# ---------------------------------------------------------------------------

def _load_env(env_override: Optional[Path] = None) -> dict:
    """Read .env, parse KEY=VALUE lines (skip # lines), return dict."""
    env: dict = {}
    path = env_override or ENV_PATH
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def notify_telegram(msg: str, env_override: Optional[Path] = None) -> None:
    env = _load_env(env_override)
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
    parser.add_argument("--target",        default="openclaw",
                        choices=list(TARGETS.keys()),
                        help="Target bot to audit (default: openclaw)")
    args = parser.parse_args()

    if not any(v for k, v in vars(args).items() if k != "target"):
        parser.print_help()
        return

    target = TARGETS[args.target]
    target_db = target["db"]
    signals_path = target["signals"]
    chat_id = target["chat_id"]
    env_path = Path(target["env_path"]).expanduser()
    label = target["label"]

    print(f"🎯 Target: {label}")
    print(f"   DB: {target_db}")

    db   = InspectorDB(); db.init()
    poly = PolymarketClient()

    # Initialize Kalshi client if credentials are available
    target_env = _load_env(env_path)
    kalshi_key = target_env.get("KALSHI_API_KEY_ID") or os.environ.get("KALSHI_API_KEY_ID", "")
    kalshi_pk  = target_env.get("KALSHI_PRIVATE_KEY_PATH") or os.environ.get("KALSHI_PRIVATE_KEY_PATH", "")
    kalshi_env = target_env.get("KALSHI_API_ENV") or os.environ.get("KALSHI_API_ENV", "demo")
    kalshi: Optional[KalshiClient] = None
    if kalshi_key and kalshi_pk:
        kalshi = KalshiClient(api_key_id=kalshi_key, private_key_path=kalshi_pk, api_env=kalshi_env)
        print(f"   Kalshi client: {kalshi_env}")
    else:
        print("   Kalshi client: not available (no credentials)")

    results: dict = {}
    start = datetime.now(timezone.utc)

    if args.full or args.verify_trades:
        print("🔍 Verifying trades...")
        tv = TradeVerifier(db=db, poly=poly, kalshi=kalshi)
        results["verify"] = tv.run(target_db)
        print(f"   → {results['verify']}")

        print("📋 Auditing resolutions...")
        ra = ResolutionAuditor(db=db, poly=poly, kalshi=kalshi)
        results["resolution"] = ra.run(target_db)
        print(f"   → {results['resolution']}")

        print("📊 Statistical audit...")
        sa = StatsAuditor()
        results["stats"] = sa.run(target_db, chat_id=chat_id)
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
        hd = HallucinationDetector(db=db, poly=poly, kalshi=kalshi)
        if signals_path:
            results["hallucination"] = hd.run_on_signals(signals_path)
        else:
            results["hallucination"] = {"checked": 0, "skipped": "no signals file for this target"}
        results["hallucination_trades"] = hd.run_on_llm_trades(target_db)
        print(f"   → {results['hallucination']}")

    if args.full or args.scan_code:
        print("🔬 Analyzing source code...")
        la = LogicAnalyzer(db=db, target_files=target["source_files"])
        results["code"] = la.run()
        print(f"   → {results['code']}")

        print("📜 Scanning git history...")
        rs = RepoScanner(db=db, repo_root=target["repo"])
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
        notify_telegram(f"🚨 INSPECTOR GADGET ALERT — {label}\n{chr(10).join(reasons)}\n\n{summary}", env_path)
    else:
        notify_telegram(summary, env_path)

    # Cleanup
    poly.close()
    if kalshi is not None:
        kalshi.close()


if __name__ == "__main__":
    main()
