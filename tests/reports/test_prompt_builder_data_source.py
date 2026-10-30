"""PromptBuilder / generators: data-source provenance note (yfinance fallback)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from daytrader.core.ib_client import OHLCV
from daytrader.reports.core.context_loader import ContractStatus, ReportContext
from daytrader.reports.core.data_source import DATA_SOURCE_NOTE_YF
from daytrader.reports.core.prompt_builder import PromptBuilder

HEADER = "## Multi-TF bar data (per instrument)"


def _ctx() -> ReportContext:
    return ReportContext(
        contract_status=ContractStatus.NOT_CREATED,
        contract_text=None,
        lock_in_trades_done=0,
        lock_in_target=30,
        cumulative_r=None,
        last_trade_date=None,
        last_trade_r=None,
        streak=None,
    )


def _bars(tfs=("4H", "1H")):
    bar = OHLCV(
        timestamp=datetime(2026, 10, 9, 13, tzinfo=timezone.utc),
        open=6850.0, high=6855.0, low=6845.0, close=6852.0, volume=1000.0,
    )
    return {s: {tf: [bar] for tf in tfs} for s in ("MES", "MNQ", "MGC")}


def _user_text(msgs) -> str:
    return msgs[1]["content"]


def _premarket(pb: PromptBuilder):
    return pb.build_premarket(
        context=_ctx(),
        bars_by_symbol_and_tf=_bars(("1W", "1D", "4H", "1H")),
        tradable_symbols=["MES", "MGC"],
        news_items=[],
        run_timestamp_pt="06:00 PT",
        run_timestamp_et="09:00 ET",
    )


def _night(pb: PromptBuilder):
    return pb.build_night_asia(
        cadence_label="asia",
        context=_ctx(),
        bars_by_symbol_and_tf=_bars(),
        tradable_symbols=["MES", "MGC"],
        news_items=[],
        run_timestamp_pt="23:00 PT",
        run_timestamp_et="02:00 ET",
    )


def test_default_builder_has_ib_source_and_no_note():
    pb = PromptBuilder()
    assert pb.data_source == "ib"
    for msgs in (_premarket(pb), _night(pb)):
        assert "数据源：yfinance" not in _user_text(msgs)


@pytest.mark.parametrize("build", [_premarket, _night])
def test_yfinance_builder_inserts_note_under_bars_header(build):
    text = _user_text(build(PromptBuilder(data_source="yfinance")))
    assert "数据源：yfinance" in text
    lines = text.splitlines()
    i = lines.index(HEADER)
    assert lines[i + 1] == (
        DATA_SOURCE_NOTE_YF + "——请在报告的数据快照/说明处原文注明这一行。"
    )


def test_eod_and_intraday_builders_also_carry_note():
    pb = PromptBuilder(data_source="yfinance")
    common = dict(
        context=_ctx(),
        bars_by_symbol_and_tf=_bars(),
        tradable_symbols=["MES", "MGC"],
        news_items=[],
        run_timestamp_pt="14:00 PT",
        run_timestamp_et="17:00 ET",
    )
    eod = pb.build_eod(**common)
    assert "数据源：yfinance" in _user_text(eod)
    intraday = pb.build_intraday_4h(cadence_label="intraday-4h-1", **common)
    assert "数据源：yfinance" in _user_text(intraday)


def test_staticmethod_keeps_legacy_positional_call():
    block = PromptBuilder._build_multi_symbol_bars_block(_bars())
    assert block.startswith(HEADER)
    assert "数据源" not in block
    block = PromptBuilder._build_multi_symbol_bars_block(_bars(), data_source="yfinance")
    assert DATA_SOURCE_NOTE_YF in block


# --- generators propagate data_source into their default PromptBuilder ---


def _gen_kwargs():
    return dict(
        ib_client=MagicMock(),
        ai_analyst=MagicMock(),
        symbols=["MES", "MNQ", "MGC"],
        tradable_symbols=["MES", "MGC"],
    )


def _all_generators(**extra):
    from daytrader.reports.types.eod import EODGenerator
    from daytrader.reports.types.intraday_4h import (
        IntradayFourHConfig,
        IntradayFourHGenerator,
    )
    from daytrader.reports.types.night_asia import NightAsiaConfig, NightAsiaGenerator
    from daytrader.reports.types.premarket import PremarketGenerator

    intraday_cfg = IntradayFourHConfig(
        cadence_label="intraday-4h-1",
        do_retrospective=False,
        sentiment_refresh=False,
        sentiment_time_window="",
        news_time_window="past 1h",
        intraday_end_time_et="10:00",
    )
    night_cfg = NightAsiaConfig(
        cadence_label="night", trigger_time_pt="19:00", news_time_window="past 4h"
    )
    return [
        PremarketGenerator(**_gen_kwargs(), **extra),
        EODGenerator(**_gen_kwargs(), **extra),
        IntradayFourHGenerator(config=intraday_cfg, **_gen_kwargs(), **extra),
        NightAsiaGenerator(config=night_cfg, **_gen_kwargs(), **extra),
    ]


def test_generators_default_to_ib():
    for gen in _all_generators():
        assert gen.prompt_builder.data_source == "ib", type(gen).__name__


def test_generators_pass_data_source_to_builder():
    for gen in _all_generators(data_source="yfinance"):
        assert gen.prompt_builder.data_source == "yfinance", type(gen).__name__


def test_explicit_prompt_builder_is_respected():
    pb = PromptBuilder()
    for gen in _all_generators(data_source="yfinance", prompt_builder=pb):
        assert gen.prompt_builder is pb
