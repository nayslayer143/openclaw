"""
Inspector Gadget — Dashboard / Report Generator (Task 9).

Reads all 5 inspector tables and generates a structured markdown audit report.
Saves to ~/openclaw/security/inspector/reports/ and inserts a summary row
into audit_reports.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from inspector.inspector_db import InspectorDB


class Dashboard:
    def __init__(self, db: InspectorDB):
        self.db = db
        self.reports_dir = Path("~/openclaw/security/inspector/reports").expanduser()
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Trust score
    # ------------------------------------------------------------------

    def _compute_trust(
        self,
        verified_trades: list,
        resolution_audits: list,
        code_findings: list,
        hallucination_checks: list,
    ) -> int:
        score = 100

        for t in verified_trades:
            if t.get("status") == "IMPOSSIBLE":
                score -= 10
            elif t.get("status") == "DISCREPANCY":
                score -= 5

        for r in resolution_audits:
            if r.get("match") == 0:
                score -= 8

        for c in code_findings:
            sev = (c.get("severity") or "").lower()
            if sev == "critical":
                score -= 15
            elif sev == "high":
                score -= 5

        for h in hallucination_checks:
            if h.get("verification_result") == "HALLUCINATED":
                score -= 10

        return max(0, score)

    # ------------------------------------------------------------------
    # Report builder
    # ------------------------------------------------------------------

    def _build_report(
        self,
        report_id: str,
        verified_trades: list,
        resolution_audits: list,
        code_findings: list,
        hallucination_checks: list,
        trust: int,
    ) -> str:
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # ---- Trade Verification counts ----
        statuses = ["VERIFIED", "DISCREPANCY", "IMPOSSIBLE", "UNVERIFIABLE"]
        tv_counts = {s: 0 for s in statuses}
        for t in verified_trades:
            s = t.get("status")
            if s in tv_counts:
                tv_counts[s] += 1
        tv_total = len(verified_trades)

        def pct(n: int, total: int) -> str:
            if total == 0:
                return "0%"
            return f"{n / total * 100:.0f}%"

        tv_rows = ""
        for s in statuses:
            n = tv_counts[s]
            tv_rows += f"| {s} | {n} | {pct(n, tv_total)} |\n"
        tv_rows += f"| **TOTAL** | **{tv_total}** | 100% |\n"

        # ---- Resolution Audit counts ----
        ra_matched = sum(1 for r in resolution_audits if r.get("match") == 1)
        ra_mismatched = sum(1 for r in resolution_audits if r.get("match") == 0)
        ra_unverifiable = sum(1 for r in resolution_audits if r.get("match") == -1)

        # ---- Code findings counts ----
        sev_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for c in code_findings:
            sev = (c.get("severity") or "low").lower()
            if sev in sev_counts:
                sev_counts[sev] += 1

        # Critical & High findings — top 10
        critical_high = [
            c for c in code_findings
            if (c.get("severity") or "").lower() in ("critical", "high")
        ]
        critical_high_sorted = sorted(
            critical_high,
            key=lambda c: ["low", "medium", "high", "critical"].index(
                (c.get("severity") or "low").lower()
            ),
            reverse=True,
        )[:10]

        ch_lines = ""
        for c in critical_high_sorted:
            sev = (c.get("severity") or "low").upper()
            fp = c.get("file_path") or "?"
            ln = c.get("line_number")
            loc = f"{fp}:{ln}" if ln else fp
            desc = c.get("description") or ""
            ch_lines += f"- **[{sev}]** `{loc}` — {desc}\n"
        if not ch_lines:
            ch_lines = "_No critical or high findings._\n"

        # ---- Hallucination counts ----
        h_grounded = sum(
            1 for h in hallucination_checks
            if h.get("verification_result") == "GROUNDED"
        )
        h_hallucinated = sum(
            1 for h in hallucination_checks
            if h.get("verification_result") == "HALLUCINATED"
        )
        h_unverifiable = sum(
            1 for h in hallucination_checks
            if h.get("verification_result") in ("UNVERIFIABLE", "PARTIALLY_GROUNDED")
        )

        # ---- Assemble markdown ----
        report = f"""\
# Inspector Gadget Audit Report
**Generated:** {now_iso}
**Overall Trust Score: {trust}/100**

---

## Trade Verification
| Status | Count | % |
|--------|-------|---|
{tv_rows}
## Resolution Audits
- \u2705 Matched: {ra_matched} ({pct(ra_matched, len(resolution_audits))})
- \u274c Mismatched: {ra_mismatched} ({pct(ra_mismatched, len(resolution_audits))})
- \u26a0\ufe0f Unverifiable: {ra_unverifiable} ({pct(ra_unverifiable, len(resolution_audits))})

## Code Analysis
- \U0001f534 Critical: {sev_counts['critical']}
- \U0001f7e0 High: {sev_counts['high']}
- \U0001f7e1 Medium: {sev_counts['medium']}
- \U0001f535 Low: {sev_counts['low']}

### Critical & High Findings (top 10)
{ch_lines}
## Hallucination Checks
- \u2705 Grounded: {h_grounded}
- \u274c Hallucinated: {h_hallucinated}
- \u26a0\ufe0f Unverifiable: {h_unverifiable}

---
*Report ID: {report_id} | Inspector Gadget v1.0*
"""
        return report

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def generate(self) -> str:
        """
        Read all inspector tables, build a markdown report, save it,
        insert a summary row into audit_reports, and return the file path.
        """
        now = datetime.now(timezone.utc)
        report_id = now.strftime("%Y%m%d-%H%M%S")
        filename = f"audit-{report_id}.md"
        report_path = self.reports_dir / filename

        # Load all 5 tables
        verified_trades     = self.db.fetch_all("verified_trades")
        resolution_audits   = self.db.fetch_all("resolution_audits")
        code_findings       = self.db.fetch_all("code_findings")
        hallucination_checks = self.db.fetch_all("hallucination_checks")

        trust = self._compute_trust(
            verified_trades,
            resolution_audits,
            code_findings,
            hallucination_checks,
        )

        report_text = self._build_report(
            report_id=report_id,
            verified_trades=verified_trades,
            resolution_audits=resolution_audits,
            code_findings=code_findings,
            hallucination_checks=hallucination_checks,
            trust=trust,
        )

        # Save to disk
        report_path.write_text(report_text, encoding="utf-8")

        # Build audit_reports row
        tv_total       = len(verified_trades)
        verified_count = sum(1 for t in verified_trades if t.get("status") == "VERIFIED")
        discrepancy_count = sum(1 for t in verified_trades if t.get("status") == "DISCREPANCY")
        impossible_count  = sum(1 for t in verified_trades if t.get("status") == "IMPOSSIBLE")
        unverifiable_count = sum(1 for t in verified_trades if t.get("status") == "UNVERIFIABLE")

        critical_findings: List[str] = [
            c.get("description", "")
            for c in code_findings
            if (c.get("severity") or "").lower() == "critical"
        ]

        summary = (
            f"Trust: {trust}/100 | "
            f"Trades: {tv_total} verified={verified_count} "
            f"discrepancy={discrepancy_count} impossible={impossible_count}"
        )

        self.db.insert("audit_reports", {
            "report_id":             report_id,
            "generated_at":          now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "summary":               summary,
            "total_trades_checked":  tv_total,
            "verified_count":        verified_count,
            "discrepancy_count":     discrepancy_count,
            "impossible_count":      impossible_count,
            "unverifiable_count":    unverifiable_count,
            "trust_scores_json":     json.dumps({"overall": trust}),
            "red_flags_json":        json.dumps(critical_findings),
            "report_path":           str(report_path),
        })

        return str(report_path)
