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
