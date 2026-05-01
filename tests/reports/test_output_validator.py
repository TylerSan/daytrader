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
