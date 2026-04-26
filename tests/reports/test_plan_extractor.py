"""Tests for PlanExtractor."""

from __future__ import annotations

import pytest

from daytrader.reports.core.plan_extractor import (
    ExtractedPlan,
    PlanExtractor,
)


REPORT_WITH_PLAN = """
# 盘前日报

## C. 计划复核

**Today's plan**:
- Setup: ORB long
- Direction: long
- Entry: 5240.00
- Stop: 5232.00
- Target: 5256.00
- R unit: $25

**Invalidation conditions**:
1. Price breaks below 5232
2. SPY breaks below 580
3. VIX above 18
"""


REPORT_WITHOUT_PLAN = """
# 盘前日报

## C. 计划复核

(Contract.md not yet filled — no plan to recheck.)
"""


def test_extract_plan_returns_structured_data():
    extractor = PlanExtractor()
    plan = extractor.extract(REPORT_WITH_PLAN)
    assert isinstance(plan, ExtractedPlan)
    assert plan.setup_name == "ORB long"
    assert plan.direction == "long"
    assert plan.entry == pytest.approx(5240.00)
    assert plan.stop == pytest.approx(5232.00)
    assert plan.target == pytest.approx(5256.00)
    assert plan.r_unit_dollars == pytest.approx(25.0)
    assert len(plan.invalidations) == 3
    assert "5232" in plan.invalidations[0]


def test_extract_plan_returns_none_when_no_plan():
    extractor = PlanExtractor()
    plan = extractor.extract(REPORT_WITHOUT_PLAN)
    assert plan is None
