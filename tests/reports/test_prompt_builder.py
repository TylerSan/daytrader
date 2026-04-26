"""Tests for PromptBuilder."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from daytrader.core.ib_client import OHLCV
from daytrader.reports.core.context_loader import ContractStatus, ReportContext
from daytrader.reports.core.prompt_builder import PromptBuilder


def _ohlcv(t: datetime, c: float) -> OHLCV:
    return OHLCV(timestamp=t, open=c - 1, high=c + 1, low=c - 2, close=c, volume=1000.0)


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
    bars_by_tf = {
        "1W": [_ohlcv(datetime(2026, 4, 18, tzinfo=timezone.utc), 5240.0)],
        "1D": [_ohlcv(datetime(2026, 4, 24, tzinfo=timezone.utc), 5246.0)],
        "4H": [_ohlcv(datetime(2026, 4, 25, 13, tzinfo=timezone.utc), 5246.5)],
        "1H": [_ohlcv(datetime(2026, 4, 25, 13, tzinfo=timezone.utc), 5246.5)],
    }

    builder = PromptBuilder()
    messages = builder.build_premarket(
        context=ctx,
        bars_by_tf=bars_by_tf,
        news_items=[],
        run_timestamp_pt="06:00 PT",
        run_timestamp_et="09:00 ET",
    )

    # First message is system with multiple cache-controlled blocks
    assert messages[0]["role"] == "system"
    system_blocks = messages[0]["content"]
    assert isinstance(system_blocks, list)
    assert len(system_blocks) >= 2  # at least template + dynamic

    # At least one block has cache_control
    cached_blocks = [b for b in system_blocks if "cache_control" in b]
    assert len(cached_blocks) >= 1

    # Second message is user
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
        bars_by_tf={"1W": [], "1D": [], "4H": [], "1H": []},
        news_items=[],
        run_timestamp_pt="06:00 PT",
        run_timestamp_et="09:00 ET",
    )

    # Concatenate all text content
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
        bars_by_tf={"1W": [], "1D": [], "4H": [], "1H": []},
        news_items=[],
        run_timestamp_pt="06:00 PT",
        run_timestamp_et="09:00 ET",
    )
    user_content = msgs[1]["content"]
    assert "7" in user_content and "30" in user_content
    assert "2L1W" in user_content
