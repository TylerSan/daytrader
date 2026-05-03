"""Sentiment section: web-sourced news + social media bull/bear index.

Mirrors the FuturesSection pattern (Phase 4). Public surface populated
incrementally by Phase 4.5 plan tasks; this stub re-exports only the
dataclasses initially. Tasks 4-5 expand to include collector + section.
"""

from daytrader.reports.sentiment.dataclasses import (
    MacroSentiment,
    SentimentResult,
    SentimentScore,
    SymbolSentiment,
)

__all__ = [
    "MacroSentiment",
    "SentimentResult",
    "SentimentScore",
    "SymbolSentiment",
]
