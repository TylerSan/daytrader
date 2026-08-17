"""SQLite database layer with repository pattern."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from daytrader.core.models import (
    Confidence,
    Signal,
    SignalDirection,
    MarketRegime,
    Trade,
    TradeSide,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    strength INTEGER NOT NULL,
    price TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    imbalance_layers INTEGER NOT NULL,
    delta_ratio TEXT NOT NULL,
    context_regime TEXT,
    confidence TEXT NOT NULL DEFAULT 'medium',
    extra TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS trades (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    entry_price TEXT NOT NULL,
    exit_price TEXT NOT NULL,
    stop_price TEXT NOT NULL,
    size INTEGER NOT NULL,
    entry_time TEXT NOT NULL,
    exit_time TEXT NOT NULL,
    signal_id TEXT,
    source TEXT DEFAULT '',
    prop_firm TEXT,
    tags TEXT DEFAULT '[]',
    extra TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol);
CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_entry_time ON trades(entry_time);
"""


class Database:
    def __init__(self, path: str) -> None:
        self._path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def initialize(self) -> None:
        conn = self._get_conn()
        conn.executescript(_SCHEMA)
        conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # --- Signals ---

    def save_signal(self, signal: Signal) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO signals
               (id, symbol, direction, strength, price, timestamp,
                imbalance_layers, delta_ratio, context_regime, confidence)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                signal.id,
                signal.symbol,
                signal.direction.value,
                signal.strength,
                str(signal.price),
                signal.timestamp.isoformat(),
                signal.imbalance_layers,
                str(signal.delta_ratio),
                signal.context_regime.value if signal.context_regime else None,
                signal.confidence.value,
            ),
        )
        conn.commit()

    def get_signal(self, signal_id: str) -> Signal | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM signals WHERE id = ?", (signal_id,)
        ).fetchone()
        if not row:
            return None
        return self._row_to_signal(row)

    def list_signals(self, symbol: str | None = None) -> list[Signal]:
        conn = self._get_conn()
        if symbol:
            rows = conn.execute(
                "SELECT * FROM signals WHERE symbol = ? ORDER BY timestamp DESC",
                (symbol,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM signals ORDER BY timestamp DESC"
            ).fetchall()
        return [self._row_to_signal(r) for r in rows]

    @staticmethod
    def _row_to_signal(row: sqlite3.Row) -> Signal:
        return Signal(
            id=row["id"],
            symbol=row["symbol"],
            direction=SignalDirection(row["direction"]),
            strength=row["strength"],
            price=Decimal(row["price"]),
            timestamp=datetime.fromisoformat(row["timestamp"]),
            imbalance_layers=row["imbalance_layers"],
            delta_ratio=Decimal(row["delta_ratio"]),
            context_regime=MarketRegime(row["context_regime"]) if row["context_regime"] else None,
            confidence=Confidence(row["confidence"]),
        )

    # --- Trades ---

    def save_trade(self, trade: Trade) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO trades
               (id, symbol, side, entry_price, exit_price, stop_price, size,
                entry_time, exit_time, signal_id, source, prop_firm, tags)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                trade.id,
                trade.symbol,
                trade.side.value,
                str(trade.entry_price),
                str(trade.exit_price),
                str(trade.stop_price),
                trade.size,
                trade.entry_time.isoformat(),
                trade.exit_time.isoformat(),
                trade.signal_id,
                trade.source,
                trade.prop_firm,
                json.dumps(trade.tags),
            ),
        )
        conn.commit()

    def get_trade(self, trade_id: str) -> Trade | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM trades WHERE id = ?", (trade_id,)
        ).fetchone()
        if not row:
            return None
        return self._row_to_trade(row)

    def list_trades(self, date: date | None = None, symbol: str | None = None) -> list[Trade]:
        conn = self._get_conn()
        query = "SELECT * FROM trades WHERE 1=1"
        params: list[Any] = []
        if date:
            query += " AND entry_time LIKE ?"
            params.append(f"{date.isoformat()}%")
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        query += " ORDER BY entry_time DESC"
        rows = conn.execute(query, params).fetchall()
        return [self._row_to_trade(r) for r in rows]

    @staticmethod
    def _row_to_trade(row: sqlite3.Row) -> Trade:
        return Trade(
            id=row["id"],
            symbol=row["symbol"],
            side=TradeSide(row["side"]),
            entry_price=Decimal(row["entry_price"]),
            exit_price=Decimal(row["exit_price"]),
            stop_price=Decimal(row["stop_price"]),
            size=row["size"],
            entry_time=datetime.fromisoformat(row["entry_time"]),
            exit_time=datetime.fromisoformat(row["exit_time"]),
            signal_id=row["signal_id"],
            source=row["source"],
            prop_firm=row["prop_firm"],
            tags=json.loads(row["tags"]),
        )
