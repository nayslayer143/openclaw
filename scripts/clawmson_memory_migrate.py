#!/usr/bin/env python3
"""
Clawmson memory system DB migration.
Safe to run multiple times — all operations are idempotent.
Run: python3 ~/openclaw/scripts/clawmson_memory_migrate.py
"""
from __future__ import annotations
import os
import sys
import sqlite3
from pathlib import Path

DB_PATH = Path(os.environ.get("CLAWMSON_DB_PATH",
               Path.home() / ".openclaw" / "clawmson.db"))


def migrate():
    if str(DB_PATH) == ":memory:":
        print("In-memory DB — skipping migration")
        return

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Add archived column to conversations if missing
    cols = {r[1] for r in conn.execute("PRAGMA table_info(conversations)").fetchall()}
    if "archived" not in cols:
        conn.execute("ALTER TABLE conversations ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
        conn.commit()
        print("  + Added archived column to conversations")
    else:
        print("  ✓ archived column already exists")

    conn.close()

    # Force re-init (creates new tables if missing)
    sys.path.insert(0, str(Path(__file__).parent))
    import clawmson_db as db
    db._init_db()

    # Count existing data
    with db._get_conn() as c:
        conv_count = c.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        ctx_count  = c.execute("SELECT COUNT(*) FROM context").fetchone()[0]
        ref_count  = c.execute("SELECT COUNT(*) FROM refs").fetchone()[0]

    print(f"\nMigration complete.")
    print(f"  Existing rows: conversations={conv_count}, context={ctx_count}, refs={ref_count}")
    print(f"  New tables ready: stm_summaries, episodic_memories, semantic_facts,"
          f" procedures, procedure_candidates, memory_fts, sessions")


if __name__ == "__main__":
    print(f"Migrating {DB_PATH} ...")
    migrate()
