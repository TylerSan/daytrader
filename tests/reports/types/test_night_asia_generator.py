"""Unit tests for NightAsiaGenerator (Phase 5.5 T8)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from daytrader.core.ib_client import OHLCV, OpenInterest
from daytrader.reports.core.context_loader import ContractStatus, ReportContext
from daytrader.reports.types.base import CadenceOutcome
from daytrader.reports.types.night_asia import (
    NightAsiaConfig,
    NightAsiaGenerator,
)


def _ctx() -> ReportContext:
    return ReportContext(
        contract_status=ContractStatus.LOCK_IN_NOT_STARTED,
        contract_text="# Contract\nfilled\n" + "## Detail\n" * 30,
        lock_in_trades_done=0, lock_in_target=30,
        cumulative_r=None, last_trade_date=None, last_trade_r=None, streak=None,
    )


def _ohlcv(c: float = 5240.0):
    return OHLCV(
        timestamp=datetime(2026, 5, 5, 19, tzinfo=timezone.utc),
        open=c, high=c + 1, low=c - 1, close=c, volume=1000,
    )


def _ai_result_text():
    text = (
        "# Night D-Archive\n"
        "## 🔒 Lock-in Metadata\nx\n"
        "## 📊 MES — Multi-TF\n#### 4H\nx\n#### 1H\nx\n"
        "## 📊 MNQ — Multi-TF\n#### 4H\nx\n#### 1H\nx\n"
        "## 📊 MGC — Multi-TF\n#### 4H\nx\n#### 1H\nx\n"
        "## F. 期货结构\nx\n## 📰 Breaking News\nx\n"
        "## D. Pattern Archive\npatterns\n## 📑 数据快照\nok\n"
    )
    result = MagicMock()
    result.text = text
    result.input_tokens = 100
    result.output_tokens = 200
    result.cache_creation_tokens = 0
    result.cache_read_tokens = 0
    result.model = "claude-opus-4-7"
    result.stop_reason = "end_turn"
    return result


def _config_night() -> NightAsiaConfig:
    return NightAsiaConfig(
        cadence_label="night",
        trigger_time_pt="19:00",
        news_time_window="past 4h",
    )


def _config_asia() -> NightAsiaConfig:
    return NightAsiaConfig(
        cadence_label="asia",
        trigger_time_pt="23:00",
        news_time_window="past 4h",
    )


def _make_generator(config):
    fake_ib = MagicMock()
    fake_ib.get_bars.return_value = [_ohlcv()]
    fake_ib.get_open_interest.return_value = OpenInterest(100, 90, 10, 0.11)
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result_text()
    return NightAsiaGenerator(
        config=config,
        ib_client=fake_ib,
        ai_analyst=fake_ai,
        symbols=["MES", "MNQ", "MGC"],
        tradable_symbols=["MES", "MGC"],
    )


def test_night_report_type_is_night():
    gen = _make_generator(_config_night())
    assert gen.report_type == "night"


def test_asia_report_type_is_asia():
    gen = _make_generator(_config_asia())
    assert gen.report_type == "asia"


def test_night_asia_tfs_are_4h_and_1h_only():
    """No D — overnight cadence, 2 TFs only."""
    gen_n = _make_generator(_config_night())
    gen_a = _make_generator(_config_asia())
    assert gen_n.tfs == ("4H", "1H")
    assert gen_a.tfs == ("4H", "1H")


def test_night_asia_bars_per_tf():
    gen = _make_generator(_config_night())
    assert gen.bars_per_tf == {"4H": 12, "1H": 24}


def test_night_default_no_sentiment():
    gen = _make_generator(_config_night())
    assert gen._maybe_fetch_sentiment() == ""


def test_night_default_no_plan_read():
    gen = _make_generator(_config_night())
    assert gen._maybe_read_plan("2026-05-05") == {}


def test_night_default_no_trades():
    gen = _make_generator(_config_night())
    assert gen._maybe_fetch_trades("2026-05-05") == []


def test_night_default_no_retrospective():
    gen = _make_generator(_config_night())
    assert gen._maybe_compose_retrospective({}, [], "2026-05-05") == ""


def test_night_generate_returns_outcome():
    gen = _make_generator(_config_night())
    outcome = gen.generate(
        context=_ctx(), date_et="2026-05-05",
        run_timestamp_pt="19:00 PT", run_timestamp_et="22:00 ET",
    )
    assert isinstance(outcome, CadenceOutcome)
    assert outcome.report_text


def test_asia_generate_only_fetches_4h_and_1h_bars():
    """3 symbols × 2 TFs = 6 multi-TF bar fetches (plus VP fetches)."""
    config = _config_asia()
    fake_ib = MagicMock()
    fake_ib.get_bars.return_value = [_ohlcv()]
    fake_ib.get_open_interest.return_value = OpenInterest(100, 90, 10, 0.11)
    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result_text()

    gen = NightAsiaGenerator(
        config=config, ib_client=fake_ib, ai_analyst=fake_ai,
        symbols=["MES", "MNQ", "MGC"], tradable_symbols=["MES", "MGC"],
    )
    gen.generate(
        context=_ctx(), date_et="2026-05-05",
        run_timestamp_pt="23:00 PT", run_timestamp_et="02:00 ET",
    )
    timeframes_called = [
        call.kwargs.get("timeframe")
        for call in fake_ib.get_bars.call_args_list
        if "timeframe" in call.kwargs
    ]
    assert "1D" not in timeframes_called
    assert "1W" not in timeframes_called
    assert "4H" in timeframes_called or "1H" in timeframes_called
