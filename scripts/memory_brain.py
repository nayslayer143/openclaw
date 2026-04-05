#!/usr/bin/env python3
"""
Memory Brain Pipeline — Cross-claw pattern extraction via TurboQuant.

Runs hourly. Collects recent activity from RivalClaw, QuantumentalClaw,
and CodeMonkeyClaw, sends to TurboQuant (long-context, KV-compressed)
for pattern extraction, then distributes insights back to each claw.

Flow:
  1. COLLECT  — query SQLite DBs for recent trades, decisions, metrics
  2. DIGEST   — send to TurboQuant with extraction prompt
  3. DISTRIBUTE — write structured insights to each claw's memory

Usage:
  python3 ~/openclaw/scripts/memory_brain.py              # full run
  python3 ~/openclaw/scripts/memory_brain.py --collect     # collect only (debug)
  python3 ~/openclaw/scripts/memory_brain.py --dry-run     # collect + show prompt
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sqlite3
import sys
import requests
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────

HOME = Path.home()
RIVALCLAW_DB       = HOME / "rivalclaw" / "rivalclaw.db"
QUANTCLAW_DB       = HOME / "quantumentalclaw" / "quantumentalclaw.db"
CODEMONKEY_DB      = HOME / "codemonkeyclaw" / "codemonkeyclaw.db"

# Output paths
RIVALCLAW_MEMORY   = HOME / "rivalclaw" / "strategy_lab" / "memory.json"
QUANTCLAW_INSIGHTS = HOME / "quantumentalclaw" / "learning" / "insights.json"
BRAIN_LOG          = HOME / "openclaw" / "memory" / "brain-log.md"

# ── Config ───────────────────────────────────────────────────────────────────

TURBOQUANT_BASE = os.environ.get("TURBOQUANT_BASE_URL", "http://localhost:8090")
OLLAMA_BASE     = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
LOOKBACK_HOURS  = int(os.environ.get("BRAIN_LOOKBACK_HOURS", "24"))
MAX_TRADES      = int(os.environ.get("BRAIN_MAX_TRADES", "20"))
MAX_DECISIONS   = int(os.environ.get("BRAIN_MAX_DECISIONS", "20"))


def _ts_cutoff() -> str:
    """ISO timestamp for lookback window."""
    dt = datetime.datetime.utcnow() - datetime.timedelta(hours=LOOKBACK_HOURS)
    return dt.isoformat()


# ── COLLECT ──────────────────────────────────────────────────────────────────

def _query(db_path: Path, sql: str, params: tuple = ()) -> list[dict]:
    """Run SQL, return list of dicts. Returns [] if DB missing."""
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"[brain] DB error {db_path.name}: {e}")
        return []


def collect_rivalclaw(cutoff: str) -> dict:
    """Collect recent RivalClaw activity."""
    trades = _query(RIVALCLAW_DB, """
        SELECT market_id, question, direction, strategy, confidence,
               entry_price, exit_price, pnl, reasoning, venue,
               expected_edge, binary_outcome, signal_to_trade_latency_ms,
               opened_at
        FROM paper_trades
        WHERE opened_at >= ?
        ORDER BY opened_at DESC
        LIMIT ?
    """, (cutoff, MAX_TRADES))

    cycle_stats = _query(RIVALCLAW_DB, """
        SELECT COUNT(*) as cycles,
               AVG(opportunities_detected) as avg_opps,
               AVG(trades_executed) as avg_trades,
               AVG(total_cycle_ms) as avg_cycle_ms,
               MIN(total_cycle_ms) as min_cycle_ms,
               MAX(total_cycle_ms) as max_cycle_ms
        FROM cycle_metrics
        WHERE cycle_started_at >= ?
    """, (cutoff,))

    daily_pnl = _query(RIVALCLAW_DB, """
        SELECT date, balance, realized_pnl, total_trades, win_rate, roi_pct
        FROM daily_pnl
        ORDER BY date DESC
        LIMIT 7
    """)

    # Strategy performance
    strategy_stats = _query(RIVALCLAW_DB, """
        SELECT strategy,
               COUNT(*) as trades,
               SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
               SUM(pnl) as total_pnl,
               AVG(confidence) as avg_confidence,
               AVG(pnl) as avg_pnl
        FROM paper_trades
        WHERE opened_at >= ?
        GROUP BY strategy
    """, (cutoff,))

    # Load strategy registry
    registry = {}
    reg_path = HOME / "rivalclaw" / "strategy_registry.json"
    if reg_path.exists():
        try:
            registry = json.loads(reg_path.read_text())
        except Exception:
            pass

    return {
        "trades": trades,
        "cycle_stats": cycle_stats[0] if cycle_stats else {},
        "daily_pnl": daily_pnl,
        "strategy_performance": strategy_stats,
        "strategy_registry": registry,
    }


def collect_quantclaw(cutoff: str) -> dict:
    """Collect recent QuantumentalClaw activity."""
    decisions = _query(QUANTCLAW_DB, """
        SELECT venue, direction, final_score, confidence,
               signal_snapshot, reasoning, time_horizon,
               decided_at
        FROM trade_decisions
        WHERE decided_at >= ?
        ORDER BY decided_at DESC
        LIMIT ?
    """, (cutoff, MAX_DECISIONS))

    # Parse signal_snapshot JSON
    for d in decisions:
        if d.get("signal_snapshot"):
            try:
                d["signal_snapshot"] = json.loads(d["signal_snapshot"])
            except Exception:
                pass

    weight_history = _query(QUANTCLAW_DB, """
        SELECT weight_asymmetry, weight_narrative, weight_event,
               weight_edgar, weight_quant, trigger_reason, logged_at
        FROM weight_log
        ORDER BY logged_at DESC
        LIMIT 20
    """)

    module_accuracy = _query(QUANTCLAW_DB, """
        SELECT module, total_signals, correct_signals, accuracy,
               avg_score, metadata, computed_at
        FROM module_accuracy
        ORDER BY computed_at DESC
        LIMIT 30
    """)

    context = _query(QUANTCLAW_DB, """
        SELECT key, value FROM context
    """)
    ctx = {r["key"]: r["value"] for r in context}

    return {
        "decisions": decisions,
        "weight_history": weight_history,
        "module_accuracy": module_accuracy,
        "context": ctx,
    }


def collect_codemonkey() -> dict:
    """Collect recent CodeMonkeyClaw work orders."""
    orders = _query(CODEMONKEY_DB, """
        SELECT id, source_instance, type, target_repo, description,
               status, model_tier, attempts, tokens_used, cost_usd,
               duration_seconds, created_at
        FROM work_orders
        ORDER BY created_at DESC
        LIMIT 10
    """)

    outputs = _query(CODEMONKEY_DB, """
        SELECT work_order_id, branch, files_changed,
               tests_added, tests_passing
        FROM output_contracts
        ORDER BY delivered_at DESC
        LIMIT 10
    """)

    return {"work_orders": orders, "output_contracts": outputs}


def collect_all() -> dict:
    """Collect from all claws."""
    cutoff = _ts_cutoff()
    print(f"[brain] Collecting data since {cutoff}")

    data = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "lookback_hours": LOOKBACK_HOURS,
        "rivalclaw": collect_rivalclaw(cutoff),
        "quantumentalclaw": collect_quantclaw(cutoff),
        "codemonkeyclaw": collect_codemonkey(),
    }

    # Stats
    n_trades = len(data["rivalclaw"]["trades"])
    n_decisions = len(data["quantumentalclaw"]["decisions"])
    n_orders = len(data["codemonkeyclaw"]["work_orders"])
    print(f"[brain] Collected: {n_trades} trades, {n_decisions} decisions, {n_orders} work orders")

    return data


# ── DIGEST ───────────────────────────────────────────────────────────────────

DIGEST_PROMPT = """\
You are the Memory Brain — a meta-learning system for a trading bot ecosystem.

You receive structured data from three autonomous systems:
1. RivalClaw — prediction market arbitrage (Polymarket, Kalshi)
2. QuantumentalClaw — signal fusion across equities + prediction markets
3. CodeMonkeyClaw — engineering task dispatch

Your job: extract ACTIONABLE patterns, NOT summaries. Focus on:

## For RivalClaw:
- Which strategies are working/degrading and WHY (not just win rates)
- Regime detection: is the market fast/slow, trending/mean-reverting?
- Latency patterns: are slower cycles correlated with losses?
- Confidence calibration: are high-confidence trades actually winning more?
- Cross-venue patterns: Kalshi vs Polymarket performance differences

## For QuantumentalClaw:
- Module weight convergence: are weights stabilizing or oscillating?
- False positive patterns: which modules generate noise vs signal?
- Time horizon analysis: sprint vs day vs week accuracy differences
- Signal correlation: are modules agreeing or diverging?

## Cross-System:
- Do RivalClaw and QuantumentalClaw see the same regime?
- Engineering bottlenecks affecting trading performance?

## Output Format:
Return valid JSON with this structure:
{
  "lessons": [
    {
      "id": "lesson-YYYYMMDD-N",
      "source": "rivalclaw|quantclaw|cross-system",
      "category": "strategy|regime|calibration|latency|module|engineering",
      "insight": "One-sentence actionable finding",
      "evidence": "Specific data points supporting this",
      "action": "Concrete next step",
      "confidence": 0.0-1.0,
      "expires": "YYYY-MM-DD or null"
    }
  ],
  "regime": {
    "market_state": "calm|volatile|trending|unclear",
    "confidence": 0.0-1.0,
    "evidence": "brief"
  },
  "alerts": [
    "Any urgent issues requiring immediate attention"
  ]
}

Return ONLY valid JSON. No markdown, no commentary."""


def _trim_for_context(data: dict) -> dict:
    """Trim data to fit within context window. Remove verbose fields."""
    trimmed = json.loads(json.dumps(data, default=str))

    # Aggressively trim trades — keep only decision-relevant fields
    for t in trimmed.get("rivalclaw", {}).get("trades", []):
        if t.get("reasoning") and len(t["reasoning"]) > 100:
            t["reasoning"] = t["reasoning"][:100] + "..."
        # Drop verbose fields
        for k in ("market_id", "question", "binary_outcome",
                  "signal_to_trade_latency_ms", "expected_edge"):
            t.pop(k, None)

    # Aggressively trim decisions
    for d in trimmed.get("quantumentalclaw", {}).get("decisions", []):
        # Drop reasoning entirely — signal_snapshot has the data
        d.pop("reasoning", None)
        # Flatten signal_snapshot to just module scores
        ss = d.get("signal_snapshot")
        if isinstance(ss, dict):
            d["signal_snapshot"] = {k: round(v, 3) if isinstance(v, float) else v
                                    for k, v in ss.items()
                                    if k.endswith("_score") or k == "final"}
        elif isinstance(ss, str):
            try:
                parsed = json.loads(ss)
                d["signal_snapshot"] = {k: round(v, 3) if isinstance(v, float) else v
                                        for k, v in parsed.items()
                                        if k.endswith("_score") or k == "final"}
            except Exception:
                d["signal_snapshot"] = "parse_error"

    # Drop module accuracy metadata field (JSON blob)
    for m in trimmed.get("quantumentalclaw", {}).get("module_accuracy", []):
        m.pop("metadata", None)

    # Trim strategy registry to just id + status
    reg = trimmed.get("rivalclaw", {}).get("strategy_registry", {})
    if isinstance(reg, dict) and "strategies" in reg:
        trimmed["rivalclaw"]["strategy_registry"] = [
            {"id": s["id"], "status": s["status"]}
            for s in reg.get("strategies", [])
        ]

    return trimmed


def digest(data: dict) -> dict | None:
    """Send collected data to TurboQuant for pattern extraction."""
    # Trim data to fit context
    trimmed = _trim_for_context(data)
    payload = json.dumps(trimmed, indent=1, default=str)

    # Use Ollama for digest (faster prefill than TurboQuant fork).
    # TurboQuant is for live long-context conversations, not batch jobs.
    endpoint = f"{OLLAMA_BASE}/v1/chat/completions"
    model = "gemma4:31b"

    print(f"[brain] Sending {len(payload)} chars to {model}")

    try:
        resp = requests.post(
            endpoint,
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": DIGEST_PROMPT},
                    {"role": "user", "content": f"Here is the last {LOOKBACK_HOURS}h of data:\n\n{payload}"},
                ],
                "max_tokens": 2048,
                "temperature": 0.2,
            },
            timeout=600,
        )
        if resp.status_code != 200:
            print(f"[brain] LLM error: {resp.status_code}")
            return None

        result = resp.json()
        msg = result.get("choices", [{}])[0].get("message", {})
        content = msg.get("content", "") or msg.get("reasoning_content", "")

        # Parse JSON from response
        # Strip markdown fencing if present
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

        return json.loads(content)

    except json.JSONDecodeError as e:
        print(f"[brain] Failed to parse LLM response as JSON: {e}")
        print(f"[brain] Raw content: {content[:500]}")
        return None
    except Exception as e:
        print(f"[brain] Digest failed: {e}")
        return None


# ── DISTRIBUTE ───────────────────────────────────────────────────────────────

def distribute(insights: dict):
    """Write insights back to each claw's memory."""
    lessons = insights.get("lessons", [])
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M")

    # 1. RivalClaw strategy_lab/memory.json — append lessons
    rival_lessons = [l for l in lessons if l.get("source") in ("rivalclaw", "cross-system")]
    if rival_lessons:
        existing = {"lessons": []}
        if RIVALCLAW_MEMORY.exists():
            try:
                existing = json.loads(RIVALCLAW_MEMORY.read_text())
            except Exception:
                pass
        existing["lessons"].extend(rival_lessons)
        # Keep last 100 lessons
        existing["lessons"] = existing["lessons"][-100:]
        RIVALCLAW_MEMORY.write_text(json.dumps(existing, indent=2))
        print(f"[brain] Wrote {len(rival_lessons)} lessons to RivalClaw memory")

    # 2. QuantumentalClaw learning/insights.json — append lessons
    quant_lessons = [l for l in lessons if l.get("source") in ("quantclaw", "cross-system")]
    if quant_lessons:
        existing = {"lessons": []}
        if QUANTCLAW_INSIGHTS.exists():
            try:
                existing = json.loads(QUANTCLAW_INSIGHTS.read_text())
            except Exception:
                pass
        existing["lessons"].extend(quant_lessons)
        existing["lessons"] = existing["lessons"][-100:]
        QUANTCLAW_INSIGHTS.parent.mkdir(parents=True, exist_ok=True)
        QUANTCLAW_INSIGHTS.write_text(json.dumps(existing, indent=2))
        print(f"[brain] Wrote {len(quant_lessons)} lessons to QuantumentalClaw insights")

    # 3. Brain log — append summary to markdown
    regime = insights.get("regime", {})
    alerts = insights.get("alerts", [])

    entry = f"\n## {ts}\n\n"
    entry += f"**Regime:** {regime.get('market_state', 'unknown')} "
    entry += f"(confidence: {regime.get('confidence', 0):.0%})\n\n"

    if alerts:
        entry += "**Alerts:**\n"
        for a in alerts:
            entry += f"- {a}\n"
        entry += "\n"

    entry += f"**Lessons extracted:** {len(lessons)}\n"
    for l in lessons[:5]:  # Top 5 in log
        entry += f"- [{l.get('source','?')}] {l.get('insight','')}\n"
    if len(lessons) > 5:
        entry += f"- ... and {len(lessons)-5} more\n"
    entry += "\n---\n"

    BRAIN_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(BRAIN_LOG, "a") as f:
        f.write(entry)
    print(f"[brain] Appended to brain-log.md")


# ── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Memory Brain Pipeline")
    parser.add_argument("--collect", action="store_true", help="Collect only (debug)")
    parser.add_argument("--dry-run", action="store_true", help="Collect + show prompt")
    args = parser.parse_args()

    print(f"[brain] Memory Brain starting at {datetime.datetime.utcnow().isoformat()}")

    # 1. COLLECT
    data = collect_all()

    if args.collect:
        print(json.dumps(data, indent=2, default=str)[:3000])
        return

    if args.dry_run:
        payload = json.dumps(data, indent=1, default=str)
        print(f"\n=== PROMPT ({len(payload)} chars) ===")
        print(DIGEST_PROMPT[:500])
        print(f"\n=== DATA PREVIEW ===")
        print(payload[:2000])
        return

    # 2. DIGEST
    insights = digest(data)
    if not insights:
        print("[brain] No insights extracted. Exiting.")
        return

    print(f"[brain] Extracted {len(insights.get('lessons', []))} lessons, "
          f"regime: {insights.get('regime', {}).get('market_state', 'unknown')}, "
          f"alerts: {len(insights.get('alerts', []))}")

    # 3. DISTRIBUTE
    distribute(insights)

    print("[brain] Pipeline complete.")


if __name__ == "__main__":
    main()
