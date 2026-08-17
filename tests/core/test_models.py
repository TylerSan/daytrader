from datetime import datetime, timezone
from decimal import Decimal

from daytrader.core.models import (
    Signal,
    SignalDirection,
    Trade,
    TradeSide,
    Level,
    LevelSource,
    MarketContext,
    MarketRegime,
)


def test_signal_creation():
    s = Signal(
        symbol="ES",
        direction=SignalDirection.BULLISH,
        strength=3,
        price=Decimal("5400.50"),
        timestamp=datetime(2026, 4, 9, 9, 35, tzinfo=timezone.utc),
        imbalance_layers=3,
        delta_ratio=Decimal("3.5"),
    )
    assert s.symbol == "ES"
    assert s.direction == SignalDirection.BULLISH
    assert s.strength == 3
    assert s.id is not None  # auto-generated UUID


def test_trade_pnl_in_r():
    t = Trade(
        symbol="ES",
        side=TradeSide.LONG,
        entry_price=Decimal("5400.00"),
        exit_price=Decimal("5406.00"),
        stop_price=Decimal("5398.00"),
        size=1,
        entry_time=datetime(2026, 4, 9, 9, 35, tzinfo=timezone.utc),
        exit_time=datetime(2026, 4, 9, 9, 42, tzinfo=timezone.utc),
    )
    assert t.risk == Decimal("2.00")  # entry - stop
    assert t.pnl == Decimal("6.00")  # exit - entry
    assert t.r_multiple == Decimal("3.00")  # pnl / risk


def test_level_creation():
    lvl = Level(
        symbol="SPY",
        price=Decimal("540.25"),
        source=LevelSource.PRIOR_DAY_HIGH,
        label="PDH",
    )
    assert lvl.source == LevelSource.PRIOR_DAY_HIGH


def test_market_context():
    ctx = MarketContext(
        timestamp=datetime(2026, 4, 9, 9, 30, tzinfo=timezone.utc),
        regime=MarketRegime.TRENDING,
        vix=Decimal("18.5"),
        es_change_pct=Decimal("0.35"),
    )
    assert ctx.regime == MarketRegime.TRENDING
