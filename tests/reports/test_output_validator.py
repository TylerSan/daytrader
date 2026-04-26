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

### 1W
data here

### 1D
data here

### 4H
data here

### 1H
data here

## Breaking news / 突发新闻
- item 1

## C. 计划复核
plan here

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
