"""Tests for instruments config loader."""

from __future__ import annotations

import pytest

from daytrader.reports.instruments.definitions import (
    InstrumentConfig,
    load_instruments,
)


def test_load_instruments_returns_three_known_symbols(fixture_instruments_yaml):
    cfg = load_instruments(str(fixture_instruments_yaml))
    assert set(cfg.keys()) == {"MES", "MNQ", "MGC"}


def test_load_instruments_parses_mes_correctly(fixture_instruments_yaml):
    cfg = load_instruments(str(fixture_instruments_yaml))
    mes = cfg["MES"]
    assert isinstance(mes, InstrumentConfig)
    assert mes.full_name == "Micro E-mini S&P 500"
    assert mes.underlying_index == "SPX"
    assert mes.cme_symbol == "MES"
    assert mes.typical_atr_pts == 14
    assert mes.cot_commodity == "S&P 500 STOCK INDEX"


def test_load_instruments_handles_null_underlying(fixture_instruments_yaml):
    cfg = load_instruments(str(fixture_instruments_yaml))
    mgc = cfg["MGC"]
    assert mgc.underlying_index is None


def test_load_instruments_missing_file_raises(tmp_path):
    missing = tmp_path / "nonexistent.yaml"
    with pytest.raises(FileNotFoundError):
        load_instruments(str(missing))


def test_load_instruments_tradable_flag(fixture_instruments_yaml):
    cfg = load_instruments(str(fixture_instruments_yaml))
    assert cfg["MES"].tradable is True
    assert cfg["MGC"].tradable is True
    assert cfg["MNQ"].tradable is False


def test_tradable_subset_helper(fixture_instruments_yaml):
    """tradable_symbols() returns only tradable=true symbols."""
    from daytrader.reports.instruments.definitions import tradable_symbols
    cfg = load_instruments(str(fixture_instruments_yaml))
    result = tradable_symbols(cfg)
    assert set(result) == {"MES", "MGC"}
    assert "MNQ" not in result
