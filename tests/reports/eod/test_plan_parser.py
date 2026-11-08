"""Unit tests for PremarketPlanParser."""

from __future__ import annotations

from daytrader.reports.eod.plan_parser import PremarketPlanParser


SAMPLE_C_MES = """**Today's plan (5/5 RTH)**:
- **Setup**: stacked_imbalance_reversal_at_level
- **Direction**: wait for setup
- **Entry**: 仅在以下其一区域出现 3+ stacked imbalance 时触发
  - **Long bias 区**: 7199.25（D low / 4H S）+ 7185–7195（5/1 W 低区, htf_demand_zone fresh check）
  - **Short bias 区**: 7271–7279.5（4H R + D high reject 区）
  - **Stretch short**: 7253（D 4/30 close 阻力）
- **Stop**: 入场 ± 1R = ± 8 pt
- **Target**: +2R

**Invalidation conditions** (任一触发即放弃今日 MES 计划):
1. MES 跌破 7185 RTH close → 转空头

**Today's posture**: neutral / wait for setup
"""


def test_parser_extracts_long_bias_levels():
    parser = PremarketPlanParser()
    plan = parser.parse(SAMPLE_C_MES, symbol="MES")
    long_levels = [lv for lv in plan.levels if lv.direction == "long_fade"]
    prices = [lv.price for lv in long_levels]
    # Should include 7199.25 (POINT) and 7185-7195 zone (could be midpoint or first)
    assert any(p == 7199.25 for p in prices), f"7199.25 missing in {prices}"
    # Zone 7185-7195 should be parsed
    zone_levels = [lv for lv in long_levels if lv.level_type == "ZONE"]
    assert len(zone_levels) >= 1
    assert zone_levels[0].zone_low == 7185.0
    assert zone_levels[0].zone_high == 7195.0


def test_parser_extracts_short_bias_levels():
    parser = PremarketPlanParser()
    plan = parser.parse(SAMPLE_C_MES, symbol="MES")
    short_levels = [lv for lv in plan.levels if lv.direction == "short_fade"]
    # Should include 7271-7279.5 zone + 7253 POINT (Stretch short)
    assert len(short_levels) >= 2
    zones = [lv for lv in short_levels if lv.level_type == "ZONE"]
    assert any(z.zone_low == 7271.0 and z.zone_high == 7279.5 for z in zones)
    points = [lv for lv in short_levels if lv.level_type == "POINT"]
    assert any(lv.price == 7253.0 for lv in points)


def test_parser_extracts_source_from_parens():
    parser = PremarketPlanParser()
    plan = parser.parse(SAMPLE_C_MES, symbol="MES")
    long_levels = [lv for lv in plan.levels if lv.direction == "long_fade" and lv.price == 7199.25]
    assert len(long_levels) >= 1
    assert "D low" in long_levels[0].source or "4H S" in long_levels[0].source


def test_parser_attaches_raw_block_for_verbatim_quote():
    parser = PremarketPlanParser()
    plan = parser.parse(SAMPLE_C_MES, symbol="MES")
    assert "Long bias 区" in plan.raw_block_md
    assert plan.symbol == "MES"


def test_parser_returns_default_stop_target_when_not_explicit():
    """Parser should default to setup yaml values (stop=2 ticks, target=2R)
    if the C block doesn't override them."""
    parser = PremarketPlanParser()
    plan = parser.parse(SAMPLE_C_MES, symbol="MES")
    assert plan.stop_offset_ticks == 2
    assert plan.target_r_multiple == 2.0


def test_parser_empty_block_returns_empty_levels():
    parser = PremarketPlanParser()
    plan = parser.parse("", symbol="MES")
    assert plan.symbol == "MES"
    assert plan.levels == []
    assert "empty" in plan.parse_warnings[0].lower() or "no" in plan.parse_warnings[0].lower()


def test_parser_unrecognized_format_emits_warning():
    """If the block is unparseable garbage, emit warning, don't crash."""
    parser = PremarketPlanParser()
    plan = parser.parse("hello world this is not a plan", symbol="MES")
    assert plan.symbol == "MES"
    assert plan.levels == []
    assert len(plan.parse_warnings) >= 1


def test_parser_handles_full_width_punctuation():
    """Real AI output uses full-width 全角 parens. Parser should tolerate."""
    block = """- **Long bias 区**: 7199.25（D low）"""
    parser = PremarketPlanParser()
    plan = parser.parse(block, symbol="MES")
    assert len(plan.levels) >= 1
    assert plan.levels[0].price == 7199.25
    assert "D low" in plan.levels[0].source


def test_parser_stretch_label_treated_as_directional():
    """**Stretch short**: 7253 should be parsed as short_fade direction."""
    block = """- **Stretch short**: 7253（D 4/30 阻力）"""
    parser = PremarketPlanParser()
    plan = parser.parse(block, symbol="MES")
    short_levels = [lv for lv in plan.levels if lv.direction == "short_fade"]
    assert len(short_levels) == 1
    assert short_levels[0].price == 7253.0


def test_parser_zone_dash_variants():
    """Both ASCII '-' and Unicode '–' (em-dash) zone separators must work."""
    for sep in ["-", "–", "—"]:
        block = f"""- **Long bias 区**: 7185{sep}7195（W 低区）"""
        parser = PremarketPlanParser()
        plan = parser.parse(block, symbol="MES")
        zones = [lv for lv in plan.levels if lv.level_type == "ZONE"]
        assert len(zones) == 1, f"separator {sep!r} produced {len(zones)} zones"
        assert zones[0].zone_low == 7185.0
        assert zones[0].zone_high == 7195.0
