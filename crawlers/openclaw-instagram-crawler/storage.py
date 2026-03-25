"""Shared storage module."""
import json, gzip, sqlite3, os, time
from pathlib import Path
from datetime import datetime, timedelta

OPENCLAW_SIGNALS = Path.home() / "openclaw" / "autoresearch" / "signals"
LOCAL_DATA = Path(__file__).parent / "data"
RAW_DIR = LOCAL_DATA / "raw"
ARCHIVE_DIR = LOCAL_DATA / "archive"
DB_PATH = LOCAL_DATA / "signals.db"
RAW_RETENTION_DAYS = 7
ARCHIVE_RETENTION_DAYS = 90

def init():
    for d in [OPENCLAW_SIGNALS, RAW_DIR, ARCHIVE_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""CREATE TABLE IF NOT EXISTS signals (
        id TEXT PRIMARY KEY, platform TEXT, type TEXT, source_url TEXT,
        source_author TEXT, title TEXT, body TEXT, ticker_or_market TEXT,
        direction TEXT, confidence REAL, urgency TEXT, engagement_json TEXT,
        tags_json TEXT, raw_json TEXT, extracted_at TEXT, crawl_id TEXT)""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_platform_time ON signals(platform, extracted_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_ticker ON signals(ticker_or_market)")
    conn.commit(); conn.close()

def write_signals(platform, crawl_id, signals):
    bus_file = OPENCLAW_SIGNALS / f"{platform}.json"
    payload = {"platform": platform, "crawl_id": crawl_id, "crawled_at": datetime.now().isoformat(), "signals": signals, "meta": {"total_signals": len(signals)}}
    bus_file.write_text(json.dumps(payload, indent=2))
    raw_file = RAW_DIR / f"{platform}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    raw_file.write_text(json.dumps(payload, indent=2))
    conn = sqlite3.connect(str(DB_PATH))
    for s in signals:
        try:
            conn.execute("INSERT OR IGNORE INTO signals (id,platform,type,source_url,source_author,title,body,ticker_or_market,direction,confidence,urgency,engagement_json,tags_json,raw_json,extracted_at,crawl_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (s["id"], platform, s.get("type",""), s.get("source_url",""), s.get("source_author",""), s.get("title",""), s.get("body",""), s.get("ticker_or_market",""), s.get("direction","unknown"), s.get("confidence",0), s.get("urgency","days"), json.dumps(s.get("engagement",{})), json.dumps(s.get("tags",[])), json.dumps(s.get("raw_data",{})), s.get("extracted_at",""), crawl_id))
        except: pass
    conn.commit(); conn.close()

def cleanup():
    now = time.time()
    for f in RAW_DIR.glob("*.json"):
        if now - f.stat().st_mtime > RAW_RETENTION_DAYS * 86400:
            with open(f, "rb") as src, gzip.open(ARCHIVE_DIR / f"{f.stem}.json.gz", "wb") as dst: dst.write(src.read())
            f.unlink()
    for f in ARCHIVE_DIR.glob("*.json.gz"):
        if now - f.stat().st_mtime > ARCHIVE_RETENTION_DAYS * 86400: f.unlink()
