"""Unit tests for IntradayFourHGenerator (Phase 5.5 T7).

Tests the concrete BaseCadenceGenerator subclass used by both intraday-4h-1
(07:00 PT) and intraday-4h-2 (11:00 PT). The two cadences share the same
generator class but are differentiated via IntradayFourHConfig:

- 4h-1: do_retrospective=False, sentiment_refresh=False, news="past 1h"
- 4h-2: do_retrospective=True,  sentiment_refresh=True (past 5h),
        news="past 5h"

The 14 tests below verify the report_type/tfs/bars contracts, hook overrides
(plan_reader, trades_query, retrospective, sentiment_refresh) gated by config,
and basic generate() integration.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from daytrader.core.ib_client import OHLCV, OpenInterest
from daytrader.reports.core.context_loader import ContractStatus, ReportContext
from daytrader.reports.eod.plan_dataclasses import RetrospectiveRow
from daytrader.reports.types.base import CadenceOutcome
from daytrader.reports.types.intraday_4h import (
    IntradayFourHConfig,
    IntradayFourHGenerator,
)


# ---------- helpers ----------


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
        timestamp=datetime(2026, 5, 5, 14, tzinfo=timezone.utc),
        open=c, high=c + 1, low=c - 1, close=c, volume=1000,
    )


def _ai_result_text() -> MagicMock:
    """Mock AI result; subclass tests assert validator-pass text."""
    result = MagicMock()
    result.text = "## Required\nstub\n"
    result.input_tokens = 100
    result.output_tokens = 200
    result.cache_creation_tokens = 0
    result.cache_read_tokens = 0
    result.model = "claude-opus-4-7"
    result.stop_reason = "end_turn"
    return result


def _config_4h_1() -> IntradayFourHConfig:
    return IntradayFourHConfig(
        cadence_label="intraday-4h-1",
        do_retrospective=False,
        sentiment_refresh=False,
        sentiment_time_window="",
        news_time_window="past 1h",
        intraday_end_time_et="10:00",
    )


def _config_4h_2() -> IntradayFourHConfig:
    return IntradayFourHConfig(
        cadence_label="intraday-4h-2",
        do_retrospective=True,
        sentiment_refresh=True,
        sentiment_time_window="past 5h",
        news_time_window="past 5h",
        intraday_end_time_et="14:00",
    )


def _make_generator(
    config: IntradayFourHConfig,
    *,
    plan_reader=None,
    trades_query=None,
    retrospective=None,
):
    """Construct an IntradayFourHGenerator with mocked deps."""
    fake_ib = MagicMock()
    fake_ib.get_bars.return_value = [_ohlcv()]
    fake_ib.get_open_interest.return_value = OpenInterest(100, 90, 10, 0.11)

    fake_ai = MagicMock()
    fake_ai.call.return_value = _ai_result_text()

    fake_validator = MagicMock()
    fake_validator.validate.return_value = MagicMock(ok=True, missing=[])

    return IntradayFourHGenerator(
        config=config,
        ib_client=fake_ib,
        ai_analyst=fake_ai,
        symbols=["MES", "MNQ", "MGC"],
        tradable_symbols=["MES", "MGC"],
        validator=fake_validator,
        plan_reader=plan_reader,
        plan_parser=MagicMock(),
        trades_query=trades_query,
        retrospective=retrospective,
    )


# ---------- tests ----------


def test_intraday_4h_report_type_is_intraday_4h():
    """Both 4h-1 and 4h-2 share the same validator key 'intraday-4h'."""
    gen_1 = _make_generator(_config_4h_1())
    gen_2 = _make_generator(_config_4h_2())
    assert gen_1.report_type == "intraday-4h"
    assert gen_2.report_type == "intraday-4h"


def test_intraday_4h_tfs_are_d_4h_1h():
    """Per spec §6.1: D / 4H / 1H — no W (weekly view is for premarket/EOD)."""
    gen = _make_generator(_config_4h_1())
    assert gen.tfs == ("1D", "4H", "1H")


def test_intraday_4h_bars_per_tf():
    """Spec: 10 D bars + 12 4H bars + 24 1H bars."""
    gen = _make_generator(_config_4h_1())
    assert gen.bars_per_tf == {"1D": 10, "4H": 12, "1H": 24}


def test_4h_1_skips_retrospective():
    """4h-1: do_retrospective=False → _maybe_compose_retrospective returns ''."""
    gen = _make_generator(_config_4h_1(), retrospective=MagicMock())
    out = gen._maybe_compose_retrospective(
        plans={"MES": "block"},
        trades=[],
        date_et="2026-05-05",
    )
    assert out == ""


def test_4h_2_runs_retrospective_when_plan_present():
    """4h-2: plans present + retrospective dep → calls compose + persist."""
    fake_retro = MagicMock()
    row = RetrospectiveRow(
        symbol="MES",
        date_et="2026-05-05",
        total_levels=2,
        triggered_count=1,
        sim_total_r=0.5,
        actual_total_r=0.0,
        gap_r=0.5,
        per_level_outcomes=[],
        open_trades_count=0,
    )
    fake_retro.compose.return_value = {"MES": row}
    gen = _make_generator(_config_4h_2(), retrospective=fake_retro)
    out = gen._maybe_compose_retrospective(
        plans={"MES": "block"},
        trades=[],
        date_et="2026-05-05",
    )
    fake_retro.compose.assert_called_once()
    fake_retro.persist.assert_called_once_with({"MES": row})
    # Render returns non-empty markdown with retrospective heading.
    assert "🔄 Plan Retrospective" in out
    assert "MES" in out


def test_4h_2_skips_retrospective_when_no_plans():
    """Even with do_retrospective=True, empty plans → returns ''."""
    fake_retro = MagicMock()
    gen = _make_generator(_config_4h_2(), retrospective=fake_retro)
    out = gen._maybe_compose_retrospective(
        plans={},
        trades=[],
        date_et="2026-05-05",
    )
    assert out == ""
    fake_retro.compose.assert_not_called()
    fake_retro.persist.assert_not_called()


def test_4h_1_does_not_refresh_sentiment():
    """4h-1: sentiment_refresh=False → returns ''."""
    gen = _make_generator(_config_4h_1())
    assert gen._maybe_fetch_sentiment() == ""


def test_intraday_4h_2_refreshes_sentiment():
    """4h-2: sentiment_refresh=True → calls SentimentSection w/ time_window='past 5h'."""
    fake_section_instance = MagicMock()
    fake_result = MagicMock()
    fake_result.unavailable = False
    fake_section_instance.collect.return_value = fake_result
    fake_section_instance.render.return_value = (
        "## D. 情绪面 / Sentiment Index\n\nrefreshed sentiment\n"
    )

    with patch(
        "daytrader.reports.types.intraday_4h.SentimentSection",
        return_value=fake_section_instance,
    ) as mock_section_cls:
        gen = _make_generator(_config_4h_2())
        out = gen._maybe_fetch_sentiment()

    # Asserts SentimentSection constructed with the config's time_window.
    mock_section_cls.assert_called_once()
    call_kwargs = mock_section_cls.call_args.kwargs
    assert call_kwargs["time_window"] == "past 5h"
    assert call_kwargs["symbols"] == ["MES", "MNQ", "MGC"]
    assert "refreshed sentiment" in out


def test_maybe_read_plan_calls_plan_reader():
    """_maybe_read_plan delegates to plan_reader.read_today_plan(date_et)."""
    fake_reader = MagicMock()
    fake_reader.read_today_plan.return_value = {"MES": "raw block"}
    gen = _make_generator(_config_4h_1(), plan_reader=fake_reader)
    out = gen._maybe_read_plan("2026-05-05")
    fake_reader.read_today_plan.assert_called_once_with("2026-05-05")
    assert out == {"MES": "raw block"}


def test_maybe_fetch_trades_calls_trades_query():
    """_maybe_fetch_trades delegates to trades_query.trades_for_date(date_et)."""
    fake_query = MagicMock()
    fake_query.trades_for_date.return_value = [
        {"symbol": "MES", "side": "long", "r": 1.0}
    ]
    gen = _make_generator(_config_4h_1(), trades_query=fake_query)
    out = gen._maybe_fetch_trades("2026-05-05")
    fake_query.trades_for_date.assert_called_once_with("2026-05-05")
    assert out == [{"symbol": "MES", "side": "long", "r": 1.0}]


def test_intraday_4h_generate_returns_cadence_outcome():
    """generate() runs the pipeline and returns a CadenceOutcome instance."""
    fake_reader = MagicMock()
    fake_reader.read_today_plan.return_value = {}
    fake_query = MagicMock()
    fake_query.trades_for_date.return_value = []
    gen = _make_generator(
        _config_4h_1(),
        plan_reader=fake_reader,
        trades_query=fake_query,
    )
    outcome = gen.generate(
        context=_ctx(),
        date_et="2026-05-05",
        run_timestamp_pt="07:00 PT",
        run_timestamp_et="10:00 ET",
        news_items=[],
        sentiment_md="",
    )
    assert isinstance(outcome, CadenceOutcome)
    assert outcome.report_text == "## Required\nstub\n"


def test_intraday_4h_2_carries_intraday_end_time_14_00():
    """4h-2 config end_time = 14:00 (RTH close); 4h-1 = 10:00."""
    cfg_2 = _config_4h_2()
    cfg_1 = _config_4h_1()
    assert cfg_2.intraday_end_time_et == "14:00"
    assert cfg_1.intraday_end_time_et == "10:00"


def test_4h_1_news_window_is_past_1h():
    """4h-1 config news_time_window = 'past 1h'."""
    assert _config_4h_1().news_time_window == "past 1h"


def test_4h_2_news_window_is_past_5h():
    """4h-2 config news_time_window = 'past 5h'."""
    assert _config_4h_2().news_time_window == "past 5h"
