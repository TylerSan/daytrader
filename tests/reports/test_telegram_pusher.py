"""Tests for TelegramPusher (mocked bot)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from daytrader.reports.delivery.telegram_pusher import (
    TelegramPusher,
    PushResult,
)


@pytest.fixture
def fake_bot():
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=100))
    bot.send_photo = AsyncMock(return_value=MagicMock(message_id=101))
    bot.send_document = AsyncMock(return_value=MagicMock(message_id=102))
    return bot


@pytest.mark.asyncio
async def test_push_messages_splits_long_text(fake_bot, tmp_path):
    long_text = "## Section\n" + ("a" * 4000) + "\n## Other\nbody"
    pusher = TelegramPusher(bot=fake_bot, chat_id="123")
    result = await pusher.push(
        text_messages=[long_text],
        chart_paths=[],
        pdf_path=None,
    )
    assert isinstance(result, PushResult)
    assert fake_bot.send_message.call_count >= 1
    assert result.success is True


@pytest.mark.asyncio
async def test_push_attaches_charts_and_pdf(fake_bot, tmp_path):
    chart = tmp_path / "chart.png"
    chart.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    pusher = TelegramPusher(bot=fake_bot, chat_id="123")
    await pusher.push(
        text_messages=["short"],
        chart_paths=[chart],
        pdf_path=pdf,
    )
    fake_bot.send_photo.assert_called_once()
    fake_bot.send_document.assert_called_once()


@pytest.mark.asyncio
async def test_push_handles_send_error_gracefully(fake_bot, tmp_path):
    fake_bot.send_message.side_effect = Exception("transient")
    pusher = TelegramPusher(bot=fake_bot, chat_id="123", max_retries=1)
    result = await pusher.push(
        text_messages=["x"],
        chart_paths=[],
        pdf_path=None,
    )
    assert result.success is False
    assert "transient" in (result.error or "").lower()
