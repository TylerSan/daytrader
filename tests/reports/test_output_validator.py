"""Tests for OutputValidator."""

from __future__ import annotations

import pytest

from daytrader.reports.core.output_validator import (
    OutputValidator,
    ValidationResult,
)


PREMARKET_SAMPLE_VALID = """
# 盘前日报 — 2026-04-25

## Lock-in status
trades_done: 0/30

## Multi-TF Analysis

### 📊 MES
#### W
data
#### D
data
#### 4H
data
#### 1H
data

### 📊 MNQ
#### W
data
#### D
data
#### 4H
data
#### 1H
data

### 📊 MGC
#### W
data
#### D
data
#### 4H
data
#### 1H
data

## Breaking news / 突发新闻
- item

## F. 期货结构

### F-MES
- Settlement: ok
- OI: ok
- Overall: bullish

### F-MGC
- Settlement: ok
- Overall: neutral

## D. 情绪面 / Sentiment Index
macro: neutral

## C. 计划复核
### C-MES
plan
### C-MGC
plan

## B. 市场叙事
narrative

## A. 建议
no action

## 数据快照
ok
"""

PREMARKET_SAMPLE_MISSING_A = PREMARKET_SAMPLE_VALID.replace("## A. 建议\nno action", "")


def test_validator_premarket_passes_when_all_sections_present():
    validator = OutputValidator()
    result = validator.validate(PREMARKET_SAMPLE_VALID, report_type="premarket")
    assert isinstance(result, ValidationResult)
    assert result.ok is True
    assert result.missing == []


def test_validator_premarket_fails_when_a_section_missing():
    validator = OutputValidator()
    result = validator.validate(PREMARKET_SAMPLE_MISSING_A, report_type="premarket")
    assert result.ok is False
    assert any("A" in s for s in result.missing)


def test_validator_unknown_report_type_raises():
    validator = OutputValidator()
    with pytest.raises(KeyError):
        validator.validate("any content", report_type="bogus-type")


PREMARKET_SAMPLE_LIVE_FORMAT = """
# 盘前每日报告 — 多标的

## Lock-in metadata
trades_done: 0/30

## Multi-TF Analysis

### 📊 MES
#### W — Bar end 13:00 PT
ohlcv data

#### D — Bar end 13:00 PT
ohlcv data

#### 4H — bar
ohlcv data

#### 1H — bar
ohlcv data

### 📊 MNQ
#### W
ohlcv
#### D
ohlcv
#### 4H
ohlcv
#### 1H
ohlcv

### 📊 MGC
#### W
ohlcv
#### D
ohlcv
#### 4H
ohlcv
#### 1H
ohlcv

## 市场新闻 / Breaking news
- item

## F. 期货结构 / Futures Positioning

### F-MES
data
### F-MGC
data

## D. 情绪面 / Sentiment Index
macro: neutral

## C. 计划复核 / Plan Formation
### C-MES
plan
### C-MGC
plan

## B. 市场叙事 / Market Narrative
narrative

## A. 建议 / Recommendation

A-3 默认: no action

## 数据快照 / Data snapshot
ok
"""


def test_validator_accepts_alternate_tf_labels_W_and_D():
    """Live AI output uses '### W' / '### D' (no '1' prefix); validator must accept."""
    validator = OutputValidator()
    result = validator.validate(PREMARKET_SAMPLE_LIVE_FORMAT, report_type="premarket")
    assert result.ok is True, f"unexpectedly missing: {result.missing}"


def test_validator_reports_human_readable_label_when_alternates_all_missing():
    """When a slot has alternates and none match, missing label shows the alternates."""
    no_weekly = PREMARKET_SAMPLE_LIVE_FORMAT.replace("#### W — Bar end 13:00 PT\nohlcv data", "")
    # Also strip any other 'W' / 'Weekly' markers so the slot truly has no match
    no_weekly = no_weekly.replace("#### W\n", "#### x\n").replace("Weekly", "x").replace("周线", "x").replace("1W", "x")
    validator = OutputValidator()
    result = validator.validate(no_weekly, report_type="premarket")
    assert result.ok is False
    # Missing entry should mention the alternative form
    missing_str = " ".join(result.missing)
    assert "W" in missing_str or "1W" in missing_str or "Weekly" in missing_str


def test_validator_premarket_fails_when_mes_section_missing():
    no_mes = PREMARKET_SAMPLE_VALID.replace("📊 MES", "x").replace("MES", "x")
    validator = OutputValidator()
    result = validator.validate(no_mes, report_type="premarket")
    assert result.ok is False
    missing_str = " ".join(result.missing)
    assert "MES" in missing_str


def test_validator_premarket_fails_when_c_mes_missing():
    no_c_mes = PREMARKET_SAMPLE_VALID.replace("### C-MES\nplan", "")
    validator = OutputValidator()
    result = validator.validate(no_c_mes, report_type="premarket")
    assert result.ok is False


def test_premarket_validator_requires_sentiment_section():
    """A premarket report without 'D. 情绪面' / 'Sentiment Index' should fail validation."""
    from daytrader.reports.core.output_validator import OutputValidator
    v = OutputValidator()
    # Build a minimal report missing the sentiment section
    content = """# 📋 Premarket Daily Report
## Lock-in Metadata
## 📊 MES
## 📊 MNQ
## 📊 MGC
### W
### D
### 4H
### 1H
News
F. 期货结构
### C-MES
### C-MGC
C.
B.
A.
数据快照
"""
    result = v.validate(content, "premarket")
    assert not result.ok
    assert any("情绪" in m or "Sentiment" in m for m in result.missing)


def test_premarket_validator_accepts_sentiment_alternatives():
    """Either '情绪面' or 'Sentiment Index' or 'D. 情绪面' should satisfy the slot."""
    from daytrader.reports.core.output_validator import OutputValidator
    v = OutputValidator()
    base = """# 📋 Premarket Daily Report
## Lock-in Metadata
## 📊 MES
## 📊 MNQ
## 📊 MGC
### W
### D
### 4H
### 1H
News
F. 期货结构
### C-MES
### C-MGC
C.
B.
A.
数据快照
"""
    for marker in ["## D. 情绪面", "Sentiment Index", "## 情绪面"]:
        full = base + f"\n{marker}\n"
        result = v.validate(full, "premarket")
        # All other required sections present, only sentiment varies → must pass on the sentiment slot
        # (it might still fail on other slots — we only assert no sentiment missing)
        assert all("情绪" not in m and "Sentiment" not in m for m in result.missing), \
            f"marker {marker!r} should satisfy sentiment slot but didn't: {result.missing}"


def test_eod_validator_requires_all_sections():
    """An EOD report missing 'Plan Retrospective' or '今日交易档案' should fail validation."""
    from daytrader.reports.core.output_validator import OutputValidator
    v = OutputValidator()
    content = """# EOD Daily Report
## Lock-in Metadata
## 📊 MES
## 📊 MNQ
## 📊 MGC
## F. 期货结构
## D. 情绪面
## C. 计划复核
## B. 市场叙事
## 数据快照
"""
    result = v.validate(content, "eod")
    assert not result.ok
    missing_concat = " ".join(result.missing).lower()
    assert "交易档案" in " ".join(result.missing) or "trade archive" in missing_concat
    assert "retrospective" in missing_concat or "复盘" in " ".join(result.missing)
    assert "tomorrow" in missing_concat or "明天" in " ".join(result.missing)


def test_eod_validator_accepts_complete_report():
    """A complete EOD with all required sections passes."""
    from daytrader.reports.core.output_validator import OutputValidator
    v = OutputValidator()
    content = """# EOD Daily Report
## Lock-in Metadata
## 📊 MES
## 📊 MNQ
## 📊 MGC
## 🌐 Cross-Asset Narrative
## 📰 Breaking News
## F. 期货结构
## D. 情绪面
## 今日交易档案
## 🔄 Plan Retrospective
## C. 计划复核
## B. 市场叙事
## 📅 Tomorrow Preliminary Plan
## 数据快照
"""
    result = v.validate(content, "eod")
    assert result.ok, f"missing: {result.missing}"


def test_eod_validator_fails_when_cross_asset_section_missing():
    """🌐 Cross-Asset Narrative is section #5 in eod.md template (line 11);
    validator must enforce it. Without this slot, AI silently dropping the
    section was undetectable.

    Regression: caught 2026-05-05 by code-reviewer agent (I7) before first
    14:00 PT EOD auto-fire.
    """
    from daytrader.reports.core.output_validator import OutputValidator
    v = OutputValidator()
    # Complete EOD MINUS the 🌐 Cross-Asset section
    content = """# EOD Daily Report
## Lock-in Metadata
## 📊 MES
## 📊 MNQ
## 📊 MGC
## 📰 Breaking News
## F. 期货结构
## D. 情绪面
## 今日交易档案
## 🔄 Plan Retrospective
## C. 计划复核
## B. 市场叙事
## 📅 Tomorrow Preliminary Plan
## 数据快照
"""
    result = v.validate(content, "eod")
    assert not result.ok
    missing_concat = " ".join(result.missing).lower()
    assert "cross-asset" in missing_concat or "cross_asset" in missing_concat or "🌐" in " ".join(result.missing) or "跨市场" in " ".join(result.missing)


def test_eod_validator_fails_when_breaking_news_section_missing():
    """📰 Breaking News is section #6 in eod.md template (line 12);
    validator must enforce it. (Same regression as above.)
    """
    from daytrader.reports.core.output_validator import OutputValidator
    v = OutputValidator()
    # Complete EOD MINUS the 📰 Breaking News section
    content = """# EOD Daily Report
## Lock-in Metadata
## 📊 MES
## 📊 MNQ
## 📊 MGC
## 🌐 Cross-Asset Narrative
## F. 期货结构
## D. 情绪面
## 今日交易档案
## 🔄 Plan Retrospective
## C. 计划复核
## B. 市场叙事
## 📅 Tomorrow Preliminary Plan
## 数据快照
"""
    result = v.validate(content, "eod")
    assert not result.ok
    missing_concat = " ".join(result.missing).lower()
    assert "breaking news" in missing_concat or "新闻" in " ".join(result.missing) or "📰" in " ".join(result.missing)


INTRADAY_4H_VALID_SAMPLE = """# Intraday 4H Report
## 🔒 Lock-in Metadata
status
## 📊 MES — Multi-TF
#### D
x
#### 4H
x
#### 1H
x
## 📊 MNQ — Multi-TF
## 📊 MGC — Multi-TF
## 🌐 Cross-Asset Narrative
narr
## 📰 Breaking News
news
## F. 期货结构
ok
## D. 情绪面 / Sentiment Index
ok
## 今日交易档案 / Today's Trade Archive
0 trades
## 🔄 Plan Retrospective / 计划复盘
n/a (4h-1)
## C. 计划复核
ok
## B. 市场叙事
narr
## A. 建议
A-3 default
## 📑 数据快照
ok
"""


def test_validator_intraday_4h_passes_when_all_sections_present():
    from daytrader.reports.core.output_validator import OutputValidator
    v = OutputValidator()
    result = v.validate(INTRADAY_4H_VALID_SAMPLE, report_type="intraday-4h")
    assert result.ok is True, f"missing: {result.missing}"


def test_validator_intraday_4h_fails_when_a_section_missing():
    """Intraday-4h KEEPS A section (unlike EOD which removes it)."""
    from daytrader.reports.core.output_validator import OutputValidator
    v = OutputValidator()
    no_a = INTRADAY_4H_VALID_SAMPLE.replace("## A. 建议\nA-3 default\n", "")
    result = v.validate(no_a, report_type="intraday-4h")
    assert result.ok is False
    missing_str = " ".join(result.missing)
    assert "A" in missing_str or "建议" in missing_str


def test_validator_intraday_4h_fails_when_plan_retrospective_missing():
    """Both 4h-1 and 4h-2 must show retrospective slot (4h-1 has placeholder)."""
    from daytrader.reports.core.output_validator import OutputValidator
    v = OutputValidator()
    no_retro = INTRADAY_4H_VALID_SAMPLE.replace(
        "## 🔄 Plan Retrospective / 计划复盘\nn/a (4h-1)\n", ""
    )
    result = v.validate(no_retro, report_type="intraday-4h")
    assert result.ok is False
    missing_str = " ".join(result.missing)
    assert "Retrospective" in missing_str or "复盘" in missing_str


NIGHT_ASIA_VALID_SAMPLE = """# Night Report
## 🔒 Lock-in Metadata
trades 0/30
## 📊 MES — Multi-TF
## 📊 MNQ — Multi-TF
## 📊 MGC — Multi-TF
## F. 期货结构
ok
## 📰 Breaking News
none
## D. Pattern Archive
patterns
## 📑 数据快照
ok
"""


def test_validator_night_passes_when_all_sections_present():
    from daytrader.reports.core.output_validator import OutputValidator
    v = OutputValidator()
    result = v.validate(NIGHT_ASIA_VALID_SAMPLE, report_type="night")
    assert result.ok is True, f"missing: {result.missing}"


def test_validator_asia_passes_with_same_required_sections_as_night():
    from daytrader.reports.core.output_validator import OutputValidator
    v = OutputValidator()
    result = v.validate(NIGHT_ASIA_VALID_SAMPLE, report_type="asia")
    assert result.ok is True, f"missing: {result.missing}"


def test_validator_night_fails_when_d_archive_section_missing():
    from daytrader.reports.core.output_validator import OutputValidator
    v = OutputValidator()
    no_d = NIGHT_ASIA_VALID_SAMPLE.replace(
        "## D. Pattern Archive\npatterns\n", ""
    )
    result = v.validate(no_d, report_type="night")
    assert result.ok is False
    missing_str = " ".join(result.missing)
    assert "Pattern Archive" in missing_str or "Archive" in missing_str or "D." in missing_str


def test_validator_night_does_not_require_a_or_b_or_c_sections():
    """night/asia explicitly lack A/B/C — must NOT enforce them."""
    from daytrader.reports.core.output_validator import OutputValidator
    v = OutputValidator()
    assert "## A." not in NIGHT_ASIA_VALID_SAMPLE
    assert "## B." not in NIGHT_ASIA_VALID_SAMPLE
    assert "## C." not in NIGHT_ASIA_VALID_SAMPLE
    result = v.validate(NIGHT_ASIA_VALID_SAMPLE, report_type="night")
    assert result.ok is True
