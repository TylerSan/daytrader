"""Base classes for pre-market data collectors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from pydantic import BaseModel


class CollectorResult(BaseModel):
    collector_name: str
    timestamp: datetime
    data: dict
    success: bool
    error: str = ""


class Collector(ABC):
    """Interface for data collector plugins."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def collect(self) -> CollectorResult: ...


class MarketDataCollector:
    """Orchestrates multiple collectors and gathers all data."""

    def __init__(self) -> None:
        self._collectors: dict[str, Collector] = {}

    def register(self, collector: Collector) -> None:
        self._collectors[collector.name] = collector

    async def collect_all(self) -> dict[str, CollectorResult]:
        results: dict[str, CollectorResult] = {}
        for name, collector in self._collectors.items():
            try:
                results[name] = await collector.collect()
            except Exception as e:
                results[name] = CollectorResult(
                    collector_name=name,
                    timestamp=datetime.now(),
                    data={},
                    success=False,
                    error=str(e),
                )
        return results
