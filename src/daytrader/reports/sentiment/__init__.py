"""Sentiment section: web-sourced news + social media bull/bear index.

Mirrors the FuturesSection pattern (Phase 4). Public surface:

- `SentimentSection`: orchestrator-facing facade
- `SentimentResult`: structured result dataclass
- `SentimentCollector`: low-level claude -p wrapper (use SentimentSection in
  most cases)
"""

from daytrader.reports.sentiment.collector import SentimentCollector
from daytrader.reports.sentiment.dataclasses import (
    MacroSentiment,
    SentimentResult,
    SentimentScore,
    SymbolSentiment,
)
from daytrader.reports.sentiment.section import SentimentSection

__all__ = [
    "MacroSentiment",
    "SentimentCollector",
    "SentimentResult",
    "SentimentScore",
    "SentimentSection",
    "SymbolSentiment",
]
