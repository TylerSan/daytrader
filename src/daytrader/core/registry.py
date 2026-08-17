"""Generic plugin registry for extensible components."""

from __future__ import annotations

from typing import Generic, TypeVar

T = TypeVar("T")


class PluginRegistry(Generic[T]):
    """Type-safe registry for plugin components."""

    def __init__(self) -> None:
        self._plugins: dict[str, T] = {}

    def register(self, name: str, plugin: T) -> None:
        if name in self._plugins:
            raise ValueError(f"Plugin '{name}' already registered")
        self._plugins[name] = plugin

    def get(self, name: str) -> T | None:
        return self._plugins.get(name)

    def list_names(self) -> list[str]:
        return list(self._plugins.keys())
