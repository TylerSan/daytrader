"""Phase 5 EOD report: today's recap + plan retrospective + tomorrow preliminary.

Module structure:
- plan_dataclasses: PlanLevel / Plan / SimOutcome / RetrospectiveRow
- plan_reader:      Read Obsidian premarket .md → extract C blocks
- plan_parser:      Raw markdown → structured Plan (regex-tolerant)
- trades_query:     Journal DB → today's trades + §6 / §9 audit
- trade_simulator:  (level, intraday_bars) → SimOutcome
- retrospective:    Compose all above + persist daily row to state.db
- tomorrow_plan:    Build preliminary tomorrow plan input

Public surface (re-exports below) intentionally minimal — orchestrator
imports from submodules directly.
"""

from daytrader.reports.eod.plan_dataclasses import (
    Plan,
    PlanLevel,
    RetrospectiveRow,
    SimOutcome,
)

__all__ = [
    "Plan",
    "PlanLevel",
    "RetrospectiveRow",
    "SimOutcome",
]
