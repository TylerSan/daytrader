"""Tests for PlanExtractor (single-plan and per-instrument)."""

from __future__ import annotations

import pytest

from daytrader.reports.core.plan_extractor import (
    ExtractedPlan,
    PlanExtractor,
)


# ---------- Single-plan (Phase 2 backward compat) ----------

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


# ---------- Per-instrument (Phase 3 new) ----------

REPORT_WITH_BOTH_PLANS = """
# 盘前日报

## C. 计划复核

### C-MES

**Today's plan**:
- Setup: ORB long
- Direction: long
- Entry: 5240.00
- Stop: 5232.00
- Target: 5256.00
- R unit: $50

**Invalidation conditions**:
1. Price breaks below 5232
2. SPY breaks below 580
3. VIX above 18

### C-MGC

**Today's plan**:
- Setup: VWAP fade
- Direction: short
- Entry: 2350.00
- Stop: 2355.00
- Target: 2340.00
- R unit: $50

**Invalidation conditions**:
1. Price breaks above 2355
2. DXY drops below 103
3. Fed announces rate cut

## B. 市场叙事
narrative
"""


REPORT_WITHOUT_PLANS = """
# 盘前日报

## C. 计划复核

(Contract.md not yet filled — no plans formed.)
"""


def test_extract_plans_returns_dict_keyed_by_symbol():
    extractor = PlanExtractor()
    plans = extractor.extract_per_instrument(
        REPORT_WITH_BOTH_PLANS, instruments=["MES", "MGC"]
    )
    assert isinstance(plans, dict)
    assert set(plans.keys()) == {"MES", "MGC"}

    mes = plans["MES"]
    assert isinstance(mes, ExtractedPlan)
    assert mes.setup_name == "ORB long"
    assert mes.entry == pytest.approx(5240.00)

    mgc = plans["MGC"]
    assert mgc.setup_name == "VWAP fade"
    assert mgc.entry == pytest.approx(2350.00)
    assert mgc.direction == "short"


def test_extract_plans_returns_empty_dict_when_no_plans():
    extractor = PlanExtractor()
    plans = extractor.extract_per_instrument(
        REPORT_WITHOUT_PLANS, instruments=["MES", "MGC"]
    )
    assert plans == {}


def test_extract_plans_skips_missing_instruments():
    """If only MES has a plan, only MES is in the result."""
    only_mes = REPORT_WITH_BOTH_PLANS.split("### C-MGC")[0]
    extractor = PlanExtractor()
    plans = extractor.extract_per_instrument(only_mes, instruments=["MES", "MGC"])
    assert "MES" in plans
    assert "MGC" not in plans
