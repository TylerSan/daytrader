"""Shared fixtures for reports tests."""

from __future__ import annotations

from pathlib import Path
import tempfile

import pytest


@pytest.fixture
def tmp_state_db(tmp_path: Path) -> Path:
    """Provide an isolated SQLite DB path for state tests."""
    return tmp_path / "state.db"


@pytest.fixture
def fixture_instruments_yaml(tmp_path: Path) -> Path:
    """Minimal instruments.yaml fixture mirroring spec §4.6."""
    content = """
instruments:
  MES:
    full_name: "Micro E-mini S&P 500"
    underlying_index: SPX
    cme_symbol: MES
    typical_atr_pts: 14
    typical_stop_pts: 8
    typical_target_pts: 16
    cot_commodity: "S&P 500 STOCK INDEX"
    tradable: true
  MNQ:
    full_name: "Micro E-mini Nasdaq 100"
    underlying_index: NDX
    cme_symbol: MNQ
    typical_atr_pts: 60
    typical_stop_pts: 30
    typical_target_pts: 60
    cot_commodity: "NASDAQ MINI"
    tradable: false
  MGC:
    full_name: "Micro Gold"
    underlying_index: null
    cme_symbol: MGC
    typical_atr_pts: 8
    typical_stop_pts: 5
    typical_target_pts: 10
    cot_commodity: "GOLD"
    tradable: true
"""
    path = tmp_path / "instruments.yaml"
    path.write_text(content)
    return path
