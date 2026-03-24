#!/usr/bin/env python3
"""
Spot price feed — fetches BTC/ETH from Binance.US + Coinbase + Kraken public APIs.
Averages prices from available exchanges. Caches to spot_prices SQLite table.

Exchange priority: Binance.US (US-compliant) > Coinbase > Kraken (backup).
Binance global (api.binance.com) is geo-blocked in the US — we use api.binance.us.

Duck-type compatible with DataFeed protocol (base_feed.py).
isinstance(this_module, DataFeed) will return False.
"""
from __future__ import annotations
import os
import sqlite3
import datetime
import requests
from pathlib import Path

source_name = "spot_prices"

SPOT_CACHE_TTL_HOURS = float(os.environ.get("SPOT_CACHE_TTL_HOURS", "0.083"))
SPOT_TIMEOUT = int(os.environ.get("SPOT_TIMEOUT", "10"))

_ASSETS = {
    "BTC": {
        "binance_us": "https://api.binance.us/api/v3/ticker/price?symbol=BTCUSDT",
        "coinbase": "https://api.coinbase.com/v2/prices/BTC-USD/spot",
        "kraken": "https://api.kraken.com/0/public/Ticker?pair=XBTUSD",
    },
    "ETH": {
        "binance_us": "https://api.binance.us/api/v3/ticker/price?symbol=ETHUSDT",
        "coinbase": "https://api.coinbase.com/v2/prices/ETH-USD/spot",
        "kraken": "https://api.kraken.com/0/public/Ticker?pair=ETHUSD",
    },
}


def _get_conn() -> sqlite3.Connection:
    db_path = Path(os.environ.get("CLAWMSON_DB_PATH",
                                   Path.home() / ".openclaw" / "clawmson.db"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _now_iso() -> str:
    return datetime.datetime.utcnow().isoformat()


def _fetch_binance_us(url: str) -> float | None:
    try:
        resp = requests.get(url, timeout=SPOT_TIMEOUT)
        resp.raise_for_status()
        return float(resp.json().get("price", 0))
    except Exception as e:
        print(f"[spot_feed] Binance.US error: {e}")
        return None


def _fetch_coinbase(url: str) -> float | None:
    try:
        resp = requests.get(url, timeout=SPOT_TIMEOUT)
        resp.raise_for_status()
        return float(resp.json().get("data", {}).get("amount", 0))
    except Exception as e:
        print(f"[spot_feed] Coinbase error: {e}")
        return None


def _fetch_kraken(url: str) -> float | None:
    try:
        resp = requests.get(url, timeout=SPOT_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if data.get("error"):
            return None
        # Kraken returns {"result": {"XXBTZUSD": {"c": ["70000.0", "0.1"]}}}
        result = data.get("result", {})
        for pair_data in result.values():
            # "c" = last trade close [price, lot_volume]
            close = pair_data.get("c", [])
            if close:
                return float(close[0])
    except Exception as e:
        print(f"[spot_feed] Kraken error: {e}")
    return None


def _fetch_spot(asset: str) -> dict | None:
    """Fetch spot price for one asset, average across available exchanges."""
    urls = _ASSETS.get(asset)
    if not urls:
        return None

    binance_price = _fetch_binance_us(urls["binance_us"])
    coinbase_price = _fetch_coinbase(urls["coinbase"])
    kraken_price = _fetch_kraken(urls["kraken"])

    prices = [p for p in [binance_price, coinbase_price, kraken_price] if p and p > 0]
    if not prices:
        return None

    avg_price = sum(prices) / len(prices)
    parts = []
    if binance_price:
        parts.append(f"binance.us=${binance_price:,.2f}")
    if coinbase_price:
        parts.append(f"coinbase=${coinbase_price:,.2f}")
    if kraken_price:
        parts.append(f"kraken=${kraken_price:,.2f}")

    return {
        "source": "spot_prices",
        "ticker": f"SPOT:{asset}",
        "signal_type": "spot_price",
        "direction": "neutral",
        "amount_usd": avg_price,
        "description": f"{asset} spot: ${avg_price:,.2f} ({' '.join(parts)})",
        "fetched_at": _now_iso(),
    }


def _is_cache_fresh() -> bool:
    cutoff = (datetime.datetime.utcnow() -
              datetime.timedelta(hours=SPOT_CACHE_TTL_HOURS)).isoformat()
    try:
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM spot_prices WHERE fetched_at > ?",
                (cutoff,)
            ).fetchone()
        return row["cnt"] > 0
    except Exception:
        return False


def _store_signals(signals: list[dict]) -> None:
    if not signals:
        return
    try:
        with _get_conn() as conn:
            conn.executemany("""
                INSERT OR IGNORE INTO spot_prices
                (source, ticker, signal_type, direction, amount_usd, description, fetched_at)
                VALUES (:source, :ticker, :signal_type, :direction,
                        :amount_usd, :description, :fetched_at)
            """, signals)
    except Exception as e:
        print(f"[spot_feed] DB write error: {e}")


def _purge_old() -> None:
    cutoff = (datetime.datetime.utcnow() - datetime.timedelta(hours=24)).isoformat()
    try:
        with _get_conn() as conn:
            conn.execute("DELETE FROM spot_prices WHERE fetched_at < ?", (cutoff,))
    except Exception as e:
        print(f"[spot_feed] Purge error: {e}")


def get_cached() -> list[dict]:
    """Return cached spot price signals within TTL."""
    cutoff = (datetime.datetime.utcnow() -
              datetime.timedelta(hours=SPOT_CACHE_TTL_HOURS)).isoformat()
    try:
        with _get_conn() as conn:
            rows = conn.execute("""
                SELECT source, ticker, signal_type, direction, amount_usd,
                       description, fetched_at
                FROM spot_prices WHERE fetched_at > ?
                ORDER BY fetched_at DESC
            """, (cutoff,)).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"[spot_feed] Cache read error: {e}")
        return []


def get_spot_dict() -> dict[str, float]:
    """Return {'BTC': price, 'ETH': price} from latest cached data."""
    result = {}
    try:
        with _get_conn() as conn:
            for asset in _ASSETS:
                row = conn.execute("""
                    SELECT amount_usd FROM spot_prices
                    WHERE ticker = ? ORDER BY fetched_at DESC LIMIT 1
                """, (f"SPOT:{asset}",)).fetchone()
                if row and row["amount_usd"]:
                    result[asset] = row["amount_usd"]
    except Exception as e:
        print(f"[spot_feed] get_spot_dict error: {e}")
    return result


def fetch() -> list[dict]:
    """Fetch BTC + ETH spot, cache, return signal dicts. Never raises."""
    if _is_cache_fresh():
        print("[spot_feed] Cache fresh — skipping live fetch")
        return get_cached()

    signals = []
    for asset in _ASSETS:
        sig = _fetch_spot(asset)
        if sig:
            signals.append(sig)

    if not signals:
        print("[spot_feed] All exchanges failed — falling back to cache")
        return get_cached()

    _purge_old()
    _store_signals(signals)
    print(f"[spot_feed] Fetched {len(signals)} spot prices")
    return signals
