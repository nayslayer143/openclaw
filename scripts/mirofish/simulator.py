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
import requests


def _get_conn() -> sqlite3.Connection:
    db_path = Path(os.environ.get("CLAWMSON_DB_PATH", Path.home() / ".openclaw" / "clawmson.db"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
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

CREATE TABLE IF NOT EXISTS context (
    chat_id  TEXT NOT NULL,
    key      TEXT NOT NULL,
    value    TEXT NOT NULL,
    PRIMARY KEY (chat_id, key)
);

CREATE TABLE IF NOT EXISTS uw_signals (
    id          INTEGER PRIMARY KEY,
    source      TEXT NOT NULL,
    ticker      TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    direction   TEXT NOT NULL,
    amount_usd  REAL,
    description TEXT NOT NULL,
    fetched_at  TEXT NOT NULL,
    UNIQUE (source, ticker, signal_type, fetched_at)
);
CREATE INDEX IF NOT EXISTS idx_uw_signals_ticker_time
    ON uw_signals(ticker, fetched_at);

CREATE TABLE IF NOT EXISTS crucix_signals (
    id          INTEGER PRIMARY KEY,
    source      TEXT NOT NULL,
    ticker      TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    direction   TEXT NOT NULL,
    amount_usd  REAL,
    description TEXT NOT NULL,
    fetched_at  TEXT NOT NULL,
    UNIQUE (source, ticker, signal_type, fetched_at)
);
CREATE INDEX IF NOT EXISTS idx_crucix_signals_ticker_time
    ON crucix_signals(ticker, fetched_at);

CREATE TABLE IF NOT EXISTS spot_prices (
    id          INTEGER PRIMARY KEY,
    source      TEXT NOT NULL,
    ticker      TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    direction   TEXT NOT NULL,
    amount_usd  REAL,
    description TEXT NOT NULL,
    fetched_at  TEXT NOT NULL,
    UNIQUE (source, ticker, signal_type, fetched_at)
);
CREATE INDEX IF NOT EXISTS idx_spot_prices_ticker_time
    ON spot_prices(ticker, fetched_at);

CREATE TABLE IF NOT EXISTS kalshi_markets (
    ticker        TEXT NOT NULL,
    event_ticker  TEXT,
    title         TEXT,
    category      TEXT,
    yes_bid       REAL,
    yes_ask       REAL,
    no_bid        REAL,
    no_ask        REAL,
    last_price    REAL,
    volume        REAL,
    volume_24h    REAL,
    open_interest REAL,
    status        TEXT,
    close_time    TEXT,
    rules_primary TEXT,
    strike_type   TEXT,
    cap_strike    REAL,
    floor_strike  REAL,
    fetched_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cross_venue_arb_trades (
    id              INTEGER PRIMARY KEY,
    pair_id         TEXT NOT NULL,
    buy_venue       TEXT NOT NULL,
    sell_venue      TEXT NOT NULL,
    buy_market_id   TEXT NOT NULL,
    sell_market_id  TEXT NOT NULL,
    buy_price       REAL NOT NULL,
    sell_price      REAL NOT NULL,
    spread          REAL NOT NULL,
    estimated_edge  REAL NOT NULL,
    match_confidence REAL NOT NULL,
    direction       TEXT NOT NULL,
    amount_usd      REAL NOT NULL,
    entry_price     REAL NOT NULL,
    detected_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_xv_arb_pair_time
    ON cross_venue_arb_trades(pair_id, detected_at);

CREATE TABLE IF NOT EXISTS price_lag_trades (
    id              INTEGER PRIMARY KEY,
    market_id       TEXT NOT NULL,
    question        TEXT NOT NULL,
    asset           TEXT NOT NULL,
    contract_type   TEXT NOT NULL,
    spot_price      REAL NOT NULL,
    threshold       REAL,
    bracket_low     REAL,
    bracket_high    REAL,
    polymarket_price REAL NOT NULL,
    raw_dislocation REAL NOT NULL,
    decayed_edge    REAL NOT NULL,
    days_to_expiry  REAL NOT NULL,
    direction       TEXT NOT NULL,
    confidence      REAL NOT NULL,
    amount_usd      REAL NOT NULL,
    entry_price     REAL NOT NULL,
    detected_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_price_lag_market_time
    ON price_lag_trades(market_id, detected_at);

INSERT OR IGNORE INTO context (chat_id, key, value)
VALUES ('mirofish', 'starting_balance', '1000.00');
"""


def migrate():
    """Create mirofish tables. Idempotent."""
    with _get_conn() as conn:
        conn.executescript(MIGRATION_SQL)
    db_path = Path(os.environ.get("CLAWMSON_DB_PATH", Path.home() / ".openclaw" / "clawmson.db"))
    print(f"[mirofish] Migration complete. DB: {db_path}")


def _log_price_lag_trade(decision) -> None:
    """Write price-lag arb tracking row from decision.metadata."""
    m = decision.metadata
    if not m:
        return
    try:
        with _get_conn() as conn:
            conn.execute("""
                INSERT INTO price_lag_trades
                (market_id, question, asset, contract_type, spot_price,
                 threshold, bracket_low, bracket_high, polymarket_price,
                 raw_dislocation, decayed_edge, days_to_expiry,
                 direction, confidence, amount_usd, entry_price, detected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                decision.market_id, decision.question,
                m.get("asset"), m.get("contract_type"), m.get("spot_price"),
                m.get("threshold"), m.get("bracket_low"), m.get("bracket_high"),
                m.get("polymarket_price"), m.get("raw_dislocation"),
                m.get("decayed_edge"), m.get("days_to_expiry"),
                decision.direction, decision.confidence,
                decision.amount_usd, decision.entry_price,
                datetime.datetime.utcnow().isoformat(),
            ))
    except Exception as e:
        print(f"[mirofish] Price-lag tracking error: {e}")


def _notify_dashboard():
    """Ping the dashboard to trigger SSE refresh."""
    try:
        requests.post("http://127.0.0.1:7080/api/trading/notify", timeout=2)
    except Exception:
        pass


def _log_cross_venue_arb_trade(decision) -> None:
    """Write cross-venue arb tracking row from decision.metadata."""
    m = decision.metadata
    if not m:
        return
    try:
        with _get_conn() as conn:
            conn.execute("""
                INSERT INTO cross_venue_arb_trades
                (pair_id, buy_venue, sell_venue, buy_market_id, sell_market_id,
                 buy_price, sell_price, spread, estimated_edge, match_confidence,
                 direction, amount_usd, entry_price, detected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                m.get("pair_id", ""),
                m.get("buy_venue", ""),
                m.get("sell_venue", ""),
                decision.market_id,
                "",  # sell leg market_id — single-leg paper trade
                m.get("buy_price", 0),
                m.get("sell_price", 0),
                m.get("spread", 0),
                m.get("estimated_edge", 0),
                m.get("match_confidence", 0),
                decision.direction,
                decision.amount_usd,
                decision.entry_price,
                datetime.datetime.utcnow().isoformat(),
            ))
    except Exception as e:
        print(f"[mirofish] Cross-venue arb tracking error: {e}")


def _normalize_polymarket_events(markets: list[dict]) -> list:
    """Convert raw Polymarket market dicts to MarketEvent objects."""
    try:
        from scripts.mirofish.market_event import MarketEventNormalizer
    except ImportError:
        return []

    events = []
    for m in markets:
        try:
            # polymarket_feed returns flat dicts; normalizer expects gamma API format
            # Rebuild the gamma-like payload from our flat dict
            raw = {
                "conditionId": m.get("market_id", ""),
                "question": m.get("question", ""),
                "category": m.get("category", ""),
                "volume": m.get("volume", 0),
                "endDate": m.get("end_date"),
                "active": True,
                "closed": False,
                "outcomePrices": [str(m.get("yes_price", 0)), str(m.get("no_price", 0))],
                "outcomes": ["Yes", "No"],
            }
            events.append(MarketEventNormalizer.normalize_polymarket(raw))
        except Exception:
            pass
    return events


def _fetch_kalshi_events() -> list:
    """Fetch Kalshi markets and normalize to MarketEvent objects."""
    try:
        import scripts.mirofish.kalshi_feed as kalshi_feed
        from scripts.mirofish.market_event import MarketEventNormalizer
    except ImportError:
        return []

    raw_markets = kalshi_feed.fetch()
    if not raw_markets:
        return []

    events = []
    for m in raw_markets:
        try:
            events.append(MarketEventNormalizer.normalize_kalshi(m))
        except Exception:
            pass

    print(f"[mirofish] Kalshi: {len(events)} markets normalized")
    return events


def run_loop():
    """Full simulation loop: fetch → analyze → trade → stops → snapshot."""
    import scripts.mirofish.polymarket_feed as feed
    import scripts.mirofish.paper_wallet as wallet
    import scripts.mirofish.trading_brain as brain
    import scripts.mirofish.dashboard as dash

    print(f"[mirofish] Run loop starting — {datetime.datetime.utcnow().isoformat()}")

    # 1. Fetch market data (Polymarket + Kalshi)
    markets = feed.fetch_markets()
    kalshi_events = _fetch_kalshi_events()
    polymarket_events = _normalize_polymarket_events(markets) if markets else []

    if kalshi_events:
        print(f"[mirofish] Cross-venue: {len(polymarket_events)} Polymarket + "
              f"{len(kalshi_events)} Kalshi events for matching")

    if not markets:
        print("[mirofish] No markets available (API down + cache stale). Skipping trades.")
    else:
        # 1.5. Data quality check — filter out bad markets before trading
        try:
            import scripts.mirofish.data_quality as dq
            quality_report = dq.validate_markets(markets)
            if quality_report.alerts:
                print(f"[mirofish] Data quality: {len(quality_report.alerts)} alerts, "
                      f"{len(quality_report.markets_blocked)} blocked")
            markets = dq.filter_tradeable(markets, quality_report)
        except Exception as e:
            print(f"[mirofish] Data quality check error: {e}")

        # 2. Get wallet state
        state = wallet.get_state()
        print(f"[mirofish] Wallet: ${state['balance']:.2f} | "
              f"Positions: {state['open_positions']} | "
              f"Win rate: {state['win_rate']*100:.0f}%")

        # 3. Fetch UW signals ([] if key not set or API down)
        import scripts.mirofish.unusual_whales_feed as uw_feed
        import scripts.mirofish.crucix_feed as crucix_feed
        import scripts.mirofish.spot_feed as spot_feed
        uw_signals = uw_feed.fetch()
        if uw_signals:
            print(f"[mirofish] UW signals: {len(uw_signals)} "
                  f"({len(set(s['ticker'] for s in uw_signals))} tickers)")

        crucix_signals = crucix_feed.fetch()
        if crucix_signals:
            print(f"[mirofish] Crucix signals: {len(crucix_signals)}")

        all_signals = uw_signals + crucix_signals

        spot_signals = spot_feed.fetch()
        spot_dict = spot_feed.get_spot_dict()
        if spot_dict:
            print(f"[mirofish] Spot prices: " +
                  ", ".join(f"{k}=${v:,.0f}" for k, v in spot_dict.items()))

        # 4. Analyze markets (now with cross-venue data)
        decisions = brain.analyze(
            markets, state,
            signals=all_signals or None,
            spot_prices=spot_dict or None,
            polymarket_events=polymarket_events or None,
            kalshi_events=kalshi_events or None,
        )
        print(f"[mirofish] Brain returned {len(decisions)} trade decisions")

        # 5. Execute trades + track strategy performance
        try:
            import scripts.mirofish.strategy_tracker as tracker
            tracker.migrate()
            tracker.sync_from_paper_trades()
        except Exception as e:
            print(f"[mirofish] Strategy tracker init: {e}")
            tracker = None

        try:
            import scripts.mirofish.security_auditor as auditor
            import scripts.mirofish.missed_opportunities as missed_opps
            missed_opps.migrate()
        except Exception:
            auditor = None
            missed_opps = None

        for d in decisions:
            # Pre-execution security audit
            if auditor:
                audit = auditor.audit_trade(
                    d.market_id, d.direction, d.entry_price,
                    d.amount_usd, state["balance"], d.strategy,
                )
                if not audit.approved:
                    print(f"[mirofish] Audit blocked: {d.market_id} — {audit.reason}")
                    if missed_opps:
                        try:
                            missed_opps.record_missed(
                                d.market_id, d.direction, d.strategy,
                                d.entry_price, d.confidence, d.amount_usd,
                                f"audit:{audit.reason}", d.metadata,
                            )
                        except Exception:
                            pass
                    continue

            result = wallet.execute_trade(d)
            if result:
                print(f"[mirofish] Executed: {d.direction} ${d.amount_usd:.0f} "
                      f"on '{d.question[:50]}' [{d.strategy}]")
                _notify_dashboard()
                if d.strategy == "price_lag_arb" and d.metadata:
                    _log_price_lag_trade(d)
                elif d.strategy == "cross_venue_arb" and d.metadata:
                    _log_cross_venue_arb_trade(d)
                # Record in strategy tracker
                if tracker:
                    try:
                        tracker.record_trade_open(
                            trade_id=result["id"],
                            strategy=d.strategy,
                            market_id=d.market_id,
                            direction=d.direction,
                            entry_price=d.entry_price,
                            expected_edge=d.confidence,
                            amount_usd=result["amount_usd"],
                            confidence=d.confidence,
                            metadata=d.metadata,
                        )
                    except Exception as e:
                        print(f"[mirofish] Strategy track error: {e}")
            else:
                print(f"[mirofish] Rejected: {d.market_id} (cap or kelly)")
                if missed_opps:
                    try:
                        missed_opps.record_missed(
                            d.market_id, d.direction, d.strategy,
                            d.entry_price, d.confidence, d.amount_usd,
                            "wallet_rejected", d.metadata,
                        )
                    except Exception:
                        pass

    # 6. Check stops (always runs, even if API is down)
    try:
        current_prices = feed.get_latest_prices()
        closed = wallet.check_stops(current_prices)
        for c in closed:
            sign = "+" if (c["pnl"] or 0) >= 0 else ""
            print(f"[mirofish] Stop closed: {c['market_id']} → {c['status']} "
                  f"{sign}${c['pnl']:.2f}")
            _notify_dashboard()
            # Record closure in strategy tracker
            if tracker:
                try:
                    tracker.record_trade_close(
                        trade_id=c["id"],
                        exit_price=c["exit_price"],
                        realized_pnl=c["pnl"],
                        status=c["status"],
                    )
                except Exception:
                    pass
    except Exception as exc:
        print(f"[mirofish] Stop check failed: {exc}")

    # 7. Daily snapshot + strategy stats (first run of the day only)
    snapshotted = dash.maybe_snapshot(chat_id_for_notify=os.environ.get("JORDAN_TELEGRAM_CHAT_ID") or None)
    if snapshotted:
        print("[mirofish] Daily snapshot written and digest sent")
        if tracker:
            try:
                tracker.snapshot_stats()
                print("[mirofish] Strategy stats snapshot written")
            except Exception as e:
                print(f"[mirofish] Strategy snapshot error: {e}")

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
    parser.add_argument("--backtest", action="store_true", help="Run backtester")
    parser.add_argument("--from", dest="from_date", default=None, help="Backtest start date")
    parser.add_argument("--to", dest="to_date", default=None, help="Backtest end date")
    parser.add_argument("--strategies", default=None, help="Comma-separated strategies")
    parser.add_argument("--tournament", action="store_true", help="Run strategy tournament")
    args = parser.parse_args()

    if args.migrate:
        migrate()
        import scripts.mirofish.strategy_tracker as tracker
        tracker.migrate()
    elif args.run:
        run_loop()
    elif args.report:
        import scripts.mirofish.dashboard as dash
        path = dash.generate_report("daily")
        print(f"[mirofish] Report: {path}")
    elif args.backtest:
        import scripts.mirofish.backtester as bt
        from_date = args.from_date or (datetime.date.today() - datetime.timedelta(days=14)).isoformat()
        to_date = args.to_date or datetime.date.today().isoformat()
        strategies = args.strategies.split(",") if args.strategies else None
        result = bt.run_backtest(from_date, to_date, strategies)
        # Print text report
        print(f"\n{'='*60}")
        print(f"BACKTEST: {result.from_date} → {result.to_date}")
        print(f"{'='*60}")
        print(f"Starting: ${result.starting_balance:,.2f}")
        print(f"Ending:   ${result.ending_balance:,.2f}")
        print(f"Return:   {result.total_return_pct:+.2f}%")
        print(f"Trades:   {len(result.all_trades)}")
        for s in result.strategy_results:
            if s.total_trades > 0:
                print(f"\n  {s.strategy}: {s.total_trades} trades, "
                      f"W:{s.wins} L:{s.losses}, PnL: ${s.total_pnl:+.2f}")
        print(f"{'='*60}")
    elif args.tournament:
        import scripts.mirofish.strategy_tracker as tracker
        tracker.migrate()
        tracker.sync_from_paper_trades()
        reports = tracker.run_tournament()
        print("\nStrategy Tournament:")
        for r in sorted(reports, key=lambda x: x.allocation_pct, reverse=True):
            if r.total_trades > 0 or r.allocation_pct > 0:
                print(f"  {r.strategy:20s} → {r.allocation_pct:6.1%} "
                      f"(trades={r.total_trades})")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
