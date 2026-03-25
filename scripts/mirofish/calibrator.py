#!/usr/bin/env python3
"""
calibrator.py — automated strategy calibration for all trading bots.
Analyzes resolved trade outcomes and tunes bot parameters.

Modes:
  --fast    Every 30min: per-bot param tweaks from recent resolved trades
  --review  Every 6hr:   deeper bucket analysis, recalibrate price zones
  --meta    Daily:       cross-bot comparison, capital reallocation report
"""
import os, sys, sqlite3, json, argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict

DB_PATH = Path(os.environ.get("CLAWMSON_DB_PATH", Path.home() / ".openclaw" / "clawmson.db"))

# Guardrails: max adjustment per cycle, hard bounds per parameter
PARAM_BOUNDS = {
    "MIN_ENTRY":          {"min": 0.01, "max": 0.70, "max_delta": 0.05},
    "MAX_ENTRY":          {"min": 0.70, "max": 0.99, "max_delta": 0.03},
    "MIN_EDGE_SCORE":     {"min": 0.10, "max": 0.80, "max_delta": 0.05},
    "POSITION_PCT":       {"min": 0.01, "max": 0.10, "max_delta": 0.01},
    "MAX_TRADES_PER_RUN": {"min": 5,    "max": 100,  "max_delta": 10},
    "EDGE_THRESHOLD":     {"min": 0.02, "max": 0.25, "max_delta": 0.02},
    "VOLUME_SPIKE_MULT":  {"min": 1.0,  "max": 3.0,  "max_delta": 0.2},
    "BET_SIZE_USD":       {"min": 1.0,  "max": 20.0, "max_delta": 2.0},
}

# Which params each bot exposes for tuning
BOT_PARAMS = {
    "phantomclaw_fv": ["MIN_ENTRY", "MAX_TRADES_PER_RUN"],
    "calendarclaw":   ["MIN_ENTRY", "MAX_ENTRY", "MIN_EDGE_SCORE", "POSITION_PCT", "MAX_TRADES_PER_RUN"],
    "newsclaw":       ["MIN_ENTRY", "MAX_ENTRY", "MIN_EDGE_SCORE", "POSITION_PCT", "MAX_TRADES_PER_RUN"],
    "sentimentclaw":  ["MIN_ENTRY", "MAX_ENTRY", "VOLUME_SPIKE_MULT", "POSITION_PCT", "MAX_TRADES_PER_RUN"],
    "dataharvester":  ["EDGE_THRESHOLD", "BET_SIZE_USD", "MAX_TRADES_PER_RUN"],
}

# Current defaults (before any DB override)
DEFAULTS = {
    "phantomclaw_fv": {"MIN_ENTRY": 0.55, "MAX_TRADES_PER_RUN": 12},
    "calendarclaw":   {"MIN_ENTRY": 0.03, "MAX_ENTRY": 0.97, "MIN_EDGE_SCORE": 0.35, "POSITION_PCT": 0.03, "MAX_TRADES_PER_RUN": 30},
    "newsclaw":       {"MIN_ENTRY": 0.03, "MAX_ENTRY": 0.97, "MIN_EDGE_SCORE": 0.40, "POSITION_PCT": 0.03, "MAX_TRADES_PER_RUN": 20},
    "sentimentclaw":  {"MIN_ENTRY": 0.03, "MAX_ENTRY": 0.97, "VOLUME_SPIKE_MULT": 1.2, "POSITION_PCT": 0.03, "MAX_TRADES_PER_RUN": 25},
    "dataharvester":  {"EDGE_THRESHOLD": 0.08, "BET_SIZE_USD": 4.0, "MAX_TRADES_PER_RUN": 50},
}


def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    # Ensure calibration_log table exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS calibration_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot TEXT NOT NULL,
            param TEXT NOT NULL,
            old_value REAL,
            new_value REAL,
            reason TEXT,
            mode TEXT,
            win_rate REAL,
            sample_size INTEGER,
            logged_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    return conn


def get_current_param(conn, bot, param):
    """Get current param value from DB or default."""
    row = conn.execute(
        "SELECT value FROM context WHERE chat_id='calibrator' AND key=?",
        (f"{bot}_{param}",)
    ).fetchone()
    if row:
        return float(row["value"])
    return DEFAULTS.get(bot, {}).get(param, 0)


def set_param(conn, bot, param, value):
    """Write param to DB context table."""
    conn.execute(
        "INSERT OR REPLACE INTO context (chat_id, key, value) VALUES (?, ?, ?)",
        ("calibrator", f"{bot}_{param}", str(round(value, 6)))
    )


def clamp_adjustment(current, target, param):
    """Apply guardrails: max delta per cycle, hard min/max bounds."""
    bounds = PARAM_BOUNDS.get(param, {"min": 0, "max": 9999, "max_delta": 999})
    delta = target - current
    # Clamp delta
    max_d = bounds["max_delta"]
    delta = max(-max_d, min(max_d, delta))
    new_val = current + delta
    # Clamp to bounds
    new_val = max(bounds["min"], min(bounds["max"], new_val))
    return new_val


def analyze_bot(conn, bot, lookback_hours=12):
    """Analyze resolved trades for a bot. Returns stats dict."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).isoformat()

    # For phantomclaw, match on strategy LIKE 'phantomclaw%'
    if bot == "phantomclaw_fv":
        where = "strategy LIKE 'phantomclaw%'"
    else:
        where = f"strategy = '{bot}'"

    trades = conn.execute(f"""
        SELECT entry_price, direction, pnl, amount_usd, status, confidence, closed_at
        FROM paper_trades
        WHERE {where} AND status IN ('closed_win','closed_loss','expired')
        AND closed_at > ?
        ORDER BY closed_at DESC
    """, (cutoff,)).fetchall()

    if not trades:
        return None

    total = len(trades)
    wins = sum(1 for t in trades if t["status"] == "closed_win")
    losses = total - wins
    win_rate = wins / total if total > 0 else 0
    total_pnl = sum(t["pnl"] or 0 for t in trades)
    avg_win = sum(t["pnl"] for t in trades if t["status"] == "closed_win") / wins if wins else 0
    avg_loss = sum(t["pnl"] for t in trades if t["status"] != "closed_win") / losses if losses else 0

    # Entry price buckets
    buckets = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0})
    for t in trades:
        ep = t["entry_price"]
        if ep < 0.15:   b = "0.00-0.15"
        elif ep < 0.30: b = "0.15-0.30"
        elif ep < 0.50: b = "0.30-0.50"
        elif ep < 0.70: b = "0.50-0.70"
        elif ep < 0.85: b = "0.70-0.85"
        else:           b = "0.85-1.00"
        if t["status"] == "closed_win":
            buckets[b]["wins"] += 1
        else:
            buckets[b]["losses"] += 1
        buckets[b]["pnl"] += t["pnl"] or 0

    return {
        "total": total, "wins": wins, "losses": losses,
        "win_rate": win_rate, "total_pnl": total_pnl,
        "avg_win": avg_win, "avg_loss": avg_loss,
        "buckets": dict(buckets),
    }


def fast_calibrate(conn, bot, stats):
    """Quick parameter adjustments based on recent performance."""
    changes = []
    current_params = {p: get_current_param(conn, bot, p) for p in BOT_PARAMS.get(bot, [])}

    # Rule 1: If win rate < 40% and sample >= 10, tighten MIN_ENTRY
    if "MIN_ENTRY" in current_params and stats["total"] >= 10:
        if stats["win_rate"] < 0.40:
            old = current_params["MIN_ENTRY"]
            new = clamp_adjustment(old, old + 0.05, "MIN_ENTRY")
            if new != old:
                changes.append(("MIN_ENTRY", old, new, f"win_rate={stats['win_rate']:.1%} < 40%, tightening"))
        elif stats["win_rate"] > 0.70 and stats["total"] >= 20:
            # Winning a lot — can afford to loosen slightly
            old = current_params["MIN_ENTRY"]
            new = clamp_adjustment(old, old - 0.02, "MIN_ENTRY")
            if new != old:
                changes.append(("MIN_ENTRY", old, new, f"win_rate={stats['win_rate']:.1%} > 70%, loosening"))

    # Rule 2: If avg loss > 2x avg win, reduce POSITION_PCT
    if "POSITION_PCT" in current_params and stats["wins"] > 0 and stats["losses"] > 0:
        if abs(stats["avg_loss"]) > 2 * stats["avg_win"]:
            old = current_params["POSITION_PCT"]
            new = clamp_adjustment(old, old - 0.005, "POSITION_PCT")
            if new != old:
                changes.append(("POSITION_PCT", old, new, f"avg_loss=${stats['avg_loss']:.2f} > 2x avg_win=${stats['avg_win']:.2f}"))

    # Rule 3: If MIN_EDGE_SCORE and win rate > 60% with good sample, loosen score
    if "MIN_EDGE_SCORE" in current_params and stats["total"] >= 15:
        if stats["win_rate"] > 0.60:
            old = current_params["MIN_EDGE_SCORE"]
            new = clamp_adjustment(old, old - 0.03, "MIN_EDGE_SCORE")
            if new != old:
                changes.append(("MIN_EDGE_SCORE", old, new, f"win_rate={stats['win_rate']:.1%}, loosening edge threshold"))
        elif stats["win_rate"] < 0.35:
            old = current_params["MIN_EDGE_SCORE"]
            new = clamp_adjustment(old, old + 0.05, "MIN_EDGE_SCORE")
            if new != old:
                changes.append(("MIN_EDGE_SCORE", old, new, f"win_rate={stats['win_rate']:.1%}, tightening edge threshold"))

    # Rule 4: EDGE_THRESHOLD for dataharvester
    if "EDGE_THRESHOLD" in current_params and stats["total"] >= 10:
        if stats["win_rate"] < 0.40:
            old = current_params["EDGE_THRESHOLD"]
            new = clamp_adjustment(old, old + 0.02, "EDGE_THRESHOLD")
            if new != old:
                changes.append(("EDGE_THRESHOLD", old, new, f"win_rate={stats['win_rate']:.1%}, raising threshold"))
        elif stats["win_rate"] > 0.65:
            old = current_params["EDGE_THRESHOLD"]
            new = clamp_adjustment(old, old - 0.01, "EDGE_THRESHOLD")
            if new != old:
                changes.append(("EDGE_THRESHOLD", old, new, f"win_rate={stats['win_rate']:.1%}, lowering threshold"))

    # Rule 5: VOLUME_SPIKE_MULT for sentimentclaw
    if "VOLUME_SPIKE_MULT" in current_params and stats["total"] >= 10:
        if stats["win_rate"] < 0.40:
            old = current_params["VOLUME_SPIKE_MULT"]
            new = clamp_adjustment(old, old + 0.2, "VOLUME_SPIKE_MULT")
            if new != old:
                changes.append(("VOLUME_SPIKE_MULT", old, new, f"win_rate={stats['win_rate']:.1%}, raising spike threshold"))

    return changes


def review_calibrate(conn, bot, stats):
    """Deeper 6-hour review: bucket-level analysis."""
    changes = fast_calibrate(conn, bot, stats)

    # Additional: find the best and worst entry price buckets
    if stats["buckets"] and "MIN_ENTRY" in BOT_PARAMS.get(bot, []):
        # Find lowest bucket with 0% win rate and >= 3 trades
        for bucket_name in ["0.00-0.15", "0.15-0.30", "0.30-0.50"]:
            b = stats["buckets"].get(bucket_name, {})
            total_b = b.get("wins", 0) + b.get("losses", 0)
            if total_b >= 3:
                wr = b["wins"] / total_b
                if wr < 0.20:
                    # This bucket is toxic — raise MIN_ENTRY above it
                    upper = float(bucket_name.split("-")[1])
                    current = get_current_param(conn, bot, "MIN_ENTRY")
                    if current < upper:
                        new = clamp_adjustment(current, upper, "MIN_ENTRY")
                        if new != current:
                            changes.append(("MIN_ENTRY", current, new,
                                f"bucket {bucket_name} win_rate={wr:.0%} ({total_b} trades) — toxic, raising floor"))
                            break

    return changes


def meta_report(conn):
    """Daily cross-bot comparison. Prints report, no auto-changes."""
    print(f"\n{'='*70}")
    print(f"META STRATEGY REVIEW — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*70}\n")

    for bot in BOT_PARAMS:
        stats = analyze_bot(conn, bot, lookback_hours=168)  # 7 days
        if not stats:
            print(f"  {bot:20s}  NO DATA")
            continue

        print(f"  {bot:20s}  {stats['wins']}W {stats['losses']}L  "
              f"WR={stats['win_rate']:.0%}  "
              f"PnL=${stats['total_pnl']:+.2f}  "
              f"AvgW=${stats['avg_win']:.2f}  AvgL=${stats['avg_loss']:.2f}")

        # Show current params
        params = {p: get_current_param(conn, bot, p) for p in BOT_PARAMS[bot]}
        print(f"    params: {params}")

        # Show bucket breakdown
        if stats["buckets"]:
            for bname, bdata in sorted(stats["buckets"].items()):
                bt = bdata["wins"] + bdata["losses"]
                bwr = bdata["wins"] / bt if bt > 0 else 0
                print(f"    {bname}: {bdata['wins']}W {bdata['losses']}L ({bwr:.0%}) PnL=${bdata['pnl']:+.2f}")
        print()

    # Recent calibration changes
    recent = conn.execute(
        "SELECT * FROM calibration_log ORDER BY logged_at DESC LIMIT 20"
    ).fetchall()
    if recent:
        print(f"  RECENT CALIBRATION CHANGES (last 20):")
        for r in recent:
            print(f"    [{r['logged_at']}] {r['bot']}.{r['param']}: "
                  f"{r['old_value']:.4f} → {r['new_value']:.4f} ({r['reason']})")
    print()


def run(mode="fast"):
    conn = get_conn()
    now = datetime.now(timezone.utc)

    lookback = {"fast": 6, "review": 24, "meta": 168}[mode]
    calibrate_fn = {"fast": fast_calibrate, "review": review_calibrate}

    print(f"[calibrator] {now.isoformat()} mode={mode} lookback={lookback}h")

    if mode == "meta":
        meta_report(conn)
        conn.close()
        return

    total_changes = 0
    for bot in BOT_PARAMS:
        stats = analyze_bot(conn, bot, lookback_hours=lookback)
        if not stats or stats["total"] < 5:
            print(f"  {bot}: insufficient data ({stats['total'] if stats else 0} resolved trades)")
            continue

        changes = calibrate_fn[mode](conn, bot, stats)

        if changes:
            for param, old_val, new_val, reason in changes:
                set_param(conn, bot, param, new_val)
                conn.execute("""
                    INSERT INTO calibration_log (bot, param, old_value, new_value, reason, mode, win_rate, sample_size)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (bot, param, old_val, new_val, reason, mode, stats["win_rate"], stats["total"]))
                print(f"  {bot}.{param}: {old_val:.4f} → {new_val:.4f} | {reason}")
                total_changes += 1
        else:
            print(f"  {bot}: {stats['wins']}W {stats['losses']}L ({stats['win_rate']:.0%}) — no changes needed")

    conn.commit()
    conn.close()
    print(f"[calibrator] {total_changes} parameter changes applied")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fast", action="store_true", help="Quick 30-min calibration")
    parser.add_argument("--review", action="store_true", help="Deep 6-hour review")
    parser.add_argument("--meta", action="store_true", help="Daily cross-bot meta report")
    args = parser.parse_args()

    if args.review:
        run("review")
    elif args.meta:
        run("meta")
    else:
        run("fast")
