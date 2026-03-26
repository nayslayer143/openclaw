# Inspector Gadget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an independent trade verification and audit system for OpenClaw's trading bots — outside their trust boundary, with its own SQLite DB and cross-references against real Polymarket API data.

**Architecture:** Modular pipeline. Each module is independently runnable and writes to its own table in `~/.openclaw/inspector_gadget.db`. A CLI orchestrator (`run_inspection.py`) calls them in sequence. The system reads `clawmson.db` as an untrusted input source and verifies all claims against external APIs or source code analysis.

**Tech Stack:** Python 3.11+, SQLite (aiosqlite not needed — sync is fine), httpx for API calls, qwen3:30b via Ollama at localhost:11434, Telegram Bot API (direct HTTP), pytest

---

## File Map

```
~/openclaw/scripts/inspector/
├── __init__.py                  # Package marker
├── config.json                  # Thresholds, API endpoints, paths
├── inspector_db.py              # DB init + helpers for inspector_gadget.db
├── polymarket_client.py         # Thin wrapper: market info, price history, resolution
├── verifier.py                  # Per-trade price/math verification vs Polymarket
├── resolution_auditor.py        # Win/loss claims vs actual resolutions
├── stats_auditor.py             # Aggregate statistical red flag detection
├── hallucination_detector.py    # LLM price-claim verification
├── logic_analyzer.py            # Source code analysis via qwen3:30b
├── repo_scanner.py              # Git history + hardcoded-data scanning
├── dashboard.py                 # Report generator → security/inspector/reports/
├── run_inspection.py            # CLI: --full / --verify-trades / --scan-code / --report
└── tests/
    ├── test_verifier.py
    ├── test_resolution.py
    ├── test_stats.py
    └── test_hallucination.py

~/openclaw/agents/configs/inspector-gadget.md   # Agent config
~/openclaw/security/inspector/reports/          # Audit reports (already created)
~/.openclaw/inspector_gadget.db                 # Inspector's own DB (independent trust boundary)
```

**Files read (never trusted as truth, only as inputs to verify):**
- `~/.openclaw/clawmson.db` — paper_trades, market_data, daily_pnl, strategy_performance tables
- `~/openclaw/trading/signals.json` — LLM signal claims
- `~/openclaw/trading/positions.json` — open position claims
- `~/openclaw/scripts/mirofish/*.py` — source files for logic analysis
- `~/openclaw/scripts/trading-bot.py` — source file for logic analysis

---

## Task 1: Bootstrap — Package, DB, Config

**Files:**
- Create: `scripts/inspector/__init__.py`
- Create: `scripts/inspector/config.json`
- Create: `scripts/inspector/inspector_db.py`

- [ ] **Step 1: Write the failing test**

```python
# scripts/inspector/tests/test_inspector_db.py
import pytest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parents[2]))
from inspector.inspector_db import InspectorDB

def test_db_creates_tables(tmp_path):
    db = InspectorDB(db_path=str(tmp_path / "test.db"))
    db.init()
    tables = db.get_tables()
    assert "verified_trades" in tables
    assert "resolution_audits" in tables
    assert "code_findings" in tables
    assert "hallucination_checks" in tables
    assert "audit_reports" in tables

def test_db_idempotent(tmp_path):
    db = InspectorDB(db_path=str(tmp_path / "test.db"))
    db.init()
    db.init()  # second call must not raise
    assert len(db.get_tables()) == 5
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/openclaw/scripts && python -m pytest inspector/tests/test_inspector_db.py -v
```
Expected: `ModuleNotFoundError` or `ImportError`

- [ ] **Step 3: Create `__init__.py`**

```python
# scripts/inspector/__init__.py
# Inspector Gadget — independent trading audit system
```

- [ ] **Step 4: Create `config.json`**

```json
{
  "db": {
    "inspector": "~/.openclaw/inspector_gadget.db",
    "clawmson": "~/.openclaw/clawmson.db"
  },
  "polymarket": {
    "gamma_api": "https://gamma-api.polymarket.com",
    "clob_api": "https://clob.polymarket.com"
  },
  "ollama": {
    "base_url": "http://localhost:11434",
    "model": "qwen3:30b",
    "timeout": 180
  },
  "thresholds": {
    "price_tolerance": 0.02,
    "pnl_tolerance": 0.01,
    "amount_tolerance_pct": 0.008,
    "win_rate_ceiling": 0.80,
    "sharpe_ceiling": 3.5,
    "kelly_cap": 0.10,
    "max_position_pct": 0.10,
    "stop_loss": -0.20,
    "take_profit": 0.50
  },
  "paths": {
    "clawmson_scripts": "~/openclaw/scripts/mirofish",
    "trading_bot": "~/openclaw/scripts/trading-bot.py",
    "signals_json": "~/openclaw/trading/signals.json",
    "positions_json": "~/openclaw/trading/positions.json",
    "reports_dir": "~/openclaw/security/inspector/reports"
  }
}
```

- [ ] **Step 5: Implement `inspector_db.py`**

```python
# scripts/inspector/inspector_db.py
import sqlite3
from pathlib import Path
from typing import List

SCHEMA = """
CREATE TABLE IF NOT EXISTS verified_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id INTEGER NOT NULL,
    bot_source TEXT NOT NULL,
    market_id TEXT NOT NULL,
    direction TEXT,
    claimed_entry REAL,
    verified_entry REAL,
    claimed_exit REAL,
    verified_exit REAL,
    claimed_pnl REAL,
    verified_pnl REAL,
    claimed_amount REAL,
    status TEXT NOT NULL,  -- VERIFIED | DISCREPANCY | IMPOSSIBLE | UNVERIFIABLE
    discrepancy_amount REAL,
    discrepancy_detail TEXT,
    checked_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS resolution_audits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id INTEGER NOT NULL,
    market_id TEXT NOT NULL,
    claimed_resolution TEXT,  -- closed_win | closed_loss | expired
    actual_resolution TEXT,   -- YES | NO | UNRESOLVED | NOT_FOUND
    match INTEGER,            -- 1=match, 0=mismatch, -1=unverifiable
    recalculated_pnl REAL,
    claimed_pnl REAL,
    pnl_delta REAL,
    checked_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS code_findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,
    line_number INTEGER,
    finding_type TEXT NOT NULL,  -- logic_error | race_condition | kelly_math | stale_data | test_leak | todo_critical
    severity TEXT NOT NULL,      -- critical | high | medium | low
    description TEXT NOT NULL,
    snippet TEXT,
    found_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hallucination_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id INTEGER,
    signal_id TEXT,
    claim_type TEXT NOT NULL,  -- price | market_existence | trend
    claim_content TEXT NOT NULL,
    verification_result TEXT NOT NULL,  -- GROUNDED | PARTIALLY_GROUNDED | HALLUCINATED | UNVERIFIABLE
    grounding_score REAL,
    actual_value TEXT,
    checked_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id TEXT NOT NULL UNIQUE,
    generated_at TEXT NOT NULL,
    summary TEXT,
    total_trades_checked INTEGER,
    verified_count INTEGER,
    discrepancy_count INTEGER,
    impossible_count INTEGER,
    unverifiable_count INTEGER,
    trust_scores_json TEXT,
    red_flags_json TEXT,
    report_path TEXT
);
"""

class InspectorDB:
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(Path("~/.openclaw/inspector_gadget.db").expanduser())
        self.db_path = db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self):
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    def get_tables(self) -> List[str]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        return [r["name"] for r in rows]

    def insert(self, table: str, row: dict) -> int:
        cols = ", ".join(row.keys())
        placeholders = ", ".join("?" * len(row))
        sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
        with self._conn() as conn:
            cur = conn.execute(sql, list(row.values()))
            return cur.lastrowid

    def fetch_all(self, table: str, where: str = "", params=()) -> List[dict]:
        sql = f"SELECT * FROM {table}"
        if where:
            sql += f" WHERE {where}"
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd ~/openclaw/scripts && python -m pytest inspector/tests/test_inspector_db.py -v
```
Expected: 2 PASSED

- [ ] **Step 7: Commit**

```bash
cd ~/openclaw && git add scripts/inspector/ && git commit -m "feat(inspector): bootstrap package, DB schema, config"
```

---

## Task 2: Polymarket API Client

**Files:**
- Create: `scripts/inspector/polymarket_client.py`

- [ ] **Step 1: Write the failing test**

```python
# scripts/inspector/tests/test_polymarket_client.py
import pytest
from unittest.mock import patch, MagicMock
from inspector.polymarket_client import PolymarketClient

def test_get_market_returns_none_for_missing():
    """UNVERIFIABLE path: market 404 → None"""
    client = PolymarketClient()
    with patch("inspector.polymarket_client.httpx.Client") as mock_get:
        mock_get.return_value.status_code = 404
        result = client.get_market("0xDEAD")
    assert result is None

def test_market_price_in_range():
    """Price must be in [0, 1] if returned."""
    from inspector.polymarket_client import _validate_price
    assert _validate_price(0.5) is True
    assert _validate_price(1.1) is False
    assert _validate_price(-0.1) is False
    assert _validate_price(0.0) is True
    assert _validate_price(1.0) is True
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/openclaw/scripts && python -m pytest inspector/tests/test_polymarket_client.py -v
```

- [ ] **Step 3: Implement `polymarket_client.py`**

```python
# scripts/inspector/polymarket_client.py
"""
Thin client for Polymarket APIs. Used ONLY by Inspector Gadget — never by trading bots.
Returns None on any failure so callers mark the trade UNVERIFIABLE rather than crashing.
"""
import httpx
from typing import Optional, Dict, Any
from datetime import datetime, timezone

GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE  = "https://clob.polymarket.com"
TIMEOUT    = 15  # seconds — fail fast, log UNVERIFIABLE

def _validate_price(price: Any) -> bool:
    try:
        p = float(price)
        return 0.0 <= p <= 1.0
    except (TypeError, ValueError):
        return False

class PolymarketClient:
    def __init__(self):
        self._client = httpx.Client(timeout=TIMEOUT, follow_redirects=True)

    def get_market(self, market_id: str) -> Optional[Dict]:
        """Fetch market metadata from Gamma API. Returns None if not found."""
        try:
            resp = self._client.get(f"{GAMMA_BASE}/markets", params={"id": market_id})
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                return data[0] if data else None
            return data if data else None
        except Exception:
            return None

    def get_price_history(self, condition_id: str, start_ts: int, end_ts: int) -> Optional[list]:
        """
        Fetch per-minute CLOB price history for a market.
        condition_id: the 0x... hex string from paper_trades.market_id
        Returns list of {t, p} dicts, or None if unavailable.
        """
        try:
            resp = self._client.get(
                f"{CLOB_BASE}/prices-history",
                params={
                    "market": condition_id,
                    "startTs": start_ts,
                    "endTs": end_ts,
                    "fidelity": 60,
                }
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            return data.get("history") or None
        except Exception:
            return None

    def get_price_at(self, condition_id: str, timestamp_iso: str) -> Optional[float]:
        """
        Get closest price point to a given ISO timestamp.
        Returns None (→ UNVERIFIABLE) if no history data available.
        """
        try:
            dt = datetime.fromisoformat(timestamp_iso.replace("Z", "+00:00"))
            ts = int(dt.timestamp())
            window = 3600  # ±1 hour window
            history = self.get_price_history(condition_id, ts - window, ts + window)
            if not history:
                return None
            # Find closest point to target ts
            closest = min(history, key=lambda x: abs(x["t"] - ts))
            price = float(closest["p"])
            return price if _validate_price(price) else None
        except Exception:
            return None

    def get_resolution(self, condition_id: str) -> Optional[Dict]:
        """
        Get market resolution status from Gamma API.
        Returns dict with: closed (bool), resolution ('YES'|'NO'|None), end_date_iso
        Returns None if market not found or API error.
        """
        try:
            market = self.get_market(condition_id)
            if not market:
                return None
            return {
                "closed": market.get("closed", False),
                "resolution": market.get("resolution"),  # 'YES', 'NO', or None
                "end_date": market.get("endDate"),
                "question": market.get("question"),
            }
        except Exception:
            return None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd ~/openclaw/scripts && python -m pytest inspector/tests/test_polymarket_client.py -v
```

- [ ] **Step 5: Commit**

```bash
cd ~/openclaw && git add scripts/inspector/polymarket_client.py scripts/inspector/tests/test_polymarket_client.py && git commit -m "feat(inspector): Polymarket API client"
```

---

## Task 3: Trade Verifier

**Files:**
- Create: `scripts/inspector/verifier.py`
- Create: `scripts/inspector/tests/test_verifier.py`

- [ ] **Step 1: Write the failing test**

```python
# scripts/inspector/tests/test_verifier.py
import pytest
from unittest.mock import patch, MagicMock
from inspector.verifier import TradeVerifier, VerificationStatus

def _make_trade(overrides={}):
    base = {
        "id": 1, "market_id": "0xABC", "direction": "YES",
        "shares": 100.0, "entry_price": 0.50, "exit_price": None,
        "amount_usd": 50.0, "pnl": None, "status": "open",
        "opened_at": "2026-03-24T10:00:00", "closed_at": None,
        "strategy": "momentum", "confidence": 0.7,
    }
    base.update(overrides)
    return base

def test_impossible_trade_negative_shares():
    tv = TradeVerifier(db=MagicMock(), poly=MagicMock())
    result = tv._check_math({"shares": -5, "entry_price": 0.5, "amount_usd": 10})
    assert result["status"] == VerificationStatus.IMPOSSIBLE

def test_amount_math_discrepancy():
    tv = TradeVerifier(db=MagicMock(), poly=MagicMock())
    # shares * price = 50, but amount_usd = 999 → DISCREPANCY
    result = tv._check_math({"shares": 100, "entry_price": 0.5, "amount_usd": 999})
    assert result["status"] == VerificationStatus.DISCREPANCY

def test_amount_math_verified_with_slippage():
    tv = TradeVerifier(db=MagicMock(), poly=MagicMock())
    # 100 shares @ 0.502 (with 50bps slippage) = 50.2, amount_usd=50 → VERIFIED
    result = tv._check_math({"shares": 100, "entry_price": 0.502, "amount_usd": 50.0})
    assert result["status"] == VerificationStatus.VERIFIED

def test_unverifiable_when_no_price_history():
    poly = MagicMock()
    poly.get_price_at.return_value = None
    poly.get_market.return_value = {"question": "Will X?", "closed": False}
    tv = TradeVerifier(db=MagicMock(), poly=poly)
    result = tv._check_price(_make_trade())
    assert result["status"] == VerificationStatus.UNVERIFIABLE
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/openclaw/scripts && python -m pytest inspector/tests/test_verifier.py -v
```

- [ ] **Step 3: Implement `verifier.py`**

```python
# scripts/inspector/verifier.py
"""
Verifies every paper trade in clawmson.db against real Polymarket data.
Writes results to verified_trades table in inspector_gadget.db.
Trust boundary: clawmson.db is INPUT, never TRUTH.
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from enum import Enum
from typing import Dict, Optional
from inspector.inspector_db import InspectorDB
from inspector.polymarket_client import PolymarketClient

class VerificationStatus(str, Enum):
    VERIFIED      = "VERIFIED"
    DISCREPANCY   = "DISCREPANCY"
    IMPOSSIBLE    = "IMPOSSIBLE"
    UNVERIFIABLE  = "UNVERIFIABLE"

SLIPPAGE_BPS  = 0.005   # 50bps — execution sim slippage
LATENCY_BPS   = 0.002   # 20bps — latency penalty
AMOUNT_TOL    = 0.015   # 1.5% combined tolerance for amount math
PRICE_TOL     = 0.02    # ±2 cents price tolerance vs historical

class TradeVerifier:
    def __init__(self, db: InspectorDB, poly: PolymarketClient):
        self.db = db
        self.poly = poly

    def _check_math(self, trade: dict) -> dict:
        """Verify shares * entry_price ≈ amount_usd (accounting for execution sim)."""
        shares = trade.get("shares", 0)
        price  = trade.get("entry_price", 0)
        amount = trade.get("amount_usd", 0)

        if shares <= 0:
            return {"status": VerificationStatus.IMPOSSIBLE,
                    "detail": f"Negative/zero shares: {shares}"}
        if not (0.0 < price <= 1.0):
            return {"status": VerificationStatus.IMPOSSIBLE,
                    "detail": f"Price out of range: {price}"}
        if amount <= 0:
            return {"status": VerificationStatus.IMPOSSIBLE,
                    "detail": f"Non-positive amount: {amount}"}

        expected = shares * price
        delta_pct = abs(expected - amount) / max(amount, 0.001)
        if delta_pct > AMOUNT_TOL:
            return {"status": VerificationStatus.DISCREPANCY,
                    "detail": f"Math mismatch: {shares}*{price}={expected:.4f} vs claimed {amount:.4f} ({delta_pct*100:.1f}%)"}
        return {"status": VerificationStatus.VERIFIED, "detail": "Math OK"}

    def _check_price(self, trade: dict) -> dict:
        """Verify entry price against Polymarket historical data."""
        market_info = self.poly.get_market(trade["market_id"])
        if market_info is None:
            return {"status": VerificationStatus.IMPOSSIBLE,
                    "detail": f"Market {trade['market_id']} not found on Polymarket"}

        hist_price = self.poly.get_price_at(trade["market_id"], trade["opened_at"])
        if hist_price is None:
            return {"status": VerificationStatus.UNVERIFIABLE,
                    "detail": "No historical price data available"}

        claimed = trade["entry_price"]
        delta = abs(hist_price - claimed)
        if delta > PRICE_TOL:
            return {"status": VerificationStatus.DISCREPANCY,
                    "detail": f"Price claim {claimed} vs actual {hist_price:.4f} (Δ={delta:.4f})"}
        return {"status": VerificationStatus.VERIFIED,
                "detail": f"Price OK: claimed {claimed}, actual {hist_price:.4f}"}

    def verify_trade(self, trade: dict) -> dict:
        """Run all checks on a single trade. Worst status wins."""
        math_result  = self._check_math(trade)
        price_result = self._check_price(trade)

        # Severity ordering: IMPOSSIBLE > DISCREPANCY > UNVERIFIABLE > VERIFIED
        priority = [VerificationStatus.IMPOSSIBLE, VerificationStatus.DISCREPANCY,
                    VerificationStatus.UNVERIFIABLE, VerificationStatus.VERIFIED]
        final = max(math_result["status"], price_result["status"],
                    key=lambda s: priority.index(s))
        combined_detail = f"Math: {math_result['detail']} | Price: {price_result['detail']}"

        claimed_pnl = trade.get("pnl")
        verified_pnl = None
        if trade.get("exit_price") and trade.get("shares"):
            verified_pnl = (trade["exit_price"] - trade["entry_price"]) * trade["shares"]

        return {
            "trade_id": trade["id"],
            "bot_source": trade.get("strategy", "unknown"),
            "market_id": trade["market_id"],
            "direction": trade.get("direction"),
            "claimed_entry": trade.get("entry_price"),
            "verified_entry": price_result.get("verified_price"),
            "claimed_exit": trade.get("exit_price"),
            "verified_exit": None,  # Resolution auditor handles exits
            "claimed_pnl": claimed_pnl,
            "verified_pnl": verified_pnl,
            "claimed_amount": trade.get("amount_usd"),
            "status": final.value,
            "discrepancy_amount": abs(claimed_pnl - verified_pnl) if (claimed_pnl and verified_pnl) else None,
            "discrepancy_detail": combined_detail,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    def run(self, clawmson_db_path: str) -> dict:
        """Read all paper_trades, verify each, write to inspector_gadget.db."""
        conn = sqlite3.connect(Path(clawmson_db_path).expanduser())
        conn.row_factory = sqlite3.Row
        trades = conn.execute("SELECT * FROM paper_trades").fetchall()
        conn.close()

        counts = {s.value: 0 for s in VerificationStatus}
        for trade in trades:
            result = self.verify_trade(dict(trade))
            self.db.insert("verified_trades", result)
            counts[result["status"]] += 1

        return {"total": len(trades), "counts": counts}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd ~/openclaw/scripts && python -m pytest inspector/tests/test_verifier.py -v
```

- [ ] **Step 5: Commit**

```bash
cd ~/openclaw && git add scripts/inspector/verifier.py scripts/inspector/tests/test_verifier.py && git commit -m "feat(inspector): trade verifier — math + price checks"
```

---

## Task 4: Resolution Auditor

**Files:**
- Create: `scripts/inspector/resolution_auditor.py`
- Create: `scripts/inspector/tests/test_resolution.py`

- [ ] **Step 1: Write the failing test**

```python
# scripts/inspector/tests/test_resolution.py
from unittest.mock import MagicMock
from inspector.resolution_auditor import ResolutionAuditor

def _closed_trade(direction="YES", status="closed_win", exit_price=0.95, pnl=45.0):
    return {"id": 1, "market_id": "0xABC", "direction": direction,
            "status": status, "exit_price": exit_price, "entry_price": 0.5,
            "shares": 100.0, "pnl": pnl, "closed_at": "2026-03-25T12:00:00"}

def test_win_matches_yes_resolution():
    poly = MagicMock()
    poly.get_resolution.return_value = {"closed": True, "resolution": "YES"}
    ra = ResolutionAuditor(db=MagicMock(), poly=poly)
    result = ra.audit_trade(_closed_trade(direction="YES", status="closed_win"))
    assert result["match"] == 1

def test_win_with_no_resolution_is_mismatch():
    poly = MagicMock()
    poly.get_resolution.return_value = {"closed": True, "resolution": "NO"}
    ra = ResolutionAuditor(db=MagicMock(), poly=poly)
    result = ra.audit_trade(_closed_trade(direction="YES", status="closed_win"))
    assert result["match"] == 0

def test_unresolved_market_is_unverifiable():
    poly = MagicMock()
    poly.get_resolution.return_value = {"closed": False, "resolution": None}
    ra = ResolutionAuditor(db=MagicMock(), poly=poly)
    result = ra.audit_trade(_closed_trade())
    assert result["match"] == -1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/openclaw/scripts && python -m pytest inspector/tests/test_resolution.py -v
```

- [ ] **Step 3: Implement `resolution_auditor.py`**

```python
# scripts/inspector/resolution_auditor.py
"""
For every closed trade, check:
1. Did the market actually resolve the way the bot claims?
2. Is the P&L mathematically correct given the real exit price?
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from inspector.inspector_db import InspectorDB
from inspector.polymarket_client import PolymarketClient

CLOSED_STATUSES = {"closed_win", "closed_loss", "expired"}

class ResolutionAuditor:
    def __init__(self, db: InspectorDB, poly: PolymarketClient):
        self.db = db
        self.poly = poly

    def _resolution_matches(self, direction: str, bot_status: str, actual_resolution: str) -> bool:
        """
        A 'closed_win' for a YES position should match actual resolution of 'YES'.
        A 'closed_loss' for a YES position should match actual resolution of 'NO'.
        """
        if bot_status == "expired":
            return True  # Expirations aren't resolution-dependent
        win = (bot_status == "closed_win")
        if direction == "YES":
            return (actual_resolution == "YES") == win
        elif direction == "NO":
            return (actual_resolution == "NO") == win
        return False

    def _recalc_pnl(self, trade: dict) -> float:
        """Recalculate P&L from scratch: (exit - entry) * shares"""
        return (trade["exit_price"] - trade["entry_price"]) * trade["shares"]

    def audit_trade(self, trade: dict) -> dict:
        status = trade.get("status", "")
        if status not in CLOSED_STATUSES:
            return None  # Skip open trades — nothing to audit yet

        resolution_data = self.poly.get_resolution(trade["market_id"])
        now = datetime.now(timezone.utc).isoformat()

        if resolution_data is None:
            return {"trade_id": trade["id"], "market_id": trade["market_id"],
                    "claimed_resolution": status, "actual_resolution": "NOT_FOUND",
                    "match": -1, "recalculated_pnl": None, "claimed_pnl": trade.get("pnl"),
                    "pnl_delta": None, "checked_at": now}

        actual_res = resolution_data.get("resolution")  # 'YES', 'NO', or None

        if not resolution_data.get("closed") or actual_res is None:
            match = -1  # UNVERIFIABLE — market not yet resolved
        else:
            match = 1 if self._resolution_matches(
                trade["direction"], status, actual_res) else 0

        recalc = self._recalc_pnl(trade) if trade.get("exit_price") else None
        claimed = trade.get("pnl")
        pnl_delta = abs(recalc - claimed) if (recalc is not None and claimed is not None) else None

        return {
            "trade_id": trade["id"], "market_id": trade["market_id"],
            "claimed_resolution": status, "actual_resolution": actual_res or "UNRESOLVED",
            "match": match, "recalculated_pnl": recalc, "claimed_pnl": claimed,
            "pnl_delta": pnl_delta, "checked_at": now,
        }

    def run(self, clawmson_db_path: str) -> dict:
        conn = sqlite3.connect(Path(clawmson_db_path).expanduser())
        conn.row_factory = sqlite3.Row
        trades = [dict(r) for r in conn.execute(
            "SELECT * FROM paper_trades WHERE status IN ('closed_win','closed_loss','expired')"
        ).fetchall()]
        conn.close()

        results = {"matched": 0, "mismatched": 0, "unverifiable": 0}
        for trade in trades:
            result = self.audit_trade(trade)
            if result:
                self.db.insert("resolution_audits", result)
                if result["match"] == 1: results["matched"] += 1
                elif result["match"] == 0: results["mismatched"] += 1
                else: results["unverifiable"] += 1
        return {"total_closed": len(trades), **results}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd ~/openclaw/scripts && python -m pytest inspector/tests/test_resolution.py -v
```

- [ ] **Step 5: Commit**

```bash
cd ~/openclaw && git add scripts/inspector/resolution_auditor.py scripts/inspector/tests/test_resolution.py && git commit -m "feat(inspector): resolution auditor"
```

---

## Task 5: Statistical Auditor

**Files:**
- Create: `scripts/inspector/stats_auditor.py`
- Create: `scripts/inspector/tests/test_stats.py`

- [ ] **Step 1: Write the failing test**

```python
# scripts/inspector/tests/test_stats.py
from inspector.stats_auditor import StatsAuditor, RedFlag

def _make_trades(win_rate: float, n: int = 100):
    trades = []
    wins = int(n * win_rate)
    for i in range(n):
        pnl = 10.0 if i < wins else -10.0
        trades.append({"id": i, "pnl": pnl, "amount_usd": 50.0,
                       "entry_price": 0.5, "confidence": 0.7,
                       "strategy": "test", "status": "closed_win" if i < wins else "closed_loss"})
    return trades

def test_high_win_rate_flagged():
    sa = StatsAuditor()
    trades = _make_trades(win_rate=0.90, n=100)
    flags = sa.check_win_rate(trades)
    assert any(f.severity == "critical" for f in flags)

def test_normal_win_rate_clean():
    sa = StatsAuditor()
    trades = _make_trades(win_rate=0.60, n=100)
    flags = sa.check_win_rate(trades)
    assert len(flags) == 0

def test_position_size_violation():
    sa = StatsAuditor()
    # Trade is 15% of $1000 balance — violates 10% cap
    trade = {"amount_usd": 150.0}
    balance = 1000.0
    flags = sa.check_position_size(trade, balance)
    assert any(f.severity in ("critical", "high") for f in flags)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/openclaw/scripts && python -m pytest inspector/tests/test_stats.py -v
```

- [ ] **Step 3: Implement `stats_auditor.py`**

```python
# scripts/inspector/stats_auditor.py
"""
Red flag detection on aggregate performance.
Does not hit external APIs — works entirely from clawmson.db data.
"""
import sqlite3
import math
import json
from dataclasses import dataclass, field
from typing import List, Dict
from pathlib import Path
from datetime import datetime, timezone
from inspector.inspector_db import InspectorDB

WIN_RATE_CEILING    = 0.80   # >80% sustained = suspicious
SHARPE_CEILING      = 3.5    # >3.5 Sharpe = statistically implausible
KELLY_CAP           = 0.10   # 10% max position
SMOOTH_PNL_FLOOR    = 0.15   # Daily P&L std dev / mean ratio — too smooth if below
MIN_SAMPLE          = 20     # Need at least this many closed trades for stats

@dataclass
class RedFlag:
    check: str
    severity: str  # critical | high | medium | low
    message: str
    value: float = None

class StatsAuditor:
    def __init__(self, db: InspectorDB = None):
        self.db = db

    def check_win_rate(self, trades: list) -> List[RedFlag]:
        closed = [t for t in trades if t.get("status") in ("closed_win", "closed_loss")]
        if len(closed) < MIN_SAMPLE:
            return []
        wins = sum(1 for t in closed if t.get("status") == "closed_win")
        rate = wins / len(closed)
        if rate > WIN_RATE_CEILING:
            return [RedFlag("win_rate", "critical",
                f"Win rate {rate*100:.1f}% exceeds ceiling {WIN_RATE_CEILING*100:.0f}% "
                f"over {len(closed)} trades — likely a bug or P&L miscalculation", rate)]
        return []

    def check_position_size(self, trade: dict, balance: float) -> List[RedFlag]:
        if balance <= 0:
            return []
        size_pct = trade.get("amount_usd", 0) / balance
        if size_pct > KELLY_CAP * 1.05:  # 5% grace for rounding
            return [RedFlag("position_size",
                "critical" if size_pct > 0.15 else "high",
                f"Position {size_pct*100:.1f}% of balance exceeds {KELLY_CAP*100:.0f}% cap",
                size_pct)]
        return []

    def check_sharpe(self, daily_pnl_rows: list) -> List[RedFlag]:
        rois = [r.get("roi_pct", 0) for r in daily_pnl_rows if r.get("roi_pct") is not None]
        if len(rois) < 7:
            return []
        mean = sum(rois) / len(rois)
        std = math.sqrt(sum((r - mean) ** 2 for r in rois) / len(rois))
        if std == 0:
            return [RedFlag("pnl_smoothness", "critical",
                "Zero variance in daily P&L — statistically impossible in real trading")]
        sharpe = (mean / std) * math.sqrt(365)
        if sharpe > SHARPE_CEILING:
            return [RedFlag("sharpe", "high",
                f"Sharpe {sharpe:.2f} exceeds ceiling {SHARPE_CEILING} — strategy may be overfitted or P&L fabricated",
                sharpe)]
        return []

    def check_no_losing_streaks(self, trades: list) -> List[RedFlag]:
        """Flag if there are no sequences of 3+ consecutive losses (improbable at >55% win rate)."""
        closed = [t for t in trades if t.get("status") in ("closed_win", "closed_loss")]
        if len(closed) < 30:
            return []
        max_streak = 0
        streak = 0
        for t in closed:
            if t["status"] == "closed_loss":
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0
        if max_streak < 3 and len(closed) >= 30:
            return [RedFlag("losing_streaks", "medium",
                f"No losing streak ≥3 in {len(closed)} trades — statistically improbable",
                max_streak)]
        return []

    def run(self, clawmson_db_path: str) -> Dict:
        conn = sqlite3.connect(Path(clawmson_db_path).expanduser())
        conn.row_factory = sqlite3.Row
        trades = [dict(r) for r in conn.execute("SELECT * FROM paper_trades").fetchall()]
        daily_pnl = [dict(r) for r in conn.execute("SELECT * FROM daily_pnl").fetchall()]
        context = dict(conn.execute(
            "SELECT key, value FROM context WHERE chat_id='mirofish'"
        ).fetchall() or [])
        conn.close()

        starting_balance = float(context.get("starting_balance", 1000.0))
        all_flags: List[RedFlag] = []

        all_flags.extend(self.check_win_rate(trades))
        all_flags.extend(self.check_sharpe(daily_pnl))
        all_flags.extend(self.check_no_losing_streaks(trades))

        for trade in trades:
            # Approximate balance at trade time — conservative: use starting_balance
            all_flags.extend(self.check_position_size(trade, starting_balance))

        trust_score = max(0, 100 - sum(
            {"critical": 30, "high": 15, "medium": 5, "low": 1}.get(f.severity, 0)
            for f in all_flags))

        summary = {
            "total_trades": len(trades),
            "closed_trades": sum(1 for t in trades if t["status"] != "open"),
            "red_flags": [{"check": f.check, "severity": f.severity, "message": f.message}
                         for f in all_flags],
            "trust_score": trust_score,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        if self.db:
            self.db.insert("audit_reports", {
                "report_id": f"stats-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}",
                "generated_at": summary["generated_at"],
                "summary": f"{len(all_flags)} red flags, trust score {trust_score}",
                "total_trades_checked": len(trades),
                "verified_count": 0, "discrepancy_count": 0,
                "impossible_count": 0, "unverifiable_count": 0,
                "trust_scores_json": json.dumps({"stats": trust_score}),
                "red_flags_json": json.dumps(summary["red_flags"]),
                "report_path": None,
            })
        return summary
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd ~/openclaw/scripts && python -m pytest inspector/tests/test_stats.py -v
```

- [ ] **Step 5: Commit**

```bash
cd ~/openclaw && git add scripts/inspector/stats_auditor.py scripts/inspector/tests/test_stats.py && git commit -m "feat(inspector): statistical red flag auditor"
```

---

## Task 6: Hallucination Detector

**Files:**
- Create: `scripts/inspector/hallucination_detector.py`
- Create: `scripts/inspector/tests/test_hallucination.py`

- [ ] **Step 1: Write the failing test**

```python
# scripts/inspector/tests/test_hallucination.py
from unittest.mock import MagicMock
from inspector.hallucination_detector import HallucinationDetector, GroundingResult

def test_price_within_tolerance_is_grounded():
    poly = MagicMock()
    poly.get_price_at.return_value = 0.52
    hd = HallucinationDetector(db=MagicMock(), poly=poly)
    result = hd.check_price_claim("0xABC", 0.51, "2026-03-24T10:00:00")
    assert result == GroundingResult.GROUNDED

def test_price_far_off_is_hallucinated():
    poly = MagicMock()
    poly.get_price_at.return_value = 0.20
    hd = HallucinationDetector(db=MagicMock(), poly=poly)
    result = hd.check_price_claim("0xABC", 0.75, "2026-03-24T10:00:00")
    assert result == GroundingResult.HALLUCINATED

def test_missing_price_history_is_unverifiable():
    poly = MagicMock()
    poly.get_price_at.return_value = None
    hd = HallucinationDetector(db=MagicMock(), poly=poly)
    result = hd.check_price_claim("0xABC", 0.5, "2026-03-24T10:00:00")
    assert result == GroundingResult.UNVERIFIABLE
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/openclaw/scripts && python -m pytest inspector/tests/test_hallucination.py -v
```

- [ ] **Step 3: Implement `hallucination_detector.py`**

```python
# scripts/inspector/hallucination_detector.py
"""
Detects when LLM-powered trading decisions are based on hallucinated data.
Scope: price/market-existence claims only (no news API in v1).
News grounding is a documented extension point.
"""
import json
import sqlite3
from enum import Enum
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from inspector.inspector_db import InspectorDB
from inspector.polymarket_client import PolymarketClient

PRICE_GROUNDED_TOL  = 0.05  # ±5 cents → GROUNDED
PRICE_PARTIAL_TOL   = 0.15  # ±5-15 cents → PARTIALLY_GROUNDED
                             # >15 cents → HALLUCINATED

class GroundingResult(str, Enum):
    GROUNDED           = "GROUNDED"
    PARTIALLY_GROUNDED = "PARTIALLY_GROUNDED"
    HALLUCINATED       = "HALLUCINATED"
    UNVERIFIABLE       = "UNVERIFIABLE"

class HallucinationDetector:
    def __init__(self, db: InspectorDB, poly: PolymarketClient):
        self.db = db
        self.poly = poly

    def check_price_claim(self, market_id: str, claimed_price: float, timestamp_iso: str) -> GroundingResult:
        actual = self.poly.get_price_at(market_id, timestamp_iso)
        if actual is None:
            return GroundingResult.UNVERIFIABLE
        delta = abs(actual - claimed_price)
        if delta <= PRICE_GROUNDED_TOL:
            return GroundingResult.GROUNDED
        if delta <= PRICE_PARTIAL_TOL:
            return GroundingResult.PARTIALLY_GROUNDED
        return GroundingResult.HALLUCINATED

    def check_market_existence(self, market_id: str) -> GroundingResult:
        info = self.poly.get_market(market_id)
        if info is None:
            return GroundingResult.HALLUCINATED
        return GroundingResult.GROUNDED

    def _score(self, result: GroundingResult) -> float:
        return {GroundingResult.GROUNDED: 1.0, GroundingResult.PARTIALLY_GROUNDED: 0.5,
                GroundingResult.HALLUCINATED: 0.0, GroundingResult.UNVERIFIABLE: -1.0}[result]

    def run_on_signals(self, signals_json_path: str) -> dict:
        """Check LLM signals from trading-bot.py against real Polymarket prices."""
        path = Path(signals_json_path).expanduser()
        if not path.exists():
            return {"error": "signals.json not found", "checked": 0}
        signals = json.loads(path.read_text())
        counts = {r.value: 0 for r in GroundingResult}
        now = datetime.now(timezone.utc).isoformat()

        for sig in signals:
            market_id = sig.get("market_id") or sig.get("id", "")
            claimed_price = sig.get("current_yes_price") or sig.get("estimated_true_prob")
            scan_time = sig.get("scan_time", now)
            if not market_id or claimed_price is None:
                continue

            result = self.check_price_claim(market_id, claimed_price, scan_time)
            actual = self.poly.get_price_at(market_id, scan_time)
            counts[result.value] += 1

            self.db.insert("hallucination_checks", {
                "trade_id": None, "signal_id": sig.get("id"),
                "claim_type": "price",
                "claim_content": f"market={market_id} price={claimed_price}",
                "verification_result": result.value,
                "grounding_score": self._score(result),
                "actual_value": str(actual) if actual else None,
                "checked_at": now,
            })

        return {"checked": len(signals), "counts": counts}

    def run_on_llm_trades(self, clawmson_db_path: str) -> dict:
        """Check LLM-strategy trades (strategy='llm') for price hallucination."""
        conn = sqlite3.connect(Path(clawmson_db_path).expanduser())
        conn.row_factory = sqlite3.Row
        trades = [dict(r) for r in conn.execute(
            "SELECT * FROM paper_trades WHERE strategy LIKE '%llm%' OR reasoning != ''"
        ).fetchall()]
        conn.close()

        counts = {r.value: 0 for r in GroundingResult}
        now = datetime.now(timezone.utc).isoformat()
        for trade in trades:
            result = self.check_price_claim(
                trade["market_id"], trade["entry_price"], trade["opened_at"])
            counts[result.value] += 1
            actual = self.poly.get_price_at(trade["market_id"], trade["opened_at"])
            self.db.insert("hallucination_checks", {
                "trade_id": trade["id"], "signal_id": None,
                "claim_type": "price",
                "claim_content": f"market={trade['market_id']} price={trade['entry_price']}",
                "verification_result": result.value,
                "grounding_score": self._score(result),
                "actual_value": str(actual) if actual else None,
                "checked_at": now,
            })
        return {"checked": len(trades), "counts": counts}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd ~/openclaw/scripts && python -m pytest inspector/tests/test_hallucination.py -v
```

- [ ] **Step 5: Commit**

```bash
cd ~/openclaw && git add scripts/inspector/hallucination_detector.py scripts/inspector/tests/test_hallucination.py && git commit -m "feat(inspector): hallucination detector"
```

---

## Task 7: Logic Analyzer

**Files:**
- Create: `scripts/inspector/logic_analyzer.py`

No unit test for this module — it calls a live Ollama model. Run integration test manually.

- [ ] **Step 1: Implement `logic_analyzer.py`**

```python
# scripts/inspector/logic_analyzer.py
"""
Static analysis of trading bot source code.
Uses qwen3:30b via Ollama for LLM-assisted logic review.
Also performs deterministic checks (Kelly math, price range guards, etc.)
"""
import ast
import re
import json
import httpx
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict
from inspector.inspector_db import InspectorDB

OLLAMA_URL   = "http://localhost:11434/api/chat"
ANALYSIS_MODEL = "qwen3:30b"
TIMEOUT      = 180

TARGET_FILES = [
    "~/openclaw/scripts/mirofish/trading_brain.py",
    "~/openclaw/scripts/mirofish/paper_wallet.py",
    "~/openclaw/scripts/mirofish/polymarket_feed.py",
    "~/openclaw/scripts/trading-bot.py",
]

LLM_PROMPT = """You are a code auditor reviewing a paper trading system for logical errors.
Analyze this Python code and report ONLY real bugs or logic flaws.

Look specifically for:
1. Off-by-one errors in price calculations or array indexing
2. Rounding errors that compound (e.g., float precision in P&L accumulation)
3. Kelly criterion math errors (formula: f = (p*b - q) / b where b = (1/price)-1)
4. Stop-loss/take-profit logic that could trigger on stale data
5. Race conditions in trade execution
6. Division by zero possibilities
7. Cases where loss can exceed stated -20% stop-loss
8. P&L calculation that doesn't match: (exit_price - entry_price) * shares

Return a JSON array. Each item: {"line": <int or null>, "type": <string>, "severity": "critical|high|medium|low", "description": <string>}
Return [] if no issues found. Return ONLY the JSON array, no explanation.

Code to analyze:
"""

class LogicAnalyzer:
    def __init__(self, db: InspectorDB):
        self.db = db

    def _deterministic_checks(self, filepath: str, source: str) -> List[dict]:
        """Fast AST-based checks that don't need LLM."""
        findings = []
        now = datetime.now(timezone.utc).isoformat()
        lines = source.splitlines()

        for i, line in enumerate(lines, 1):
            # Check for TODO/FIXME/HACK near financial logic keywords
            if re.search(r'(TODO|FIXME|HACK)', line, re.I):
                context = " ".join(lines[max(0,i-3):i+3])
                if any(kw in context.lower() for kw in ["pnl","price","trade","wallet","kelly"]):
                    findings.append({
                        "file_path": filepath, "line_number": i,
                        "finding_type": "todo_critical", "severity": "medium",
                        "description": f"TODO/FIXME near financial logic: {line.strip()}",
                        "snippet": line.strip(), "found_at": now
                    })
            # Check for hardcoded prices that might leak into production
            if re.search(r'(test_price|mock_price|hardcoded|fake_price)\s*=\s*[0-9]', line, re.I):
                findings.append({
                    "file_path": filepath, "line_number": i,
                    "finding_type": "test_leak", "severity": "high",
                    "description": f"Possible test/mock price value: {line.strip()}",
                    "snippet": line.strip(), "found_at": now
                })
        return findings

    def _llm_analysis(self, filepath: str, source: str) -> List[dict]:
        """Send source to qwen3:30b for logic review."""
        now = datetime.now(timezone.utc).isoformat()
        # Truncate to 8000 chars to stay within context
        truncated = source[:8000]
        try:
            resp = httpx.post(OLLAMA_URL, json={
                "model": ANALYSIS_MODEL,
                "messages": [{"role": "user", "content": LLM_PROMPT + truncated}],
                "stream": False
            }, timeout=TIMEOUT)
            content = resp.json()["message"]["content"]
            # Extract JSON array
            match = re.search(r'\[.*\]', content, re.DOTALL)
            if not match:
                return []
            items = json.loads(match.group())
            return [{
                "file_path": filepath,
                "line_number": item.get("line"),
                "finding_type": item.get("type", "logic_error"),
                "severity": item.get("severity", "medium"),
                "description": item.get("description", ""),
                "snippet": None,
                "found_at": now,
            } for item in items if isinstance(item, dict)]
        except Exception as e:
            return [{
                "file_path": filepath, "line_number": None,
                "finding_type": "analysis_error", "severity": "low",
                "description": f"LLM analysis failed: {e}",
                "snippet": None, "found_at": now
            }]

    def analyze_file(self, filepath: str) -> List[dict]:
        path = Path(filepath).expanduser()
        if not path.exists():
            return []
        source = path.read_text(encoding="utf-8", errors="ignore")
        findings = self._deterministic_checks(str(path), source)
        findings.extend(self._llm_analysis(str(path), source))
        return findings

    def run(self) -> dict:
        all_findings = []
        for fp in TARGET_FILES:
            findings = self.analyze_file(fp)
            for f in findings:
                self.db.insert("code_findings", f)
            all_findings.extend(findings)

        by_severity = {}
        for f in all_findings:
            by_severity[f["severity"]] = by_severity.get(f["severity"], 0) + 1
        return {"total_findings": len(all_findings), "by_severity": by_severity}
```

- [ ] **Step 2: Smoke-test (no pytest — requires Ollama)**

```bash
cd ~/openclaw/scripts && python -c "
from inspector.inspector_db import InspectorDB
from inspector.logic_analyzer import LogicAnalyzer
db = InspectorDB(); db.init()
la = LogicAnalyzer(db)
# Test deterministic checks only (no LLM)
findings = la._deterministic_checks('/tmp/test.py', 'x = 1  # TODO fix price calculation')
print('Findings:', findings)
"
```

Expected: prints 1 finding with `todo_critical`

- [ ] **Step 3: Commit**

```bash
cd ~/openclaw && git add scripts/inspector/logic_analyzer.py && git commit -m "feat(inspector): logic analyzer — deterministic + LLM code review"
```

---

## Task 8: Repo Scanner

**Files:**
- Create: `scripts/inspector/repo_scanner.py`

- [ ] **Step 1: Implement `repo_scanner.py`**

```python
# scripts/inspector/repo_scanner.py
"""
Scans git history for suspicious changes to trading logic.
Flags: P&L code changes after trades recorded, test data leaks, suspicious commit patterns.
"""
import subprocess
import re
from datetime import datetime, timezone
from pathlib import Path
from inspector.inspector_db import InspectorDB

REPO_ROOT     = Path("~/openclaw").expanduser()
CRITICAL_FILES = [
    "scripts/mirofish/paper_wallet.py",
    "scripts/mirofish/trading_brain.py",
    "scripts/trading-bot.py",
]
# Keywords that suggest retroactive P&L fixing
SUSPICIOUS_PATTERNS = [
    r'pnl\s*=',
    r'exit_price\s*=',
    r'closed_win',
    r'closed_loss',
    r'balance\s*=',
]

class RepoScanner:
    def __init__(self, db: InspectorDB, repo_root: str = None):
        self.db = db
        self.repo = Path(repo_root or REPO_ROOT)

    def _git(self, *args) -> str:
        try:
            result = subprocess.run(
                ["git", "-C", str(self.repo)] + list(args),
                capture_output=True, text=True, timeout=30
            )
            return result.stdout.strip()
        except Exception:
            return ""

    def _get_recent_commits(self, days: int = 7) -> list:
        log = self._git("log", f"--since={days} days ago", "--format=%H|%ai|%s", "--",
                       *CRITICAL_FILES)
        commits = []
        for line in log.splitlines():
            if "|" in line:
                parts = line.split("|", 2)
                if len(parts) == 3:
                    commits.append({"hash": parts[0], "date": parts[1], "message": parts[2]})
        return commits

    def _check_commit_diff(self, commit_hash: str, filepath: str) -> list:
        diff = self._git("show", commit_hash, "--", filepath)
        now = datetime.now(timezone.utc).isoformat()
        findings = []
        for i, line in enumerate(diff.splitlines()):
            if not line.startswith("+") or line.startswith("+++"):
                continue
            for pattern in SUSPICIOUS_PATTERNS:
                if re.search(pattern, line, re.I):
                    findings.append({
                        "file_path": filepath, "line_number": i,
                        "finding_type": "retroactive_pnl_change",
                        "severity": "high",
                        "description": f"Commit {commit_hash[:8]} modified P&L-related logic: {line.strip()[:100]}",
                        "snippet": line.strip()[:200],
                        "found_at": now,
                    })
        return findings

    def run(self) -> dict:
        commits = self._get_recent_commits(days=7)
        all_findings = []
        for commit in commits:
            for fp in CRITICAL_FILES:
                findings = self._check_commit_diff(commit["hash"], fp)
                for f in findings:
                    self.db.insert("code_findings", f)
                all_findings.extend(findings)

        return {
            "commits_scanned": len(commits),
            "findings": len(all_findings),
        }
```

- [ ] **Step 2: Smoke-test**

```bash
cd ~/openclaw/scripts && python -c "
from inspector.inspector_db import InspectorDB
from inspector.repo_scanner import RepoScanner
db = InspectorDB(); db.init()
rs = RepoScanner(db)
print('Recent commits:', rs._get_recent_commits(7))
"
```

- [ ] **Step 3: Commit**

```bash
cd ~/openclaw && git add scripts/inspector/repo_scanner.py && git commit -m "feat(inspector): repo scanner — git history analysis"
```

---

## Task 9: Dashboard (Report Generator)

**Files:**
- Create: `scripts/inspector/dashboard.py`

- [ ] **Step 1: Implement `dashboard.py`**

```python
# scripts/inspector/dashboard.py
"""
Generates markdown audit reports from inspector_gadget.db.
Saves to ~/openclaw/security/inspector/reports/
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from inspector.inspector_db import InspectorDB

REPORTS_DIR = Path("~/openclaw/security/inspector/reports").expanduser()

class Dashboard:
    def __init__(self, db: InspectorDB):
        self.db = db
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    def _pct(self, n, total):
        return f"{n/total*100:.1f}%" if total > 0 else "N/A"

    def generate(self) -> str:
        verified    = self.db.fetch_all("verified_trades")
        resolutions = self.db.fetch_all("resolution_audits")
        findings    = self.db.fetch_all("code_findings")
        halluc      = self.db.fetch_all("hallucination_checks")

        total_v = len(verified)
        status_counts = {}
        for row in verified:
            s = row.get("status", "UNKNOWN")
            status_counts[s] = status_counts.get(s, 0) + 1

        total_r = len(resolutions)
        res_match    = sum(1 for r in resolutions if r.get("match") == 1)
        res_mismatch = sum(1 for r in resolutions if r.get("match") == 0)
        res_unkown   = sum(1 for r in resolutions if r.get("match") == -1)

        critical_findings = [f for f in findings if f.get("severity") == "critical"]
        high_findings     = [f for f in findings if f.get("severity") == "high"]

        halluc_grounded = sum(1 for h in halluc if h.get("verification_result") == "GROUNDED")
        halluc_bad      = sum(1 for h in halluc if h.get("verification_result") == "HALLUCINATED")

        # Trust score: start at 100, deduct per issue
        trust = 100
        trust -= status_counts.get("IMPOSSIBLE", 0) * 10
        trust -= status_counts.get("DISCREPANCY", 0) * 5
        trust -= res_mismatch * 8
        trust -= len(critical_findings) * 15
        trust -= len(high_findings) * 5
        trust -= halluc_bad * 10
        trust = max(0, trust)

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        report_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

        lines = [
            f"# Inspector Gadget Audit Report",
            f"**Generated:** {now_str}",
            f"**Overall Trust Score: {trust}/100**",
            "",
            "---",
            "",
            "## Trade Verification",
            f"| Status | Count | % |",
            f"|--------|-------|---|",
        ]
        for status in ["VERIFIED", "DISCREPANCY", "IMPOSSIBLE", "UNVERIFIABLE"]:
            n = status_counts.get(status, 0)
            lines.append(f"| {status} | {n} | {self._pct(n, total_v)} |")
        lines.append(f"| **TOTAL** | **{total_v}** | 100% |")

        lines += [
            "",
            "## Resolution Audits",
            f"- ✅ Matched: {res_match} ({self._pct(res_match, total_r)})",
            f"- ❌ Mismatched: {res_mismatch} ({self._pct(res_mismatch, total_r)})",
            f"- ⚠️ Unverifiable: {res_unkown} ({self._pct(res_unkown, total_r)})",
            "",
            "## Code Analysis",
            f"- 🔴 Critical: {len(critical_findings)}",
            f"- 🟠 High: {len(high_findings)}",
            f"- 🟡 Medium: {sum(1 for f in findings if f.get('severity') == 'medium')}",
            f"- 🔵 Low: {sum(1 for f in findings if f.get('severity') == 'low')}",
            "",
        ]

        if critical_findings or high_findings:
            lines.append("### Critical & High Findings")
            for f in (critical_findings + high_findings)[:10]:
                lines.append(f"- **[{f['severity'].upper()}]** `{f.get('file_path','?')}:{f.get('line_number','?')}` — {f.get('description','')}")
            lines.append("")

        lines += [
            "## Hallucination Checks",
            f"- ✅ Grounded: {halluc_grounded}",
            f"- ❌ Hallucinated: {halluc_bad}",
            f"- ⚠️ Unverifiable: {sum(1 for h in halluc if h.get('verification_result') == 'UNVERIFIABLE')}",
            "",
            "---",
            f"*Report ID: {report_id} | Inspector Gadget v1.0*",
        ]

        report_text = "\n".join(lines)
        report_path = REPORTS_DIR / f"audit-{report_id}.md"
        report_path.write_text(report_text)

        self.db.insert("audit_reports", {
            "report_id": report_id, "generated_at": now_str,
            "summary": f"Trust: {trust}/100 | {total_v} trades | {res_mismatch} resolution mismatches | {len(critical_findings)} critical findings",
            "total_trades_checked": total_v,
            "verified_count": status_counts.get("VERIFIED", 0),
            "discrepancy_count": status_counts.get("DISCREPANCY", 0),
            "impossible_count": status_counts.get("IMPOSSIBLE", 0),
            "unverifiable_count": status_counts.get("UNVERIFIABLE", 0),
            "trust_scores_json": json.dumps({"overall": trust}),
            "red_flags_json": json.dumps([f.get("description") for f in critical_findings]),
            "report_path": str(report_path),
        })
        return str(report_path)
```

- [ ] **Step 2: Smoke-test**

```bash
cd ~/openclaw/scripts && python -c "
from inspector.inspector_db import InspectorDB
from inspector.dashboard import Dashboard
db = InspectorDB(); db.init()
d = Dashboard(db)
path = d.generate()
print('Report saved to:', path)
import subprocess; subprocess.run(['cat', path])
"
```

- [ ] **Step 3: Commit**

```bash
cd ~/openclaw && git add scripts/inspector/dashboard.py && git commit -m "feat(inspector): markdown report generator"
```

---

## Task 10: CLI Entry Point + Telegram

**Files:**
- Create: `scripts/inspector/run_inspection.py`

- [ ] **Step 1: Implement `run_inspection.py`**

```python
#!/usr/bin/env python3
# scripts/inspector/run_inspection.py
"""
Inspector Gadget CLI
Usage:
  python run_inspection.py --full
  python run_inspection.py --verify-trades
  python run_inspection.py --scan-code
  python run_inspection.py --report
"""
import argparse
import json
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

# Bootstrap path so imports work when called from any directory
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from inspector.inspector_db import InspectorDB
from inspector.polymarket_client import PolymarketClient
from inspector.verifier import TradeVerifier
from inspector.resolution_auditor import ResolutionAuditor
from inspector.stats_auditor import StatsAuditor
from inspector.hallucination_detector import HallucinationDetector
from inspector.logic_analyzer import LogicAnalyzer
from inspector.repo_scanner import RepoScanner
from inspector.dashboard import Dashboard

CONFIG_PATH  = Path(__file__).parent / "config.json"
ENV_PATH     = Path("~/.openclaw/.env").expanduser()
CLAWMSON_DB  = "~/.openclaw/clawmson.db"
SIGNALS_JSON = "~/openclaw/trading/signals.json"

def _load_env() -> dict:
    env = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            if line.strip() and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env

def notify_telegram(msg: str):
    env = _load_env()
    token   = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_ALLOWED_USERS", "").strip().strip('"[]').split(",")[0].strip()
    if not token or not chat_id:
        print("[Telegram] No credentials — skipping notification")
        return
    try:
        data = json.dumps({"chat_id": chat_id, "text": msg[:4000]}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data, headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=10)
        print("[Telegram] Notification sent.")
    except Exception as e:
        print(f"[Telegram] Failed: {e}")

def main():
    parser = argparse.ArgumentParser(description="Inspector Gadget — trading audit system")
    parser.add_argument("--full",          action="store_true", help="Run all checks")
    parser.add_argument("--verify-trades", action="store_true", help="Trade + resolution verification only")
    parser.add_argument("--scan-code",     action="store_true", help="Code analysis only")
    parser.add_argument("--report",        action="store_true", help="Generate report from existing data")
    args = parser.parse_args()

    if not any(vars(args).values()):
        parser.print_help()
        return

    db   = InspectorDB()
    db.init()
    poly = PolymarketClient()

    results = {}
    start   = datetime.now(timezone.utc)

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
        sa = StatsAuditor(db=db)
        results["stats"] = sa.run(CLAWMSON_DB)
        print(f"   → {results['stats'].get('trust_score', '?')} trust score, {len(results['stats'].get('red_flags',[]))} flags")

        print("🧠 Hallucination detection...")
        hd = HallucinationDetector(db=db, poly=poly)
        results["hallucination"] = hd.run_on_signals(SIGNALS_JSON)
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

    # Always generate report
    print("📄 Generating report...")
    dash = Dashboard(db=db)
    report_path = dash.generate()
    print(f"   → Report saved: {report_path}")

    elapsed = (datetime.now(timezone.utc) - start).seconds
    report = db.fetch_all("audit_reports")
    last_report = report[-1] if report else {}
    trust = json.loads(last_report.get("trust_scores_json", "{}")).get("overall", "?")
    impossible = last_report.get("impossible_count", 0)
    discrepancy = last_report.get("discrepancy_count", 0)

    summary = (
        f"🔍 Inspector Gadget Report ({datetime.now(timezone.utc).strftime('%Y-%m-%d')})\n"
        f"Trust Score: {trust}/100\n"
        f"Trades checked: {last_report.get('total_trades_checked', '?')}\n"
        f"✅ Verified: {last_report.get('verified_count', '?')}\n"
        f"⚠️ Discrepancies: {discrepancy}\n"
        f"🚨 Impossible: {impossible}\n"
        f"Code findings: {results.get('code', {}).get('total_findings', '?')}\n"
        f"Report: {report_path}\n"
        f"Elapsed: {elapsed}s"
    )
    print("\n" + summary)

    hallucinated = sum(1 for h in db.fetch_all("hallucination_checks")
                       if h.get("verification_result") == "HALLUCINATED")
    alert_needed = (impossible and impossible > 0) or (discrepancy and discrepancy > 5) or (hallucinated and hallucinated > 0)
    if alert_needed:
        notify_telegram(f"🚨 INSPECTOR GADGET ALERT\n{summary}")
    else:
        notify_telegram(summary)

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Make executable**

```bash
chmod +x ~/openclaw/scripts/inspector/run_inspection.py
```

- [ ] **Step 3: Smoke-test (report-only mode, no API calls)**

```bash
cd ~/openclaw/scripts && python inspector/run_inspection.py --report
```
Expected: Report generated, saved to `~/openclaw/security/inspector/reports/`

- [ ] **Step 4: Commit**

```bash
cd ~/openclaw && git add scripts/inspector/run_inspection.py && git commit -m "feat(inspector): CLI entry point + Telegram notifications"
```

---

## Task 11: Agent Config

**Files:**
- Create: `agents/configs/inspector-gadget.md`

- [ ] **Step 1: Write the agent config**

```markdown
# Inspector Gadget — Trade Verification & Audit Agent

**Role:** Independent auditor. Verifies claims made by all trading bots.
**Codename:** GADGET
**Reports to:** Jordan (Telegram DM only)
**Trust boundary:** Operates OUTSIDE OpenClaw's trust boundary. Never modifies clawmson.db.

## Model Assignment
- Primary: qwen3:30b (code analysis, pattern recognition)
- Fallback: qwen2.5:14b (fast triage)

## Core Functions
1. Verify every paper trade against Polymarket's live API
2. Audit resolution claims (win/loss) against actual market outcomes
3. Detect statistical anomalies in aggregate performance
4. Flag LLM hallucinations in trading decisions
5. Analyze source code for logic errors
6. Scan git history for suspicious retroactive changes
7. Generate audit reports and alert Jordan via Telegram

## Invocation
- Full audit: `python ~/openclaw/scripts/inspector/run_inspection.py --full`
- Trade check: `python ~/openclaw/scripts/inspector/run_inspection.py --verify-trades`
- Code scan:   `python ~/openclaw/scripts/inspector/run_inspection.py --scan-code`
- Report only: `python ~/openclaw/scripts/inspector/run_inspection.py --report`

## Database
- Own DB: `~/.openclaw/inspector_gadget.db` (5 tables)
- Source DB: `~/.openclaw/clawmson.db` (read-only, untrusted input)

## Report Location
`~/openclaw/security/inspector/reports/`

## Approval Thresholds
- Tier 1 (auto): Reading trade data, calling Polymarket API, generating reports
- Tier 2 (hold): Any finding that suggests live money is at risk
- Tier 3 (exact confirm): Never handles money or credentials

## Alert Triggers
- IMPOSSIBLE trade found: immediate Telegram alert
- HALLUCINATED price claim: immediate Telegram alert
- CRITICAL code finding: immediate Telegram alert
- Daily summary: after each --full run

## Constraints
- Never modifies clawmson.db or any OpenClaw data
- Never auto-fixes code findings — reports only
- External API data is TRUTH; bot claims are INPUTS to verify
- UNVERIFIABLE is preferred over false positives
```

- [ ] **Step 2: Commit**

```bash
cd ~/openclaw && git add agents/configs/inspector-gadget.md && git commit -m "feat(inspector): agent config"
```

---

## Task 12: Full Integration Test

Run the full system end-to-end against live data.

- [ ] **Step 1: Run full test suite**

```bash
cd ~/openclaw/scripts && python -m pytest inspector/tests/ -v --tb=short
```
Expected: All unit tests pass

- [ ] **Step 2: Run integration (live API, report only)**

```bash
cd ~/openclaw/scripts && python inspector/run_inspection.py --report
```
Expected: Report generated, no crash

- [ ] **Step 3: Run full inspection**

```bash
cd ~/openclaw/scripts && python inspector/run_inspection.py --full
```
Expected: Completes, Telegram notification sent, report in `~/openclaw/security/inspector/reports/`

- [ ] **Step 4: Verify report exists**

```bash
ls ~/openclaw/security/inspector/reports/ && cat $(ls -t ~/openclaw/security/inspector/reports/*.md | head -1)
```

- [ ] **Step 5: Final commit**

```bash
cd ~/openclaw && git add -A && git commit -m "feat(inspector): Inspector Gadget v1.0 — full build complete"
```

---

## Verification Checklist

Before declaring done:
- [ ] All 4 unit test files pass (`pytest inspector/tests/ -v`)
- [ ] `inspector_gadget.db` created at `~/.openclaw/`
- [ ] `--report` mode works with empty DB (no crash)
- [ ] `--full` mode completes against live clawmson.db
- [ ] At least one audit report exists in `~/openclaw/security/inspector/reports/`
- [ ] Telegram notification delivered
- [ ] `agents/configs/inspector-gadget.md` exists

---

*Plan: Inspector Gadget v1.0 | Written: 2026-03-26 | OpenClaw*
