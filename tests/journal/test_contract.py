"""Tests for Contract.md parser."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from daytrader.journal.contract import (
    ContractParseError,
    parse_contract_md,
)


def test_parse_valid_contract(sample_contract_md: Path):
    c = parse_contract_md(sample_contract_md)
    assert c.version == 1
    assert c.active is True
    assert c.r_unit_usd == Decimal("50")
    assert c.daily_loss_limit_r == 3
    assert c.locked_setup_name == "opening_range_breakout"


def test_reject_placeholder_values(tmp_path: Path):
    p = tmp_path / "bad.md"
    p.write_text(
        """# Trading Contract

**Version:** 1
**Signed date:** YYYY-MM-DD
**Active:** false

## 1. Account & R Unit
- R unit (USD): $XX

## 2. Per-Trade Risk
- max_loss_per_trade_r: 1
"""
    )
    with pytest.raises(ContractParseError):
        parse_contract_md(p)


def test_reject_vague_word(tmp_path: Path):
    """Virtue words like 'careful trading' must be rejected."""
    p = tmp_path / "bad2.md"
    p.write_text(
        """# Trading Contract

**Version:** 1
**Signed date:** 2026-04-20
**Active:** true

## 1. Account & R Unit
- R unit (USD): $50

## Some Custom Section
- Approach: careful trading when volatile
"""
    )
    with pytest.raises(ContractParseError, match="vague"):
        parse_contract_md(p)
