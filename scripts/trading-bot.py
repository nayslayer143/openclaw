#!/usr/bin/env python3
"""
trading-bot.py — Prediction market scanner + paper trading tracker.

Scans Polymarket via gamma API, identifies mispriced markets using Ollama,
auto-paper-trades high-confidence signals, tracks P&L over time.

Usage:
  python3 trading-bot.py scan          # Scan markets, generate signals
  python3 trading-bot.py trade         # Auto-paper-trade high-confidence signals
  python3 trading-bot.py portfolio     # Show current paper portfolio + P&L
  python3 trading-bot.py full          # scan + trade + portfolio (for cron)

Data files:
  ~/openclaw/trading/signals.json      — all generated signals
  ~/openclaw/trading/positions.json    — paper trade positions
  ~/openclaw/trading/history.json      — closed positions with P&L
"""

import os
import sys
import json
import re
import datetime
import urllib.request
from pathlib import Path

OPENCLAW = Path.home() / "openclaw"
TRADING_DIR = OPENCLAW / "trading"
SIGNALS_FILE = TRADING_DIR / "signals.json"
POSITIONS_FILE = TRADING_DIR / "positions.json"
HISTORY_FILE = TRADING_DIR / "history.json"

OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
MODEL = os.environ.get("TRADING_MODEL", "qwen2.5:7b")

TRADING_DIR.mkdir(parents=True, exist_ok=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_json(path, default=None):
    if default is None:
        default = []
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return default


def save_json(path, data):
    path.write_text(json.dumps(data, indent=2))


def llm(prompt, system="", timeout=180):
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    data = json.dumps({"model": MODEL, "messages": messages, "stream": False}).encode()
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat", data=data,
        headers={"Content-Type": "application/json"}
    )
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        content = json.loads(resp.read()).get("message", {}).get("content", "")
        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
        return content
    except Exception as e:
        return f"[LLM error: {e}]"


def notify(msg):
    try:
        env = {}
        for line in (OPENCLAW / ".env").read_text().splitlines():
            if line.strip() and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
        token = env.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = env.get("TELEGRAM_ALLOWED_USERS", "").strip().strip('"[]').split(",")[0]
        if token and chat_id:
            data = json.dumps({"chat_id": chat_id, "text": msg[:4000]}).encode()
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data=data, headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


# ── Market Scanner ────────────────────────────────────────────────────────────

def fetch_polymarket(limit=100):
    """Fetch active markets from Polymarket gamma API, sorted by volume."""
    url = f"https://gamma-api.polymarket.com/markets?closed=false&limit={limit}&order=volume&ascending=false"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        resp = urllib.request.urlopen(req, timeout=15)
        markets = json.loads(resp.read())
        results = []
        for m in markets:
            if not m.get("outcomePrices"):
                continue
            prices = json.loads(m["outcomePrices"]) if isinstance(m["outcomePrices"], str) else m["outcomePrices"]
            yes_price = float(prices[0]) if prices else 0
            no_price = float(prices[1]) if len(prices) > 1 else 1 - yes_price
            results.append({
                "question": m.get("question", ""),
                "slug": m.get("slug", ""),
                "yes_price": round(yes_price, 4),
                "no_price": round(no_price, 4),
                "volume": m.get("volume", 0),
                "end_date": (m.get("endDate") or "")[:10],
                "description": (m.get("description") or "")[:200],
            })
        return results
    except Exception as e:
        print(f"[trading] Polymarket fetch error: {e}")
        return []


def scan_markets():
    """Scan markets and identify opportunities using LLM analysis."""
    print("[trading] Scanning Polymarket...")
    markets = fetch_polymarket(30)
    if not markets:
        print("[trading] No markets fetched")
        return []

    # Filter markets where mispricings are possible (not extreme odds)
    interesting = sorted(
        [m for m in markets if 0.10 < m["yes_price"] < 0.90],
        key=lambda x: abs(x["yes_price"] - 0.5)  # prefer markets near 50/50 — more room for edge
    )[:20]

    market_text = "\n".join(
        f"- {m['question'][:80]} | YES:{m['yes_price']} NO:{m['no_price']} | ends:{m['end_date']} | vol:{m['volume']}"
        for m in interesting
    )

    print(f"[trading] Analyzing {len(interesting)} markets via LLM...")
    analysis = llm(f"""You are a prediction market analyst. Analyze these active Polymarket contracts
and identify ANY where the current price appears mispriced based on your knowledge of current events.

ACTIVE MARKETS:
{market_text}

For each market where you see an edge (mispricing > 5 cents), return a JSON array:
[
  {{
    "question": "market question",
    "current_yes_price": 0.XX,
    "estimated_true_prob": 0.XX,
    "edge": 0.XX,
    "direction": "buy_yes" or "buy_no",
    "confidence": "high" or "medium" or "low",
    "reasoning": "one sentence why",
    "suggested_size_usd": 10
  }}
]

Rules:
- Only include markets where you genuinely believe there's a mispricing
- Edge = |estimated_true_prob - current_yes_price| (for buy_yes) or |estimated_true_prob - current_no_price| (for buy_no)
- Minimum edge: 0.05 (5 cents)
- suggested_size_usd: $5 for low confidence, $10 for medium, $25 for high
- If no opportunities, return empty array []
- Return ONLY valid JSON array, no explanation""",
        system="You are a quantitative prediction market analyst. Be conservative. Only flag genuine mispricings.")

    # Parse signals — strip markdown fences and think tags
    try:
        cleaned = re.sub(r'<think>.*?</think>', '', analysis, flags=re.DOTALL)
        cleaned = re.sub(r'```json\s*', '', cleaned)
        cleaned = re.sub(r'```\s*', '', cleaned)
        match = re.search(r'\[.*\]', cleaned, re.DOTALL)
        if match:
            signals = json.loads(match.group())
        else:
            signals = []
    except Exception as e:
        print(f"[trading] Failed to parse LLM output: {e}")
        print(f"[trading] Raw: {analysis[:200]}")
        signals = []

    # Tag with metadata
    now = datetime.datetime.now().isoformat()
    for s in signals:
        s["scan_time"] = now
        s["status"] = "signal"
        s["id"] = f"sig-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}-{hash(s['question']) % 10000:04d}"

    # Save signals
    existing = load_json(SIGNALS_FILE)
    existing.extend(signals)
    # Keep last 200 signals
    save_json(SIGNALS_FILE, existing[-200:])

    print(f"[trading] Found {len(signals)} opportunities")
    for s in signals:
        print(f"  [{s.get('confidence','?')}] {s.get('direction','?')} {s.get('question','?')[:50]} edge={s.get('edge',0):.2f}")

    return signals


# ── Paper Trading ─────────────────────────────────────────────────────────────

def auto_paper_trade(signals=None):
    """Auto-paper-trade high and medium confidence signals."""
    if signals is None:
        signals = load_json(SIGNALS_FILE)
        # Only trade untraded signals from last 24h
        cutoff = (datetime.datetime.now() - datetime.timedelta(hours=24)).isoformat()
        signals = [s for s in signals if s.get("scan_time", "") > cutoff and s.get("status") == "signal"]

    positions = load_json(POSITIONS_FILE)
    traded = 0

    for s in signals:
        if s.get("confidence") not in ("high", "medium"):
            continue

        # Don't double-trade same market
        existing_qs = [p.get("question") for p in positions]
        if s.get("question") in existing_qs:
            continue

        position = {
            "id": s.get("id", "").replace("sig-", "pos-"),
            "question": s["question"],
            "direction": s["direction"],
            "entry_price": s["current_yes_price"] if s["direction"] == "buy_yes" else (1 - s["current_yes_price"]),
            "estimated_true_prob": s["estimated_true_prob"],
            "edge": s["edge"],
            "size_usd": s.get("suggested_size_usd", 10),
            "confidence": s["confidence"],
            "reasoning": s.get("reasoning", ""),
            "opened_at": datetime.datetime.now().isoformat(),
            "status": "open",
            "pnl": 0,
        }
        positions.append(position)
        s["status"] = "traded"
        traded += 1
        print(f"[trading] Paper trade: {position['direction']} {position['question'][:50]} @ {position['entry_price']:.2f} (${position['size_usd']})")

    save_json(POSITIONS_FILE, positions)
    # Update signal statuses
    all_signals = load_json(SIGNALS_FILE)
    for s in signals:
        for existing in all_signals:
            if existing.get("id") == s.get("id"):
                existing["status"] = s["status"]
    save_json(SIGNALS_FILE, all_signals)

    print(f"[trading] {traded} new paper trades opened")
    return traded


def check_portfolio():
    """Check current portfolio, update prices, calculate P&L."""
    positions = load_json(POSITIONS_FILE)
    history = load_json(HISTORY_FILE)

    if not positions:
        print("[trading] No open positions")
        return {"open": 0, "total_pnl": 0, "positions": []}

    # Fetch current market prices
    markets = fetch_polymarket(50)
    market_map = {m["question"]: m for m in markets}

    total_invested = 0
    total_current = 0
    total_pnl = 0

    for p in positions:
        q = p["question"]
        current = market_map.get(q)

        if current:
            if p["direction"] == "buy_yes":
                current_price = current["yes_price"]
            else:
                current_price = current["no_price"]

            invested = p["size_usd"]
            shares = invested / p["entry_price"] if p["entry_price"] > 0 else 0
            current_value = shares * current_price
            pnl = current_value - invested
            pnl_pct = (pnl / invested * 100) if invested > 0 else 0

            p["current_price"] = current_price
            p["current_value"] = round(current_value, 2)
            p["pnl"] = round(pnl, 2)
            p["pnl_pct"] = round(pnl_pct, 1)

            total_invested += invested
            total_current += current_value
            total_pnl += pnl
        else:
            p["current_price"] = None
            p["note"] = "Market not found — may have resolved"

    save_json(POSITIONS_FILE, positions)

    summary = {
        "open_positions": len(positions),
        "total_invested": round(total_invested, 2),
        "total_current_value": round(total_current, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round((total_pnl / total_invested * 100) if total_invested > 0 else 0, 1),
        "positions": positions,
        "as_of": datetime.datetime.now().isoformat(),
    }

    print(f"\n[trading] === PAPER PORTFOLIO ===")
    print(f"  Open positions: {len(positions)}")
    print(f"  Total invested: ${total_invested:.2f}")
    print(f"  Current value:  ${total_current:.2f}")
    print(f"  P&L:            ${total_pnl:+.2f} ({summary['total_pnl_pct']:+.1f}%)")
    print()
    for p in positions:
        icon = "+" if p.get("pnl", 0) >= 0 else "-"
        print(f"  {icon} {p['direction']:7} {p['question'][:45]} | entry:{p['entry_price']:.2f} now:{p.get('current_price','?')} | ${p.get('pnl',0):+.2f}")

    return summary


# ── Dashboard API data ────────────────────────────────────────────────────────

def export_dashboard_data():
    """Write trading data for the dashboard API to read."""
    portfolio = check_portfolio()
    signals = load_json(SIGNALS_FILE)[-20:]
    history = load_json(HISTORY_FILE)

    dashboard = {
        "portfolio": portfolio,
        "recent_signals": signals,
        "history": history[-20:],
        "updated_at": datetime.datetime.now().isoformat(),
    }
    save_json(TRADING_DIR / "dashboard.json", dashboard)
    return dashboard


# ── Full cycle ────────────────────────────────────────────────────────────────

def full_cycle(do_notify=True):
    """Run complete scan → trade → portfolio check cycle."""
    signals = scan_markets()
    traded = auto_paper_trade(signals)
    portfolio = check_portfolio()
    export_dashboard_data()

    if do_notify and (signals or traded):
        msg = f"Trading Bot Scan — {datetime.date.today()}\n\n"
        msg += f"Signals: {len(signals)} found\n"
        msg += f"New trades: {traded}\n"
        msg += f"Portfolio: {portfolio['open_positions']} positions\n"
        msg += f"P&L: ${portfolio['total_pnl']:+.2f} ({portfolio['total_pnl_pct']:+.1f}%)\n"
        if signals:
            msg += "\nTop signals:\n"
            for s in signals[:3]:
                msg += f"  [{s.get('confidence','')}] {s.get('direction','')} {s.get('question','')[:40]} edge={s.get('edge',0):.2f}\n"
        notify(msg)

    return portfolio


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "full"

    if cmd == "scan":
        scan_markets()
    elif cmd == "trade":
        auto_paper_trade()
    elif cmd == "portfolio":
        check_portfolio()
    elif cmd == "full":
        full_cycle()
    elif cmd == "export":
        export_dashboard_data()
    else:
        print("Usage: python3 trading-bot.py [scan|trade|portfolio|full|export]")
