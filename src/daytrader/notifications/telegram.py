"""Telegram Bot notification channel."""

from __future__ import annotations

import httpx

from daytrader.notifications.base import Notifier, NotificationMessage


class TelegramNotifier(Notifier):
    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._base_url = f"https://api.telegram.org/bot{bot_token}"

    @property
    def name(self) -> str:
        return "telegram"

    async def send(self, message: NotificationMessage) -> bool:
        text = f"*{message.title}*\n\n{message.body}"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._base_url}/sendMessage",
                json={
                    "chat_id": self._chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                },
            )
        return resp.status_code == 200
