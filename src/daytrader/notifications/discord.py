"""Discord webhook notification channel."""

from __future__ import annotations

import httpx

from daytrader.notifications.base import Notifier, NotificationMessage


class DiscordNotifier(Notifier):
    def __init__(self, webhook_url: str) -> None:
        self._webhook_url = webhook_url

    @property
    def name(self) -> str:
        return "discord"

    async def send(self, message: NotificationMessage) -> bool:
        payload = {
            "embeds": [
                {
                    "title": message.title,
                    "description": message.body,
                    "color": 0x00FF00 if message.priority == "normal" else 0xFF0000,
                }
            ]
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(self._webhook_url, json=payload)
        return resp.status_code in (200, 204)
