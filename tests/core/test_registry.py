import pytest

from daytrader.core.registry import PluginRegistry


class DummyCollector:
    name = "dummy"

    def collect(self) -> str:
        return "data"


class AnotherCollector:
    name = "another"

    def collect(self) -> str:
        return "more data"


def test_register_and_get():
    registry = PluginRegistry[DummyCollector]()
    plugin = DummyCollector()
    registry.register("dummy", plugin)
    assert registry.get("dummy") is plugin


def test_get_unknown_returns_none():
    registry = PluginRegistry()
    assert registry.get("nonexistent") is None


def test_list_registered():
    registry = PluginRegistry()
    registry.register("a", DummyCollector())
    registry.register("b", AnotherCollector())
    names = registry.list_names()
    assert sorted(names) == ["a", "b"]


def test_register_duplicate_raises():
    registry = PluginRegistry()
    registry.register("dup", DummyCollector())
    with pytest.raises(ValueError, match="already registered"):
        registry.register("dup", AnotherCollector())
