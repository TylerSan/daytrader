"""iMessage notification channel via macOS AppleScript."""

from __future__ import annotations

import asyncio
import subprocess

from daytrader.notifications.base import Notifier, NotificationMessage


class IMessageNotifier(Notifier):
    def __init__(self, recipient: str) -> None:
        self._recipient = recipient

    @property
    def name(self) -> str:
        return "imessage"

    async def send(self, message: NotificationMessage) -> bool:
        text = f"{message.title}: {message.body}"
        script = (
            f'tell application "Messages"\n'
            f'  set targetService to 1st account whose service type = iMessage\n'
            f'  set targetBuddy to participant "{self._recipient}" of targetService\n'
            f'  send "{text}" to targetBuddy\n'
            f'end tell'
        )
        try:
            proc = await asyncio.create_subprocess_exec(
                "osascript", "-e", script,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            await proc.wait()
            return proc.returncode == 0
        except OSError:
            return False
