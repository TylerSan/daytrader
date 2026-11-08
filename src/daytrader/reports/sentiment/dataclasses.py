"""Frozen dataclasses for sentiment section data."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class SentimentScore:
    """One symbol's or macro's sentiment breakdown.

    All scores are integers in [-5, +5]:
      -5 = extremely bearish, 0 = neutral, +5 = extremely bullish.
    """
    news: int           # -5..+5
    social: int         # -5..+5
    combined: int       # -5..+5 (AI-weighted, typically 60% news + 40% social)
    narrative: str      # 1-sentence summary


@dataclass(frozen=True)
class MacroSentiment:
    """Overall macro sentiment + key context for the report period."""
    score: SentimentScore
    main_themes: list[str] = field(default_factory=list)        # 主流叙事
    risks: list[str] = field(default_factory=list)              # 风险点
    upcoming_events: list[str] = field(default_factory=list)    # 关键事件 (24-48h)


@dataclass(frozen=True)
class SymbolSentiment:
    """Per-symbol sentiment."""
    symbol: str            # e.g. "MES", "MGC", "MNQ"
    score: SentimentScore


@dataclass(frozen=True)
class SentimentResult:
    """Top-level sentiment fetch result.

    `unavailable=True` signals graceful degradation — main pipeline must
    continue and the renderer writes an "unavailable" block.
    """
    timestamp: datetime                          # UTC
    unavailable: bool
    unavailable_reason: str
    macro: MacroSentiment | None
    per_symbol: list[SymbolSentiment]
    sources: list[str]                           # URLs cited by the AI

    @classmethod
    def unavailable_due_to(cls, reason: str) -> SentimentResult:
        """Factory for the failure case."""
        return cls(
            timestamp=datetime.now(timezone.utc),
            unavailable=True,
            unavailable_reason=reason,
            macro=None,
            per_symbol=[],
            sources=[],
        )
