from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from daytrader.notifications.base import Notifier, NotificationMessage, NotificationManager
from daytrader.notifications.telegram import TelegramNotifier
from daytrader.notifications.discord import DiscordNotifier
from daytrader.notifications.imessage import IMessageNotifier


class FakeNotifier(Notifier):
    def __init__(self):
        self.sent: list[NotificationMessage] = []

    @property
    def name(self) -> str:
        return "fake"

    async def send(self, message: NotificationMessage) -> bool:
        self.sent.append(message)
        return True


def test_notification_message():
    msg = NotificationMessage(title="Test", body="Hello world", channel="test")
    assert msg.title == "Test"
    assert msg.body == "Hello world"


@pytest.mark.asyncio
async def test_fake_notifier():
    notifier = FakeNotifier()
    msg = NotificationMessage(title="T", body="B", channel="fake")
    result = await notifier.send(msg)
    assert result is True
    assert len(notifier.sent) == 1


@pytest.mark.asyncio
async def test_notification_manager_dispatches():
    fake = FakeNotifier()
    manager = NotificationManager()
    manager.register(fake)

    msg = NotificationMessage(title="T", body="B", channel="fake")
    results = await manager.notify(msg)
    assert results == {"fake": True}
    assert len(fake.sent) == 1


@pytest.mark.asyncio
async def test_notification_manager_skip_disabled():
    fake = FakeNotifier()
    manager = NotificationManager()
    manager.register(fake)

    msg = NotificationMessage(title="T", body="B", channel="nonexistent")
    results = await manager.notify(msg)
    assert results == {}
