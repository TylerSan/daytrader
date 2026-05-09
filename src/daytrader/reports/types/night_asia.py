"""NightAsiaGenerator — concrete BaseCadenceGenerator subclass.

Used by both night (19:00 PT) and asia (23:00 PT) cadences.
D-only learning archive — overrides nothing except _build_prompt.
All BaseCadenceGenerator hooks default to skip:
  - no sentiment refresh
  - no plan read
  - no trade fetch beyond lock-in counter (covered by lock_in_block)
  - no retrospective
  - no tomorrow preliminary

Per master spec §3.7: "night/asia D | Removes A, B, C; only multi-TF
+ news + D frontmatter".

Phase 5.5 T8 (2026-05-05).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from daytrader.core.ib_client import IBClient
from daytrader.reports.core.ai_analyst import AIAnalyst
from daytrader.reports.core.output_validator import OutputValidator
from daytrader.reports.core.prompt_builder import PromptBuilder
from daytrader.reports.types.base import BaseCadenceGenerator


@dataclass(frozen=True)
class NightAsiaConfig:
    """Differentiates night vs asia cadence. Same generator class, two configs."""
    cadence_label: str           # "night" | "asia"
    trigger_time_pt: str         # "19:00" | "23:00"
    news_time_window: str        # "past 4h" both


class NightAsiaGenerator(BaseCadenceGenerator):
    """Generates D-only learning archive reports (both night and asia)."""

    def __init__(
        self,
        config: NightAsiaConfig,
        ib_client: IBClient,
        ai_analyst: AIAnalyst,
        symbols: list[str],
        tradable_symbols: list[str],
        prompt_builder: PromptBuilder | None = None,
        validator: OutputValidator | None = None,
        underlying_price_fetcher=None,
        term_price_fetcher=None,
        tick_sizes: dict[str, float] | None = None,
        news_collector=None,
    ) -> None:
        super().__init__(
            ib_client=ib_client,
            ai_analyst=ai_analyst,
            symbols=symbols,
            tradable_symbols=tradable_symbols,
            prompt_builder=prompt_builder,
            validator=validator,
            underlying_price_fetcher=underlying_price_fetcher,
            term_price_fetcher=term_price_fetcher,
            tick_sizes=tick_sizes,
            news_collector=news_collector,
        )
        self._config = config

    @property
    def report_type(self) -> str:
        return self._config.cadence_label  # "night" | "asia"

    @property
    def tfs(self) -> tuple[str, ...]:
        return ("4H", "1H")  # No D — overnight cadence, 2 TFs only

    @property
    def bars_per_tf(self) -> dict[str, int]:
        return {"4H": 12, "1H": 24}

    # NO override of _maybe_* hooks — all defaults apply (return ""/[]/{}).

    def _build_prompt(self, **inputs) -> list[dict[str, Any]]:
        return self.prompt_builder.build_night_asia(
            cadence_label=self._config.cadence_label, **inputs
        )
