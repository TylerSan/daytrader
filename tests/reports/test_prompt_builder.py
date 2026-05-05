"""Tests for PromptBuilder (Phase 3 multi-instrument signature)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from daytrader.core.ib_client import OHLCV
from daytrader.reports.core.context_loader import ContractStatus, ReportContext
from daytrader.reports.core.prompt_builder import PromptBuilder


def _ohlcv(t: datetime, c: float) -> OHLCV:
    return OHLCV(timestamp=t, open=c - 1, high=c + 1, low=c - 2, close=c, volume=1000.0)


def _empty_bars_by_symbol() -> dict[str, dict[str, list[OHLCV]]]:
    return {
        s: {tf: [] for tf in ("1W", "1D", "4H", "1H")}
        for s in ("MES", "MNQ", "MGC")
    }


def test_prompt_builder_premarket_returns_messages_list():
    """build_premarket() returns a list of two messages: system + user."""
    ctx = ReportContext(
        contract_status=ContractStatus.NOT_CREATED,
        contract_text=None,
        lock_in_trades_done=0,
        lock_in_target=30,
        cumulative_r=None,
        last_trade_date=None,
        last_trade_r=None,
        streak=None,
    )
    bars = {
        "MES": {
            "1W": [_ohlcv(datetime(2026, 4, 18, tzinfo=timezone.utc), 5240.0)],
            "1D": [_ohlcv(datetime(2026, 4, 24, tzinfo=timezone.utc), 5246.0)],
            "4H": [_ohlcv(datetime(2026, 4, 25, 13, tzinfo=timezone.utc), 5246.5)],
            "1H": [_ohlcv(datetime(2026, 4, 25, 13, tzinfo=timezone.utc), 5246.5)],
        },
        "MNQ": {tf: [] for tf in ("1W", "1D", "4H", "1H")},
        "MGC": {tf: [] for tf in ("1W", "1D", "4H", "1H")},
    }

    builder = PromptBuilder()
    messages = builder.build_premarket(
        context=ctx,
        bars_by_symbol_and_tf=bars,
        tradable_symbols=["MES", "MGC"],
        news_items=[],
        run_timestamp_pt="06:00 PT",
        run_timestamp_et="09:00 ET",
    )

    assert messages[0]["role"] == "system"
    system_blocks = messages[0]["content"]
    assert isinstance(system_blocks, list)
    assert len(system_blocks) >= 2

    cached_blocks = [b for b in system_blocks if "cache_control" in b]
    assert len(cached_blocks) >= 1

    assert messages[1]["role"] == "user"


def test_prompt_builder_premarket_handles_missing_contract():
    """When Contract.md is NOT_CREATED, prompt notes degraded mode."""
    ctx = ReportContext(
        contract_status=ContractStatus.NOT_CREATED,
        contract_text=None,
        lock_in_trades_done=0,
        lock_in_target=30,
        cumulative_r=None,
        last_trade_date=None,
        last_trade_r=None,
        streak=None,
    )
    builder = PromptBuilder()
    msgs = builder.build_premarket(
        context=ctx,
        bars_by_symbol_and_tf=_empty_bars_by_symbol(),
        tradable_symbols=["MES", "MGC"],
        news_items=[],
        run_timestamp_pt="06:00 PT",
        run_timestamp_et="09:00 ET",
    )

    full_text = ""
    for msg in msgs:
        if isinstance(msg["content"], list):
            for block in msg["content"]:
                full_text += block.get("text", "")
        else:
            full_text += msg["content"]

    assert "not yet" in full_text.lower() or "not_created" in full_text.lower()


def test_prompt_builder_premarket_includes_lock_in_status():
    """Lock-in trades_done and target appear in the user prompt."""
    ctx = ReportContext(
        contract_status=ContractStatus.LOCK_IN_ACTIVE,
        contract_text="# Contract\n## Setup\nORB long\n",
        lock_in_trades_done=7,
        lock_in_target=30,
        cumulative_r=1.5,
        last_trade_date="2026-04-23",
        last_trade_r=-0.5,
        streak="2L1W",
    )
    builder = PromptBuilder()
    msgs = builder.build_premarket(
        context=ctx,
        bars_by_symbol_and_tf=_empty_bars_by_symbol(),
        tradable_symbols=["MES", "MGC"],
        news_items=[],
        run_timestamp_pt="06:00 PT",
        run_timestamp_et="09:00 ET",
    )
    user_content = msgs[1]["content"]
    assert "7" in user_content and "30" in user_content
    assert "2L1W" in user_content


def test_prompt_builder_premarket_multi_symbol_in_user_block():
    """User message contains explicit per-symbol bar blocks."""
    ctx = ReportContext(
        contract_status=ContractStatus.LOCK_IN_NOT_STARTED,
        contract_text="# Contract\nfilled\n",
        lock_in_trades_done=0,
        lock_in_target=30,
        cumulative_r=None,
        last_trade_date=None,
        last_trade_r=None,
        streak=None,
    )
    bars = {
        "MES": {
            "1W": [_ohlcv(datetime(2026, 4, 18, tzinfo=timezone.utc), 5240.0)],
            "1D": [_ohlcv(datetime(2026, 4, 24, tzinfo=timezone.utc), 5246.0)],
            "4H": [], "1H": [],
        },
        "MNQ": {
            "1W": [_ohlcv(datetime(2026, 4, 18, tzinfo=timezone.utc), 18420.0)],
            "1D": [_ohlcv(datetime(2026, 4, 24, tzinfo=timezone.utc), 18500.0)],
            "4H": [], "1H": [],
        },
        "MGC": {
            "1W": [_ohlcv(datetime(2026, 4, 18, tzinfo=timezone.utc), 2340.0)],
            "1D": [_ohlcv(datetime(2026, 4, 24, tzinfo=timezone.utc), 2342.0)],
            "4H": [], "1H": [],
        },
    }
    builder = PromptBuilder()
    msgs = builder.build_premarket(
        context=ctx,
        bars_by_symbol_and_tf=bars,
        tradable_symbols=["MES", "MGC"],
        news_items=[],
        run_timestamp_pt="06:00 PT",
        run_timestamp_et="09:00 ET",
    )
    user_text = msgs[1]["content"]
    assert "MES" in user_text
    assert "MNQ" in user_text
    assert "MGC" in user_text
    assert "5246" in user_text
    assert "18500" in user_text
    assert "2342" in user_text


def test_prompt_builder_user_block_lists_tradable_symbols():
    """User message explicitly states which symbols are tradable."""
    ctx = ReportContext(
        contract_status=ContractStatus.LOCK_IN_ACTIVE,
        contract_text="# Contract\nfilled\n",
        lock_in_trades_done=3,
        lock_in_target=30,
        cumulative_r=0.5,
        last_trade_date="2026-04-24",
        last_trade_r=1.0,
        streak="2W1L",
    )
    builder = PromptBuilder()
    msgs = builder.build_premarket(
        context=ctx,
        bars_by_symbol_and_tf=_empty_bars_by_symbol(),
        tradable_symbols=["MES", "MGC"],
        news_items=[],
        run_timestamp_pt="06:00 PT",
        run_timestamp_et="09:00 ET",
    )
    user_text = msgs[1]["content"]
    assert "tradable" in user_text.lower()
    assert "MES" in user_text and "MGC" in user_text


def test_prompt_builder_includes_f_section_when_futures_data_provided():
    from daytrader.reports.futures_data.futures_section import (
        FuturesSection, SymbolFuturesData,
    )
    from daytrader.reports.futures_data.basis import BasisResult
    from daytrader.reports.futures_data.term_structure import TermStructure
    from daytrader.reports.futures_data.volume_profile import VolumeProfile
    from daytrader.core.ib_client import OpenInterest

    ctx = ReportContext(
        contract_status=ContractStatus.LOCK_IN_NOT_STARTED,
        contract_text="# Contract\nfilled\n",
        lock_in_trades_done=0,
        lock_in_target=30,
        cumulative_r=None,
        last_trade_date=None,
        last_trade_r=None,
        streak=None,
    )
    fs = FuturesSection(per_symbol={
        "MES": SymbolFuturesData(
            symbol="MES",
            open_interest=OpenInterest(2143820, 2131390, 12430, 0.006),
            basis=BasisResult(5246.75, 5244.50, 2.25),
            term_structure=TermStructure(5246.75, 5252.00, 5258.50, 5.25, 6.50, True),
            volume_profile=VolumeProfile(5244.0, 5249.0, 5240.0, 1500000.0, 0.25),
        ),
    })
    builder = PromptBuilder()
    msgs = builder.build_premarket(
        context=ctx,
        bars_by_symbol_and_tf=_empty_bars_by_symbol(),
        tradable_symbols=["MES"],
        news_items=[],
        run_timestamp_pt="06:00 PT",
        run_timestamp_et="09:00 ET",
        futures_data=fs,
    )
    user_text = msgs[1]["content"]
    assert "F. 期货结构" in user_text
    assert "12430" in user_text
    assert "contango" in user_text
    assert "POC=5244" in user_text


def test_prompt_builder_omits_f_section_when_no_futures_data():
    ctx = ReportContext(
        contract_status=ContractStatus.NOT_CREATED,
        contract_text=None,
        lock_in_trades_done=0,
        lock_in_target=30,
        cumulative_r=None,
        last_trade_date=None,
        last_trade_r=None,
        streak=None,
    )
    builder = PromptBuilder()
    msgs = builder.build_premarket(
        context=ctx,
        bars_by_symbol_and_tf=_empty_bars_by_symbol(),
        tradable_symbols=["MES"],
        news_items=[],
        run_timestamp_pt="06:00 PT",
        run_timestamp_et="09:00 ET",
        futures_data=None,
    )
    user_text = msgs[1]["content"]
    assert "no F-section data available" in user_text


def _basic_ctx() -> ReportContext:
    """Minimal ReportContext for prompt-builder tests that don't care about
    contract/lock-in state."""
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


def test_build_premarket_includes_sentiment_block_when_provided():
    """PromptBuilder.build_premarket should embed sentiment_md verbatim
    when supplied."""
    pb = PromptBuilder()
    sentiment_md = (
        "## D. 情绪面 / Sentiment Index\n\n"
        "### 🌐 Macro Sentiment\n"
        "**总体综合 +3 / 10**（news +4, social +2）\n"
        "..."
    )
    msgs = pb.build_premarket(
        context=_basic_ctx(),
        bars_by_symbol_and_tf=_empty_bars_by_symbol(),
        tradable_symbols=["MES"],
        news_items=[],
        run_timestamp_pt="06:00 PT",
        run_timestamp_et="09:00 ET",
        futures_data=None,
        sentiment_md=sentiment_md,
    )
    user_text = msgs[1]["content"]
    assert "## D. 情绪面" in user_text or "Sentiment Index" in user_text


def test_build_premarket_without_sentiment_md_works():
    """sentiment_md is optional — omitting it must not crash, just no D. section."""
    pb = PromptBuilder()
    msgs = pb.build_premarket(
        context=_basic_ctx(),
        bars_by_symbol_and_tf=_empty_bars_by_symbol(),
        tradable_symbols=["MES"],
        news_items=[],
        run_timestamp_pt="06:00 PT",
        run_timestamp_et="09:00 ET",
        futures_data=None,
    )
    user_text = msgs[1]["content"]
    # Sentiment block absent
    assert "## D. 情绪面" not in user_text


def _joined_prompt_text(msgs: list[dict]) -> str:
    """Concatenate every text payload across all roles + content blocks."""
    text = ""
    for msg in msgs:
        content = msg["content"]
        if isinstance(content, list):
            for block in content:
                text += block.get("text", "")
        else:
            text += content
    return text


def test_build_eod_includes_all_input_blocks():
    """EOD prompt must embed every grounding input verbatim so AI can quote them."""
    pb = PromptBuilder()
    sentiment_md = (
        "## D. 情绪面 / Sentiment Index\n\n"
        "### 🌐 Macro Sentiment\n"
        "**总体综合 +3 / 10**（news +4, social +2）\n"
    )
    today_plan_blocks = {
        "MES": (
            "**Today's plan**:\n"
            "- Setup: stacked imbalance reversal\n"
            "- Direction: long\n"
            "- Entry: 7199.25\n"
            "- Stop: 7194.25 (-1R)\n"
            "- Target: 7209.25 (+2R)\n"
        ),
        "MGC": (
            "**Today's plan**:\n"
            "- Setup: discretionary read\n"
            "- Direction: wait\n"
        ),
    }
    retrospective_md = (
        "## 🔄 Plan Retrospective / 计划复盘\n\n"
        "### MES per-level table\n"
        "| Level | Plan | Hit? |\n| --- | --- | --- |\n"
        "| 7199.25 | long entry | yes |\n"
    )
    today_trades_md = (
        "## 今日交易档案 / Today's Trade Archive\n\n"
        "| # | Time | Symbol | Side | Entry | Exit | R |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n"
        "| 1 | 09:32 ET | MES | long | 7199.25 | 7209.25 | +2.0R |\n"
    )
    tomorrow_preliminary_md = (
        "## 📅 Tomorrow Preliminary Plan\n\n"
        "**preliminary — premarket 06:00 PT will finalize**\n\n"
        "- MES: watch 7280 reaction\n"
    )

    msgs = pb.build_eod(
        context=_basic_ctx(),
        bars_by_symbol_and_tf=_empty_bars_by_symbol(),
        tradable_symbols=["MES", "MGC"],
        news_items=[],
        run_timestamp_pt="13:30 PT",
        run_timestamp_et="16:30 ET",
        futures_data=None,
        sentiment_md=sentiment_md,
        today_plan_blocks=today_plan_blocks,
        retrospective_md=retrospective_md,
        today_trades_md=today_trades_md,
        tomorrow_preliminary_md=tomorrow_preliminary_md,
    )

    full_text = _joined_prompt_text(msgs)
    # Sentiment input
    assert "情绪面" in full_text
    # Verbatim plan block content (specific price)
    assert "7199.25" in full_text
    # Retrospective input
    assert "Plan Retrospective" in full_text or "计划复盘" in full_text
    # Trade archive input
    assert "今日交易档案" in full_text
    # Tomorrow preliminary input
    assert (
        "Tomorrow Preliminary" in full_text
        or "明天初步" in full_text
        or "7280" in full_text
    )

    # Structural sanity: messages list has system + user
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"


def test_build_eod_omits_A_section_marker():
    """EOD prompt template must instruct AI to skip the A. (建议 / Recommendation) section."""
    pb = PromptBuilder()
    msgs = pb.build_eod(
        context=_basic_ctx(),
        bars_by_symbol_and_tf=_empty_bars_by_symbol(),
        tradable_symbols=["MES"],
        news_items=[],
        run_timestamp_pt="13:30 PT",
        run_timestamp_et="16:30 ET",
    )
    full_text = _joined_prompt_text(msgs)
    # Template must signal A section is excluded — accept any of the explicit markers
    lowered = full_text.lower()
    assert (
        "no a." in lowered
        or "no a section" in lowered
        or "a section explicitly excluded" in lowered
        or "a 段" in full_text
        or "forbidden" in lowered
    ), "EOD prompt should explicitly mark the A section as excluded"
