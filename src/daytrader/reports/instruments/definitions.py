"""Instrument configuration loader.

Reads `config/instruments.yaml` (or another path) into `InstrumentConfig`
pydantic models keyed by symbol (MES, MNQ, MGC).
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel


class InstrumentConfig(BaseModel):
    """Per-instrument futures parameters."""
    full_name: str
    underlying_index: str | None
    cme_symbol: str
    typical_atr_pts: float
    typical_stop_pts: float
    typical_target_pts: float
    cot_commodity: str
    tradable: bool = False


def tradable_symbols(instruments: dict[str, InstrumentConfig]) -> list[str]:
    """Return symbols where tradable=True. Order is stable (insertion order)."""
    return [sym for sym, cfg in instruments.items() if cfg.tradable]


def load_instruments(path: str) -> dict[str, InstrumentConfig]:
    """Load instruments.yaml into a dict of symbol -> InstrumentConfig.

    Raises FileNotFoundError if the file does not exist.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Instruments config not found: {path}")
    raw = yaml.safe_load(p.read_text())
    instruments_raw = raw.get("instruments", {})
    return {
        symbol: InstrumentConfig(**params)
        for symbol, params in instruments_raw.items()
    }
