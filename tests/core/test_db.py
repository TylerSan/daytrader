# tests/core/test_db.py
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from daytrader.core.db import Database
from daytrader.core.models import (
    Signal,
    SignalDirection,
    Trade,
    TradeSide,
    Confidence,
)


@pytest.fixture
def db(tmp_dir: Path) -> Database:
    db_path = tmp_dir / "test.db"
    database = Database(str(db_path))
    database.initialize()
    return database


def _sample_signal() -> Signal:
    return Signal(
        symbol="ES",
        direction=SignalDirection.BULLISH,
        strength=3,
        price=Decimal("5400.50"),
        timestamp=datetime(2026, 4, 9, 9, 35, tzinfo=timezone.utc),
        imbalance_layers=3,
        delta_ratio=Decimal("3.5"),
    )


def _sample_trade() -> Trade:
    return Trade(
        symbol="ES",
        side=TradeSide.LONG,
        entry_price=Decimal("5400.00"),
        exit_price=Decimal("5406.00"),
        stop_price=Decimal("5398.00"),
        size=1,
        entry_time=datetime(2026, 4, 9, 9, 35, tzinfo=timezone.utc),
        exit_time=datetime(2026, 4, 9, 9, 42, tzinfo=timezone.utc),
    )


def test_save_and_get_signal(db: Database):
    signal = _sample_signal()
    db.save_signal(signal)
    loaded = db.get_signal(signal.id)
    assert loaded is not None
    assert loaded.symbol == "ES"
    assert loaded.price == Decimal("5400.50")


def test_list_signals_by_symbol(db: Database):
    s1 = _sample_signal()
    s2 = Signal(
        symbol="NQ",
        direction=SignalDirection.BEARISH,
        strength=2,
        price=Decimal("19200.00"),
        timestamp=datetime(2026, 4, 9, 10, 0, tzinfo=timezone.utc),
        imbalance_layers=2,
        delta_ratio=Decimal("2.8"),
    )
    db.save_signal(s1)
    db.save_signal(s2)
    es_signals = db.list_signals(symbol="ES")
    assert len(es_signals) == 1
    assert es_signals[0].symbol == "ES"


def test_save_and_get_trade(db: Database):
    trade = _sample_trade()
    db.save_trade(trade)
    loaded = db.get_trade(trade.id)
    assert loaded is not None
    assert loaded.symbol == "ES"
    assert loaded.pnl == Decimal("6.00")


def test_list_trades_by_date(db: Database):
    trade = _sample_trade()
    db.save_trade(trade)
    trades = db.list_trades(date=datetime(2026, 4, 9).date())
    assert len(trades) == 1


def test_empty_results(db: Database):
    assert db.get_signal("nonexistent") is None
    assert db.list_signals(symbol="AAPL") == []
    assert db.list_trades() == []
