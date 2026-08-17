"""Notification system base classes and manager."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel


class NotificationMessage(BaseModel):
    title: str
    body: str
    channel: str  # target channel name, or "all"
    priority: str = "normal"  # "normal", "high"
    metadata: dict = {}


class Notifier(ABC):
    """Interface for notification channel plugins."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def send(self, message: NotificationMessage) -> bool: ...


class NotificationManager:
    """Dispatches notifications to registered channels."""

    def __init__(self) -> None:
        self._notifiers: dict[str, Notifier] = {}

    def register(self, notifier: Notifier) -> None:
        self._notifiers[notifier.name] = notifier

    async def notify(
        self, message: NotificationMessage
    ) -> dict[str, bool]:
        results: dict[str, bool] = {}
        if message.channel == "all":
            targets = self._notifiers.values()
        else:
            n = self._notifiers.get(message.channel)
            targets = [n] if n else []
        for notifier in targets:
            results[notifier.name] = await notifier.send(message)
        return results
