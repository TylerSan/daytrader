"""Tests for FuturesSection aggregator (per-symbol F-section data bundle)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from daytrader.core.ib_client import OHLCV, OpenInterest
from daytrader.reports.futures_data.futures_section import (
    FuturesSection,
    SymbolFuturesData,
    build_futures_section,
)


def _bar(c: float, v: float = 1000) -> OHLCV:
    return OHLCV(
        timestamp=datetime(2026, 4, 25, 14, tzinfo=timezone.utc),
        open=c, high=c + 1, low=c - 1, close=c, volume=v,
    )


def test_build_futures_section_assembles_per_symbol_data():
    fake_ib = MagicMock()
    fake_ib.is_healthy.return_value = True
    fake_ib.get_open_interest.return_value = OpenInterest(
        today=2143820.0, yesterday=2131390.0, delta=12430.0, delta_pct=0.006
    )
    fake_ib.get_bars.return_value = [
        _bar(5240.0, 1000), _bar(5244.0, 2000), _bar(5246.0, 1500),
    ]

    underlying_prices = {"MES": 5244.50, "MNQ": 18495.0, "MGC": 2342.5}
    term_prices = {
        "MES": (5246.75, 5252.00, 5258.50),
        "MNQ": (18500.0, 18560.0, 18620.0),
        "MGC": (2350.00, 2348.00, 2345.00),
    }

    section = build_futures_section(
        ib_client=fake_ib,
        symbols=["MES", "MNQ", "MGC"],
        underlying_prices=underlying_prices,
        term_prices=term_prices,
        tick_sizes={"MES": 0.25, "MNQ": 0.25, "MGC": 0.10},
    )

    assert isinstance(section, FuturesSection)
    assert set(section.per_symbol.keys()) == {"MES", "MNQ", "MGC"}
    mes = section.per_symbol["MES"]
    assert isinstance(mes, SymbolFuturesData)
    assert mes.open_interest.delta == pytest.approx(12430.0)
    assert mes.basis.basis == pytest.approx(5246.75 - 5244.50)
    assert mes.term_structure.contango is True
    assert mes.volume_profile.total_volume == pytest.approx(4500.0)


def test_build_futures_section_handles_oi_failure_gracefully():
    fake_ib = MagicMock()
    fake_ib.get_bars.return_value = [_bar(5240.0)]
    fake_ib.get_open_interest.side_effect = [
        RuntimeError("Insufficient OI bars"),
        OpenInterest(today=900000, yesterday=890000, delta=10000, delta_pct=0.011),
    ]

    section = build_futures_section(
        ib_client=fake_ib,
        symbols=["MES", "MGC"],
        underlying_prices={"MES": 5244.5, "MGC": 2342.5},
        term_prices={"MES": (5246.75, 5252, 5258), "MGC": (2350, 2348, 2345)},
        tick_sizes={"MES": 0.25, "MGC": 0.10},
    )

    assert section.per_symbol["MES"].open_interest is None
    assert section.per_symbol["MGC"].open_interest is not None
