"""Tests for premarket type handler (multi-instrument)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from daytrader.core.ib_client import OHLCV
from daytrader.reports.core.context_loader import ContractStatus, ReportContext
from daytrader.reports.types.premarket import (
    PremarketGenerator,
    GenerationOutcome,
)


def _ctx(status=ContractStatus.LOCK_IN_NOT_STARTED) -> ReportContext:
    return ReportContext(
        contract_status=status,
        contract_text="# Contract\nfilled\n" + "## Detail\n" * 30,
        lock_in_trades_done=0,
        lock_in_target=30,
        cumulative_r=None,
        last_trade_date=None,
        last_trade_r=None,
        streak=None,
    )


def _ohlcv(c: float) -> OHLCV:
    return OHLCV(
        timestamp=datetime(2026, 4, 25, 13, tzinfo=timezone.utc),
        open=c, high=c + 1, low=c - 1, close=c, volume=1000,
    )


def test_premarket_generator_fetches_bars_for_each_symbol():
    """get_bars called 4 TFs × 3 symbols = 12 times."""
    fake_ib = MagicMock()
    fake_ib.get_bars.return_value = [_ohlcv(5240.0)]

    fake_ai = MagicMock()
    fake_ai_result = MagicMock()
    fake_ai_result.text = (
        "## Lock-in\nstatus\n\n"
        "## Multi-TF Analysis\n"
        "### 📊 MES\n#### W\nx\n#### D\nx\n#### 4H\nx\n#### 1H\nx\n"
        "### 📊 MNQ\n#### W\nx\n#### D\nx\n#### 4H\nx\n#### 1H\nx\n"
        "### 📊 MGC\n#### W\nx\n#### D\nx\n#### 4H\nx\n#### 1H\nx\n\n"
        "## 突发新闻\nnone\n\n"
        "## C. 计划复核\n### C-MES\nplan\n### C-MGC\nplan\n\n"
        "## B. 市场叙事\nnarr\n\n"
        "## A. 建议\nno action\n\n"
        "## 数据快照\nok\n"
    )
    fake_ai_result.input_tokens = 1000
    fake_ai_result.output_tokens = 500
    fake_ai_result.cache_creation_tokens = 0
    fake_ai_result.cache_read_tokens = 0
    fake_ai_result.model = "claude-opus-4-7"
    fake_ai_result.stop_reason = "end_turn"
    fake_ai.call.return_value = fake_ai_result

    generator = PremarketGenerator(
        ib_client=fake_ib,
        ai_analyst=fake_ai,
        symbols=["MES", "MNQ", "MGC"],
        tradable_symbols=["MES", "MGC"],
    )
    outcome = generator.generate(
        context=_ctx(),
        run_timestamp_pt="06:00 PT",
        run_timestamp_et="09:00 ET",
    )

    assert isinstance(outcome, GenerationOutcome)
    assert fake_ib.get_bars.call_count == 12
    assert fake_ai.call.call_count == 1
    assert outcome.validation.ok is True


def test_premarket_generator_marks_validation_failure_on_short_text():
    """If AI returns truncated text missing instrument blocks, validation fails."""
    fake_ib = MagicMock()
    fake_ib.get_bars.return_value = [_ohlcv(5240.0)]

    fake_ai = MagicMock()
    fake_ai_result = MagicMock()
    fake_ai_result.text = "(too short)"
    fake_ai_result.input_tokens = 100
    fake_ai_result.output_tokens = 50
    fake_ai_result.cache_creation_tokens = 0
    fake_ai_result.cache_read_tokens = 0
    fake_ai_result.model = "claude-opus-4-7"
    fake_ai_result.stop_reason = "end_turn"
    fake_ai.call.return_value = fake_ai_result

    generator = PremarketGenerator(
        ib_client=fake_ib,
        ai_analyst=fake_ai,
        symbols=["MES", "MNQ", "MGC"],
        tradable_symbols=["MES", "MGC"],
    )
    outcome = generator.generate(
        context=_ctx(),
        run_timestamp_pt="06:00 PT",
        run_timestamp_et="09:00 ET",
    )

    assert outcome.validation.ok is False
    assert len(outcome.validation.missing) > 0


def test_premarket_generator_rejects_tradable_not_in_symbols():
    """If a tradable_symbol is not in the full symbols list, raise ValueError."""
    fake_ib = MagicMock()
    fake_ai = MagicMock()
    with pytest.raises(ValueError, match="not in symbols list"):
        PremarketGenerator(
            ib_client=fake_ib,
            ai_analyst=fake_ai,
            symbols=["MES", "MNQ"],
            tradable_symbols=["MES", "MGC"],  # MGC missing from symbols
        )


def test_premarket_generator_rejects_empty_symbols():
    """Empty symbols list → ValueError."""
    fake_ib = MagicMock()
    fake_ai = MagicMock()
    with pytest.raises(ValueError, match="non-empty"):
        PremarketGenerator(
            ib_client=fake_ib,
            ai_analyst=fake_ai,
            symbols=[],
            tradable_symbols=[],
        )
