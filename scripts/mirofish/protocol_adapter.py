"""Protocol adapter for Clawmpson. Single gateway for all sub-agent trade execution."""
from __future__ import annotations
import os
import sys
import hashlib
import uuid
import time
import logging
import sqlite3

# Ensure openclaw-protocol is importable
try:
    from openclaw_protocol import ProtocolEngine, ProtocolConfig
    from openclaw_protocol.store.sqlite import SqliteEventStore
    from openclaw_protocol.config.defaults import DEFAULT_PROTOCOL_CONFIG
    from openclaw_protocol.lock import FileExecutionLock
    from openclaw_protocol.helpers import build_synthetic_book, build_synthetic_market
    from openclaw_protocol.schemas.trade_intent import TradeIntent
    from openclaw_protocol.schemas.base import ExecutionStatus, ExitReason
    from openclaw_protocol.commands import CommandLog, ProtocolCommand
    from openclaw_protocol.observability import ObservabilityStore, CycleReport
    PROTOCOL_AVAILABLE = True
except ImportError:
    PROTOCOL_AVAILABLE = False

logger = logging.getLogger("clawmpson.protocol")

BOT_ID = "clawmpson"
INITIAL_BALANCE = 10000.0
USE_PROTOCOL = True  # Master toggle

_engine = None
_command_log = None
_initialized = False


def init_engine(db_dir=None):
    global _engine, _command_log, _initialized
    if _initialized:
        return
    if not PROTOCOL_AVAILABLE:
        logger.warning("openclaw_protocol not installed — using legacy path")
        return

    if db_dir is None:
        db_dir = os.path.expanduser("~/.openclaw")

    store = SqliteEventStore(os.path.join(db_dir, "protocol_events.db"))
    config = ProtocolConfig(
        venues=DEFAULT_PROTOCOL_CONFIG.venues,
        profile=DEFAULT_PROTOCOL_CONFIG.profile,
        initial_balance=INITIAL_BALANCE,
    )
    _engine = ProtocolEngine(config=config, store=store)
    _command_log = CommandLog(os.path.join(db_dir, "protocol_commands.db"))
    _engine.create_wallet(BOT_ID, INITIAL_BALANCE)
    _initialized = True
    logger.info(f"Clawmpson protocol engine initialized. Balance: {_engine.get_wallet(BOT_ID).cash_balance}")


def submit_trade(
    market_id: str,
    question: str,
    direction: str,
    shares: float,
    entry_price: float,
    amount_usd: float,
    confidence: float,
    reasoning: str,
    strategy: str,
    venue: str = "polymarket",
    cycle_id: str | None = None,
    db_conn: sqlite3.Connection | None = None,
) -> int | None:
    """Single gateway for all sub-agent trade execution.

    Returns trade_id (int) for backward compatibility with lastrowid,
    or None if rejected/failed.

    If db_conn is provided, also writes a shadow row to legacy paper_trades
    table for backward compatibility with readers (dashboard, inspector, etc.).
    """
    if not USE_PROTOCOL or not PROTOCOL_AVAILABLE or _engine is None:
        return None  # Caller should fall back to legacy INSERT

    now_ms = int(time.time() * 1000)
    if cycle_id is None:
        cycle_id = str(now_ms)

    side = "BUY" if direction.upper() in ("YES", "BUY") else "SELL"

    intent_id = hashlib.sha256(
        f"{BOT_ID}:{cycle_id}:{market_id}:{side}:{strategy}".encode()
    ).hexdigest()[:16]

    intent = TradeIntent(
        intent_id=intent_id,
        bot_id=BOT_ID,
        experiment_id="clawmpson_default",
        strategy_name=strategy,
        market_id=market_id,
        venue=venue,
        contract_id=market_id,
        side=side,
        target_price=entry_price,
        max_notional_usd=amount_usd,
        max_contracts=int(shares) if shares > 0 else None,
        thesis_score=confidence,
        confidence=confidence,
        rationale_hash=hashlib.sha256(reasoning.encode()).hexdigest()[:16] if reasoning else None,
        signal_time_ms=now_ms - 100,
        decision_time_ms=now_ms - 50,
        submit_time_ms=now_ms,
        protocol_version=_engine.config.protocol_version,
    )

    # Log command
    cmd = ProtocolCommand(
        command_id=str(uuid.uuid4()),
        bot_id=BOT_ID,
        cycle_id=cycle_id,
        command_type="entry_intent",
        source_agent=strategy,
        dedupe_key=intent_id,
        requested_at_ms=now_ms,
        status="accepted",
        market_id=market_id,
        contract_id=market_id,
        payload=intent.model_dump_json(),
    )
    _command_log.log_command(cmd)

    # Build synthetic book and market
    book = build_synthetic_book(contract_id=market_id, venue=venue, price=entry_price, fetched_at_ms=now_ms)
    market = build_synthetic_market(market_id=market_id, venue=venue, title=question, contract_id=market_id, fetched_at_ms=now_ms)

    try:
        result = _engine.execute_entry(intent, book, market)
    except Exception as e:
        _command_log.update_status(cmd.command_id, "failed", error_message=str(e))
        logger.error(f"Protocol execution failed for {strategy}/{market_id}: {e}")
        return None

    if result.execution_status == ExecutionStatus.REJECTED:
        _command_log.update_status(cmd.command_id, "rejected", error_code=result.rejection_reason)
        logger.info(f"Trade rejected ({strategy}): {result.rejection_reason}")
        return None

    _command_log.update_status(cmd.command_id, "executed")

    # Shadow write to legacy paper_trades for backward compatibility
    trade_id = None
    if db_conn is not None:
        try:
            actual_fee = result.fees_entry
            actual_amount = result.filled_size * result.entry_price
            cursor = db_conn.execute(
                """INSERT INTO paper_trades
                   (market_id, question, direction, shares, entry_price, amount_usd,
                    status, confidence, reasoning, strategy, opened_at, venue, entry_fee)
                   VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, datetime('now'), ?, ?)""",
                (market_id, question, direction, result.filled_size, result.entry_price,
                 actual_amount, confidence, reasoning, strategy, venue, actual_fee),
            )
            db_conn.commit()
            trade_id = cursor.lastrowid
        except Exception as e:
            logger.warning(f"Shadow write to legacy paper_trades failed: {e}")

    if trade_id is None:
        # Generate a pseudo trade_id for callers that need it
        trade_id = abs(hash(result.execution_id)) % (10**9)

    logger.info(f"Trade executed ({strategy}): {result.filled_size} @ {result.entry_price} "
                f"fees={result.fees_entry:.2f} slippage={result.slippage_bps}bps")

    return trade_id


def get_balance() -> float:
    if _engine is None:
        return 0.0
    return _engine.get_wallet(BOT_ID).cash_balance


def get_open_positions():
    if _engine is None:
        return []
    return _engine.get_positions(BOT_ID)


def check_stops(current_prices: dict) -> list:
    """Check stops for protocol-managed positions.
    current_prices: {market_id: float} (the current yes_price)
    """
    if _engine is None:
        return []

    STOP_LOSS_PCT = -0.20
    TAKE_PROFIT_PCT = 0.50
    closed = []

    for pos in _engine.get_positions(BOT_ID):
        price = current_prices.get(pos.contract_id)
        if price is None:
            continue

        if pos.side == "BUY":
            pnl_pct = (price - pos.entry_price_avg) / pos.entry_price_avg if pos.entry_price_avg > 0 else 0
        else:
            pnl_pct = (pos.entry_price_avg - price) / pos.entry_price_avg if pos.entry_price_avg > 0 else 0

        exit_reason = None
        if pnl_pct <= STOP_LOSS_PCT:
            exit_reason = ExitReason.STOP_LOSS
        elif pnl_pct >= TAKE_PROFIT_PCT:
            exit_reason = ExitReason.TAKE_PROFIT

        if exit_reason:
            now_ms = int(time.time() * 1000)
            try:
                exit_book = build_synthetic_book(contract_id=pos.contract_id, venue=pos.venue, price=price, fetched_at_ms=now_ms)
                close = _engine.execute_exit(BOT_ID, pos.contract_id, price, exit_reason, exit_book)
                closed.append({"contract_id": pos.contract_id, "pnl": close.pnl_net, "reason": exit_reason.value})
            except Exception as e:
                logger.error(f"Exit failed for {pos.contract_id}: {e}")

    return closed
