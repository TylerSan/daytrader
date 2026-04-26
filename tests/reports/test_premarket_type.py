"""Tests for premarket type handler."""

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


def _ctx(status=ContractStatus.NOT_CREATED) -> ReportContext:
    return ReportContext(
        contract_status=status,
        contract_text=None,
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


def test_premarket_generator_calls_ai_then_validates():
    fake_ib = MagicMock()
    fake_ib.get_bars.return_value = [_ohlcv(5240.0)]

    fake_ai = MagicMock()
    fake_ai_result = MagicMock()
    fake_ai_result.text = (
        "## Lock-in\nstatus\n\n## 1W\nx\n## 1D\nx\n## 4H\nx\n## 1H\nx\n\n"
        "## 突发新闻\nnone\n\n## C. 计划复核\nplan\n\n"
        "## B. 市场叙事\nnarr\n\n## A. 建议\nno action\n\n"
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
    )
    outcome = generator.generate(
        context=_ctx(),
        run_timestamp_pt="06:00 PT",
        run_timestamp_et="09:00 ET",
    )

    assert isinstance(outcome, GenerationOutcome)
    assert outcome.report_text.startswith("## Lock-in")
    assert outcome.validation.ok is True
    # IB.get_bars called for W, D, 4H, 1H
    assert fake_ib.get_bars.call_count == 4


def test_premarket_generator_marks_validation_failure():
    fake_ib = MagicMock()
    fake_ib.get_bars.return_value = [_ohlcv(5240.0)]

    fake_ai = MagicMock()
    fake_ai_result = MagicMock()
    fake_ai_result.text = "(short text missing all required sections)"
    fake_ai_result.input_tokens = 100
    fake_ai_result.output_tokens = 50
    fake_ai_result.cache_creation_tokens = 0
    fake_ai_result.cache_read_tokens = 0
    fake_ai_result.model = "claude-opus-4-7"
    fake_ai_result.stop_reason = "end_turn"
    fake_ai.call.return_value = fake_ai_result

    generator = PremarketGenerator(ib_client=fake_ib, ai_analyst=fake_ai)
    outcome = generator.generate(
        context=_ctx(),
        run_timestamp_pt="06:00 PT",
        run_timestamp_et="09:00 ET",
    )

    assert outcome.validation.ok is False
    assert len(outcome.validation.missing) > 0
