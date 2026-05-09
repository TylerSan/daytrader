"""Unit tests for UnderlyingPriceFetcher."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from daytrader.reports.futures_data.underlying_prices import (
    SYMBOL_TO_UNDERLYING,
    UnderlyingPriceFetcher,
)


def test_fetcher_happy_path_indexes():
    """Index-based symbols (MES/MNQ) use multiplier 1.0 — close = spot."""
    fake_ib = MagicMock()
    # SPX close = 7230.12, NDX close = 27710.36
    fake_ib.get_daily_close.side_effect = lambda c: {
        "SPX": 7230.12,
        "NDX": 27710.36,
    }[c.symbol]

    fetcher = UnderlyingPriceFetcher(fake_ib)
    out = fetcher(["MES", "MNQ"])

    assert out["MES"] == pytest.approx(7230.12)
    assert out["MNQ"] == pytest.approx(27710.36)


def test_fetcher_happy_path_gold_applies_multiplier():
    """MGC uses GLD × 10.95 (approximate gold spot)."""
    fake_ib = MagicMock()
    fake_ib.get_daily_close.return_value = 423.50  # GLD close

    fetcher = UnderlyingPriceFetcher(fake_ib)
    out = fetcher(["MGC"])

    expected = 423.50 * 10.95
    assert out["MGC"] == pytest.approx(expected)


def test_fetcher_unknown_symbol_skipped():
    """Symbols not in SYMBOL_TO_UNDERLYING are silently skipped."""
    fake_ib = MagicMock()
    fetcher = UnderlyingPriceFetcher(fake_ib)
    out = fetcher(["BOGUS", "UNKNOWN"])
    assert out == {}
    fake_ib.get_daily_close.assert_not_called()


def test_fetcher_per_symbol_failure_does_not_abort_others(capsys):
    """If MGC fetch fails, MES + MNQ still succeed."""
    fake_ib = MagicMock()

    def _fake_close(contract):
        if contract.symbol == "GLD":
            raise RuntimeError("GLD subscription unavailable")
        if contract.symbol == "SPX":
            return 7230.0
        if contract.symbol == "NDX":
            return 27700.0
        raise AssertionError(f"unexpected contract {contract}")

    fake_ib.get_daily_close.side_effect = _fake_close

    fetcher = UnderlyingPriceFetcher(fake_ib)
    out = fetcher(["MES", "MNQ", "MGC"])

    assert "MES" in out
    assert "MNQ" in out
    assert "MGC" not in out  # graceful drop

    captured = capsys.readouterr()
    assert "GLD subscription unavailable" in captured.err
    assert "MGC" in captured.err


def test_fetcher_empty_symbols_returns_empty_dict():
    fake_ib = MagicMock()
    fetcher = UnderlyingPriceFetcher(fake_ib)
    assert fetcher([]) == {}
    fake_ib.get_daily_close.assert_not_called()


def test_fetcher_index_constructs_correct_ib_contract():
    """For MES, fetcher passes Index('SPX', 'CBOE') to get_daily_close."""
    fake_ib = MagicMock()
    fake_ib.get_daily_close.return_value = 7230.0

    fetcher = UnderlyingPriceFetcher(fake_ib)
    fetcher(["MES"])

    fake_ib.get_daily_close.assert_called_once()
    contract = fake_ib.get_daily_close.call_args.args[0]
    assert contract.symbol == "SPX"
    assert contract.exchange == "CBOE"


def test_fetcher_stock_constructs_correct_ib_contract():
    """For MGC, fetcher passes Stock('GLD', 'ARCA', 'USD') to get_daily_close."""
    fake_ib = MagicMock()
    fake_ib.get_daily_close.return_value = 423.5

    fetcher = UnderlyingPriceFetcher(fake_ib)
    fetcher(["MGC"])

    fake_ib.get_daily_close.assert_called_once()
    contract = fake_ib.get_daily_close.call_args.args[0]
    assert contract.symbol == "GLD"
    assert contract.exchange == "ARCA"
    assert contract.currency == "USD"


def test_symbol_mapping_covers_supported_symbols():
    """All currently-traded symbols (MES/MNQ/MGC) are in the mapping."""
    for sym in ["MES", "MNQ", "MGC"]:
        assert sym in SYMBOL_TO_UNDERLYING
