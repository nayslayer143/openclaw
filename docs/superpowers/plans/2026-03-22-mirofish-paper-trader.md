# Mirofish Paper Trading Simulator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a paper trading simulator that runs Clawmson's prediction market logic against real Polymarket data with a fake $1,000 wallet, tracking P&L until it earns live trading access.

**Architecture:** Five focused Python modules in `scripts/mirofish/` communicate through shared SQLite (`~/.openclaw/clawmson.db`). `simulator.py` is the cron-triggered orchestrator; all other modules are independently importable and testable. Replaces `cron-prediction-market.sh`.

**Tech Stack:** Python 3.11+, SQLite (WAL mode), `requests`, `statistics` stdlib, Ollama HTTP API (`qwen3:30b`), `python-telegram-bot` (not used — outbound messages go via existing `notify-telegram.sh`), `pytest`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `scripts/mirofish/__init__.py` | Create | Package marker |
| `scripts/mirofish/paper_wallet.py` | Create | Wallet state, trade execution, stop management, P&L math |
| `scripts/mirofish/polymarket_feed.py` | Create | Polymarket API fetch, market_data table writes, price queries |
| `scripts/mirofish/trading_brain.py` | Create | Arbitrage fast-path, Ollama call, Kelly sizing, trade decisions |
| `scripts/mirofish/dashboard.py` | Create | Graduation check, report generation, Telegram message formatting, daily snapshot |
| `scripts/mirofish/simulator.py` | Create | CLI orchestrator: `--run`, `--migrate`, `--report` |
| `scripts/mirofish/tests/__init__.py` | Create | Test package marker |
| `scripts/mirofish/tests/test_wallet.py` | Create | Wallet math tests (balance, stops, Sharpe, drawdown) |
| `scripts/mirofish/tests/test_positions.py` | Create | Arbitrage detection, Kelly sizing, graduation logic tests |
| `scripts/telegram-dispatcher.py` | Modify | Add `/portfolio`, `/pnl`, `/trades`, `/bet` slash handlers |
| `agents/configs/mirofish-trader.md` | Create | Agent config doc for the system |
| `mirofish/reports/` | Create dir | Report output directory |

---

## Task 1: DB Migration

**Files:**
- Create: `scripts/mirofish/__init__.py`
- Create: `scripts/mirofish/simulator.py` (migration only for now)

- [ ] **Step 1.1: Create package marker**

```bash
mkdir -p scripts/mirofish/tests
touch scripts/mirofish/__init__.py scripts/mirofish/tests/__init__.py
```

- [ ] **Step 1.2: Write `simulator.py` with migration only**

```python
#!/usr/bin/env python3
"""
Mirofish simulator — cron orchestrator for paper trading.
CLI: python3 simulator.py --run | --migrate | --report
"""
from __future__ import annotations
import argparse
import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.environ.get("CLAWMSON_DB_PATH", Path.home() / ".openclaw" / "clawmson.db"))


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS market_data (
    id           INTEGER PRIMARY KEY,
    market_id    TEXT NOT NULL,
    question     TEXT NOT NULL,
    category     TEXT,
    yes_price    REAL,
    no_price     REAL,
    volume       REAL,
    end_date     TEXT,
    fetched_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_market_data_market_time
    ON market_data(market_id, fetched_at);

CREATE TABLE IF NOT EXISTS paper_trades (
    id           INTEGER PRIMARY KEY,
    market_id    TEXT NOT NULL,
    question     TEXT NOT NULL,
    direction    TEXT NOT NULL,
    shares       REAL NOT NULL,
    entry_price  REAL NOT NULL,
    exit_price   REAL,
    amount_usd   REAL NOT NULL,
    pnl          REAL,
    status       TEXT NOT NULL,
    confidence   REAL NOT NULL DEFAULT 1.0,
    reasoning    TEXT NOT NULL DEFAULT '',
    strategy     TEXT NOT NULL DEFAULT 'manual',
    opened_at    TEXT NOT NULL,
    closed_at    TEXT
);

CREATE TABLE IF NOT EXISTS daily_pnl (
    id              INTEGER PRIMARY KEY,
    date            TEXT NOT NULL UNIQUE,
    balance         REAL NOT NULL,
    open_positions  INTEGER,
    realized_pnl    REAL,
    unrealized_pnl  REAL,
    total_trades    INTEGER,
    win_rate        REAL,
    roi_pct         REAL
);

-- Seed starting balance in context table if not already set
INSERT OR IGNORE INTO context (chat_id, key, value)
VALUES ('mirofish', 'starting_balance', '1000.00');
"""


def migrate():
    """Create mirofish tables. Idempotent."""
    with _get_conn() as conn:
        conn.executescript(MIGRATION_SQL)
    print(f"[mirofish] Migration complete. DB: {DB_PATH}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--migrate", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()

    if args.migrate:
        migrate()
    elif args.run:
        print("[mirofish] --run not yet implemented")
    elif args.report:
        print("[mirofish] --report not yet implemented")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
```

- [ ] **Step 1.3: Run migration against a temp DB to verify it's idempotent**

> **Note:** The migration's `INSERT OR IGNORE INTO context` requires a pre-existing `context` table.
> On a blank temp DB this will fail — run against the real DB (which already has the `context` table
> from `clawmson_db.py`). Use the temp DB only to confirm the new tables are created; skip the
> `context` row check against blank DBs.

```bash
cd ~/openclaw
# Smoke test on real DB (read-only check — migration is IF NOT EXISTS, safe to re-run)
python3 scripts/mirofish/simulator.py --migrate
sqlite3 ~/.openclaw/clawmson.db ".tables"
# Expected: context  conversations  daily_pnl  market_data  paper_trades  refs (+ others)
sqlite3 ~/.openclaw/clawmson.db "SELECT * FROM context WHERE chat_id='mirofish';"
# Expected: mirofish|starting_balance|1000.00
# Run a second time to confirm idempotency:
python3 scripts/mirofish/simulator.py --migrate
# Expected: no error
```

- [ ] **Step 1.4: Commit**

```bash
git add scripts/mirofish/__init__.py scripts/mirofish/tests/__init__.py scripts/mirofish/simulator.py
git commit -m "feat(mirofish): DB migration — market_data, paper_trades, daily_pnl tables"
```

---

## Task 2: `paper_wallet.py` — Wallet Math (TDD)

**Files:**
- Create: `scripts/mirofish/tests/test_wallet.py`
- Create: `scripts/mirofish/paper_wallet.py`

- [ ] **Step 2.1: Write failing tests**

```python
# scripts/mirofish/tests/test_wallet.py
from __future__ import annotations
import os
import sqlite3
import tempfile
from pathlib import Path
from statistics import mean, stdev
import pytest

# Point at a temp DB for all wallet tests
@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    db = str(tmp_path / "test.db")
    monkeypatch.setenv("CLAWMSON_DB_PATH", db)
    # Run migration to create tables
    import importlib, sys
    # Force re-import with new env var
    for mod in list(sys.modules.keys()):
        if "mirofish" in mod or "clawmson" in mod:
            del sys.modules[mod]
    import scripts.mirofish.simulator as sim
    sim.DB_PATH = Path(db)
    sim.migrate()
    yield db


def _get_wallet():
    # Re-import after env var is set
    import importlib, sys
    for mod in list(sys.modules.keys()):
        if "paper_wallet" in mod:
            del sys.modules[mod]
    import scripts.mirofish.paper_wallet as pw
    return pw


# ── Balance derivation ─────────────────────────────────────────────────────
def test_starting_balance_is_1000(temp_db):
    pw = _get_wallet()
    state = pw.get_state()
    assert state["starting_balance"] == 1000.0
    assert state["balance"] == 1000.0   # no trades yet


def test_balance_includes_realized_pnl(temp_db):
    pw = _get_wallet()
    # Manually insert a closed winning trade
    conn = sqlite3.connect(temp_db)
    conn.execute("""
        INSERT INTO paper_trades
        (market_id, question, direction, shares, entry_price, exit_price,
         amount_usd, pnl, status, opened_at, closed_at)
        VALUES ('mkt1', 'test', 'YES', 100, 0.50, 0.70, 50.0, 20.0, 'closed_win',
                '2026-01-01T00:00:00', '2026-01-02T00:00:00')
    """)
    conn.commit(); conn.close()
    state = pw.get_state()
    assert state["balance"] == pytest.approx(1020.0)


def test_balance_includes_unrealized_pnl(temp_db):
    pw = _get_wallet()
    # Open YES trade at 0.40, market now at 0.60 → unrealized = shares*(0.60-0.40)
    conn = sqlite3.connect(temp_db)
    conn.execute("""
        INSERT INTO paper_trades
        (market_id, question, direction, shares, entry_price,
         amount_usd, status, opened_at)
        VALUES ('mkt2', 'open trade', 'YES', 100, 0.40, 40.0, 'open', '2026-01-01T00:00:00')
    """)
    # Seed a current price snapshot
    conn.execute("""
        INSERT INTO market_data (market_id, question, yes_price, no_price, fetched_at)
        VALUES ('mkt2', 'open trade', 0.60, 0.40, '2026-01-01T01:00:00')
    """)
    conn.commit(); conn.close()
    state = pw.get_state()
    assert state["balance"] == pytest.approx(1020.0)  # 1000 + 100*(0.60-0.40)


# ── Position cap ───────────────────────────────────────────────────────────
def test_position_cap_rejects_over_10pct(temp_db):
    pw = _get_wallet()
    from types import SimpleNamespace
    decision = SimpleNamespace(
        market_id="mkt3", question="big bet", direction="YES",
        amount_usd=101.0,  # 10.1% of $1000
        entry_price=0.50, shares=202.0,
        confidence=0.8, reasoning="test", strategy="momentum"
    )
    result = pw.execute_trade(decision)
    assert result is None  # rejected


def test_position_cap_allows_exactly_10pct(temp_db):
    pw = _get_wallet()
    from types import SimpleNamespace
    decision = SimpleNamespace(
        market_id="mkt4", question="10pct bet", direction="YES",
        amount_usd=100.0,  # exactly 10%
        entry_price=0.50, shares=200.0,
        confidence=0.8, reasoning="test", strategy="momentum"
    )
    result = pw.execute_trade(decision)
    assert result is not None
    assert result["status"] == "open"


# ── Stop management ────────────────────────────────────────────────────────
def test_stop_loss_closes_at_minus_20pct(temp_db):
    pw = _get_wallet()
    conn = sqlite3.connect(temp_db)
    # YES trade: bought 100 shares at 0.50 for $50. Stop at -20% = P&L < -$10
    # Current yes_price = 0.40 → unrealized = 100*(0.40-0.50) = -$10 = -20%
    conn.execute("""
        INSERT INTO paper_trades (id, market_id, question, direction, shares,
         entry_price, amount_usd, status, opened_at)
        VALUES (1, 'mkt5', 'stop test', 'YES', 100, 0.50, 50.0, 'open', '2026-01-01T00:00:00')
    """)
    conn.commit(); conn.close()
    current_prices = {"mkt5": {"yes_price": 0.40, "no_price": 0.60}}
    closed = pw.check_stops(current_prices)
    assert len(closed) == 1
    assert closed[0]["status"] == "closed_loss"
    assert closed[0]["exit_price"] == pytest.approx(0.40)


def test_take_profit_closes_at_plus_50pct(temp_db):
    pw = _get_wallet()
    conn = sqlite3.connect(temp_db)
    # YES trade: bought 100 shares at 0.40 for $40. Take-profit at +50% = P&L > +$20
    # Current yes_price = 0.60 → unrealized = 100*(0.60-0.40) = +$20 = +50%
    conn.execute("""
        INSERT INTO paper_trades (id, market_id, question, direction, shares,
         entry_price, amount_usd, status, opened_at)
        VALUES (2, 'mkt6', 'profit test', 'YES', 100, 0.40, 40.0, 'open', '2026-01-01T00:00:00')
    """)
    conn.commit(); conn.close()
    current_prices = {"mkt6": {"yes_price": 0.60, "no_price": 0.40}}
    closed = pw.check_stops(current_prices)
    assert len(closed) == 1
    assert closed[0]["status"] == "closed_win"


# ── Sharpe ratio ───────────────────────────────────────────────────────────
def test_sharpe_returns_correct_value(temp_db):
    pw = _get_wallet()
    # Inject 14 days of daily_pnl with known returns
    conn = sqlite3.connect(temp_db)
    returns = [0.02, 0.01, 0.03, -0.01, 0.02, 0.01, 0.04,
               0.01, 0.02, -0.01, 0.03, 0.01, 0.02, 0.01]
    balance = 1000.0
    for i, r in enumerate(returns):
        balance *= (1 + r)
        conn.execute("""
            INSERT INTO daily_pnl (date, balance, roi_pct, open_positions, total_trades, win_rate)
            VALUES (?, ?, ?, 0, 0, 0.0)
        """, (f"2026-01-{i+1:02d}", balance, r))
    conn.commit(); conn.close()
    state = pw.get_state()
    expected = mean(returns) / stdev(returns)
    assert state["sharpe_ratio"] == pytest.approx(expected, rel=1e-3)


def test_sharpe_returns_none_when_std_is_zero(temp_db):
    pw = _get_wallet()
    conn = sqlite3.connect(temp_db)
    for i in range(14):
        conn.execute("""
            INSERT INTO daily_pnl (date, balance, roi_pct, open_positions, total_trades, win_rate)
            VALUES (?, ?, ?, 0, 0, 0.0)
        """, (f"2026-01-{i+1:02d}", 1000.0, 0.01))
    conn.commit(); conn.close()
    state = pw.get_state()
    assert state["sharpe_ratio"] is None


# ── Max drawdown ───────────────────────────────────────────────────────────
def test_max_drawdown_calculation(temp_db):
    pw = _get_wallet()
    conn = sqlite3.connect(temp_db)
    # Balances: 1000 → 1100 (peak) → 880 → 990
    # Drawdown from peak 1100 to 880 = (1100-880)/1100 = 0.2 = 20%
    for date, bal in [("2026-01-01", 1000), ("2026-01-02", 1100),
                      ("2026-01-03", 880),  ("2026-01-04", 990)]:
        roi = (bal - 1000) / 1000
        conn.execute("""
            INSERT INTO daily_pnl (date, balance, roi_pct, open_positions, total_trades, win_rate)
            VALUES (?, ?, ?, 0, 0, 0.0)
        """, (date, bal, roi))
    conn.commit(); conn.close()
    state = pw.get_state()
    assert state["max_drawdown"] == pytest.approx(0.2, rel=1e-3)
```

- [ ] **Step 2.2: Run tests to confirm they all fail**

```bash
cd ~/openclaw
python -m pytest scripts/mirofish/tests/test_wallet.py -v 2>&1 | head -30
# Expected: ImportError or ModuleNotFoundError for paper_wallet
```

- [ ] **Step 2.3: Write `paper_wallet.py`**

```python
#!/usr/bin/env python3
"""
Mirofish paper wallet — fake wallet manager for prediction market simulation.
DB: ~/.openclaw/clawmson.db (tables: paper_trades, daily_pnl, context)
"""
from __future__ import annotations
import os
import sqlite3
import datetime
from pathlib import Path
from statistics import mean, stdev
from typing import Any

DB_PATH = Path(os.environ.get("CLAWMSON_DB_PATH", Path.home() / ".openclaw" / "clawmson.db"))

STOP_LOSS_PCT    = float(os.environ.get("MIROFISH_STOP_LOSS_PCT",    "0.20"))
TAKE_PROFIT_PCT  = float(os.environ.get("MIROFISH_TAKE_PROFIT_PCT",  "0.50"))
MAX_POSITION_PCT = float(os.environ.get("MIROFISH_MAX_POSITION_PCT", "0.10"))
MIN_HISTORY_DAYS = int(os.environ.get("MIROFISH_MIN_HISTORY_DAYS", "14"))


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _get_starting_balance() -> float:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT value FROM context WHERE chat_id='mirofish' AND key='starting_balance'"
        ).fetchone()
    return float(row["value"]) if row else 1000.0


def _get_latest_prices() -> dict[str, dict]:
    """Return {market_id: {yes_price, no_price}} from most recent snapshot per market."""
    with _get_conn() as conn:
        rows = conn.execute("""
            SELECT md.market_id, md.yes_price, md.no_price
            FROM market_data md
            INNER JOIN (
                SELECT market_id, MAX(fetched_at) AS latest
                FROM market_data GROUP BY market_id
            ) latest ON md.market_id = latest.market_id AND md.fetched_at = latest.latest
        """).fetchall()
    return {r["market_id"]: {"yes_price": r["yes_price"], "no_price": r["no_price"]} for r in rows}


def _compute_balance(starting: float, prices: dict[str, dict]) -> float:
    """Derive current balance from trade history + mark-to-market open positions."""
    with _get_conn() as conn:
        closed = conn.execute(
            "SELECT COALESCE(SUM(pnl), 0) as total FROM paper_trades WHERE status != 'open'"
        ).fetchone()["total"]
        open_trades = conn.execute(
            "SELECT market_id, direction, shares, entry_price FROM paper_trades WHERE status='open'"
        ).fetchall()

    unrealized = 0.0
    for t in open_trades:
        p = prices.get(t["market_id"], {})
        if t["direction"] == "YES":
            price = p.get("yes_price", t["entry_price"])
        else:
            price = p.get("no_price", t["entry_price"])
        unrealized += t["shares"] * (price - t["entry_price"])

    return starting + closed + unrealized


def get_state() -> dict[str, Any]:
    """Return full wallet state. Balance is always derived, never cached."""
    starting = _get_starting_balance()
    prices = _get_latest_prices()
    balance = _compute_balance(starting, prices)

    with _get_conn() as conn:
        closed_trades = conn.execute(
            "SELECT status FROM paper_trades WHERE status != 'open'"
        ).fetchall()
        open_positions = conn.execute(
            "SELECT COUNT(*) as cnt FROM paper_trades WHERE status='open'"
        ).fetchone()["cnt"]
        daily_rows = conn.execute(
            "SELECT balance, roi_pct FROM daily_pnl ORDER BY date ASC"
        ).fetchall()

    total_closed = len(closed_trades)
    wins = sum(1 for t in closed_trades if t["status"] == "closed_win")
    win_rate = wins / total_closed if total_closed > 0 else 0.0

    # Sharpe: mean/std of daily roi_pct (unannualized)
    returns = [r["roi_pct"] for r in daily_rows if r["roi_pct"] is not None]
    sharpe = None
    if len(returns) >= MIN_HISTORY_DAYS:
        s = stdev(returns)
        if s > 0:
            sharpe = mean(returns) / s

    # Max drawdown: peak-to-trough over all daily balances
    balances = [r["balance"] for r in daily_rows]
    max_dd = 0.0
    if balances:
        peak = balances[0]
        for b in balances:
            peak = max(peak, b)
            dd = (peak - b) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, dd)

    return {
        "balance": balance,
        "starting_balance": starting,
        "open_positions": open_positions,
        "win_rate": win_rate,
        "sharpe_ratio": sharpe,
        "max_drawdown": max_dd,
        "total_trades": total_closed,
    }


def execute_trade(decision: Any) -> dict | None:
    """
    Execute a paper trade. Returns trade dict or None if rejected.
    Rejects if: amount_usd > 10% of balance.
    Manual /bet trades: pass decision with strategy='manual', confidence=1.0.
    """
    state = get_state()
    cap = state["balance"] * MAX_POSITION_PCT

    if decision.amount_usd > cap:
        return None  # position cap breached

    ts = datetime.datetime.utcnow().isoformat()
    with _get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO paper_trades
            (market_id, question, direction, shares, entry_price, amount_usd,
             status, confidence, reasoning, strategy, opened_at)
            VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?)
        """, (
            decision.market_id, decision.question, decision.direction,
            decision.shares, decision.entry_price, decision.amount_usd,
            getattr(decision, "confidence", 1.0),
            getattr(decision, "reasoning", "manual via /bet"),
            getattr(decision, "strategy", "manual"),
            ts,
        ))
        trade_id = cur.lastrowid

    return {"id": trade_id, "status": "open", "amount_usd": decision.amount_usd,
            "market_id": decision.market_id, "direction": decision.direction}


def check_stops(current_prices: dict[str, dict]) -> list[dict]:
    """
    Check all open positions for stop-loss (-20%) and take-profit (+50%).
    Also closes positions in markets whose end_date has passed.
    Returns list of closed trade dicts.
    """
    now = datetime.datetime.utcnow()
    closed = []

    with _get_conn() as conn:
        open_trades = conn.execute("""
            SELECT pt.*, md.end_date
            FROM paper_trades pt
            LEFT JOIN (
                SELECT market_id, end_date, MAX(fetched_at) AS latest
                FROM market_data GROUP BY market_id
            ) md ON pt.market_id = md.market_id
            WHERE pt.status = 'open'
        """).fetchall()

    for t in open_trades:
        p = current_prices.get(t["market_id"], {})
        if t["direction"] == "YES":
            current_price = p.get("yes_price", t["entry_price"])
        else:
            current_price = p.get("no_price", t["entry_price"])

        unrealized_pnl = t["shares"] * (current_price - t["entry_price"])
        pnl_pct = unrealized_pnl / t["amount_usd"] if t["amount_usd"] > 0 else 0.0

        # Check expiry
        expired = False
        if t["end_date"]:
            try:
                end = datetime.datetime.fromisoformat(t["end_date"].replace("Z", ""))
                expired = now > end
            except (ValueError, AttributeError):
                pass

        should_close = (
            pnl_pct <= -STOP_LOSS_PCT or
            pnl_pct >= TAKE_PROFIT_PCT or
            expired
        )

        if should_close:
            status = "expired" if expired else ("closed_win" if unrealized_pnl >= 0 else "closed_loss")
            ts = now.isoformat()
            with _get_conn() as conn:
                conn.execute("""
                    UPDATE paper_trades
                    SET exit_price=?, pnl=?, status=?, closed_at=?
                    WHERE id=?
                """, (current_price, unrealized_pnl, status, ts, t["id"]))
            closed.append({
                "id": t["id"], "market_id": t["market_id"],
                "status": status, "exit_price": current_price, "pnl": unrealized_pnl,
            })

    return closed


def get_open_positions() -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM paper_trades WHERE status='open' ORDER BY opened_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_pnl_summary(days: int = 7) -> dict:
    with _get_conn() as conn:
        rows = conn.execute("""
            SELECT date, balance, roi_pct, win_rate
            FROM daily_pnl ORDER BY date DESC LIMIT ?
        """, (days,)).fetchall()
    return {"rows": [dict(r) for r in rows], "days": days}
```

- [ ] **Step 2.4: Run tests**

```bash
cd ~/openclaw
python -m pytest scripts/mirofish/tests/test_wallet.py -v
# Expected: all tests PASS
```

- [ ] **Step 2.5: Commit**

```bash
git add scripts/mirofish/paper_wallet.py scripts/mirofish/tests/test_wallet.py
git commit -m "feat(mirofish): paper_wallet — balance derivation, stops, Sharpe, drawdown (TDD)"
```

---

## Task 3: `polymarket_feed.py` — Market Data Fetcher

**Files:**
- Create: `scripts/mirofish/polymarket_feed.py`

No unit tests for this module (it wraps an external API). Manual smoke test in step 3.3.

- [ ] **Step 3.1: Write `polymarket_feed.py`**

```python
#!/usr/bin/env python3
"""
Polymarket feed — fetches market data from gamma-api.polymarket.com and caches to SQLite.
"""
from __future__ import annotations
import os
import sqlite3
import datetime
import requests
from pathlib import Path

DB_PATH = Path(os.environ.get("CLAWMSON_DB_PATH", Path.home() / ".openclaw" / "clawmson.db"))
GAMMA_API = "https://gamma-api.polymarket.com/markets"
MIN_VOLUME = float(os.environ.get("MIROFISH_MIN_MARKET_VOLUME", "10000"))
CACHE_MAX_AGE_HOURS = 6


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _is_cache_fresh() -> bool:
    """True if we have market_data rows less than CACHE_MAX_AGE_HOURS old."""
    cutoff = (datetime.datetime.utcnow() -
              datetime.timedelta(hours=CACHE_MAX_AGE_HOURS)).isoformat()
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM market_data WHERE fetched_at > ?", (cutoff,)
        ).fetchone()
    return row["cnt"] > 0


def fetch_markets(categories: list[str] | None = None) -> list[dict]:
    """
    Fetch active Polymarket markets, filter by volume and category, cache to DB.
    Returns list of market dicts. Falls back to cached data if API is unavailable.
    """
    if categories is None:
        categories = ["crypto", "politics", "sports", "weather", "tech"]

    now = datetime.datetime.utcnow().isoformat()

    try:
        resp = requests.get(
            GAMMA_API,
            params={"active": "true", "closed": "false", "limit": 100},
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json()
        markets_raw = raw if isinstance(raw, list) else raw.get("data", raw.get("markets", []))
    except Exception as e:
        print(f"[mirofish/feed] Polymarket API error: {e}. Using cache.")
        return _load_cached_markets(categories)

    markets = []
    with _get_conn() as conn:
        for m in markets_raw:
            volume = float(m.get("volume", 0) or 0)
            if volume < MIN_VOLUME:
                continue

            # Extract prices from tokens list
            tokens = m.get("tokens", []) or []
            yes_price = no_price = None
            for tok in tokens:
                outcome = (tok.get("outcome") or "").upper()
                if outcome == "YES":
                    yes_price = float(tok.get("price", 0) or 0)
                elif outcome == "NO":
                    no_price = float(tok.get("price", 0) or 0)

            if yes_price is None or no_price is None:
                continue

            market_id = m.get("conditionId") or m.get("id") or ""
            question  = m.get("question", "")
            category  = (m.get("category") or "").lower()
            end_date  = m.get("endDate") or m.get("end_date")

            if not market_id or not question:
                continue

            conn.execute("""
                INSERT INTO market_data
                (market_id, question, category, yes_price, no_price, volume, end_date, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (market_id, question, category, yes_price, no_price, volume, end_date, now))

            markets.append({
                "market_id": market_id, "question": question, "category": category,
                "yes_price": yes_price, "no_price": no_price,
                "volume": volume, "end_date": end_date,
            })

    # Filter by category (post-insert so cache is always populated)
    filtered = [m for m in markets if not categories or m["category"] in categories]
    print(f"[mirofish/feed] Fetched {len(markets)} markets, {len(filtered)} after category filter")
    return filtered


def _load_cached_markets(categories: list[str]) -> list[dict]:
    """Return most recent snapshot per market from cache."""
    cutoff = (datetime.datetime.utcnow() -
              datetime.timedelta(hours=CACHE_MAX_AGE_HOURS)).isoformat()
    with _get_conn() as conn:
        rows = conn.execute("""
            SELECT md.*
            FROM market_data md
            INNER JOIN (
                SELECT market_id, MAX(fetched_at) AS latest
                FROM market_data WHERE fetched_at > ?
                GROUP BY market_id
            ) latest ON md.market_id = latest.market_id AND md.fetched_at = latest.latest
        """, (cutoff,)).fetchall()
    markets = [dict(r) for r in rows]
    if not markets:
        print("[mirofish/feed] Cache empty or stale. No markets available.")
    return [m for m in markets if not categories or m.get("category") in categories]


def get_recent_snapshots(market_id: str, limit: int = 3) -> list[dict]:
    """Return the `limit` most recent price snapshots for a market (oldest first)."""
    with _get_conn() as conn:
        rows = conn.execute("""
            SELECT yes_price, no_price, fetched_at
            FROM market_data
            WHERE market_id = ?
            ORDER BY fetched_at DESC
            LIMIT ?
        """, (market_id, limit)).fetchall()
    return list(reversed([dict(r) for r in rows]))


def get_latest_prices() -> dict[str, dict]:
    """Return {market_id: {yes_price, no_price}} from most recent snapshot per market."""
    with _get_conn() as conn:
        rows = conn.execute("""
            SELECT md.market_id, md.yes_price, md.no_price
            FROM market_data md
            INNER JOIN (
                SELECT market_id, MAX(fetched_at) AS latest
                FROM market_data GROUP BY market_id
            ) l ON md.market_id = l.market_id AND md.fetched_at = l.latest
        """).fetchall()
    return {r["market_id"]: {"yes_price": r["yes_price"], "no_price": r["no_price"]}
            for r in rows}
```

- [ ] **Step 3.2: Smoke test against live API**

```bash
cd ~/openclaw
CLAWMSON_DB_PATH=/tmp/mirofish-smoke.db python3 scripts/mirofish/simulator.py --migrate
CLAWMSON_DB_PATH=/tmp/mirofish-smoke.db python3 -c "
import scripts.mirofish.polymarket_feed as feed
markets = feed.fetch_markets()
print(f'Fetched {len(markets)} markets')
if markets:
    m = markets[0]
    print(f'  Example: {m[\"question\"][:60]}')
    print(f'  YES={m[\"yes_price\"]:.2f} NO={m[\"no_price\"]:.2f} vol=\${m[\"volume\"]:,.0f}')
prices = feed.get_latest_prices()
print(f'Latest prices cached for {len(prices)} markets')
"
rm /tmp/mirofish-smoke.db
# Expected: printed market list with prices. If Polymarket API is down, sees cache message.
```

- [ ] **Step 3.3: Commit**

```bash
git add scripts/mirofish/polymarket_feed.py
git commit -m "feat(mirofish): polymarket_feed — market fetch, SQLite cache, price history"
```

---

## Task 4: `trading_brain.py` — Arbitrage + Ollama Analysis

**Files:**
- Create: `scripts/mirofish/tests/test_positions.py`
- Create: `scripts/mirofish/trading_brain.py`

- [ ] **Step 4.1: Write failing tests for arbitrage detection and Kelly sizing**

```python
# scripts/mirofish/tests/test_positions.py
from __future__ import annotations
import os
import pytest
import sqlite3
import tempfile
from pathlib import Path


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    db = str(tmp_path / "test.db")
    monkeypatch.setenv("CLAWMSON_DB_PATH", db)
    import sys
    for mod in list(sys.modules.keys()):
        if "mirofish" in mod:
            del sys.modules[mod]
    import scripts.mirofish.simulator as sim
    sim.DB_PATH = Path(db)
    sim.migrate()
    yield db


def _brain():
    import sys
    for mod in list(sys.modules.keys()):
        if "trading_brain" in mod:
            del sys.modules[mod]
    import scripts.mirofish.trading_brain as tb
    return tb


def _wallet():
    import sys
    for mod in list(sys.modules.keys()):
        if "paper_wallet" in mod:
            del sys.modules[mod]
    import scripts.mirofish.paper_wallet as pw
    return pw


# ── Arbitrage detection ────────────────────────────────────────────────────
def test_arbitrage_detected_when_gap_exceeds_threshold():
    tb = _brain()
    # yes=0.60 + no=0.45 → gap = 0.05 > 0.03 → flagged
    market = {"market_id": "m1", "question": "test", "yes_price": 0.60, "no_price": 0.45,
              "volume": 50000, "end_date": None, "category": "crypto"}
    result = tb._check_arbitrage(market)
    assert result is not None
    assert result["strategy"] == "arbitrage"
    # Should buy the underpriced side (NO at 0.45 < 0.50)
    assert result["direction"] == "NO"


def test_arbitrage_detected_buy_yes_when_yes_underpriced():
    tb = _brain()
    # yes=0.45 + no=0.60 → gap=0.05; yes is underpriced (< 0.50)
    market = {"market_id": "m2", "question": "test", "yes_price": 0.45, "no_price": 0.60,
              "volume": 50000, "end_date": None, "category": "crypto"}
    result = tb._check_arbitrage(market)
    assert result is not None
    assert result["direction"] == "YES"


def test_arbitrage_not_detected_below_threshold():
    tb = _brain()
    # yes=0.60 + no=0.41 → gap=0.01 ≤ 0.03 → not flagged
    market = {"market_id": "m3", "question": "test", "yes_price": 0.60, "no_price": 0.41,
              "volume": 50000, "end_date": None, "category": "crypto"}
    result = tb._check_arbitrage(market)
    assert result is None


# ── Kelly sizing ───────────────────────────────────────────────────────────
def test_kelly_positive_returns_within_cap():
    tb = _brain()
    # confidence=0.70, entry=0.30 → b=2.33, kelly=(0.70*2.33 - 0.30)/2.33 ≈ 0.57
    # position_size = min(0.57 * 1000, 0.10 * 1000) = 100
    size = tb._kelly_size(confidence=0.70, entry_price=0.30, balance=1000.0)
    assert size is not None
    assert size <= 100.0  # capped at 10%
    assert size > 0


def test_kelly_negative_returns_none():
    tb = _brain()
    # confidence=0.20, entry=0.80 → b=0.25, kelly=(0.20*0.25 - 0.80)/0.25 < 0
    size = tb._kelly_size(confidence=0.20, entry_price=0.80, balance=1000.0)
    assert size is None


def test_kelly_cap_never_exceeded():
    tb = _brain()
    # Even extremely high confidence should not exceed 10% cap
    size = tb._kelly_size(confidence=0.99, entry_price=0.10, balance=1000.0)
    assert size is not None
    assert size <= 100.0


# ── Graduation ─────────────────────────────────────────────────────────────
def test_graduation_all_pass(temp_db):
    import sqlite3
    from pathlib import Path
    conn = sqlite3.connect(temp_db)
    # Insert 14 days of positive returns
    balance = 1000.0
    for i in range(14):
        r = 0.02
        balance *= (1 + r)
        conn.execute("""
            INSERT INTO daily_pnl (date, balance, roi_pct, open_positions, total_trades, win_rate)
            VALUES (?, ?, ?, 0, 0, 0.0)
        """, (f"2026-01-{i+1:02d}", balance, r))
    # Insert wins: 12 wins, 6 losses → 66% win rate
    for i in range(12):
        conn.execute("""
            INSERT INTO paper_trades (market_id, question, direction, shares, entry_price,
             amount_usd, pnl, status, opened_at, closed_at)
            VALUES ('m', 'q', 'YES', 10, 0.5, 5, 2.5, 'closed_win', '2026-01-01', '2026-01-02')
        """)
    for i in range(6):
        conn.execute("""
            INSERT INTO paper_trades (market_id, question, direction, shares, entry_price,
             amount_usd, pnl, status, opened_at, closed_at)
            VALUES ('m', 'q', 'YES', 10, 0.5, 5, -1.0, 'closed_loss', '2026-01-01', '2026-01-02')
        """)
    conn.commit(); conn.close()

    import sys
    for mod in list(sys.modules.keys()):
        if "dashboard" in mod or "paper_wallet" in mod:
            del sys.modules[mod]
    import scripts.mirofish.dashboard as dash
    status = dash.check_graduation()
    assert status["has_minimum_history"] is True
    assert status["win_rate"] > 0.55
    assert status["roi_7d"] > 0
    assert status["ready"] is True


def test_graduation_fails_insufficient_history(temp_db):
    import sqlite3
    conn = sqlite3.connect(temp_db)
    for i in range(7):  # Only 7 days, need 14
        conn.execute("""
            INSERT INTO daily_pnl (date, balance, roi_pct, open_positions, total_trades, win_rate)
            VALUES (?, ?, ?, 0, 0, 0.0)
        """, (f"2026-01-{i+1:02d}", 1020.0, 0.02))
    conn.commit(); conn.close()

    import sys
    for mod in list(sys.modules.keys()):
        if "dashboard" in mod or "paper_wallet" in mod:
            del sys.modules[mod]
    import scripts.mirofish.dashboard as dash
    status = dash.check_graduation()
    assert status["has_minimum_history"] is False
    assert status["ready"] is False


def test_graduation_fails_low_win_rate(temp_db):
    import sqlite3
    conn = sqlite3.connect(temp_db)
    balance = 1000.0
    for i in range(14):
        r = 0.01
        balance *= (1 + r)
        conn.execute("""
            INSERT INTO daily_pnl (date, balance, roi_pct, open_positions, total_trades, win_rate)
            VALUES (?, ?, ?, 0, 0, 0.0)
        """, (f"2026-01-{i+1:02d}", balance, r))
    # 50% win rate — below 55% threshold
    for _ in range(5):
        conn.execute("""
            INSERT INTO paper_trades (market_id, question, direction, shares, entry_price,
             amount_usd, pnl, status, opened_at, closed_at)
            VALUES ('m', 'q', 'YES', 10, 0.5, 5, 2, 'closed_win', '2026-01-01', '2026-01-02')
        """)
        conn.execute("""
            INSERT INTO paper_trades (market_id, question, direction, shares, entry_price,
             amount_usd, pnl, status, opened_at, closed_at)
            VALUES ('m', 'q', 'YES', 10, 0.5, 5, -1, 'closed_loss', '2026-01-01', '2026-01-02')
        """)
    conn.commit(); conn.close()

    import sys
    for mod in list(sys.modules.keys()):
        if "dashboard" in mod or "paper_wallet" in mod:
            del sys.modules[mod]
    import scripts.mirofish.dashboard as dash
    status = dash.check_graduation()
    assert status["ready"] is False


def test_manual_bet_enforces_position_cap(temp_db):
    import sys
    for mod in list(sys.modules.keys()):
        if "paper_wallet" in mod:
            del sys.modules[mod]
    import scripts.mirofish.paper_wallet as pw
    from types import SimpleNamespace
    decision = SimpleNamespace(
        market_id="manual1", question="manual bet", direction="YES",
        amount_usd=150.0,  # 15% — over cap
        entry_price=0.50, shares=300.0,
        confidence=1.0, reasoning="manual via /bet", strategy="manual"
    )
    result = pw.execute_trade(decision)
    assert result is None  # Rejected even for manual trades
```

- [ ] **Step 4.2: Run tests — expect failures**

```bash
cd ~/openclaw
python -m pytest scripts/mirofish/tests/test_positions.py -v 2>&1 | head -20
# Expected: ImportError — trading_brain not yet written
```

- [ ] **Step 4.3: Write `trading_brain.py`**

```python
#!/usr/bin/env python3
"""
Mirofish trading brain — arbitrage detection + Ollama market analysis.
Produces TradeDecision objects for simulator to execute.
"""
from __future__ import annotations
import os
import json
import re
import requests
from dataclasses import dataclass
from typing import Any

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
MIROFISH_MODEL  = os.environ.get("MIROFISH_MODEL", "qwen3:30b")
MAX_POSITION_PCT = float(os.environ.get("MIROFISH_MAX_POSITION_PCT", "0.10"))
ARB_THRESHOLD = 0.03
ARB_POSITION_PCT = 0.05  # Fixed 5% of portfolio for arb trades


@dataclass
class TradeDecision:
    market_id:   str
    question:    str
    direction:   str    # YES | NO
    confidence:  float
    reasoning:   str
    strategy:    str
    amount_usd:  float
    entry_price: float
    shares:      float


def _kelly_size(confidence: float, entry_price: float, balance: float) -> float | None:
    """
    Correct Kelly criterion for prediction markets.
    b = payout odds (e.g., entry=0.30 → b=2.33x)
    kelly = (confidence * b - (1 - confidence)) / b
    Returns None if kelly ≤ 0 (negative edge).
    """
    if entry_price <= 0 or entry_price >= 1:
        return None
    b = (1.0 / entry_price) - 1.0
    kelly = (confidence * b - (1.0 - confidence)) / b
    if kelly <= 0:
        return None
    return min(kelly * balance, MAX_POSITION_PCT * balance)


def _check_arbitrage(market: dict) -> TradeDecision | None:
    """
    Pure-math arbitrage check. No Ollama needed.
    Flags if abs(yes + no - 1.0) > ARB_THRESHOLD.
    Single-leg: buy whichever side is underpriced.
    """
    yes_p = market.get("yes_price", 0) or 0
    no_p  = market.get("no_price", 0) or 0
    gap = abs(yes_p + no_p - 1.0)
    if gap <= ARB_THRESHOLD:
        return None

    # Buy the underpriced side
    if yes_p < 0.50:
        direction, entry_price = "YES", yes_p
    else:
        direction, entry_price = "NO", no_p

    confidence = min(gap / 0.10, 1.0)
    reasoning = (f"Arbitrage: YES={yes_p:.3f} + NO={no_p:.3f} = {yes_p+no_p:.3f} "
                 f"(gap={gap:.3f} > {ARB_THRESHOLD})")

    return TradeDecision(
        market_id=market["market_id"],
        question=market["question"],
        direction=direction,
        confidence=confidence,
        reasoning=reasoning,
        strategy="arbitrage",
        amount_usd=0.0,  # sized by caller using ARB_POSITION_PCT
        entry_price=entry_price,
        shares=0.0,
    )


def _call_ollama(prompt: str) -> str:
    """Call Ollama and return the response text."""
    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": MIROFISH_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            },
            timeout=180,
        )
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "")
    except Exception as e:
        print(f"[mirofish/brain] Ollama error: {e}")
        return ""


def _extract_json(text: str) -> list[dict]:
    """Extract JSON array from LLM response with regex fallback."""
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Regex fallback: find [...] block
    m = re.search(r'\[.*?\]', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return []


def analyze(markets: list[dict], wallet: dict[str, Any]) -> list[TradeDecision]:
    """
    Main entry point. Returns list of TradeDecisions sorted by confidence desc.
    Step 1: Arbitrage fast-path (no Ollama).
    Step 2: Ollama analysis for momentum/contrarian/news_catalyst.
    """
    balance = wallet.get("balance", 1000.0)
    decisions: list[TradeDecision] = []

    # Step 1: Arbitrage fast-path
    arb_market_ids = set()
    for market in markets:
        arb = _check_arbitrage(market)
        if arb:
            arb.amount_usd = ARB_POSITION_PCT * balance
            arb.shares = arb.amount_usd / arb.entry_price if arb.entry_price > 0 else 0
            decisions.append(arb)
            arb_market_ids.add(market["market_id"])

    # Step 2: Ollama analysis for non-arb markets
    non_arb = [m for m in markets if m["market_id"] not in arb_market_ids]
    if not non_arb:
        return sorted(decisions, key=lambda d: d.confidence, reverse=True)

    open_positions = wallet.get("open_positions", 0)
    market_lines = "\n".join(
        f'- [{m["market_id"]}] {m["question"][:80]} | YES={m["yes_price"]:.2f} NO={m["no_price"]:.2f} vol=${m["volume"]:,.0f}'
        for m in non_arb[:30]
    )

    prompt = f"""You are Mirofish, a prediction market paper trading system.
Current portfolio: ${balance:.2f} balance, {open_positions} open positions.

Analyze these Polymarket markets and identify trading opportunities using:
- momentum: YES price trending upward strongly (>5% over recent snapshots)
- contrarian: YES price moved >20% in one direction (likely overreaction)
- news_catalyst: you know of recent news that changes the true probability significantly

For each opportunity, calculate:
- Expected true probability vs current market price
- Confidence (0.0-1.0) in your edge
- Direction (YES or NO)
- One-sentence reasoning

Markets:
{market_lines}

Return ONLY a JSON array (no explanation), max 5 opportunities:
[
  {{
    "market_id": "...",
    "direction": "YES|NO",
    "confidence": 0.0-1.0,
    "strategy": "momentum|contrarian|news_catalyst",
    "reasoning": "one sentence",
    "entry_price": 0.0
  }}
]
Only include opportunities where you have genuine edge (confidence > 0.6).
If no clear opportunities, return [].
"""

    raw = _call_ollama(prompt)
    parsed = _extract_json(raw)

    for item in parsed:
        market_id  = item.get("market_id", "")
        direction  = item.get("direction", "").upper()
        confidence = float(item.get("confidence", 0))
        strategy   = item.get("strategy", "news_catalyst")
        reasoning  = item.get("reasoning", "")
        entry_price = float(item.get("entry_price", 0))

        if not market_id or direction not in ("YES", "NO") or confidence <= 0:
            continue

        # Look up entry price from market if not provided by LLM
        if entry_price <= 0:
            for m in non_arb:
                if m["market_id"] == market_id:
                    entry_price = m["yes_price"] if direction == "YES" else m["no_price"]
                    break

        if entry_price <= 0 or entry_price >= 1:
            continue

        amount = _kelly_size(confidence, entry_price, balance)
        if amount is None:
            continue  # negative edge — skip

        question = next((m["question"] for m in non_arb if m["market_id"] == market_id), "")
        decisions.append(TradeDecision(
            market_id=market_id, question=question, direction=direction,
            confidence=confidence, reasoning=reasoning, strategy=strategy,
            amount_usd=amount, entry_price=entry_price,
            shares=amount / entry_price,
        ))

    return sorted(decisions, key=lambda d: d.confidence, reverse=True)
```

- [ ] **Step 4.4: Run tests**

```bash
cd ~/openclaw
python -m pytest scripts/mirofish/tests/test_positions.py::test_arbitrage_detected_when_gap_exceeds_threshold \
    scripts/mirofish/tests/test_positions.py::test_arbitrage_detected_buy_yes_when_yes_underpriced \
    scripts/mirofish/tests/test_positions.py::test_arbitrage_not_detected_below_threshold \
    scripts/mirofish/tests/test_positions.py::test_kelly_positive_returns_within_cap \
    scripts/mirofish/tests/test_positions.py::test_kelly_negative_returns_none \
    scripts/mirofish/tests/test_positions.py::test_kelly_cap_never_exceeded \
    scripts/mirofish/tests/test_positions.py::test_manual_bet_enforces_position_cap \
    -v
# Expected: all PASS (graduation tests need dashboard.py — skip those for now)
```

- [ ] **Step 4.5: Commit**

```bash
git add scripts/mirofish/trading_brain.py scripts/mirofish/tests/test_positions.py
git commit -m "feat(mirofish): trading_brain — arb fast-path, Kelly sizing, Ollama analysis"
```

---

## Task 5: `dashboard.py` — Graduation + Reports + Telegram Formatting

**Files:**
- Create: `scripts/mirofish/dashboard.py`

- [ ] **Step 5.1: Write `dashboard.py`**

```python
#!/usr/bin/env python3
"""
Mirofish dashboard — graduation checks, report generation, Telegram message formatting.
"""
from __future__ import annotations
import os
import sqlite3
import datetime
from pathlib import Path
from statistics import mean, stdev
from typing import Any

DB_PATH = Path(os.environ.get("CLAWMSON_DB_PATH", Path.home() / ".openclaw" / "clawmson.db"))
REPORTS_DIR = Path(os.environ.get("MIROFISH_REPORTS_DIR",
                                   Path.home() / "openclaw" / "mirofish" / "reports"))
MIN_HISTORY_DAYS = int(os.environ.get("MIROFISH_MIN_HISTORY_DAYS", "14"))

WIN_RATE_THRESHOLD  = 0.55
SHARPE_THRESHOLD    = 1.0
MAX_DRAWDOWN_LIMIT  = 0.25
ROI_7D_THRESHOLD    = 0.0


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def check_graduation() -> dict[str, Any]:
    """
    Evaluate all graduation criteria. Returns GraduationStatus dict.
    ready=True only if all criteria pass AND history >= MIN_HISTORY_DAYS.
    """
    with _get_conn() as conn:
        all_pnl = conn.execute(
            "SELECT date, balance, roi_pct FROM daily_pnl ORDER BY date ASC"
        ).fetchall()
        closed = conn.execute(
            "SELECT status FROM paper_trades WHERE status != 'open'"
        ).fetchall()

    history_days = len(all_pnl)
    has_min_history = history_days >= MIN_HISTORY_DAYS

    # ROI (last 7 days) — sum of roi_pct as approximation
    last7 = all_pnl[-7:] if len(all_pnl) >= 7 else all_pnl
    roi_7d = sum(r["roi_pct"] for r in last7 if r["roi_pct"] is not None)

    # Win rate
    total_closed = len(closed)
    wins = sum(1 for t in closed if t["status"] == "closed_win")
    win_rate = wins / total_closed if total_closed > 0 else 0.0

    # Sharpe (unannualized mean/std)
    returns = [r["roi_pct"] for r in all_pnl if r["roi_pct"] is not None]
    sharpe = None
    if len(returns) >= MIN_HISTORY_DAYS:
        s = stdev(returns)
        if s > 0:
            sharpe = mean(returns) / s

    # Max drawdown
    balances = [r["balance"] for r in all_pnl]
    max_dd = 0.0
    if balances:
        peak = balances[0]
        for b in balances:
            peak = max(peak, b)
            if peak > 0:
                max_dd = max(max_dd, (peak - b) / peak)

    criteria = {
        "min_history": has_min_history,
        "roi_7d_positive": roi_7d > ROI_7D_THRESHOLD,
        "win_rate_55pct": win_rate > WIN_RATE_THRESHOLD,
        "sharpe_above_1": sharpe is not None and sharpe > SHARPE_THRESHOLD,
        "drawdown_below_25pct": max_dd < MAX_DRAWDOWN_LIMIT,
    }
    ready = has_min_history and all(criteria.values())

    return {
        "ready": ready,
        "has_minimum_history": has_min_history,
        "history_days": history_days,
        "roi_7d": roi_7d,
        "win_rate": win_rate,
        "sharpe_all_time": sharpe,
        "max_drawdown": max_dd,
        "criteria": criteria,
    }


def maybe_snapshot(chat_id_for_notify: str | None = None) -> bool:
    """
    Write daily_pnl row if not already written today.
    Returns True if snapshot was written (first call of the day).
    Fires daily Telegram digest if chat_id_for_notify is set.
    """
    today = datetime.date.today().isoformat()
    with _get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM daily_pnl WHERE date=?", (today,)
        ).fetchone()

    if existing:
        return False  # Already snapshotted today

    # Import here to avoid circular deps
    import scripts.mirofish.paper_wallet as pw
    import scripts.mirofish.polymarket_feed as feed

    prices = feed.get_latest_prices()
    state = pw.get_state()

    # Compute roi_pct: (today_balance - prev_balance) / prev_balance
    with _get_conn() as conn:
        prev_row = conn.execute(
            "SELECT balance FROM daily_pnl ORDER BY date DESC LIMIT 1"
        ).fetchone()
    prev_balance = prev_row["balance"] if prev_row else state["starting_balance"]
    roi_pct = (state["balance"] - prev_balance) / prev_balance if prev_balance > 0 else 0.0

    with _get_conn() as conn:
        open_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM paper_trades WHERE status='open'"
        ).fetchone()["cnt"]
        total_trades = conn.execute(
            "SELECT COUNT(*) as cnt FROM paper_trades WHERE status != 'open'"
        ).fetchone()["cnt"]

        realized_pnl = conn.execute(
            "SELECT COALESCE(SUM(pnl), 0) as s FROM paper_trades WHERE status != 'open'"
        ).fetchone()["s"]

        unrealized_pnl = state["balance"] - state["starting_balance"] - realized_pnl

        conn.execute("""
            INSERT OR IGNORE INTO daily_pnl
            (date, balance, open_positions, realized_pnl, unrealized_pnl,
             total_trades, win_rate, roi_pct)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (today, state["balance"], open_count, realized_pnl,
              unrealized_pnl, total_trades, state["win_rate"], roi_pct))

    # Generate report
    report_path = generate_report("daily")

    # Check graduation and notify once
    grad = check_graduation()
    if grad["ready"]:
        with _get_conn() as conn:
            already_notified = conn.execute(
                "SELECT value FROM context WHERE chat_id='mirofish' AND key='graduation_notified'"
            ).fetchone()
        if not already_notified:
            with _get_conn() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO context (chat_id, key, value)
                    VALUES ('mirofish', 'graduation_notified', '1')
                """)
            if chat_id_for_notify:
                _send_telegram(chat_id_for_notify,
                    "MIROFISH: READY FOR LIVE TRADING\n"
                    f"7d ROI: {grad['roi_7d']*100:.1f}% | "
                    f"Win: {grad['win_rate']*100:.0f}% | "
                    f"Sharpe: {grad['sharpe_all_time']:.2f} | "
                    f"MaxDD: {grad['max_drawdown']*100:.1f}%")

    # Daily digest
    if chat_id_for_notify:
        pnl_today = state["balance"] - prev_balance
        pct_today = roi_pct * 100
        sign = "+" if pnl_today >= 0 else ""
        msg = (
            f"Mirofish Daily — {today}\n"
            f"P&L today: {sign}${pnl_today:.2f} ({sign}{pct_today:.1f}%)\n"
            f"Open positions: {open_count}\n"
            f"Win rate: {state['win_rate']*100:.0f}%\n"
            f"Portfolio: ${state['balance']:.2f}"
        )
        if grad["ready"]:
            msg = "READY FOR LIVE TRADING\n\n" + msg
        _send_telegram(chat_id_for_notify, msg)

    return True


def _send_telegram(chat_id: str, message: str):
    """Send via notify-telegram.sh (consistent with other cron scripts)."""
    import subprocess
    script = Path.home() / "openclaw" / "scripts" / "notify-telegram.sh"
    if script.exists():
        subprocess.run([str(script), message], timeout=30, capture_output=True)


def generate_report(period: str = "daily") -> Path:
    """Generate markdown report. Returns path to written file."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    import scripts.mirofish.paper_wallet as pw
    state = pw.get_state()
    grad = check_graduation()
    today = datetime.date.today().isoformat()

    with _get_conn() as conn:
        recent_trades = conn.execute("""
            SELECT market_id, question, direction, amount_usd, pnl, status, strategy,
                   opened_at, closed_at
            FROM paper_trades ORDER BY opened_at DESC LIMIT 10
        """).fetchall()
        last7_pnl = conn.execute("""
            SELECT date, balance, roi_pct FROM daily_pnl
            ORDER BY date DESC LIMIT 7
        """).fetchall()

    lines = []
    if grad["ready"]:
        lines.append("# READY FOR LIVE TRADING\n")
    lines.append(f"# Mirofish {period.title()} Report — {today}\n")
    lines.append(f"**Portfolio:** ${state['balance']:.2f} "
                 f"(started ${state['starting_balance']:.2f})\n")
    lines.append(f"**Win rate:** {state['win_rate']*100:.0f}%  |  "
                 f"**Open positions:** {state['open_positions']}\n")

    if state["sharpe_ratio"] is not None:
        lines.append(f"**Sharpe:** {state['sharpe_ratio']:.2f}  |  "
                     f"**Max drawdown:** {state['max_drawdown']*100:.1f}%\n")

    lines.append("\n## Graduation Status\n")
    lines.append(f"- Min history (14d): {'✓' if grad['criteria']['min_history'] else '✗'} "
                 f"({grad['history_days']} days)\n")
    lines.append(f"- ROI 7d > 0%: {'✓' if grad['criteria']['roi_7d_positive'] else '✗'} "
                 f"({grad['roi_7d']*100:.2f}%)\n")
    lines.append(f"- Win rate > 55%: {'✓' if grad['criteria']['win_rate_55pct'] else '✗'} "
                 f"({grad['win_rate']*100:.0f}%)\n")
    lines.append(f"- Sharpe > 1.0: {'✓' if grad['criteria']['sharpe_above_1'] else '✗'} "
                 f"({grad['sharpe_all_time']:.2f if grad['sharpe_all_time'] else 'N/A'})\n")
    lines.append(f"- Drawdown < 25%: {'✓' if grad['criteria']['drawdown_below_25pct'] else '✗'} "
                 f"({grad['max_drawdown']*100:.1f}%)\n")

    if last7_pnl:
        lines.append("\n## 7-Day P&L\n")
        for row in reversed(last7_pnl):
            r = row["roi_pct"] or 0
            sign = "+" if r >= 0 else ""
            lines.append(f"- {row['date']}: ${row['balance']:.2f} ({sign}{r*100:.2f}%)\n")

    if recent_trades:
        lines.append("\n## Recent Trades\n")
        for t in recent_trades:
            pnl_str = f"+${t['pnl']:.2f}" if (t['pnl'] or 0) >= 0 else f"-${abs(t['pnl'] or 0):.2f}"
            lines.append(f"- [{t['status']}] {t['direction']} ${t['amount_usd']:.0f} "
                         f"on {t['question'][:50]}  {pnl_str}  [{t['strategy']}]\n")

    report_path = REPORTS_DIR / f"mirofish-{period}-{today}.md"
    report_path.write_text("".join(lines))
    return report_path


def format_portfolio_message() -> str:
    import scripts.mirofish.paper_wallet as pw
    state = pw.get_state()
    positions = pw.get_open_positions()
    lines = [f"Portfolio: ${state['balance']:.2f}"]
    lines.append(f"Open positions: {len(positions)}")
    for p in positions[:5]:
        lines.append(f"  {p['direction']} ${p['amount_usd']:.0f} — {p['question'][:40]}")
    if len(positions) > 5:
        lines.append(f"  ...and {len(positions)-5} more")
    return "\n".join(lines)


def format_pnl_message() -> str:
    import scripts.mirofish.paper_wallet as pw
    state = pw.get_state()
    grad = check_graduation()
    summary = pw.get_pnl_summary(7)
    roi_7d = grad["roi_7d"]
    sign = "+" if roi_7d >= 0 else ""
    lines = [
        f"7d ROI: {sign}{roi_7d*100:.2f}%",
        f"Win rate: {state['win_rate']*100:.0f}% ({state['total_trades']} closed trades)",
        f"Balance: ${state['balance']:.2f}",
    ]
    if state["sharpe_ratio"]:
        lines.append(f"Sharpe: {state['sharpe_ratio']:.2f}  |  Drawdown: {state['max_drawdown']*100:.1f}%")
    if grad["ready"]:
        lines.insert(0, "READY FOR LIVE TRADING")
    elif grad["has_minimum_history"]:
        failing = [k for k, v in grad["criteria"].items() if not v]
        lines.append(f"Graduation: failing {', '.join(failing)}")
    else:
        lines.append(f"Graduation: {grad['history_days']}/{MIN_HISTORY_DAYS} days history")
    return "\n".join(lines)


def format_trades_message(limit: int = 10) -> str:
    with _get_conn() as conn:
        trades = conn.execute("""
            SELECT direction, amount_usd, question, pnl, status, strategy, opened_at
            FROM paper_trades ORDER BY opened_at DESC LIMIT ?
        """, (limit,)).fetchall()
    if not trades:
        return "No trades yet."
    lines = []
    for t in trades:
        pnl_str = ""
        if t["pnl"] is not None:
            sign = "+" if t["pnl"] >= 0 else ""
            pnl_str = f" {sign}${t['pnl']:.2f}"
        lines.append(f"[{t['status']}] {t['direction']} ${t['amount_usd']:.0f}{pnl_str} "
                     f"— {t['question'][:45]} [{t['strategy']}]")
    return "\n".join(lines)
```

- [ ] **Step 5.2: Run graduation tests**

```bash
cd ~/openclaw
python -m pytest scripts/mirofish/tests/test_positions.py -v
# Expected: all tests PASS including graduation tests
```

- [ ] **Step 5.3: Create reports directory**

```bash
mkdir -p ~/openclaw/mirofish/reports
```

- [ ] **Step 5.4: Commit**

```bash
git add scripts/mirofish/dashboard.py
git commit -m "feat(mirofish): dashboard — graduation check, report generation, Telegram formatters"
```

---

## Task 6: `simulator.py` — Complete Orchestrator

**Files:**
- Modify: `scripts/mirofish/simulator.py` (implement `--run` and `--report`)

- [ ] **Step 6.1: Replace simulator.py stub with full implementation**

```python
#!/usr/bin/env python3
"""
Mirofish simulator — cron orchestrator for paper trading.
CLI: python3 simulator.py --run | --migrate | --report
"""
from __future__ import annotations
import argparse
import os
import sqlite3
import datetime
from pathlib import Path

DB_PATH = Path(os.environ.get("CLAWMSON_DB_PATH", Path.home() / ".openclaw" / "clawmson.db"))
JORDAN_CHAT_ID = os.environ.get("JORDAN_TELEGRAM_CHAT_ID", "")


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS market_data (
    id           INTEGER PRIMARY KEY,
    market_id    TEXT NOT NULL,
    question     TEXT NOT NULL,
    category     TEXT,
    yes_price    REAL,
    no_price     REAL,
    volume       REAL,
    end_date     TEXT,
    fetched_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_market_data_market_time
    ON market_data(market_id, fetched_at);

CREATE TABLE IF NOT EXISTS paper_trades (
    id           INTEGER PRIMARY KEY,
    market_id    TEXT NOT NULL,
    question     TEXT NOT NULL,
    direction    TEXT NOT NULL,
    shares       REAL NOT NULL,
    entry_price  REAL NOT NULL,
    exit_price   REAL,
    amount_usd   REAL NOT NULL,
    pnl          REAL,
    status       TEXT NOT NULL,
    confidence   REAL NOT NULL DEFAULT 1.0,
    reasoning    TEXT NOT NULL DEFAULT '',
    strategy     TEXT NOT NULL DEFAULT 'manual',
    opened_at    TEXT NOT NULL,
    closed_at    TEXT
);

CREATE TABLE IF NOT EXISTS daily_pnl (
    id              INTEGER PRIMARY KEY,
    date            TEXT NOT NULL UNIQUE,
    balance         REAL NOT NULL,
    open_positions  INTEGER,
    realized_pnl    REAL,
    unrealized_pnl  REAL,
    total_trades    INTEGER,
    win_rate        REAL,
    roi_pct         REAL
);

INSERT OR IGNORE INTO context (chat_id, key, value)
VALUES ('mirofish', 'starting_balance', '1000.00');
"""


def migrate():
    """Create mirofish tables. Idempotent."""
    with _get_conn() as conn:
        conn.executescript(MIGRATION_SQL)
    print(f"[mirofish] Migration complete. DB: {DB_PATH}")


def run_loop():
    """Full simulation loop: fetch → analyze → trade → stops → snapshot."""
    import scripts.mirofish.polymarket_feed as feed
    import scripts.mirofish.paper_wallet as wallet
    import scripts.mirofish.trading_brain as brain
    import scripts.mirofish.dashboard as dash

    print(f"[mirofish] Run loop starting — {datetime.datetime.utcnow().isoformat()}")

    # 1. Fetch market data
    markets = feed.fetch_markets()
    if not markets:
        print("[mirofish] No markets available (API down + cache stale). Skipping trades.")
    else:
        # 2. Get wallet state
        state = wallet.get_state()
        print(f"[mirofish] Wallet: ${state['balance']:.2f} | "
              f"Positions: {state['open_positions']} | "
              f"Win rate: {state['win_rate']*100:.0f}%")

        # 3. Analyze markets
        decisions = brain.analyze(markets, state)
        print(f"[mirofish] Brain returned {len(decisions)} trade decisions")

        # 4. Execute trades
        for d in decisions:
            result = wallet.execute_trade(d)
            if result:
                print(f"[mirofish] Executed: {d.direction} ${d.amount_usd:.0f} "
                      f"on '{d.question[:50]}' [{d.strategy}]")
            else:
                print(f"[mirofish] Rejected: {d.market_id} (cap or kelly)")

    # 5. Check stops (always runs, even if API is down)
    current_prices = feed.get_latest_prices()
    closed = wallet.check_stops(current_prices)
    for c in closed:
        sign = "+" if (c["pnl"] or 0) >= 0 else ""
        print(f"[mirofish] Stop closed: {c['market_id']} → {c['status']} "
              f"{sign}${c['pnl']:.2f}")

    # 6. Daily snapshot (first run of the day only)
    snapshotted = dash.maybe_snapshot(chat_id_for_notify=JORDAN_CHAT_ID or None)
    if snapshotted:
        print("[mirofish] Daily snapshot written and digest sent")

    print(f"[mirofish] Run complete — {datetime.datetime.utcnow().isoformat()}")


def main():
    # Load .env
    env_file = Path.home() / "openclaw" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    parser = argparse.ArgumentParser(description="Mirofish paper trading simulator")
    parser.add_argument("--migrate", action="store_true", help="Create DB tables")
    parser.add_argument("--run", action="store_true", help="Run simulation loop")
    parser.add_argument("--report", action="store_true", help="Generate report only")
    args = parser.parse_args()

    if args.migrate:
        migrate()
    elif args.run:
        run_loop()
    elif args.report:
        import scripts.mirofish.dashboard as dash
        path = dash.generate_report("daily")
        print(f"[mirofish] Report: {path}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
```

- [ ] **Step 6.2: Smoke test `--run` (dry run with temp DB)**

```bash
cd ~/openclaw
CLAWMSON_DB_PATH=/tmp/mirofish-run-test.db python3 scripts/mirofish/simulator.py --migrate
CLAWMSON_DB_PATH=/tmp/mirofish-run-test.db python3 scripts/mirofish/simulator.py --run 2>&1
# Expected: log lines showing fetch → analyze → (0 or more trades) → stops → snapshot
# Ollama call may take 60-180s. No errors.
rm /tmp/mirofish-run-test.db
```

- [ ] **Step 6.3: Run full test suite to confirm no regressions**

```bash
cd ~/openclaw
python -m pytest scripts/mirofish/tests/ -v
# Expected: all tests PASS
```

- [ ] **Step 6.4: Commit**

```bash
git add scripts/mirofish/simulator.py
git commit -m "feat(mirofish): simulator orchestrator — --run, --migrate, --report CLI"
```

---

## Task 7: Telegram Integration

**Files:**
- Modify: `scripts/telegram-dispatcher.py`

- [ ] **Step 7.1: Read the existing dispatcher and check notify-telegram.sh**

Read `scripts/telegram-dispatcher.py` around the `# ── New command handlers ──` block and the `/context` routing block to find the exact insertion points (line numbers may differ from comments in this plan — search for the string, don't trust line numbers).

Also check `notify-telegram.sh`'s calling convention:
```bash
head -20 ~/openclaw/scripts/notify-telegram.sh
```
If it reads `JORDAN_TELEGRAM_CHAT_ID` from the environment, the `_send_telegram()` call in `dashboard.py` is correct as written. If it expects `chat_id` as a positional argument (`$1`), update `_send_telegram()` to pass it: `subprocess.run([str(script), chat_id, message], ...)`.

- [ ] **Step 7.2: Add mirofish import and four command handlers**

Find the block `# ── New command handlers ──` (around line 300) and add after it:

```python
# ── Mirofish paper trading commands ──────────────────────────────────────
def handle_portfolio(chat_id: str):
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        import scripts.mirofish.dashboard as dash
        send(chat_id, dash.format_portfolio_message())
    except Exception as e:
        send(chat_id, f"Portfolio error: {e}")


def handle_pnl(chat_id: str):
    try:
        import scripts.mirofish.dashboard as dash
        send(chat_id, dash.format_pnl_message())
    except Exception as e:
        send(chat_id, f"P&L error: {e}")


def handle_trades(chat_id: str):
    try:
        import scripts.mirofish.dashboard as dash
        send(chat_id, dash.format_trades_message())
    except Exception as e:
        send(chat_id, f"Trades error: {e}")


def handle_bet(chat_id: str, text: str):
    """
    /bet [market_id] [YES|NO] [amount]
    Example: /bet 0xabc123 YES 50
    """
    parts = text.split()
    if len(parts) < 3:
        send(chat_id, "Usage: /bet [market_id] [YES|NO] [amount]\nExample: /bet 0xabc YES 50")
        return
    market_id = parts[0]
    direction = parts[1].upper()
    if direction not in ("YES", "NO"):
        send(chat_id, "Direction must be YES or NO")
        return
    try:
        amount = float(parts[2])
    except ValueError:
        send(chat_id, f"Invalid amount: {parts[2]}")
        return

    try:
        import scripts.mirofish.paper_wallet as pw
        import scripts.mirofish.polymarket_feed as feed
        from types import SimpleNamespace

        # Look up current price for the market
        prices = feed.get_latest_prices()
        p = prices.get(market_id, {})
        if direction == "YES":
            entry_price = p.get("yes_price", 0.50)
        else:
            entry_price = p.get("no_price", 0.50)

        shares = amount / entry_price if entry_price > 0 else 0

        decision = SimpleNamespace(
            market_id=market_id,
            question=f"Manual bet on {market_id}",
            direction=direction,
            amount_usd=amount,
            entry_price=entry_price,
            shares=shares,
            confidence=1.0,
            reasoning="manual via /bet",
            strategy="manual",
        )
        result = pw.execute_trade(decision)
        if result:
            send(chat_id,
                 f"Paper trade executed\n"
                 f"{direction} ${amount:.2f} on {market_id}\n"
                 f"Entry: ${entry_price:.3f} | Shares: {shares:.1f}")
        else:
            state = pw.get_state()
            cap = state["balance"] * 0.10
            send(chat_id,
                 f"Trade rejected — ${amount:.2f} exceeds 10% position cap "
                 f"(max ${cap:.2f} at current balance ${state['balance']:.2f})")
    except Exception as e:
        send(chat_id, f"Bet error: {e}")
```

- [ ] **Step 7.3: Add the four routes in the slash command routing section**

Find the block `if lower == "/context":` and add after the existing slash routes (before the media handling section):

```python
        if lower == "/portfolio":
            handle_portfolio(chat_id)
            return
        if lower == "/pnl":
            handle_pnl(chat_id)
            return
        if lower == "/trades":
            handle_trades(chat_id)
            return
        if lower.startswith("/bet ") or lower == "/bet":
            bet_args = text[len("/bet"):].strip()
            handle_bet(chat_id, bet_args)
            return
```

- [ ] **Step 7.4: Verify the dispatcher still imports cleanly**

```bash
cd ~/openclaw
python3 -c "import scripts.telegram_dispatcher" 2>&1 || \
python3 -c "
import ast, sys
with open('scripts/telegram-dispatcher.py') as f:
    src = f.read()
try:
    ast.parse(src)
    print('Syntax OK')
except SyntaxError as e:
    print(f'Syntax error: {e}')
    sys.exit(1)
"
# Expected: Syntax OK
```

- [ ] **Step 7.5: Commit**

```bash
git add scripts/telegram-dispatcher.py
git commit -m "feat(mirofish): Telegram commands — /portfolio /pnl /trades /bet"
```

---

## Task 8: Agent Config Doc

**Files:**
- Create: `agents/configs/mirofish-trader.md`

- [ ] **Step 8.1: Write agent config**

```markdown
# Agent Config: Mirofish Trader

**Role:** Paper trading simulator for Polymarket prediction markets
**Status:** Active (Phase 4)
**Mode:** Paper trading only — no real capital until graduation criteria met

---

## What It Does

Runs every 30 minutes via cron. Fetches live Polymarket markets, analyzes them
for trading opportunities using qwen3:30b, executes paper trades against a fake
$1,000 wallet, and manages positions (stop-loss / take-profit). Generates daily
P&L reports and fires Telegram digests.

Replaces: `cron-prediction-market.sh`

---

## Pipeline

```
polymarket_feed.fetch_markets()
  → paper_wallet.get_state()
  → trading_brain.analyze()     # arb fast-path + qwen3:30b
  → paper_wallet.execute_trade()
  → paper_wallet.check_stops()
  → dashboard.maybe_snapshot()
```

---

## Key Files

| File | Purpose |
|------|---------|
| `scripts/mirofish/simulator.py` | CLI orchestrator (`--run`, `--migrate`, `--report`) |
| `scripts/mirofish/paper_wallet.py` | Wallet state, P&L math, stop management |
| `scripts/mirofish/polymarket_feed.py` | Polymarket API + SQLite cache |
| `scripts/mirofish/trading_brain.py` | Arbitrage detection, Kelly sizing, Ollama |
| `scripts/mirofish/dashboard.py` | Graduation check, reports, Telegram formatting |
| `~/.openclaw/clawmson.db` | DB: `market_data`, `paper_trades`, `daily_pnl` tables |
| `~/openclaw/mirofish/reports/` | Generated markdown reports |

---

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/portfolio` | Current balance, open positions, unrealized P&L |
| `/pnl` | 7-day P&L, win rate, ROI, graduation status |
| `/trades` | Last 10 trades |
| `/bet [market_id] [YES\|NO] [amount]` | Manual paper trade |

---

## Trading Strategies

| Strategy | Signal | Method |
|----------|--------|--------|
| arbitrage | `abs(YES + NO - 1.0) > 0.03` | Pure math, 5% fixed sizing |
| momentum | YES price up >5% over 3 snapshots | qwen3:30b |
| contrarian | YES price moved >20% in one window | qwen3:30b |
| news_catalyst | LLM has relevant knowledge | qwen3:30b |

**Kelly sizing** (prediction market formula):
```
b = (1 / entry_price) - 1
kelly = (confidence × b − (1 − confidence)) / b
position = min(kelly × balance, 10% × balance)
```

---

## Graduation Criteria (all must pass for 14+ days)

| Criterion | Threshold |
|-----------|-----------|
| Min history | ≥ 14 days |
| 7-day ROI | > 0% |
| Win rate | > 55% |
| Sharpe ratio | > 1.0 (unannualized mean/std) |
| Max drawdown | < 25% |

When all pass: report gets `READY FOR LIVE TRADING` header + one-time Telegram alert.
Live wallet access requires separate Tier-3 Jordan approval.

---

## Risk Limits

- Max 10% of portfolio per position (hard cap, including manual `/bet`)
- Minimum $10K market volume
- Kelly ≤ 0 → trade skipped (negative edge)
- Stop-loss: -20% unrealized P&L
- Take-profit: +50% unrealized P&L

---

## Model

- **Trading analysis:** `qwen3:30b` (research/business model — 3x daily research tasks, 18 GB)
- **Inference:** Local Ollama at `http://localhost:11434` — zero API cost

---

## Configuration (`.env`)

```bash
MIROFISH_STARTING_BALANCE=1000.00
MIROFISH_MAX_POSITION_PCT=0.10
MIROFISH_STOP_LOSS_PCT=0.20
MIROFISH_TAKE_PROFIT_PCT=0.50
MIROFISH_MIN_MARKET_VOLUME=10000
MIROFISH_MIN_HISTORY_DAYS=14
MIROFISH_MODEL=qwen3:30b
JORDAN_TELEGRAM_CHAT_ID=<your_chat_id>
```

---

## Cron Entry

```
*/30 * * * *  python3 ~/openclaw/scripts/mirofish/simulator.py --run >> ~/openclaw/logs/mirofish.log 2>&1
```

---

## Known Limitations

- Expired market P&L uses last cached price, not actual binary settlement (approximation)
- Sharpe ratio requires 14+ days of data (std=0 guard before that)
- No backtest mode in current version (future phase)
```

- [ ] **Step 8.2: Commit**

```bash
git add agents/configs/mirofish-trader.md
git commit -m "docs(mirofish): agent config — mirofish-trader.md"
```

---

## Task 9: Cron Update

**Files:**
- Modify: `.claude/settings.json` (or crontab — check which manages the cron)

- [ ] **Step 9.1: Check how the existing prediction market cron is registered**

```bash
crontab -l | grep prediction-market
# OR
grep -r "cron-prediction-market" ~/openclaw/.claude/settings.json 2>/dev/null
```

- [ ] **Step 9.2a: If managed via crontab**

```bash
crontab -l > /tmp/crontab-backup.txt  # backup first
# Edit crontab: replace prediction-market line with mirofish
crontab -e
# Change:
#   0 9,15,21 * * *  ~/openclaw/scripts/cron-prediction-market.sh
# To:
#   */30 * * * *  python3 ~/openclaw/scripts/mirofish/simulator.py --run >> ~/openclaw/logs/mirofish.log 2>&1
```

- [ ] **Step 9.2b: If managed via settings.json**

Update the cron entry in `.claude/settings.json` from `cron-prediction-market.sh` to:
```
python3 ~/openclaw/scripts/mirofish/simulator.py --run >> ~/openclaw/logs/mirofish.log 2>&1
```
with schedule `*/30 * * * *`.

- [ ] **Step 9.3: Run migration against the real DB**

```bash
python3 ~/openclaw/scripts/mirofish/simulator.py --migrate
# Expected: "Migration complete. DB: /Users/nayslayer/.openclaw/clawmson.db"
sqlite3 ~/.openclaw/clawmson.db ".tables"
# Expected: context  conversations  daily_pnl  market_data  paper_trades  refs
```

- [ ] **Step 9.4: Commit**

```bash
git add .claude/settings.json  # or note crontab change in commit message
git commit -m "chore(mirofish): replace cron-prediction-market.sh with simulator.py --run (every 30min)"
```

---

## Task 10: Final Verification

- [ ] **Step 10.1: Run full test suite**

```bash
cd ~/openclaw
python -m pytest scripts/mirofish/tests/ -v --tb=short
# Expected: all tests PASS, 0 failures
```

- [ ] **Step 10.2: End-to-end smoke test against real DB**

```bash
python3 ~/openclaw/scripts/mirofish/simulator.py --run
# Watch the log output. Expected:
# - "[mirofish] Fetched N markets"
# - "[mirofish] Brain returned N trade decisions"
# - "[mirofish] Daily snapshot written" (on first run of day)
# No Python tracebacks.
```

- [ ] **Step 10.3: Test Telegram commands manually**

Send to Clawmson:
```
/portfolio
/pnl
/trades
/bet fake-market-id YES 10
```
Expected: each returns a formatted response. `/bet` returns rejection (market not in cache) or confirmation if market_id matches a real cached market.

- [ ] **Step 10.4: Generate a report**

```bash
python3 ~/openclaw/scripts/mirofish/simulator.py --report
cat ~/openclaw/mirofish/reports/mirofish-daily-$(date +%Y-%m-%d).md
```

- [ ] **Step 10.5: Final commit and PR**

```bash
git add -A
git status  # confirm only mirofish files + dispatcher + agent config
git commit -m "feat(mirofish): Polymarket paper trading simulator — complete"
```
