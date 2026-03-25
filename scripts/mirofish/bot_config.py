#!/usr/bin/env python3
"""
bot_config — shared parameter loader for all trading bots.
Priority: DB context table → environment variable → hardcoded default.
The calibrator writes here; bots read from here.
"""
import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.environ.get("CLAWMSON_DB_PATH", Path.home() / ".openclaw" / "clawmson.db"))

def _get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def get_param(bot_name: str, param_name: str, default=None):
    """Get a bot parameter. Checks DB first, then env, then default."""
    key = f"{bot_name}_{param_name}"
    # 1. Try DB
    try:
        conn = _get_conn()
        row = conn.execute(
            "SELECT value FROM context WHERE chat_id=? AND key=?",
            ("calibrator", key)
        ).fetchone()
        conn.close()
        if row:
            val = row["value"]
            if isinstance(default, float):
                return float(val)
            elif isinstance(default, int):
                return int(float(val))
            return val
    except Exception:
        pass
    # 2. Try env
    env_key = f"MIROFISH_{bot_name.upper()}_{param_name}"
    env_val = os.environ.get(env_key)
    if env_val is not None:
        try:
            if isinstance(default, float):
                return float(env_val)
            elif isinstance(default, int):
                return int(float(env_val))
            return env_val
        except Exception:
            pass
    # 3. Default
    return default

def set_param(bot_name: str, param_name: str, value):
    """Write a bot parameter to DB (used by calibrator)."""
    key = f"{bot_name}_{param_name}"
    conn = _get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO context (chat_id, key, value) VALUES (?, ?, ?)",
        ("calibrator", key, str(value))
    )
    conn.commit()
    conn.close()

def get_all_params(bot_name: str) -> dict:
    """Get all calibrator-set params for a bot."""
    conn = _get_conn()
    prefix = f"{bot_name}_"
    rows = conn.execute(
        "SELECT key, value FROM context WHERE chat_id='calibrator' AND key LIKE ?",
        (prefix + "%",)
    ).fetchall()
    conn.close()
    return {r["key"].removeprefix(prefix): r["value"] for r in rows}


def confidence_position_pct(confidence: float, base_pct: float = 0.03) -> float:
    """Scale position size by confidence. Higher confidence = bigger bet.

    Tiers calibrated from 107 resolved trades (2026-03-25):
    - <0.50: 8.7% WR → cut to 1/3 base (exploratory only)
    - 0.50-0.70: 33% WR → base rate
    - 0.70-0.90: 58% WR → 1.5x base (proven edge)
    - 0.90+: 66% WR → 1.5x base (cap here — was oversizing)
    """
    if confidence < 0.50:
        return base_pct * 0.33
    elif confidence < 0.70:
        return base_pct
    elif confidence < 0.90:
        return base_pct * 1.5
    else:
        return base_pct * 1.5  # cap — very high was losing money from oversizing
