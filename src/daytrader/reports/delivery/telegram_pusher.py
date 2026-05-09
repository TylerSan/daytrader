"""Telegram push integration.

Splits long markdown into ≤4000-char chunks (Telegram's 4096 limit minus
buffer), sends each as a MarkdownV2 message, then sends each chart as a
photo, then the PDF as a document.

Per spec §5.5.5 and user choice "multi-message + PDF 双发送":
text chunks first, charts in middle, PDF last.

Uses python-telegram-bot 21+ async Bot interface.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_MAX_MSG_CHARS = 4000  # Telegram limit is 4096; leave ~100 buffer
_MARKDOWN_V2_ESCAPE_RE = re.compile(r"([_*\[\]()~`>#+\-=|{}.!])")


@dataclass(frozen=True)
class PushResult:
    success: bool
    message_count: int
    error: str | None = None


def _escape_markdown_v2(text: str) -> str:
    """Escape MarkdownV2 reserved characters."""
    return _MARKDOWN_V2_ESCAPE_RE.sub(r"\\\1", text)


def _split_text(text: str, max_chars: int = _MAX_MSG_CHARS) -> list[str]:
    """Split text at section/paragraph boundaries to fit Telegram message size."""
    if len(text) <= max_chars:
        return [text]
    # Prefer splitting at H2 boundaries
    parts = re.split(r"(?=^## )", text, flags=re.MULTILINE)
    chunks: list[str] = []
    current = ""
    for part in parts:
        if len(current) + len(part) > max_chars:
            if current:
                chunks.append(current)
            current = part
            # Hard-split if a single section is too large
            while len(current) > max_chars:
                chunks.append(current[:max_chars])
                current = current[max_chars:]
        else:
            current += part
    if current:
        chunks.append(current)
    return chunks


class TelegramPusher:
    """Push markdown reports + charts + PDF to a Telegram chat."""

    def __init__(self, bot: Any, chat_id: str, max_retries: int = 3) -> None:
        self.bot = bot
        self.chat_id = chat_id
        self.max_retries = max_retries

    async def push(
        self,
        text_messages: list[str],
        chart_paths: list[Path],
        pdf_path: Path | None,
    ) -> PushResult:
        sent = 0
        try:
            for raw in text_messages:
                for chunk in _split_text(raw):
                    safe = _escape_markdown_v2(chunk)
                    await self._send_with_retry(
                        lambda c=safe: self.bot.send_message(
                            chat_id=self.chat_id,
                            text=c,
                            parse_mode="MarkdownV2",
                        )
                    )
                    sent += 1

            for chart in chart_paths:
                await self._send_with_retry(
                    lambda p=chart: self.bot.send_photo(
                        chat_id=self.chat_id,
                        photo=p.read_bytes(),
                    )
                )
                sent += 1

            if pdf_path is not None:
                await self._send_with_retry(
                    lambda p=pdf_path: self.bot.send_document(
                        chat_id=self.chat_id,
                        document=p.read_bytes(),
                        filename=p.name,
                    )
                )
                sent += 1

            return PushResult(success=True, message_count=sent)
        except Exception as exc:
            return PushResult(success=False, message_count=sent, error=str(exc))

    async def _send_with_retry(self, send_callable) -> None:
        last: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                await send_callable()
                return
            except Exception as e:
                last = e
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise
        if last is not None:
            raise last
