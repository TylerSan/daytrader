"""Unit tests for EODGenerator (Phase 5 T9)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from daytrader.core.ib_client import OHLCV, OpenInterest
from daytrader.reports.core.context_loader import ContractStatus, ReportContext
from daytrader.reports.eod.plan_dataclasses import RetrospectiveRow
from daytrader.reports.types.eod import EODGenerator, EODOutcome


def _ctx() -> ReportContext:
    return ReportContext(
        contract_status=ContractStatus.LOCK_IN_NOT_STARTED,
        contract_text="# Contract\nfilled\n" + "## Detail\n" * 30,
        lock_in_trades_done=0,
        lock_in_target=30,
        cumulative_r=None,
        last_trade_date=None,
        last_trade_r=None,
        streak=None,
    )


def _ohlcv(c: float = 5240.0) -> OHLCV:
    return OHLCV(
        timestamp=datetime(2026, 5, 4, 21, tzinfo=timezone.utc),
        open=c, high=c + 1, low=c - 1, close=c, volume=1000,
    )


def _ai_result_with_all_eod_sections() -> MagicMock:
    """Return a MagicMock AIResult whose text passes EOD OutputValidator."""
    text = (
        "# EOD Report\n"
        "## Lock-in Metadata\nx\n\n"
        "## 📊 MES — Multi-TF\n#### W\nx\n#### D\nx\n#### 4H\nx\n"
        "## 📊 MNQ — Multi-TF\n#### W\nx\n#### D\nx\n#### 4H\nx\n"
        "## 📊 MGC — Multi-TF\n#### W\nx\n#### D\nx\n#### 4H\nx\n\n"
        "## F. 期货结构\n### F-MES\nbullish\n\n"
        "## D. 情绪面 / Sentiment Index\nx\n\n"
        "## 今日交易档案 / Today's Trade Archive\n0 trades\n\n"
        "## 🔄 Plan Retrospective\n(no plan)\n\n"
        "## C. 计划复核\nx\n\n"
        "## B. 市场叙事\nx\n\n"
        "## 📅 Tomorrow Preliminary\nx\n\n"
        "## 数据快照\nok\n"
    )
    result = MagicMock()
    result.text = text
    result.input_tokens = 0
    result.output_tokens = 0
    result.cache_creation_tokens = 0
    result.cache_read_tokens = 0
    result.model = "claude-opus-4-7"
    result.stop_reason = "end_turn"
    return result


def test_eod_generator_calls_all_components():
    """EODGenerator.generate() should call: bars fetch -> trades query -> retrospective -> AI."""
    fake_ib = MagicMock()
    fake_ib.get_bars.return_value = [_ohlcv(5240.0)]
    fake_ib.get_open_interest.return_value = OpenInterest(100, 90, 10, 0.11)

    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result_with_all_eod_sections()

    fake_plan_reader = MagicMock()
    fake_plan_reader.read_today_plan.return_value = {"MES": "raw block"}

    fake_plan_parser = MagicMock()

    fake_trades_query = MagicMock()
    fake_trades_query.trades_for_date.return_value = []
    fake_trades_query.audit_summary.return_value = {
        "count": 0,
        "daily_r": 0.0,
        "violations_total": 0,
        "screenshots_complete": 0,
        "per_trade_violations": {},
    }

    fake_retrospective = MagicMock()
    fake_retrospective.compose.return_value = {}
    fake_retrospective.persist = MagicMock()

    fake_tomorrow = MagicMock()
    fake_tomorrow.build_input_data.return_value = "tomorrow data"

    gen = EODGenerator(
        ib_client=fake_ib,
        ai_analyst=fake_ai,
        symbols=["MES", "MNQ", "MGC"],
        tradable_symbols=["MES", "MGC"],
        plan_reader=fake_plan_reader,
        plan_parser=fake_plan_parser,
        trades_query=fake_trades_query,
        retrospective=fake_retrospective,
        tomorrow_planner=fake_tomorrow,
    )

    outcome = gen.generate(
        context=_ctx(),
        date_et="2026-05-04",
        run_timestamp_pt="14:00 PT",
        run_timestamp_et="17:00 ET",
        sentiment_md="",
    )

    assert isinstance(outcome, EODOutcome)
    # Each EOD-specific dep gets called exactly once with the expected key inputs.
    fake_plan_reader.read_today_plan.assert_called_once_with("2026-05-04")
    fake_trades_query.trades_for_date.assert_called_once_with("2026-05-04")
    fake_retrospective.compose.assert_called_once()
    fake_retrospective.persist.assert_called_once()
    fake_tomorrow.build_input_data.assert_called_once()
    fake_ai.call.assert_called_once()
    # 3 TFs (W/D/4H) x 3 symbols = 9 multi-TF bar fetches +
    # 1 volume-profile (1m) fetch per symbol = 3 -> total 12.
    assert fake_ib.get_bars.call_count == 12


def test_eod_generator_handles_missing_premarket_file_gracefully():
    """If premarket file missing, plan_reader returns {} and pipeline still completes."""
    fake_ib = MagicMock()
    fake_ib.get_bars.return_value = [_ohlcv(5240.0)]
    fake_ib.get_open_interest.return_value = OpenInterest(100, 90, 10, 0.11)

    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result_with_all_eod_sections()

    fake_plan_reader = MagicMock()
    fake_plan_reader.read_today_plan.return_value = {}  # premarket missing

    fake_retrospective = MagicMock()
    fake_retrospective.compose.return_value = {}
    fake_retrospective.persist = MagicMock()

    fake_trades_query = MagicMock()
    fake_trades_query.trades_for_date.return_value = []
    fake_trades_query.audit_summary.return_value = {
        "count": 0,
        "daily_r": 0.0,
        "violations_total": 0,
        "screenshots_complete": 0,
        "per_trade_violations": {},
    }

    fake_tomorrow = MagicMock()
    fake_tomorrow.build_input_data.return_value = "x"

    gen = EODGenerator(
        ib_client=fake_ib,
        ai_analyst=fake_ai,
        symbols=["MES"],
        tradable_symbols=["MES"],
        plan_reader=fake_plan_reader,
        plan_parser=MagicMock(),
        trades_query=fake_trades_query,
        retrospective=fake_retrospective,
        tomorrow_planner=fake_tomorrow,
    )

    outcome = gen.generate(
        context=_ctx(),
        date_et="2026-05-04",
        run_timestamp_pt="14:00 PT",
        run_timestamp_et="17:00 ET",
        sentiment_md="",
    )

    # Should not raise. Should produce some report text (even if degraded).
    assert outcome is not None
    assert outcome.report_text  # non-empty
    # Retrospective skipped when no plan blocks — compose/persist must NOT be called.
    fake_retrospective.compose.assert_not_called()
    fake_retrospective.persist.assert_not_called()
    # Tomorrow planner still receives bars + (empty) retrospective.
    fake_tomorrow.build_input_data.assert_called_once()
    # AI still called.
    fake_ai.call.assert_called_once()
